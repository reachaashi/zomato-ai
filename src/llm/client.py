"""LLM client interface and Groq provider implementation (architecture §6.4, Phase P2)."""

from abc import ABC, abstractmethod
from typing import Any
import httpx

from src.config import Settings, get_settings


class CompletionResult:
    """The result of an LLM completion request."""

    def __init__(self, content: str, token_usage: dict[str, int] | None = None) -> None:
        self.content = content
        self.token_usage = token_usage or {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }


class LLMClient(ABC):
    """Abstract base class/interface for LLM clients."""

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
    ) -> CompletionResult:
        """Send chat messages and return the completion result."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Verify the LLM provider is reachable and responsive."""
        pass


class GroqClient(LLMClient):
    """Client for Groq API using HTTP POST via httpx."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.api_key = self.settings.llm_api_key
        self.model = self.settings.llm_model
        # Groq uses an OpenAI-compatible URL path for completions
        self.base_url = "https://api.groq.com/openai/v1"

    def complete(
        self,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
    ) -> CompletionResult:
        """Call Groq chat completion endpoint synchronously."""
        if not self.api_key:
            raise ValueError("LLM_API_KEY is not configured in settings/environment.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,  # Lower temperature for recommendations and parsing
        }

        if response_format:
            payload["response_format"] = response_format

        url = f"{self.base_url}/chat/completions"

        with httpx.Client(timeout=self.settings.llm_timeout) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            res_json = response.json()

            content = res_json["choices"][0]["message"]["content"]
            usage = res_json.get("usage", {})
            token_usage = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }
            return CompletionResult(content, token_usage)

    def health_check(self) -> bool:
        """Check if the Groq service is available by performing a cheap call."""
        if not self.api_key:
            return False
        try:
            # Send a minimal call with very low token budget
            messages = [{"role": "user", "content": "ping"}]
            self.complete(messages)
            return True
        except Exception:
            return False
