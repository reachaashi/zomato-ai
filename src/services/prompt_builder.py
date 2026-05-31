"""Assemble prompt payloads for candidate ranking and explanations (architecture §6.2, Phase P2)."""

import json
from src.data.models import Restaurant, UserPreferences


class PromptBuilder:
    """Build system and user chat completion message lists."""

    SYSTEM_PROMPT = (
        "You are an expert restaurant recommendation ranking assistant.\n"
        "Your task is to rank a list of candidate restaurants based on the user's preferences "
        "and provide a short, tailored, and personalized explanation for why each recommended "
        "restaurant matches their preferences (e.g. food style, budget, rating, special requests).\n\n"
        "CRITICAL RULES:\n"
        "1. You MUST only recommend restaurants that are present in the provided 'candidates' list.\n"
        "2. Do NOT invent new restaurants, and do NOT modify names, ratings, or costs.\n"
        "3. Use the exact 'id' from the candidate list as the 'restaurant_id' in your output.\n"
        "4. You must rank the top K restaurants (where K is requested by the user, default 5) in order of relevance.\n"
        "5. Your explanation for each restaurant must specifically mention why it fits the user's "
        "preferences, including any 'additional_preferences' if provided.\n"
        "6. Return a JSON object matching this exact schema:\n"
        "{\n"
        "  \"summary\": \"A brief overall summary of the recommendations\",\n"
        "  \"recommendations\": [\n"
        "    {\n"
        "      \"restaurant_id\": \"The exact id from candidate list (e.g., r_102)\",\n"
        "      \"rank\": 1,\n"
        "      \"explanation\": \"A short personalized explanation matching user preferences\"\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "Do not output any conversational text before or after the JSON."
    )

    def build_messages(
        self,
        candidates: list[Restaurant],
        preferences: UserPreferences,
        top_k: int = 5,
    ) -> list[dict[str, str]]:
        """Construct the chat message sequence (system prompt + structured user context)."""
        system_msg = {"role": "system", "content": self.SYSTEM_PROMPT}

        # Structure the user preferences
        user_prefs_dict = {
            "location": preferences.location,
            "budget": preferences.budget.value,
            "cuisine": preferences.cuisine or "any",
            "min_rating": preferences.min_rating,
            "additional_preferences": preferences.additional_preferences or "none",
        }

        # Structure candidates list (only keep relevant details to save tokens)
        candidates_list = []
        for rest in candidates:
            candidates_list.append(
                {
                    "id": rest.id,
                    "name": rest.name,
                    "location": rest.display_location,
                    "cuisines": rest.cuisines,
                    "rating": rest.rating,
                    "cost": rest.cost,
                    "cost_band": rest.cost_band.value,
                    "tags": rest.metadata.get("tags", []),
                }
            )

        user_content_dict = {
            "user_preferences": user_prefs_dict,
            "candidates": candidates_list,
            "instructions": {
                "top_k": top_k,
                "rank_by": "relevance to all preferences including additional_preferences",
                "include_summary": True,
            },
        }

        user_msg = {
            "role": "user",
            "content": json.dumps(user_content_dict, indent=2),
        }

        return [system_msg, user_msg]
