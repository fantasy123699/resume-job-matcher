"""OpenAI-compatible chat-completions adapter.

Written against the wire format rather than a vendor SDK so the same adapter serves
any compatible endpoint (a hosted API or a local Ollama/vLLM runtime) by changing
two settings. The client is injected so tests can drive the adapter without network
access.
"""

from typing import Any

import httpx

from resume_job_matcher.core.config import Settings
from resume_job_matcher.domain.llm import (
    LlmCompletion,
    LlmExtractionRequest,
    LlmProvider,
    LlmProviderError,
    LlmProviderTimeout,
)


class OpenAiCompatibleLlmProvider:
    """Calls ``{base_url}/chat/completions`` and normalizes the response."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._client = client

    @property
    def name(self) -> str:
        return f"openai-compatible:{self._model}"

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url and self._model)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _payload(self, request: LlmExtractionRequest) -> dict[str, Any]:
        return {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
            "stream": False,
        }

    async def complete(self, request: LlmExtractionRequest) -> LlmCompletion:
        if not self.is_configured:
            raise LlmProviderError("LLM provider is not configured")

        url = f"{self._base_url}/chat/completions"
        try:
            if self._client is not None:
                response = await self._client.post(
                    url, json=self._payload(request), headers=self._headers()
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        url, json=self._payload(request), headers=self._headers()
                    )
        except httpx.TimeoutException as exc:
            raise LlmProviderTimeout("The LLM provider did not respond in time") from exc
        except httpx.HTTPError as exc:
            raise LlmProviderError("The LLM provider is unreachable") from exc

        if response.status_code >= 400:
            raise LlmProviderError(f"The LLM provider returned HTTP {response.status_code}")

        try:
            body = response.json()
            text = body["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LlmProviderError("The LLM provider returned an unexpected payload") from exc

        usage = body.get("usage") or {}
        return LlmCompletion(
            text=text or "",
            model=str(body.get("model") or self._model),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )


def build_llm_provider(settings: Settings) -> LlmProvider:
    """Return the configured provider, or the null provider when unconfigured.

    Returning a null provider (rather than raising) keeps the import path usable in
    every environment: a deployment without model credentials still extracts the
    deterministic facts instead of failing outright.
    """

    from resume_job_matcher.domain.llm import NullLlmProvider

    if settings.llm_provider == "openai_compatible":
        api_key = settings.llm_api_key
        return OpenAiCompatibleLlmProvider(
            base_url=settings.llm_base_url or "",
            model=settings.llm_model or "",
            api_key=api_key.get_secret_value() if api_key is not None else None,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    return NullLlmProvider()
