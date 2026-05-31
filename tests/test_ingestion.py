"""Phase P0: data ingestion and index tests (fixture-only, no HF network)."""

from pathlib import Path

import pandas as pd
import pytest

from src.data.index import clear_index, get_index
from src.data.ingestion import (
    _assign_cost_bands,
    _load_cache,
    _parse_cost,
    _parse_rating,
    _resolve_columns,
    _save_cache,
    load_and_index,
    load_dataset,
    preprocess_dataframe,
)
from src.data.models import CostBand

FIXTURE_CSV = Path(__file__).parent / "fixtures" / "sample_restaurants.csv"


@pytest.fixture
def sample_df() -> pd.DataFrame:
    return pd.read_csv(FIXTURE_CSV)


@pytest.fixture(autouse=True)
def reset_index():
    clear_index()
    yield
    clear_index()


def test_resolve_columns(sample_df: pd.DataFrame):
    cols = _resolve_columns(sample_df)
    assert cols["name"] == "name"
    assert cols["cost"] == "approx_cost(for two people)"
    assert cols["rating"] == "rate"


def test_display_location_comma_split(sample_df: pd.DataFrame):
    from src.data.ingestion import _build_location_fields
    cols = _resolve_columns(sample_df)
    row = pd.Series({
        "name": "Test Restaurant",
        "location": "BTM, Bannerghatta Road",
        "listed_in(city)": "Bangalore",
        "address": "123 Main St",
        "rate": "4.0/5",
        "approx_cost(for two people)": "500",
        "cuisines": "Italian"
    })
    loc_fields = _build_location_fields(row, cols)
    assert loc_fields is not None
    match_location, display_location = loc_fields
    assert display_location == "BTM"
    assert "btm" in match_location
    assert "bannerghatta road" in match_location


def test_restaurant_clean_ndarray_validator():
    import numpy as np
    import json
    from src.data.models import Restaurant, CostBand
    r = Restaurant(
        id="test-id",
        name="Test",
        location="btm",
        display_location="BTM",
        cuisines=np.array(["Italian", "Chinese"]),
        rating=4.0,
        cost=500.0,
        cost_band=CostBand.MEDIUM,
        metadata={"tags": np.array(["tag1", "tag2"])}
    )
    assert isinstance(r.cuisines, list)
    assert isinstance(r.metadata["tags"], list)
    dumped = json.dumps(r.model_dump())
    assert "Italian" in dumped
    assert "tag1" in dumped


def test_parse_rating_and_cost():
    assert _parse_rating("4.1/5") == 4.1
    assert _parse_rating("NEW") is None
    assert _parse_cost(800) == 800.0
    assert _parse_cost("₹1,200") == 1200.0
    assert _parse_cost("") is None


def test_preprocess_drops_invalid_rows(sample_df: pd.DataFrame):
    restaurants, stats = preprocess_dataframe(sample_df)
    names = {r.name for r in restaurants}
    assert "Alpha Bistro" in names
    assert "Beta Kitchen" in names
    assert "Gamma Grill" in names
    assert "nan" not in names
    assert "Delta Diner" not in names  # NEW rating
    assert "Epsilon Eats" not in names  # missing cost
    assert stats.dropped_rows >= 3
    assert all(r.cost_band for r in restaurants)


def test_cost_band_percentiles():
    bands, percentiles = _assign_cost_bands([100.0, 500.0, 900.0])
    assert percentiles["p33"] <= percentiles["p66"]
    assert bands[0] == CostBand.LOW
    assert bands[-1] == CostBand.HIGH


def test_load_dataset_from_fixture(sample_df: pd.DataFrame):
    restaurants, stats = load_dataset(use_cache=False, dataframe=sample_df)
    assert len(restaurants) == 3
    assert stats.retained_rows == 3
    assert stats.valid_field_ratio >= 0.5
    assert all(r.cost_band in CostBand for r in restaurants)


def test_cache_roundtrip(sample_df: pd.DataFrame, tmp_path: Path):
    from src.config import Settings

    settings = Settings(data_cache_path=tmp_path / "cache.parquet")
    restaurants, stats = load_dataset(settings=settings, use_cache=False, dataframe=sample_df)
    cache_key = "test-cache-key"
    _save_cache(settings.data_cache_path, restaurants, cache_key, stats)

    loaded = _load_cache(settings.data_cache_path, cache_key)
    assert loaded is not None
    assert len(loaded) == len(restaurants)
    assert loaded[0].name == restaurants[0].name

    stale = _load_cache(settings.data_cache_path, "other-key")
    assert stale is None


def test_load_and_index_singleton(sample_df: pd.DataFrame):
    index, stats = load_and_index(use_cache=False, dataframe=sample_df)
    assert index.ready
    assert stats.retained_rows == 3
    assert len(index.get_all()) == 3
    assert get_index() is index
    assert len(index.locations()) >= 1
    assert any(c.lower() == "italian" for c in index.cuisines())


def test_index_location_query_performance(sample_df: pd.DataFrame):
    import time

    index, _ = load_and_index(use_cache=False, dataframe=sample_df)
    location = index.locations()[0]
    start = time.perf_counter()
    matches = index.by_location(location)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 100
    assert isinstance(matches, list)
