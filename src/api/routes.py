"""FastAPI routes for the restaurant recommendation service (architecture §8.1, Phase P3)."""

import logging
from typing import Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.data.models import UserPreferences
from src.services.recommender import RecommendationOrchestrator
from src.services.filter import FilterService
from src.llm.client import GroqClient
from src.data.index import get_index

router = APIRouter()
logger = logging.getLogger(__name__)


# API Request and Response schemas
class APIRecommendationRequest(UserPreferences):
    top_k: int = Field(default=5, ge=1, le=50, description="Number of recommendations to return")


class APIRecItem(BaseModel):
    rank: int
    name: str
    cuisine: str
    rating: float
    estimated_cost: float
    explanation: str


class APIMeta(BaseModel):
    candidates_considered: int
    filters_applied: dict[str, Any]


class APIRecommendationResponse(BaseModel):
    recommendations: list[APIRecItem]
    summary: str | None = None
    degraded_mode: bool = False
    meta: APIMeta
    message: str | None = None


class HealthResponse(BaseModel):
    status: str
    dataset_loaded: bool
    llm_connected: bool


@router.get("/health", response_model=HealthResponse)
def health_check():
    """Verify application liveness, dataset loading, and LLM connectivity."""
    index = get_index()
    dataset_loaded = index.ready if index else False

    # Check LLM health
    client = GroqClient()
    llm_connected = client.health_check()

    overall_status = "ok" if dataset_loaded else "error"

    return HealthResponse(
        status=overall_status,
        dataset_loaded=dataset_loaded,
        llm_connected=llm_connected,
    )


@router.get("/metadata/locations", response_model=list[str])
def get_locations():
    """Get distinct locations from index for UI autocomplete."""
    index = get_index()
    if not index or not index.ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Restaurant index is not ready",
        )
    return index.locations()


@router.get("/metadata/cuisines", response_model=list[str])
def get_cuisines():
    """Get distinct cuisines from index for UI dropdown."""
    index = get_index()
    if not index or not index.ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Restaurant index is not ready",
        )
    return index.cuisines()


@router.post("/recommend", response_model=APIRecommendationResponse)
def get_recommendations(request: APIRecommendationRequest):
    """Orchestrate the end-to-end filtering and LLM recommendation pipeline."""
    index = get_index()
    if not index or not index.ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Restaurant index is not ready",
        )

    # Instantiate services
    filter_service = FilterService(index)
    orchestrator = RecommendationOrchestrator(filter_service=filter_service)

    # Perform recommendation
    response = orchestrator.recommend(request, top_k=request.top_k)

    # Map backend response to API contract schema
    api_recs = []
    for rec in response.recommendations:
        api_recs.append(
            APIRecItem(
                rank=rec.rank,
                name=rec.restaurant.name,
                cuisine=", ".join(rec.restaurant.cuisines),
                rating=rec.restaurant.rating,
                estimated_cost=rec.restaurant.cost,
                explanation=rec.explanation,
            )
        )

    meta = APIMeta(
        candidates_considered=response.candidates_considered,
        filters_applied=response.filters_applied,
    )

    return APIRecommendationResponse(
        recommendations=api_recs,
        summary=response.summary,
        degraded_mode=response.degraded_mode,
        meta=meta,
        message=response.message,
    )
