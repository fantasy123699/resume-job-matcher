"""Ports and value objects for model-backed extraction.

The provider is a *port*: the application layer depends on this protocol, never on
a vendor SDK. That keeps the deterministic path testable and lets deployments swap
an OpenAI-compatible endpoint for a local runtime without touching business logic.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class LlmExtractionRequest(BaseModel):
    """One extraction call: a system instruction plus numbered source lines."""

    system_prompt: str = Field(min_length=1)
    user_prompt: str = Field(min_length=1)
    max_output_tokens: int = Field(default=1024, ge=1, le=8192)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


@dataclass(frozen=True)
class LlmCompletion:
    """Raw model output plus the accounting needed to attribute it."""

    text: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LlmProviderError(RuntimeError):
    """Raised when a provider cannot answer; callers must degrade, not crash."""


class LlmProviderTimeout(LlmProviderError):
    """A slow provider must not hold a request open indefinitely."""


@runtime_checkable
class LlmProvider(Protocol):
    """Minimal surface the application needs from any chat-completions backend."""

    @property
    def name(self) -> str: ...

    @property
    def is_configured(self) -> bool: ...

    async def complete(self, request: LlmExtractionRequest) -> LlmCompletion: ...


class NullLlmProvider:
    """Default provider: reports itself unconfigured and refuses to guess.

    Chosen over returning an empty completion so that a missing configuration is a
    visible, typed failure rather than silently producing zero facts.
    """

    @property
    def name(self) -> str:
        return "null"

    @property
    def is_configured(self) -> bool:
        return False

    async def complete(self, request: LlmExtractionRequest) -> LlmCompletion:
        raise LlmProviderError("No LLM provider is configured")


class ScriptedLlmProvider:
    """Deterministic in-process provider used by tests and local dry runs.

    It returns queued completions in order, which lets tests assert on fact-guard
    behaviour without a network call or an API key.
    """

    def __init__(self, completions: Sequence[str], model: str = "scripted-test-model") -> None:
        self._completions = list(completions)
        self._model = model
        self.requests: list[LlmExtractionRequest] = []

    @property
    def name(self) -> str:
        return "scripted"

    @property
    def is_configured(self) -> bool:
        return True

    async def complete(self, request: LlmExtractionRequest) -> LlmCompletion:
        self.requests.append(request)
        if not self._completions:
            raise LlmProviderError("ScriptedLlmProvider ran out of queued completions")
        return LlmCompletion(text=self._completions.pop(0), model=self._model)
