"""Orchestrate candidate filtering, prompt construction, LLM ranking, and fallback (architecture §3.4, Phase P2)."""

import logging
from typing import Any

from src.data.models import (
    RecommendationResponse,
    RecommendationResult,
    Restaurant,
    UserPreferences,
)
from src.llm.client import GroqClient, LLMClient
from src.llm.schemas import LLMResponseSchema
from src.services.filter import FilterResult, FilterService
from src.services.prompt_builder import PromptBuilder

logger = logging.getLogger(__name__)


class RecommendationOrchestrator:
    """Orchestrate the restaurant recommendation pipeline."""

    def __init__(
        self,
        filter_service: FilterService | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.filter_service = filter_service or FilterService()
        self.llm_client = llm_client or GroqClient()
        self.prompt_builder = PromptBuilder()

        # Initialize Recommendation Cache using settings (shared across instances)
        if getattr(RecommendationOrchestrator, "_cache_instance", None) is None:
            settings = self.filter_service._settings
            from src.services.cache import RecommendationCache
            RecommendationOrchestrator._cache_instance = RecommendationCache(
                max_size=settings.cache_max_size,
                ttl_seconds=settings.cache_ttl_seconds,
            )
        self.cache = RecommendationOrchestrator._cache_instance

    def recommend(self, preferences: UserPreferences, top_k: int = 5) -> RecommendationResponse:
        """Filter candidate restaurants, rank them via LLM, and return explanations."""
        import time
        from src.services.cache import generate_cache_key

        cache_key = generate_cache_key(preferences, top_k)
        try:
            cached_val = self.cache.get(cache_key)
            if cached_val is not None:
                logger.info("Recommendation cache HIT for key: %s", cache_key)
                return cached_val

            logger.info("Recommendation cache MISS for key: %s", cache_key)
            start_time = time.perf_counter()

            # 1. Deterministic Filtering
            filter_result = self.filter_service.filter_with_meta(preferences)
            candidates = filter_result.restaurants

            # 2. Check for empty candidate list
            if not candidates:
                response = RecommendationResponse(
                    recommendations=[],
                    summary=None,
                    filters_applied=filter_result.filters_applied,
                    degraded_mode=False,
                    message=filter_result.message or "No restaurants matched your filters.",
                    candidates_considered=filter_result.candidates_considered,
                )
                self.cache.set(cache_key, response)
                elapsed = time.perf_counter() - start_time
                logger.info(
                    "Recommendation request (empty candidates) completed in %.2fs. Candidates considered: %d.",
                    elapsed,
                    response.candidates_considered,
                )
                return response

            # 3. Build prompts
            messages = self.prompt_builder.build_messages(candidates, preferences, top_k)

            # 4. Invoke LLM with retry and validation/repair
            try:
                response_format = {"type": "json_object"}
                llm_data = self._parse_and_repair(messages, response_format)
            except Exception as parse_err:
                logger.exception("LLM execution and repair failed: %s", parse_err)
                response = self._fallback_degraded(
                    candidates, filter_result, top_k, str(parse_err)
                )
                self.cache.set(cache_key, response)
                elapsed = time.perf_counter() - start_time
                logger.info(
                    "Recommendation request (degraded fallback) completed in %.2fs. Candidates considered: %d. Error: %s",
                    elapsed,
                    response.candidates_considered,
                    parse_err,
                )
                return response

            # 5. Merge and validate LLM outputs against candidates (prevent hallucinations)
            candidate_map = {r.id: r for r in candidates}
            valid_recs: list[RecommendationResult] = []
            seen_ids = set()

            # Ensure order based on LLM-specified rank
            llm_items = sorted(
                llm_data.recommendations,
                key=lambda x: x.rank if x.rank is not None else 99,
            )

            for item in llm_items:
                rest_id = item.restaurant_id
                if rest_id not in candidate_map:
                    logger.warning(
                        "LLM hallucinated restaurant ID %r. Dropping from recommendations.",
                        rest_id,
                    )
                    continue

                if rest_id in seen_ids:
                    continue

                seen_ids.add(rest_id)
                valid_recs.append(
                    RecommendationResult(
                        rank=len(valid_recs) + 1,  # Sequential rank starting from 1
                        restaurant=candidate_map[rest_id],
                        explanation=item.explanation,
                    )
                )

                if len(valid_recs) >= top_k:
                    break

            # If all recommendations were hallucinated or invalid, use degraded fallback
            if not valid_recs:
                response = self._fallback_degraded(
                    candidates,
                    filter_result,
                    top_k,
                    "LLM response contained no valid candidate IDs.",
                )
                self.cache.set(cache_key, response)
                elapsed = time.perf_counter() - start_time
                logger.info(
                    "Recommendation request (no valid recs) completed in %.2fs. Candidates considered: %d.",
                    elapsed,
                    response.candidates_considered,
                )
                return response

            # Assemble response
            # Prepend filter-relaxation messages if they were applied
            message = filter_result.message
            if filter_result.filters_relaxed and not message:
                relaxed_str = ", ".join(filter_result.filters_relaxed)
                message = f"Note: Strict filters were relaxed for: {relaxed_str}."

            response = RecommendationResponse(
                recommendations=valid_recs,
                summary=llm_data.summary,
                filters_applied=filter_result.filters_applied,
                degraded_mode=False,
                message=message,
                candidates_considered=filter_result.candidates_considered,
            )
            self.cache.set(cache_key, response)
            elapsed = time.perf_counter() - start_time
            logger.info(
                "Recommendation request completed in %.2fs. Candidates considered: %d. Degraded mode: %s.",
                elapsed,
                response.candidates_considered,
                response.degraded_mode,
            )
            return response

        except Exception as global_err:
            logger.exception("Global exception in recommender orchestrator: %s", global_err)
            # Attempt to fall back safely using empty values
            return RecommendationResponse(
                recommendations=[],
                summary=None,
                degraded_mode=True,
                message=f"Global recommendation failure: {global_err}",
            )

    def _call_llm_with_retry(
        self,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None,
    ) -> Any:
        """Send prompt to LLM with up to 1 retry on connection/API exceptions."""
        try:
            return self.llm_client.complete(messages, response_format)
        except Exception as err:
            logger.warning("First LLM call failed with error: %s. Retrying once...", err)
            return self.llm_client.complete(messages, response_format)

    def _parse_and_repair(
        self,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None,
    ) -> LLMResponseSchema:
        """Call LLM and parse JSON, invoking a schema repair prompt if formatting is invalid."""
        result = self._call_llm_with_retry(messages, response_format)

        def heal_keys(raw_content: str) -> LLMResponseSchema:
            import json
            data = json.loads(raw_content)
            if not isinstance(data, dict):
                raise ValueError("LLM response is not a JSON object")
            if "recommended_restaurants" in data and "recommendations" not in data:
                data["recommendations"] = data.pop("recommended_restaurants")
            if "recommendations" in data and isinstance(data["recommendations"], list):
                for item in data["recommendations"]:
                    if isinstance(item, dict):
                        for key in ("reason", "rationale", "description"):
                            if key in item and "explanation" not in item:
                                item["explanation"] = item.pop(key)
            return LLMResponseSchema.model_validate(data)

        try:
            return heal_keys(result.content)
        except Exception as json_err:
            logger.warning(
                "LLM output failed JSON validation: %s. Attempting repair request...", json_err
            )

            # Repair prompt: feed back the bad output and ask to fix it
            repair_messages = list(messages) + [
                {"role": "assistant", "content": result.content},
                {
                    "role": "user",
                    "content": (
                        "Your previous response was not valid JSON matching the requested schema. "
                        "Please output ONLY a valid JSON object matching the requested schema. "
                        "Do not include any other markdown wrappers, introductory, or concluding text."
                    ),
                },
            ]

            repair_result = self._call_llm_with_retry(repair_messages, response_format)
            return heal_keys(repair_result.content)

    def _fallback_degraded(
        self,
        candidates: list[Restaurant],
        filter_result: FilterResult,
        top_k: int,
        error_msg: str,
    ) -> RecommendationResponse:
        """Degraded mode fallback returning top candidate list directly from filters."""
        logger.error("Activating degraded mode recommendations: %s", error_msg)

        top_candidates = candidates[:top_k]
        recommendations = []
        for i, rest in enumerate(top_candidates, start=1):
            recommendations.append(
                RecommendationResult(
                    rank=i,
                    restaurant=rest,
                    explanation="AI explanation unavailable (degraded mode).",
                )
            )

        message = (
            f"Recommendations provided in degraded mode (LLM service unavailable). "
            f"Error details: {error_msg}."
        )
        if filter_result.message:
            message = f"{filter_result.message} | {message}"

        return RecommendationResponse(
            recommendations=recommendations,
            summary="AI summary unavailable (degraded mode).",
            filters_applied=filter_result.filters_applied,
            degraded_mode=True,
            message=message,
            candidates_considered=filter_result.candidates_considered,
        )
