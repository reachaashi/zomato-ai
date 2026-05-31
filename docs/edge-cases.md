# Edge Cases: AI-Powered Restaurant Recommendation System

This document catalogs edge cases across the pipeline, with **expected behavior**, **handling guidance**, and **test priority**. It complements [context.md](./context.md), [architecture.md](./architecture.md), and [implementation-plan.md](./implementation-plan.md).

---

## How to use this document

| Column | Meaning |
|--------|---------|
| **ID** | Stable reference (e.g. `DATA-01`) for tests and issues |
| **Priority** | `P0` = must handle before MVP; `P1` = before release; `P2` = nice-to-have |
| **Phase** | Implementation phase from [implementation-plan.md](./implementation-plan.md) |

When implementing, each edge case should map to at least one of: validation rule, filter relaxation, degraded mode, user-visible message, or structured log.

---

## Table of contents

1. [Data ingestion and preprocessing](#1-data-ingestion-and-preprocessing)
2. [Domain model and indexing](#2-domain-model-and-indexing)
3. [User input and validation](#3-user-input-and-validation)
4. [Filtering and candidate preparation](#4-filtering-and-candidate-preparation)
5. [LLM integration](#5-llm-integration)
6. [Recommendation merge and response](#6-recommendation-merge-and-response)
7. [API layer](#7-api-layer)
8. [Presentation layer (UI)](#8-presentation-layer-ui)
9. [Configuration and environment](#9-configuration-and-environment)
10. [Performance, cost, and concurrency](#10-performance-cost-and-concurrency)
11. [Security and abuse](#11-security-and-abuse)
12. [Deployment and operations](#12-deployment-and-operations)
13. [Cross-cutting and end-to-end](#13-cross-cutting-and-end-to-end)
14. [Test matrix summary](#14-test-matrix-summary)

---

## 1. Data ingestion and preprocessing

| ID | Edge case | Expected behavior | Priority | Phase |
|----|-----------|-------------------|----------|-------|
| DATA-01 | Hugging Face download fails (network, 503, timeout) | Retry with exponential backoff (e.g. 3 attempts); if `DATA_CACHE_PATH` exists, load from local Parquet; else fail startup with clear error | P0 | P0 |
| DATA-02 | Dataset revision changed on HF (schema or row count shift) | Recompute cache hash; re-ingest; log revision change; do not silently use stale mapping | P0 | P0 |
| DATA-03 | Unexpected or renamed HF columns | Log schema diff; map known aliases; drop unmapped optional fields; fail fast if required columns missing | P0 | P0 |
| DATA-04 | Required column missing entirely (`name`, `location`, etc.) | Abort ingest with actionable error listing missing columns | P0 | P0 |
| DATA-05 | Row missing `name` or `location` | Drop row; increment `dropped_rows` counter | P0 | P0 |
| DATA-06 | Row with null/empty `rating` | Drop or default only if dataset policy allows; prefer drop for recommendation quality | P0 | P0 |
| DATA-07 | Row with null/empty `cost` | Drop row (cannot derive `cost_band` or filter by budget) | P0 | P0 |
| DATA-08 | Invalid rating: negative, NaN, or > 5 (or > dataset max) | Clamp to valid range if minor; drop if nonsensical (e.g. 99, -1) | P0 | P0 |
| DATA-09 | Invalid cost: negative, zero, NaN, extreme outlier | Drop or cap outliers at 99th percentile; log outlier count | P1 | P0 |
| DATA-10 | Duplicate restaurant names in same location | Assign stable unique `id` per row (hash of name+location+row index); do not collapse unless business rule defined | P1 | P0 |
| DATA-11 | Duplicate rows (exact repeat) | Deduplicate on hash of normalized fields; log dedupe count | P1 | P0 |
| DATA-12 | Empty dataset after cleaning | Fail startup: "no valid restaurants" | P0 | P0 |
| DATA-13 | Very small dataset (< 50 rows) | Ingest succeeds; warn in logs; percentiles for `cost_band` may be unstable | P1 | P0 |
| DATA-14 | Single cost value for all restaurants | All rows get same `cost_band` (document behavior); budget filter still works but is low value | P2 | P0 |
| DATA-15 | Location string inconsistent (`Delhi`, `delhi`, ` New Delhi `) | Normalize: trim, lowercase for matching; preserve `display_location` for UI | P0 | P0 |
| DATA-16 | Compound cuisine field (`"Italian, Pizza, Fast Food"`) | Split on comma/semicolon; trim tokens; empty tokens removed | P0 | P0 |
| DATA-17 | Cuisine string empty after split | Drop cuisine tag; keep restaurant if other fields valid | P1 | P0 |
| DATA-18 | Non-UTF-8 or special characters in text fields | Normalize Unicode; strip control characters; keep valid emoji if present | P1 | P0 |
| DATA-19 | Local cache file corrupted or partial write | Detect on load failure; delete corrupt cache and re-download | P1 | P0 |
| DATA-20 | Disk full when writing Parquet cache | Log error; continue in-memory only for session; warn operator | P2 | P0 |
| DATA-21 | HF rate limit or auth required unexpectedly | Surface error; document token/env if needed | P1 | P0 |
| DATA-22 | Cost stored as string (`"₹800"`, `"800 for two"`) | Parse numeric portion; drop if unparseable | P0 | P0 |

---

## 2. Domain model and indexing

| ID | Edge case | Expected behavior | Priority | Phase |
|----|-----------|-------------------|----------|-------|
| IDX-01 | Index built before ingest completes | Block API/UI until `RestaurantIndex.ready == true` | P0 | P0 |
| IDX-02 | Location index key mismatch (user "Bangalore" vs data "Bengaluru") | Maintain alias map (`bangalore` → `bengaluru`); fuzzy suggest in validation message | P1 | P1 |
| IDX-03 | Restaurant with multiple cuisines indexed | Appears under each cuisine token | P0 | P0 |
| IDX-04 | Metadata dict very large per row | Truncate or whitelist keys before prompt serialization | P1 | P2 |
| IDX-05 | `cost_band` percentile ties at boundaries | Use consistent rule: `<= p33` low, `<= p66` medium, else high | P1 | P0 |
| IDX-06 | Query location with no restaurants in index | Valid state; filter returns empty (not an error) | P0 | P1 |
| IDX-07 | `/metadata/locations` with 1000+ distinct values | Paginate or cap autocomplete; sort by frequency | P2 | P3 |
| IDX-08 | `/metadata/cuisines` includes rare typo tokens | Return sorted list; optional min-count threshold | P2 | P3 |

---

## 3. User input and validation

| ID | Edge case | Expected behavior | Priority | Phase |
|----|-----------|-------------------|----------|-------|
| IN-01 | Missing `location` | 422 validation error: "location is required" | P0 | P1/P3 |
| IN-02 | Empty string `location` (`""`, whitespace only) | Treat as missing; 422 | P0 | P1/P3 |
| IN-03 | `location` not in dataset (unknown city) | 422 with hint: "Unknown location" + sample valid locations (top N) | P0 | P1/P3 |
| IN-04 | Case-variant location (`delhi` vs `Delhi`) | Normalize and match; accept if normalized form exists | P0 | P1 |
| IN-05 | Missing `budget` | Default to `medium` or 422 — **pick one and document** (recommend 422 for explicit UX) | P0 | P1 |
| IN-06 | Invalid `budget` value (`"cheap"`, `1`, `null`) | 422: allowed values `low`, `medium`, `high` | P0 | P1/P3 |
| IN-07 | Missing `cuisine` | 422 or treat as "any cuisine" — **recommend 422** for MVP clarity | P0 | P1 |
| IN-08 | Empty `cuisine` string | Same as missing | P0 | P1 |
| IN-09 | Cuisine not in dataset (`"Mexican"` when none exist) | Allow request; filter may return empty then relaxation; message suggests valid cuisines | P0 | P1 |
| IN-10 | `min_rating` omitted | Default to `0.0` or sensible floor (e.g. `3.0`) — document in API | P0 | P1 |
| IN-11 | `min_rating` negative | 422 | P0 | P1 |
| IN-12 | `min_rating` > 5 | 422 | P0 | P1 |
| IN-13 | `min_rating` impossibly high (e.g. 4.9) for location | 200 with empty results + suggestion to lower rating | P0 | P1 |
| IN-14 | `additional_preferences` null / omitted | Pass as empty string to LLM; no filter effect | P0 | P1 |
| IN-15 | `additional_preferences` very long (> 2 KB) | Truncate with ellipsis; log truncation; LLM still works | P1 | P2 |
| IN-16 | `additional_preferences` only whitespace | Treat as empty | P1 | P1 |
| IN-17 | `additional_preferences` contains prompt injection ("ignore instructions…") | Sanitize length only; system prompt forbids following user override; do not execute embedded instructions | P0 | P2 |
| IN-18 | `top_k` omitted | Use `DEFAULT_TOP_K` from config | P0 | P3 |
| IN-19 | `top_k` = 0 or negative | 422 | P0 | P3 |
| IN-20 | `top_k` very large (e.g. 100) | Cap at max (e.g. 10 or `len(candidates)`); log cap applied | P1 | P3 |
| IN-21 | `top_k` > number of candidates | Return all candidates ranked (or available after LLM) | P1 | P2 |
| IN-22 | Unicode / emoji in preferences | Accept if valid UTF-8; normalize for logs | P1 | P1 |
| IN-23 | SQL/HTML in input strings | Treat as plain text; escape on UI render | P1 | P4 |
| IN-24 | All fields valid but contradictory (low budget + "fine dining only" in extras) | Filter applies structurally; LLM ranks best effort; explanation may note tradeoff | P1 | P2 |

---

## 4. Filtering and candidate preparation

| ID | Edge case | Expected behavior | Priority | Phase |
|----|-----------|-------------------|----------|-------|
| FIL-01 | Zero restaurants match strict filters | Apply relaxation ladder (§7.1 architecture); record `filters_relaxed` in meta | P0 | P1 |
| FIL-02 | Zero restaurants after all relaxations | 200, `recommendations: []`, message: relax location/cuisine/rating/budget | P0 | P1 |
| FIL-03 | Fewer than 5 matches before LLM (e.g. 2) | Proceed with available; LLM ranks 2; UI shows 2 cards | P0 | P1 |
| FIL-04 | Thousands match location only | Apply rating/cuisine/budget; cap at `MAX_CANDIDATES` | P0 | P1 |
| FIL-05 | Exactly `MAX_CANDIDATES` matches | Pass all; no random drop without documented sort | P0 | P1 |
| FIL-06 | Relaxed rating (−0.5) still zero results | Continue to cuisine partial, then budget adjacent band | P0 | P1 |
| FIL-07 | Budget `low` but user location has only `high` band restaurants | After relaxation, include `medium`; if still empty, return [] with explanation | P0 | P1 |
| FIL-08 | Cuisine partial match false positives (`"chin"` → Chinese and Indian Chinese) | Acceptable for relaxation; LLM disambiguates in ranking | P1 | P1 |
| FIL-09 | User cuisine matches multi-cuisine restaurant partially | Include if any token matches (case-insensitive) | P0 | P1 |
| FIL-10 | `min_rating` filter excludes all but 1 restaurant | LLM receives 1 candidate; return 1 recommendation | P0 | P1 |
| FIL-11 | Location alias not configured | Strict match only; may yield empty — suggest alias in docs | P1 | P1 |
| FIL-12 | Additional preferences imply vegetarian; no veg flag in data | No structured pre-filter unless metadata tag exists; rely on LLM | P1 | P2 |
| FIL-13 | Pre-LLM sort by rating ties | Secondary sort by name or id for deterministic order | P1 | P1 |
| FIL-14 | Candidate cap drops high-rated restaurants | Sort by rating desc before cap so best stay in prompt | P0 | P1 |
| FIL-15 | Filter called before index ready | 503 Service Unavailable | P0 | P3 |

---

## 5. LLM integration

| ID | Edge case | Expected behavior | Priority | Phase |
|----|-----------|-------------------|----------|-------|
| LLM-01 | Missing `LLM_API_KEY` | Startup warning or fail on first recommend; clear error message | P0 | P2 |
| LLM-02 | Invalid API key (401) | No retry; degraded mode; log auth failure (no key in logs) | P0 | P2 |
| LLM-03 | Rate limit (429) | Retry once with backoff; then degraded mode | P0 | P2 |
| LLM-04 | Provider timeout | Retry once; then degraded mode | P0 | P2 |
| LLM-05 | Provider 5xx | Retry once; then degraded mode | P0 | P2 |
| LLM-06 | Empty completion content | Treat as parse failure; retry then degraded | P0 | P2 |
| LLM-07 | Non-JSON response (markdown fenced JSON, prose) | Strip fences; extract JSON block; retry if fail | P0 | P2 |
| LLM-08 | Malformed JSON (truncated, trailing comma) | Schema repair retry; then degraded | P0 | P2 |
| LLM-09 | Valid JSON but wrong schema (missing `recommendations`) | Retry with stricter reminder; then degraded | P0 | P2 |
| LLM-10 | Hallucinated `restaurant_id` not in candidates | Drop entry; log warning; backfill rank from next valid | P0 | P2 |
| LLM-11 | Duplicate ranks (two `rank: 1`) | Renumber by order in array or re-sort by rank field | P0 | P2 |
| LLM-12 | Missing ranks | Assign ranks 1..n by array order | P0 | P2 |
| LLM-13 | Fewer than `top_k` items in LLM output | Return what was parsed; pad from filter-only order if needed | P1 | P2 |
| LLM-14 | More than `top_k` items in LLM output | Truncate to `top_k` | P0 | P2 |
| LLM-15 | Empty `explanation` string | Use fallback: "Recommended based on your preferences." | P1 | P2 |
| LLM-16 | Explanation contradicts facts ("5.0 rating" when data says 4.1) | Optional post-check: flag in `confidence_note`; do not change rating | P1 | P2 |
| LLM-17 | LLM invents restaurant name matching no candidate | Reject row (ID guardrail); never surface new restaurant | P0 | P2 |
| LLM-18 | Token/context overflow from provider | Reduce candidates and retry once; else degraded | P1 | P2 |
| LLM-19 | `summary` field missing | `summary: null` in response; UI hides summary block | P1 | P2 |
| LLM-20 | `summary` excessively long | Truncate for UI (e.g. 500 chars) | P2 | P4 |
| LLM-21 | Model returns moderated/refusal ("I can't help") | Degraded mode + user message | P1 | P2 |
| LLM-22 | Concurrent requests exhaust token budget | Queue or limit concurrency; return 503 or degraded per policy | P2 | P5 |
| LLM-23 | Local Ollama offline (dev) | Degraded mode; health check false | P1 | P2 |
| LLM-24 | JSON mode unsupported by provider | Rely on prompt + parser; extra retry | P1 | P2 |

---

## 6. Recommendation merge and response

| ID | Edge case | Expected behavior | Priority | Phase |
|----|-----------|-------------------|----------|-------|
| MERGE-01 | LLM returns ID for deleted/capped candidate | Drop; log | P0 | P2 |
| MERGE-02 | Join by ID fails but name matches exactly one candidate | Fallback join by normalized name; log ambiguity if multiple | P1 | P2 |
| MERGE-03 | Join by name matches multiple candidates | Prefer ID match only; drop ambiguous name match | P0 | P2 |
| MERGE-04 | `degraded_mode: true` | Explanations null or generic; banner in UI; `meta.degraded_reason` | P0 | P2/P4 |
| MERGE-05 | Partial LLM success (3 valid of 5 requested) | Return 3; optionally fill 2 from filter order without explanation | P1 | P2 |
| MERGE-06 | `estimated_cost` formatting | Use dataset cost; format with locale-agnostic number; handle missing as "N/A" | P0 | P2 |
| MERGE-07 | Display cuisine from multi-value | Join primary cuisines or first token; show full list in detail | P1 | P4 |
| MERGE-08 | Rating displayed with excessive precision | Show one decimal (e.g. 4.3) | P2 | P4 |
| MERGE-09 | Response cache hit with stale data after re-ingest | Invalidate cache on dataset hash change | P1 | P5 |
| MERGE-10 | Identical request repeated rapidly | Optional cache return; same results; log cache hit | P2 | P5 |

---

## 7. API layer

| ID | Edge case | Expected behavior | Priority | Phase |
|----|-----------|-------------------|----------|-------|
| API-01 | `GET /health` before dataset load | `status: starting` or 503 until ready | P0 | P3 |
| API-02 | `POST /recommend` with invalid JSON body | 422 with parse error detail | P0 | P3 |
| API-03 | `POST /recommend` with extra unknown fields | Ignore extras (Pydantic `extra=forbid` or ignore — document) | P1 | P3 |
| API-04 | `POST /recommend` while index loading | 503 | P0 | P3 |
| API-05 | Wrong `Content-Type` | 415 Unsupported Media Type | P2 | P3 |
| API-06 | `GET /metadata/locations` when index empty | 200, `[]` | P1 | P3 |
| API-07 | Very large response payload | Unlikely with top_k ≤ 10; gzip if deployed behind proxy | P2 | P5 |
| API-08 | Internal unhandled exception | 500; generic message; stack in logs only | P0 | P3 |
| API-09 | Request ID for tracing | Generate `X-Request-ID`; include in logs and optional response meta | P1 | P5 |
| API-10 | CORS from browser UI | Configure allowed origins for Streamlit/React host | P1 | P3/P4 |

---

## 8. Presentation layer (UI)

| ID | Edge case | Expected behavior | Priority | Phase |
|----|-----------|-------------------|----------|-------|
| UI-01 | User submits before selecting location | Inline validation; block submit | P0 | P4 |
| UI-02 | Double-click submit (duplicate requests) | Disable button during load; debounce | P0 | P4 |
| UI-03 | LLM slow (> 10 s) | Loading spinner; optional cancel (P2) | P0 | P4 |
| UI-04 | API unreachable from UI | Error banner: check API URL / server | P0 | P4 |
| UI-05 | Empty results | Empty state with tips (relax filters) | P0 | P4 |
| UI-06 | `degraded_mode` true | Prominent info banner; hide or dim missing explanations | P0 | P4 |
| UI-07 | Missing `explanation` in degraded mode | Show "AI explanation unavailable" | P0 | P4 |
| UI-08 | Very long explanation text | Scrollable card section or truncate with "read more" | P1 | P4 |
| UI-09 | Rating/cost null in payload | Display "N/A"; do not crash render | P0 | P4 |
| UI-10 | Autocomplete location not in list but typed manually | Validate against API or show warning | P1 | P4 |
| UI-11 | Streamlit session rerun mid-request | Handle stale state; show error or retry | P1 | P4 |
| UI-12 | Mobile narrow viewport | Cards stack; readable typography | P2 | P4 |

---

## 9. Configuration and environment

| ID | Edge case | Expected behavior | Priority | Phase |
|----|-----------|-------------------|----------|-------|
| CFG-01 | `.env` missing | Use defaults where safe; require `LLM_API_KEY` only when calling LLM | P0 | 0 |
| CFG-02 | Invalid `MAX_CANDIDATES` (0, negative, non-int) | Fall back to default 30; log warning | P1 | 0 |
| CFG-03 | `MAX_CANDIDATES` > 100 | Cap at 100 to protect tokens | P1 | 0 |
| CFG-04 | Unknown `LLM_PROVIDER` | Fail at client init with list of supported providers | P0 | P2 |
| CFG-05 | `HF_DATASET_NAME` wrong | Ingest error with dataset not found | P0 | P0 |
| CFG-06 | Secrets committed to git | Document in README; use `.env` gitignored | P0 | 0 |

---

## 10. Performance, cost, and concurrency

| ID | Edge case | Expected behavior | Priority | Phase |
|----|-----------|-------------------|----------|-------|
| PERF-01 | First request after cold start slow | Expected; health shows loading; warm index on startup | P1 | P3 |
| PERF-02 | 30 candidates × verbose metadata → high tokens | Whitelist prompt fields; cap metadata size | P1 | P2 |
| PERF-03 | Burst of parallel `/recommend` calls | Document single-process limits; optional rate limit | P2 | P5 |
| PERF-04 | Memory pressure with full dataset in RAM | Monitor row count; document max dataset size | P2 | P5 |

---

## 11. Security and abuse

| ID | Edge case | Expected behavior | Priority | Phase |
|----|-----------|-------------------|----------|-------|
| SEC-01 | API key in logs or error traces | Never log `LLM_API_KEY`; redact in debug | P0 | P5 |
| SEC-02 | Oversized request body (> 1 MB) | 413 Payload Too Large | P1 | P3 |
| SEC-03 | Automated scraping `/recommend` | Rate limit per IP (deployment concern) | P2 | P5 |
| SEC-04 | PII in `additional_preferences` | Do not persist in v1; avoid logging full text in prod | P1 | P5 |
| SEC-05 | XSS via API response in web UI | Escape rendered text | P0 | P4 |

---

## 12. Deployment and operations

| ID | Edge case | Expected behavior | Priority | Phase |
|----|-----------|-------------------|----------|-------|
| OPS-01 | Container starts before volume mount ready | Retry dataset load; backoff | P1 | P5 |
| OPS-02 | Process restart during active request | Client sees failure; idempotent retry safe | P1 | P5 |
| OPS-03 | Clock skew affecting cache TTL | Use monotonic or version hash not wall clock only | P2 | P5 |
| OPS-04 | CI without network | Tests use `tests/fixtures/` only | P0 | P5 |

---

## 13. Cross-cutting and end-to-end

| ID | Edge case | Expected behavior | Priority | Phase |
|----|-----------|-------------------|----------|-------|
| E2E-01 | User wants only filter, no LLM (cost saving) | Feature flag `SKIP_LLM=true` → filter-only response | P2 | P5 |
| E2E-02 | Same preferences, different results on rerun | LLM may vary; optional `temperature=0` for stability | P2 | P2 |
| E2E-03 | All filters relaxed — user not informed | `meta.filters_relaxed: true` and human-readable list | P0 | P1 |
| E2E-04 | Pipeline order violation (LLM before filter) | Architecture forbids; code review / test | P0 | P2 |
| E2E-05 | Dataset has no restaurants for popular city name typo | Suggest closest location via Levenshtein (P2) | P2 | P1 |

---

## Decision log (ambiguous cases)

Document team choices here when implementing:

| Topic | Recommended default | Alternative |
|-------|---------------------|-------------|
| Missing `budget` | 422 required field | Default `medium` |
| Missing `cuisine` | 422 required field | Filter any cuisine |
| Unknown `location` | 422 with suggestions | 200 empty results |
| `min_rating` default | `0.0` | `3.0` |
| Partial LLM output | Return partial + filter backfill | Return partial only |

---

## 14. Test matrix summary

Map high-priority edge cases to test types:

| Layer | Test file (suggested) | IDs (minimum) |
|-------|----------------------|---------------|
| Ingestion | `tests/test_ingestion.py` | DATA-05–08, 12, 15–16, 22 |
| Filter | `tests/test_filter.py` | FIL-01–04, 10, 14 |
| LLM parse | `tests/test_llm_parse.py` | LLM-07–10, 13–14 (mocked) |
| API | `tests/test_api.py` | IN-01–06, 11–12, API-02, 04 |
| Integration | `tests/test_e2e.py` | E2E-03, LLM-03–05 (mocked), MERGE-04 |
| UI | Manual / Playwright (optional) | UI-01–06 |

---

## Requirements traceability

| Context requirement | Edge-case sections |
|---------------------|-------------------|
| Load and preprocess dataset | §1, §2 |
| Accept user preferences | §3 |
| Filter by user input | §4 |
| LLM prompt and ranking | §5, §6 |
| Display results | §6, §8 |

---

## Related documents

- [context.md](./context.md) — Project overview and workflow
- [architecture.md](./architecture.md) — Error handling (§11), filtering (§7), LLM guardrails (§6.5)
- [implementation-plan.md](./implementation-plan.md) — Phase deliverables and acceptance criteria
