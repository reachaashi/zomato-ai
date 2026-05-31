"""JSON schemas for LLM requests and responses (architecture §6.3, Phase P2)."""

from pydantic import BaseModel, Field


class LLMRecommendationItem(BaseModel):
    """A single ranked restaurant item recommended by the LLM."""

    restaurant_id: str = Field(
        description="The unique ID of the recommended restaurant from the candidate list"
    )
    rank: int | None = Field(
        default=None, description="The assigned rank (1 to K, where 1 is the best)"
    )
    explanation: str = Field(description="Personalized explanation matching user preferences")


class LLMResponseSchema(BaseModel):
    """The structured JSON response expected from the LLM."""

    summary: str | None = Field(
        default=None, description="A brief overall summary of the recommendations"
    )
    recommendations: list[LLMRecommendationItem] = Field(
        description="List of recommended restaurants"
    )
