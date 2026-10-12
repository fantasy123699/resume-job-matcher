"""Tests for the LLM provider port, its HTTP adapter, and the extraction service."""

import asyncio

import httpx
import pytest

from resume_job_matcher.application.llm_extraction_service import (
    SYSTEM_PROMPT,
    extract_facts_with_guard,
)
from resume_job_matcher.domain.llm import (
    LlmExtractionRequest,
    LlmProviderError,
    NullLlmProvider,
    ScriptedLlmProvider,
)
from resume_job_matcher.infrastructure.llm_provider import (
    OpenAiCompatibleLlmProvider,
    build_llm_provider,
)

SOURCE_LINES = [
    ("line:1", "个人优势"),
    ("line:2", "熟练使用 Python、C++，遵循编程规范"),
    ("line:3", "南通大学 本科 通信工程 2023-2027"),
]


# --- the null provider is the default and must never pretend to work -------------


def test_null_provider_reports_itself_unconfigured_and_refuses_to_answer() -> None:
    provider = NullLlmProvider()

    assert provider.is_configured is False
    assert provider.name == "null"
    with pytest.raises(LlmProviderError):
        asyncio.run(provider.complete(LlmExtractionRequest(system_prompt="s", user_prompt="u")))


def test_factory_returns_null_provider_when_disabled() -> None:
    class Disabled:
        llm_provider = "disabled"

    assert isinstance(build_llm_provider(Disabled()), NullLlmProvider)


def test_factory_builds_the_http_adapter_from_settings() -> None:
    from pydantic import SecretStr

    class Configured:
        llm_provider = "openai_compatible"
        llm_base_url = "https://example.invalid/v1"
        llm_model = "some-model"
        llm_api_key = SecretStr("secret-key")
        llm_timeout_seconds = 12.0

    provider = build_llm_provider(Configured())

    assert isinstance(provider, OpenAiCompatibleLlmProvider)
    assert provider.is_configured is True
    assert provider.name == "openai-compatible:some-model"


# --- extraction degrades instead of failing -------------------------------------


def test_extraction_without_a_provider_still_returns_deterministic_skills() -> None:
    """A deployment with no model credentials must still import resumes."""

    outcome = extract_facts_with_guard(NullLlmProvider(), SOURCE_LINES)

    assert outcome.used_model is False
    assert outcome.degraded_reason == "provider_not_configured"
    names = {fact.value.name for fact in outcome.accepted if fact.fact_type == "skill"}
    assert "Python" in names
    assert "C++" in names


def test_a_provider_error_degrades_rather_than_raising() -> None:
    class BrokenProvider:
        name = "broken"
        is_configured = True

        async def complete(self, request: LlmExtractionRequest):
            raise LlmProviderError("upstream is down")

    outcome = extract_facts_with_guard(BrokenProvider(), SOURCE_LINES)

    assert outcome.used_model is False
    assert outcome.degraded_reason == "provider_error:LlmProviderError"
    # The deterministic baseline is still delivered.
    assert outcome.accepted


def test_guard_keeps_a_real_quote_and_drops_an_invented_one() -> None:
    completion = (
        '[{"category":"skill","statement":"熟练使用 Python 和 C++",'
        '"quote":"熟练使用 Python、C++","source_ref":"line:2"},'
        '{"category":"skill","statement":"精通 Kubernetes 集群运维",'
        '"quote":"精通 Kubernetes 集群运维","source_ref":"line:2"}]'
    )
    provider = ScriptedLlmProvider([completion])

    outcome = extract_facts_with_guard(provider, SOURCE_LINES)

    assert outcome.used_model is True
    assert outcome.guard is not None
    assert len(outcome.guard.accepted) == 1
    assert outcome.guard.accepted[0].source_ref == "line:2"
    assert len(outcome.guard.rejected) == 1
    # The hallucination is recorded with its reason so quality can be measured.
    assert outcome.guard.rejected[0].statement == "精通 Kubernetes 集群运维"


def test_the_system_prompt_forbids_inference_and_demands_a_verbatim_quote() -> None:
    """The prompt is advisory, but it must at least state the contract."""

    assert "verbatim" in SYSTEM_PROMPT
    assert "Never infer" in SYSTEM_PROMPT
    assert "confidence" in SYSTEM_PROMPT


def test_scripted_provider_records_the_request_it_received() -> None:
    provider = ScriptedLlmProvider(["[]"])

    asyncio.run(provider.complete(LlmExtractionRequest(system_prompt="sys", user_prompt="usr")))

    assert len(provider.requests) == 1
    assert provider.requests[0].system_prompt == "sys"
    assert provider.requests[0].temperature == 0.0


# --- the HTTP adapter maps the wire format and its failures ---------------------


def _provider_with(handler) -> OpenAiCompatibleLlmProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return OpenAiCompatibleLlmProvider(
        base_url="https://example.invalid/v1",
        model="test-model",
        api_key="key",
        client=client,
    )


def test_adapter_parses_a_normal_completion_and_its_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer key"
        return httpx.Response(
            200,
            json={
                "model": "test-model-2026",
                "choices": [{"message": {"content": "[]"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 3},
            },
        )

    completion = asyncio.run(
        _provider_with(handler).complete(LlmExtractionRequest(system_prompt="s", user_prompt="u"))
    )

    assert completion.text == "[]"
    assert completion.model == "test-model-2026"
    assert completion.prompt_tokens == 11


def test_adapter_reports_an_http_error_as_a_provider_error() -> None:
    provider = _provider_with(lambda request: httpx.Response(429, json={"error": "rate limited"}))

    with pytest.raises(LlmProviderError, match="HTTP 429"):
        asyncio.run(provider.complete(LlmExtractionRequest(system_prompt="s", user_prompt="u")))


def test_adapter_reports_a_timeout_distinctly() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("too slow")

    with pytest.raises(LlmProviderError):
        asyncio.run(
            _provider_with(handler).complete(
                LlmExtractionRequest(system_prompt="s", user_prompt="u")
            )
        )


def test_adapter_rejects_an_unexpected_payload() -> None:
    provider = _provider_with(lambda request: httpx.Response(200, json={"unexpected": True}))

    with pytest.raises(LlmProviderError, match="unexpected payload"):
        asyncio.run(provider.complete(LlmExtractionRequest(system_prompt="s", user_prompt="u")))
