"""Hugging Face dataset load, preprocess, cache, and index bootstrap (Phase P0)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from huggingface_hub import hf_hub_download
from huggingface_hub.utils import HfHubHTTPError

from src.config import Settings, get_settings
from src.data.index import RestaurantIndex, build_index, normalize_text, set_index
from src.data.models import CostBand, Restaurant

logger = logging.getLogger(__name__)

MIN_VALID_ROW_RATIO = 0.90
RATING_MAX = 5.0

# Canonical field -> known HF / alias column names (lowercase keys)
COLUMN_ALIASES: dict[str, list[str]] = {
    "name": ["name", "restaurant_name", "restaurant name"],
    "locality": ["location", "locality", "area"],
    "city": ["listed_in(city)", "listed_in_city", "city"],
    "address": ["address"],
    "cuisines": ["cuisines", "cuisine"],
    "rating": ["rate", "rating", "aggregate_rating"],
    "cost": [
        "approx_cost(for two people)",
        "approx_cost",
        "cost",
        "price",
        "average_cost_for_two",
        "cost for two",
    ],
}

HF_DATA_FILE = "zomato.csv"


@dataclass
class IngestionStats:
    raw_rows: int = 0
    retained_rows: int = 0
    dropped_rows: int = 0
    dropped_missing_name: int = 0
    dropped_missing_location: int = 0
    dropped_missing_rating: int = 0
    dropped_missing_cost: int = 0
    dropped_invalid_rating: int = 0
    dropped_invalid_cost: int = 0
    deduplicated_rows: int = 0
    cost_outliers_capped: int = 0
    schema_unmapped: list[str] = field(default_factory=list)
    cost_percentiles: dict[str, float] = field(default_factory=dict)
    cost_band_distribution: dict[str, int] = field(default_factory=dict)
    dataset_revision: str | None = None
    loaded_from_cache: bool = False

    @property
    def valid_field_ratio(self) -> float:
        if self.raw_rows == 0:
            return 0.0
        return self.retained_rows / self.raw_rows


def _meta_path(cache_path: Path) -> Path:
    return cache_path.with_name(f"{cache_path.stem}.meta.json")


def _resolve_columns(df: pd.DataFrame) -> dict[str, str]:
    """Map canonical fields to actual dataframe columns."""
    lower_map = {str(c).strip().lower(): str(c) for c in df.columns}
    resolved: dict[str, str] = {}
    unmapped_source = set(df.columns)

    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            key = alias.strip().lower()
            if key in lower_map:
                resolved[canonical] = lower_map[key]
                unmapped_source.discard(lower_map[key])
                break

    missing_required = [f for f in ("name", "cuisines", "rating", "cost") if f not in resolved]
    if missing_required:
        raise ValueError(
            f"Required columns missing after mapping: {missing_required}. "
            f"Available columns: {list(df.columns)}"
        )

    if "locality" not in resolved and "address" not in resolved and "city" not in resolved:
        raise ValueError(
            "No location columns found. Need at least one of: location, address, listed_in(city)."
        )

    return resolved


def _log_schema_diff(df: pd.DataFrame, resolved: dict[str, str]) -> list[str]:
    """Log and return source columns that were not mapped to canonical fields."""
    mapped_sources = set(resolved.values())
    extras = [str(c) for c in df.columns if str(c) not in mapped_sources]
    if extras:
        logger.info("Unmapped optional columns (kept in metadata where possible): %s", extras[:20])
    return extras


def _parse_rating(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().upper()
    if not text or text in {"NEW", "NAN", "NONE", "-", "N/A"}:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    rating = float(match.group(1))
    if "/" in text:
        # e.g. 4.1/5 — already numerator; if value > 5 might be wrong scale
        pass
    if rating < 0 or rating > 10:
        return None
    if rating > RATING_MAX:
        if rating <= 10:
            # scale 8.5/10 style rarely appears; treat as invalid if > 5
            return None
        return None
    return min(rating, RATING_MAX)


def _parse_cost(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)) and not pd.isna(value):
        cost = float(value)
        return cost if cost > 0 else None
    text = str(value).strip().lower()
    if not text or text in {"nan", "none", "-"}:
        return None
    numbers = re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))
    if not numbers:
        return None
    try:
        if len(numbers) >= 2 and ("-" in text or "to" in text):
            cost = (float(numbers[0]) + float(numbers[1])) / 2
        else:
            cost = float(numbers[0])
    except ValueError:
        return None
    return cost if cost > 0 else None


def _extract_city_from_address(address: str) -> str:
    if not address:
        return ""
    parts = [p.strip() for p in address.split(",") if p.strip()]
    return parts[-1] if parts else ""


def _build_location_fields(row: pd.Series, cols: dict[str, str]) -> tuple[str, str] | None:
    """Return (normalized_match_location, display_location) or None if unusable."""
    locality = _safe_str(row.get(cols["locality"])) if "locality" in cols else ""
    city = _safe_str(row.get(cols["city"])) if "city" in cols else ""
    address = _safe_str(row.get(cols["address"])) if "address" in cols else ""
    if not city and address:
        city = _extract_city_from_address(address)

    parts = []
    for p in (locality, city):
        if p and p not in parts:
            parts.append(p)
    if not parts and address:
        parts = [address]
    if not parts:
        return None

    display = ", ".join(dict.fromkeys(parts))  # preserve order, dedupe
    if "," in display:
        display = display.split(",")[0].strip()
    match_tokens = [normalize_text(p) for p in parts]
    if address:
        match_tokens.append(normalize_text(address))
    match_location = " ".join(dict.fromkeys(match_tokens))
    return match_location, display


def _safe_str(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _split_cuisines(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    text = str(value).strip()
    if not text:
        return []
    tokens = re.split(r"[,;]", text)
    return [t.strip() for t in tokens if t.strip()]


def _stable_id(name: str, location: str, row_index: int) -> str:
    payload = f"{name}|{location}|{row_index}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _assign_cost_bands(costs: list[float]) -> tuple[list[CostBand], dict[str, float]]:
    if not costs:
        return [], {}
    series = pd.Series(costs)
    p33 = float(series.quantile(0.33))
    p66 = float(series.quantile(0.66))
    percentiles = {"p33": p33, "p66": p66}

    bands: list[CostBand] = []
    for cost in costs:
        if cost <= p33:
            bands.append(CostBand.LOW)
        elif cost <= p66:
            bands.append(CostBand.MEDIUM)
        else:
            bands.append(CostBand.HIGH)
    return bands, percentiles


def _row_to_metadata(row: pd.Series, cols: dict[str, str], unmapped: list[str]) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for col in unmapped:
        val = row.get(col)
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            meta[str(col)] = val
    if "address" in cols:
        meta["address"] = row.get(cols["address"])
    if "city" in cols:
        meta["listed_in_city"] = row.get(cols["city"])
    tags: list[str] = []
    for tag_col in ("rest_type", "dish_liked", "online_order", "book_table"):
        if tag_col in row.index:
            val = row.get(tag_col)
            if val is not None and str(val).strip():
                tags.append(f"{tag_col}:{val}")
    if tags:
        meta["tags"] = tags
    return meta


def preprocess_dataframe(df: pd.DataFrame) -> tuple[list[Restaurant], IngestionStats]:
    """Normalize raw dataframe rows into Restaurant models."""
    stats = IngestionStats(raw_rows=len(df))
    cols = _resolve_columns(df)
    stats.schema_unmapped = _log_schema_diff(df, cols)

    name_col = cols["name"]
    rating_col = cols["rating"]
    cost_col = cols["cost"]
    cuisines_col = cols["cuisines"]

    candidates: list[dict[str, Any]] = []
    costs_for_bands: list[float] = []

    for idx, row in df.iterrows():
        name = _safe_str(row.get(name_col))
        if not name:
            stats.dropped_missing_name += 1
            continue

        loc_fields = _build_location_fields(row, cols)
        if not loc_fields:
            stats.dropped_missing_location += 1
            continue
        match_location, display_location = loc_fields

        rating = _parse_rating(row.get(rating_col))
        if rating is None:
            stats.dropped_missing_rating += 1
            continue

        cost = _parse_cost(row.get(cost_col))
        if cost is None:
            stats.dropped_missing_cost += 1
            continue

        cuisines = _split_cuisines(row.get(cuisines_col))
        candidates.append(
            {
                "name": name,
                "location": match_location,
                "display_location": display_location,
                "cuisines": cuisines,
                "rating": rating,
                "cost": cost,
                "row_index": int(idx) if isinstance(idx, int) else len(candidates),
                "metadata": _row_to_metadata(row, cols, stats.schema_unmapped),
            }
        )
        costs_for_bands.append(cost)

    if not candidates:
        stats.dropped_rows = stats.raw_rows
        return [], stats

    cost_series = pd.Series([c["cost"] for c in candidates])
    cap = float(cost_series.quantile(0.99))
    for c in candidates:
        if c["cost"] > cap:
            c["cost"] = cap
            stats.cost_outliers_capped += 1

    costs_for_bands = [c["cost"] for c in candidates]
    bands, percentiles = _assign_cost_bands(costs_for_bands)
    stats.cost_percentiles = percentiles

    seen: set[str] = set()
    restaurants: list[Restaurant] = []
    for c, band in zip(candidates, bands, strict=True):
        cuisine_key = ",".join(sorted(normalize_text(cu) for cu in c["cuisines"]))
        dedupe_key = normalize_text(
            f"{c['name']}|{c['location']}|{c['rating']}|{c['cost']}|{cuisine_key}"
        )
        if dedupe_key in seen:
            stats.deduplicated_rows += 1
            continue
        seen.add(dedupe_key)
        restaurants.append(
            Restaurant(
                id=_stable_id(c["name"], c["location"], c["row_index"]),
                name=c["name"],
                location=c["location"],
                display_location=c["display_location"],
                cuisines=c["cuisines"],
                rating=c["rating"],
                cost=c["cost"],
                cost_band=band,
                metadata=c["metadata"],
            )
        )

    stats.retained_rows = len(restaurants)
    stats.dropped_rows = stats.raw_rows - stats.retained_rows
    stats.dropped_invalid_rating = stats.dropped_missing_rating  # aggregated
    stats.dropped_invalid_cost = stats.dropped_missing_cost
    stats.cost_band_distribution = {
        band.value: sum(1 for r in restaurants if r.cost_band == band) for band in CostBand
    }

    if stats.valid_field_ratio < MIN_VALID_ROW_RATIO:
        logger.warning(
            "Retained %.1f%% of rows (target >= %.0f%%)",
            stats.valid_field_ratio * 100,
            MIN_VALID_ROW_RATIO * 100,
        )

    return restaurants, stats


def _fetch_dataset_revision(dataset_name: str) -> str:
    try:
        from huggingface_hub import HfApi

        info = HfApi().dataset_info(dataset_name)
        sha = getattr(info, "sha", None) or getattr(info, "id", None)
        return str(sha or dataset_name)
    except Exception as exc:
        logger.warning("Could not fetch dataset revision: %s", exc)
        return dataset_name


def _compute_cache_key(dataset_name: str, revision: str) -> str:
    return hashlib.sha256(f"{dataset_name}:{revision}:{HF_DATA_FILE}".encode()).hexdigest()


def _load_cache(cache_path: Path, expected_key: str) -> list[Restaurant] | None:
    meta_path = _meta_path(cache_path)
    if not cache_path.exists() or not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("cache_key") != expected_key:
            logger.info("Cache key mismatch; re-ingesting dataset")
            return None
        df = pd.read_parquet(cache_path)
        records = df.to_dict(orient="records")
        restaurants = [Restaurant.model_validate(r) for r in records]
        logger.info("Loaded %d restaurants from cache %s", len(restaurants), cache_path)
        return restaurants
    except Exception as exc:
        logger.warning("Failed to load cache (%s); re-ingesting", exc)
        if cache_path.exists():
            cache_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        return None


def _save_cache(cache_path: Path, restaurants: list[Restaurant], cache_key: str, stats: IngestionStats) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [r.model_dump(mode="json") for r in restaurants]
    pd.DataFrame(rows).to_parquet(cache_path, index=False)
    meta = {
        "cache_key": cache_key,
        "retained_rows": stats.retained_rows,
        "raw_rows": stats.raw_rows,
        "dataset_revision": stats.dataset_revision,
        "cost_percentiles": stats.cost_percentiles,
    }
    _meta_path(cache_path).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    logger.info("Wrote cache to %s", cache_path)


def load_raw_dataframe(
    settings: Settings | None = None,
    *,
    max_retries: int = 3,
) -> pd.DataFrame:
    """Download and load the raw CSV from Hugging Face with retries."""
    settings = settings or get_settings()
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            path = hf_hub_download(
                repo_id=settings.hf_dataset_name,
                filename=HF_DATA_FILE,
                repo_type="dataset",
            )
            logger.info("Loading CSV from %s", path)
            return pd.read_csv(path)
        except (HfHubHTTPError, OSError, ValueError) as exc:
            last_error = exc
            wait = 2**attempt
            logger.warning("HF download failed (attempt %d/%d): %s", attempt, max_retries, exc)
            time.sleep(wait)

    raise RuntimeError(f"Failed to load dataset after {max_retries} attempts") from last_error


def load_dataset(
    settings: Settings | None = None,
    *,
    use_cache: bool = True,
    dataframe: pd.DataFrame | None = None,
) -> tuple[list[Restaurant], IngestionStats]:
    """
    Load restaurants from cache or Hugging Face, preprocess, and optionally write cache.
    Pass `dataframe` to ingest from an in-memory frame (tests/fixtures).
    """
    settings = settings or get_settings()
    revision = _fetch_dataset_revision(settings.hf_dataset_name)
    cache_key = _compute_cache_key(settings.hf_dataset_name, revision)
    cache_path = settings.data_cache_path
    stats = IngestionStats(dataset_revision=revision)

    if use_cache and dataframe is None:
        cached = _load_cache(cache_path, cache_key)
        if cached is not None:
            stats.retained_rows = len(cached)
            stats.raw_rows = len(cached)
            stats.loaded_from_cache = True
            stats.cost_band_distribution = {
                band.value: sum(1 for r in cached if r.cost_band == band) for band in CostBand
            }
            return cached, stats

    if dataframe is None:
        df = load_raw_dataframe(settings)
    else:
        df = dataframe

    stats.raw_rows = len(df)
    restaurants, stats = preprocess_dataframe(df)
    stats.dataset_revision = revision

    if not restaurants:
        raise RuntimeError("No valid restaurants after preprocessing")

    if use_cache and dataframe is None:
        try:
            _save_cache(cache_path, restaurants, cache_key, stats)
        except OSError as exc:
            logger.error("Could not write Parquet cache: %s", exc)

    logger.info(
        "Ingestion complete: raw=%d retained=%d dropped=%d deduped=%d",
        stats.raw_rows,
        stats.retained_rows,
        stats.dropped_rows,
        stats.deduplicated_rows,
    )
    return restaurants, stats


def load_and_index(
    settings: Settings | None = None,
    *,
    use_cache: bool = True,
    dataframe: pd.DataFrame | None = None,
) -> tuple[RestaurantIndex, IngestionStats]:
    """Load dataset, build in-memory index, and register the singleton."""
    restaurants, stats = load_dataset(settings, use_cache=use_cache, dataframe=dataframe)
    index = build_index(restaurants)
    set_index(index)
    return index, stats


def _print_cli_report(index: RestaurantIndex, stats: IngestionStats) -> None:
    print(f"Rows (raw):        {stats.raw_rows}")
    print(f"Rows (retained):   {stats.retained_rows}")
    print(f"Rows (dropped):    {stats.dropped_rows}")
    print(f"Deduplicated:      {stats.deduplicated_rows}")
    print(f"Loaded from cache: {stats.loaded_from_cache}")
    print(f"Valid ratio:       {stats.valid_field_ratio:.1%}")
    print(f"Cost percentiles:  {stats.cost_percentiles}")
    print(f"Cost band counts:  {stats.cost_band_distribution}")

    sample = index.get_all()[0]
    print("\nSample restaurant:")
    print(f"  id={sample.id}")
    print(f"  name={sample.name}")
    print(f"  location={sample.display_location}")
    print(f"  cuisines={sample.cuisines}")
    print(f"  rating={sample.rating} cost={sample.cost} band={sample.cost_band.value}")

    locations = index.locations()
    if locations:
        probe = locations[0]
        start = time.perf_counter()
        matches = index.by_location(probe)
        elapsed_ms = (time.perf_counter() - start) * 1000
        print(f"\nIndex probe location={probe!r}: {len(matches)} matches in {elapsed_ms:.2f} ms")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    index, stats = load_and_index()
    _print_cli_report(index, stats)


if __name__ == "__main__":
    main()
