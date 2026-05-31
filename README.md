# Zomato AI Restaurant Recommendation

AI-powered restaurant recommendations using the [Zomato Hugging Face dataset](https://huggingface.co/datasets/ManikaSaini/zomato-restaurant-recommendation), deterministic filtering, and an LLM for ranking and explanations.

See [docs/context.md](docs/context.md) and [docs/architecture.md](docs/architecture.md) for design details. Phase-wise delivery is tracked in [docs/implementation-plan.md](docs/implementation-plan.md).

## Prerequisites

- Python 3.10 or newer
- (Later phases) An API key for your chosen LLM provider

## Setup

From the project root:

```bash
python -m venv .venv

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Copy environment template and adjust as needed:

```bash
copy .env.example .env   # Windows
# cp .env.example .env   # macOS / Linux
```

Verify the package imports:

```bash
python -c "import src; from src.config import get_settings; print(get_settings().hf_dataset_name)"
```

## Environment variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `HF_DATASET_NAME` | Hugging Face dataset id | `ManikaSaini/zomato-restaurant-recommendation` |
| `LLM_PROVIDER` | LLM vendor (`groq` only for P2) | `groq` |
| `LLM_API_KEY` | Groq API key from [console.groq.com](https://console.groq.com/) (**do not commit**) | — |
| `LLM_MODEL` | Groq model id (e.g. `llama-3.3-70b-versatile`) | `llama-3.3-70b-versatile` |
| `MAX_CANDIDATES` | Cap on restaurants sent to the LLM | `30` |
| `DEFAULT_TOP_K` | Number of recommendations returned | `5` |
| `DATA_CACHE_PATH` | Optional local Parquet cache file | `data/cache.parquet` |

Configuration is loaded via `src.config.get_settings()` (Pydantic Settings + `python-dotenv`).

## Project layout

```text
src/
  config.py          # Settings (Phase 0)
  data/              # Ingestion, models, index (Phase P0)
  services/          # Filter, prompt builder, recommender (P1–P2)
  llm/               # LLM client and schemas (P2)
  api/               # FastAPI routes (P3)
  ui/                # Streamlit app (P4)
tests/
  fixtures/          # CI fixture data (P5)
data/                # Gitignored local cache
```

## Entry points (by phase)

### Data ingestion (P0)

```bash
python -m src.data.ingestion
```

Downloads the Hugging Face CSV (or loads `DATA_CACHE_PATH` Parquet cache), preprocesses rows, derives `cost_band`, and builds the in-memory `RestaurantIndex` singleton.

Run tests without network (fixture CSV only):

```bash
pytest tests/test_ingestion.py -q
```

| Phase | Command | Description |
|-------|---------|-------------|
| **P0** | `python -m src.data.ingestion` | Load dataset, print stats, build index |
| **P1** | `pytest tests/test_filter.py -q` | Filter service unit tests |
| **P3** | `uvicorn src.api.main:app --reload` | REST API (coming in P3) |
| **P4** | `streamlit run src/ui/app.py` | Web UI (coming in P4) |
| **P5** | `pytest` | Test suite (coming in P5) |

## Development status

| Phase | Status |
|-------|--------|
| 0 — Scaffolding | Done |
| P0 — Data ingestion | Done |
| P1 — Filter service | Done |
| P2 — LLM engine | Done |
| P3 — API layer | Done |
| P4 — UI | Done |
| P5 — Hardening | Planned |

## License

See repository license (if applicable).
