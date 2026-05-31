"""Phase P2: LLM engine, schemas, prompt builder, and orchestrator tests."""

import os
import json
import pytest
from pydantic import ValidationError

from src.config import Settings
from src.data.models import CostBand, Restaurant, UserPreferences
from src.llm.client import CompletionResult, LLMClient, GroqClient
from src.llm.schemas import LLMResponseSchema, LLMRecommendationItem
from src.services.prompt_builder import PromptBuilder
from src.services.recommender import RecommendationOrchestrator
from src.services.filter import FilterService


class MockLLMClient(LLMClient):
    """A mock LLM client to intercept and inspect LLM operations."""

    def __init__(self, response_content: str = "", throws_exception: bool = False) -> None:
        self.response_content = response_content
        self.throws_exception = throws_exception
        self.calls: list[tuple[list[dict[str, str]], dict | None]] = []

    def complete(self, messages: list[dict[str, str]], response_format: dict | None = None) -> CompletionResult:
        self.calls.append((messages, response_format))
        if self.throws_exception:
            raise RuntimeError("Mock API connection failure")
        return CompletionResult(self.response_content)

    def health_check(self) -> bool:
        return not self.throws_exception


def test_schemas_validation():
    """Verify that valid and invalid LLM JSON schemas parse correctly."""
    valid_json = """{
        "summary": "These are great options.",
        "recommendations": [
            {"restaurant_id": "r1", "rank": 1, "explanation": "Fits perfectly"}
        ]
    }"""
    schema = LLMResponseSchema.model_validate_json(valid_json)
    assert schema.summary == "These are great options."
    assert len(schema.recommendations) == 1
    assert schema.recommendations[0].restaurant_id == "r1"

    # Missing recommendations should fail validation
    invalid_json = '{"summary": "No recommendations here."}'
    with pytest.raises(ValidationError):
        LLMResponseSchema.model_validate_json(invalid_json)


def test_parser_self_healing_keys():
    from src.services.recommender import RecommendationOrchestrator
    orchestrator = RecommendationOrchestrator()
    
    raw_response = """{
        "summary": "Healing test",
        "recommended_restaurants": [
            {"restaurant_id": "r1", "reason": "Tastes great"},
            {"restaurant_id": "r2", "rationale": "Lovely place"}
        ]
    }"""
    
    class MockResult:
        def __init__(self, content):
            self.content = content
            
    orchestrator._call_llm_with_retry = lambda msg, fmt: MockResult(raw_response)
    
    parsed = orchestrator._parse_and_repair([], None)
    assert parsed.summary == "Healing test"
    assert len(parsed.recommendations) == 2
    assert parsed.recommendations[0].restaurant_id == "r1"
    assert parsed.recommendations[0].explanation == "Tastes great"
    assert parsed.recommendations[1].restaurant_id == "r2"
    assert parsed.recommendations[1].explanation == "Lovely place"


def test_prompt_builder(restaurant_index):
    """Verify that PromptBuilder builds system and user messages containing all candidates."""
    builder = PromptBuilder()
    prefs = UserPreferences(
        location="koramangala",
        budget=CostBand.LOW,
        cuisine="Italian",
        min_rating=4.0,
        additional_preferences="quiet place",
    )
    candidates = restaurant_index.by_location("koramangala")
    messages = builder.build_messages(candidates, prefs, top_k=3)

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "restaurant_id" in messages[0]["content"]

    user_payload = json.loads(messages[1]["content"])
    assert user_payload["user_preferences"]["location"] == "koramangala"
    assert user_payload["user_preferences"]["additional_preferences"] == "quiet place"
    assert len(user_payload["candidates"]) == len(candidates)
    assert user_payload["instructions"]["top_k"] == 3


def test_recommender_successful_flow(restaurant_index, filter_settings):
    """Verify standard happy-path recommendation flow with mock LLM client."""
    mock_response = json.dumps({
        "summary": "Top choices for you.",
        "recommendations": [
            {"restaurant_id": "r1", "rank": 1, "explanation": "Perfect match"},
            {"restaurant_id": "r7", "rank": 2, "explanation": "Great vibe"}
        ]
    })
    mock_client = MockLLMClient(response_content=mock_response)
    service = FilterService(restaurant_index, filter_settings)
    orchestrator = RecommendationOrchestrator(service, mock_client)

    prefs = UserPreferences(location="koramangala", budget=CostBand.LOW, min_rating=4.0)
    response = orchestrator.recommend(prefs, top_k=2)

    assert not response.degraded_mode
    assert response.summary == "Top choices for you."
    assert len(response.recommendations) == 2
    assert response.recommendations[0].restaurant.name == "Alpha"
    assert response.recommendations[0].explanation == "Perfect match"
    assert response.recommendations[1].restaurant.name == "Family Spot"


def test_recommender_filters_empty_skips_llm(restaurant_index, filter_settings):
    """Verify that if deterministic filters yield 0 candidates, the LLM call is skipped."""
    mock_client = MockLLMClient(throws_exception=True)
    service = FilterService(restaurant_index, filter_settings)
    orchestrator = RecommendationOrchestrator(service, mock_client)

    # Empty location should return 0 candidates
    prefs = UserPreferences(location="UnknownPlace", budget=CostBand.LOW)
    response = orchestrator.recommend(prefs)

    assert not response.degraded_mode
    assert response.recommendations == []
    assert len(mock_client.calls) == 0
    assert "UnknownPlace" in response.message


def test_recommender_degraded_mode_on_llm_exception(restaurant_index, filter_settings):
    """Verify orchestrator falls back to degraded mode if LLM throws an exception."""
    mock_client = MockLLMClient(throws_exception=True)
    service = FilterService(restaurant_index, filter_settings)
    orchestrator = RecommendationOrchestrator(service, mock_client)

    prefs = UserPreferences(location="koramangala", budget=CostBand.LOW)
    response = orchestrator.recommend(prefs, top_k=2)

    assert response.degraded_mode
    assert "degraded mode" in response.message.lower()
    # Should fall back to top filter results directly
    assert len(response.recommendations) == 2
    assert response.recommendations[0].explanation == "AI explanation unavailable (degraded mode)."
    # Should have retried once (2 calls total)
    assert len(mock_client.calls) == 2


def test_recommender_repair_prompt_on_invalid_json(restaurant_index, filter_settings):
    """Verify orchestrator attempts to repair LLM response if it is malformed JSON."""
    class TwoStageMockClient(LLMClient):
        def __init__(self) -> None:
            self.calls = []

        def complete(self, messages, response_format=None):
            self.calls.append(messages)
            if len(self.calls) == 1:
                return CompletionResult("This is not JSON!")
            return CompletionResult(json.dumps({
                "summary": "Repaired summary.",
                "recommendations": [
                    {"restaurant_id": "r1", "rank": 1, "explanation": "Repaired explanation"}
                ]
            }))

        def health_check(self):
            return True

    mock_client = TwoStageMockClient()
    service = FilterService(restaurant_index, filter_settings)
    orchestrator = RecommendationOrchestrator(service, mock_client)

    prefs = UserPreferences(location="koramangala", budget=CostBand.LOW)
    response = orchestrator.recommend(prefs, top_k=1)

    assert not response.degraded_mode
    assert len(mock_client.calls) == 2  # First call + 1 repair call
    # The last message of the repair call should be the repair request
    assert "previous response was not valid JSON" in mock_client.calls[1][-1]["content"]
    assert response.recommendations[0].explanation == "Repaired explanation"


def test_recommender_double_invalid_json_degraded_fallback(restaurant_index, filter_settings):
    """Verify orchestrator activates degraded mode if both original and repair LLM calls fail JSON validation."""
    mock_client = MockLLMClient(response_content="Completely invalid content")
    service = FilterService(restaurant_index, filter_settings)
    orchestrator = RecommendationOrchestrator(service, mock_client)

    prefs = UserPreferences(location="koramangala", budget=CostBand.LOW)
    response = orchestrator.recommend(prefs, top_k=2)

    assert response.degraded_mode
    assert "degraded mode" in response.message.lower()
    assert len(response.recommendations) == 2
    # First call failed -> repair call also returned invalid content -> fallback to degraded
    # Each stage has up to 1 retry on HTTP level, but since this is JSON error,
    # it does: 1st complete -> JSON error -> repair complete -> JSON error -> degraded
    # total calls = 1 (first) + 1 (repair) = 2 calls
    assert len(mock_client.calls) == 2


def test_recommender_anti_hallucination_filtering(restaurant_index, filter_settings):
    """Verify that hallucinated restaurant IDs in LLM response are discarded."""
    mock_response = json.dumps({
        "summary": "Mixing valid and invalid items.",
        "recommendations": [
            {"restaurant_id": "r_non_existent", "rank": 1, "explanation": "Hallucinated"},
            {"restaurant_id": "r1", "rank": 2, "explanation": "Valid"}
        ]
    })
    mock_client = MockLLMClient(response_content=mock_response)
    service = FilterService(restaurant_index, filter_settings)
    orchestrator = RecommendationOrchestrator(service, mock_client)

    prefs = UserPreferences(location="koramangala", budget=CostBand.LOW)
    response = orchestrator.recommend(prefs, top_k=5)

    assert not response.degraded_mode
    assert len(response.recommendations) == 1
    assert response.recommendations[0].restaurant.id == "r1"
    assert response.recommendations[0].restaurant.name == "Alpha"
    assert response.recommendations[0].explanation == "Valid"


@pytest.mark.skipif(
    not os.getenv("LLM_API_KEY"),
    reason="LLM_API_KEY environment variable not set for live smoke tests",
)
def test_live_groq_recommendation_smoke(restaurant_index, filter_settings):
    """Live smoke test calling the actual Groq API when an API key is available."""
    # Ensure real Groq client is instantiated
    service = FilterService(restaurant_index, filter_settings)
    orchestrator = RecommendationOrchestrator(service)

    prefs = UserPreferences(
        location="koramangala",
        budget=CostBand.LOW,
        cuisine="Italian",
        min_rating=4.0,
        additional_preferences="family-friendly dining",
    )
    response = orchestrator.recommend(prefs, top_k=2)

    assert not response.degraded_mode
    assert len(response.recommendations) >= 1
    assert response.recommendations[0].restaurant.name in ["Alpha", "Family Spot"]
    assert len(response.recommendations[0].explanation) > 0
    assert response.summary is not None
