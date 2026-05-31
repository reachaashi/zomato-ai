"""Phase P3: FastAPI API contract and validation tests."""

import json
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from src.api.main import app
from src.data.models import CostBand
from src.llm.client import CompletionResult


@pytest.fixture(autouse=True)
def mock_startup_ingestion():
    """Mock the startup ingestion download to run tests fully offline."""
    with patch("src.api.main.load_and_index") as mock:
        yield mock


@pytest.fixture
def client():
    """FastAPI TestClient with lifespan context enabled."""
    with TestClient(app) as c:
        yield c


def test_health_endpoint(client, restaurant_index):
    """Verify that GET /health checks dataset liveness and LLM reachability."""
    with patch("src.api.routes.GroqClient") as MockClient:
        instance = MockClient.return_value
        instance.health_check.return_value = True

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["dataset_loaded"] is True
        assert data["llm_connected"] is True


def test_metadata_endpoints(client, restaurant_index):
    """Verify metadata retrieval for autocomplete UI items."""
    # Test locations endpoint
    response = client.get("/metadata/locations")
    assert response.status_code == 200
    locations = response.json()
    assert any(l.lower() == "koramangala bangalore" for l in locations)

    # Test cuisines endpoint
    response = client.get("/metadata/cuisines")
    assert response.status_code == 200
    cuisines = response.json()
    assert any(c.lower() == "italian" for c in cuisines)


def test_recommend_endpoint_success(client, restaurant_index):
    """Verify successful POST /recommend execution and contract matching."""
    with patch("src.services.recommender.GroqClient") as MockClient:
        instance = MockClient.return_value
        mock_completion_json = {
            "summary": "Top choices for Italian in Koramangala.",
            "recommendations": [
                {
                    "restaurant_id": "r1",
                    "rank": 1,
                    "explanation": "Authentic Italian wood-fired pizza.",
                }
            ],
        }
        instance.complete.return_value = CompletionResult(json.dumps(mock_completion_json))

        payload = {
            "location": "koramangala",
            "budget": "low",
            "cuisine": "Italian",
            "min_rating": 4.0,
            "additional_preferences": "cozy ambiance",
            "top_k": 2,
        }

        response = client.post("/recommend", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert data["degraded_mode"] is False
        assert data["summary"] == "Top choices for Italian in Koramangala."
        assert len(data["recommendations"]) == 1
        assert data["recommendations"][0]["name"] == "Alpha"
        assert data["recommendations"][0]["cuisine"] == "Italian"
        assert data["recommendations"][0]["estimated_cost"] == 300.0
        assert data["recommendations"][0]["explanation"] == "Authentic Italian wood-fired pizza."

        # Verify meta contracts are fully present
        assert data["meta"]["candidates_considered"] == 1
        assert "location" in data["meta"]["filters_applied"]
        assert data["meta"]["filters_applied"]["location"] == "koramangala"


def test_recommend_endpoint_empty_candidates(client, restaurant_index):
    """Verify that unknown locations return empty recommendations and descriptive messages."""
    payload = {"location": "Delhi", "budget": "low", "cuisine": "Italian"}
    response = client.post("/recommend", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["recommendations"] == []
    assert data["degraded_mode"] is False
    assert "Delhi" in data["message"]
    assert data["meta"]["candidates_considered"] == 0


def test_recommend_endpoint_invalid_input(client):
    """Verify bad inputs trigger standard FastAPI Pydantic ValidationErrors."""
    # Location missing/empty should trigger a 422 Unprocessable Entity error
    payload = {"location": "", "budget": "low"}
    response = client.post("/recommend", json=payload)
    assert response.status_code == 422

    # Missing budget should trigger 422
    payload = {"location": "koramangala"}
    response = client.post("/recommend", json=payload)
    assert response.status_code == 422

    # Invalid budget should trigger 422
    payload = {"location": "koramangala", "budget": "cheap"}
    response = client.post("/recommend", json=payload)
    assert response.status_code == 422

    # Negative rating should trigger 422
    payload = {"location": "koramangala", "budget": "low", "min_rating": -1.0}
    response = client.post("/recommend", json=payload)
    assert response.status_code == 422

    # Rating > 5 should trigger 422
    payload = {"location": "koramangala", "budget": "low", "min_rating": 6.0}
    response = client.post("/recommend", json=payload)
    assert response.status_code == 422

    # Invalid JSON body should trigger 422
    response = client.post("/recommend", content="not a json string")
    assert response.status_code == 422


def test_recommend_endpoint_index_not_ready(client):
    """Verify 503 is returned if request is sent before the index is loaded."""
    with patch("src.api.routes.get_index") as mock_get_index:
        mock_get_index.return_value = None
        payload = {"location": "koramangala", "budget": "low"}
        response = client.post("/recommend", json=payload)
        assert response.status_code == 503
        assert "ready" in response.json()["detail"].lower()


def test_recommend_endpoint_degraded_mode(client, restaurant_index):
    """Verify that when the LLM client throws an exception, the API handles it and returns degraded response."""
    with patch("src.services.recommender.GroqClient") as MockClient:
        instance = MockClient.return_value
        instance.complete.side_effect = RuntimeError("Mock API timeout")

        payload = {
            "location": "koramangala",
            "budget": "low",
            "cuisine": "Italian",
            "min_rating": 4.0,
        }

        response = client.post("/recommend", json=payload)
        assert response.status_code == 200
        data = response.json()

        assert data["degraded_mode"] is True
        assert "degraded" in data["message"].lower()
        # Fallback recommendations should be returned
        assert len(data["recommendations"]) >= 1
        assert data["recommendations"][0]["explanation"] == "AI explanation unavailable (degraded mode)."


def test_recommend_endpoint_cached(client, restaurant_index):
    """Verify that duplicate recommendation requests hitting the API are cached."""
    from src.services.recommender import RecommendationOrchestrator
    if getattr(RecommendationOrchestrator, "_cache_instance", None) is not None:
        RecommendationOrchestrator._cache_instance.clear()

    with patch("src.services.recommender.GroqClient") as MockClient:
        instance = MockClient.return_value
        mock_completion_json = {
            "summary": "Caching test.",
            "recommendations": [
                {
                    "restaurant_id": "r1",
                    "rank": 1,
                    "explanation": "Perfect match",
                }
            ],
        }
        instance.complete.return_value = CompletionResult(json.dumps(mock_completion_json))

        payload = {
            "location": "koramangala",
            "budget": "low",
            "cuisine": "Italian",
            "min_rating": 4.0,
        }

        # First Request: Cache Miss, invokes complete
        response1 = client.post("/recommend", json=payload)
        assert response1.status_code == 200
        assert instance.complete.call_count == 1

        # Second Request: Cache Hit, bypasses complete
        response2 = client.post("/recommend", json=payload)
        assert response2.status_code == 200
        # Call count remains 1
        assert instance.complete.call_count == 1

        # Check identical payload responses
        assert response1.json()["recommendations"] == response2.json()["recommendations"]


