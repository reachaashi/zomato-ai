"""Canonical domain models (architecture §4.2)."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class CostBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


Budget = CostBand  # user budget maps directly to cost_band


def _to_python_types(val: Any) -> Any:
    if type(val).__name__ == "ndarray":
        return _to_python_types(val.tolist())
    if isinstance(val, dict):
        return {k: _to_python_types(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_to_python_types(x) for x in val]
    if isinstance(val, tuple):
        return tuple(_to_python_types(x) for x in val)
    return val


class Restaurant(BaseModel):
    id: str
    name: str
    location: str  # normalized (lowercase, trimmed) for matching
    display_location: str  # preserved for UI
    cuisines: list[str]
    rating: float = Field(ge=0, le=5)
    cost: float = Field(gt=0)
    cost_band: CostBand
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def clean_ndarray(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return _to_python_types(data)
        return data


class UserPreferences(BaseModel):
    location: str = Field(min_length=1, description="City or locality (required)")
    budget: CostBand
    cuisine: str = ""
    min_rating: float = Field(default=0.0, ge=0, le=5)
    additional_preferences: str | None = None

    @field_validator("location", "cuisine", mode="before")
    @classmethod
    def strip_strings(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("additional_preferences", mode="before")
    @classmethod
    def normalize_additional(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped if stripped else None
        return value


class RecommendationResult(BaseModel):
    rank: int
    restaurant: Restaurant
    explanation: str
    confidence_note: str | None = None


class RecommendationResponse(BaseModel):
    recommendations: list[RecommendationResult]
    summary: str | None = None
    filters_applied: dict[str, Any] = Field(default_factory=dict)
    degraded_mode: bool = False
    message: str | None = None
    candidates_considered: int = 0


