"""Integration tests: the LLM path as reached through the import endpoint.

Unit tests prove the guard and the loop behave. These prove the endpoint actually
calls them, which is the difference between "the code exists" and "the product does
it" — an unwired service is invisible to a user, and claiming otherwise would not
survive an interview.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_resume_import import authenticated_client, csrf_headers

from resume_job_matcher.api.routes import resumes as resume_routes
from resume_job_matcher.domain.llm import (
    LlmExtractionRequest,
    LlmProviderError,
    NullLlmProvider,
    ScriptedLlmProvider,
)

RESUME_TEXT = "\n".join(
    [
        "张三",
        "个人简介",
        "三年 Python 后端开发经验",
        "专业技能",
        "熟练使用 Python、FastAPI，掌握 RAG 完整流程",
        "项目经历",
        "负责内部数据平台开发",
    ]
)


def post_import(client: TestClient) -> Any:
    return client.post(
        "/api/v1/resumes/import",
        data={"text_content": RESUME_TEXT},
        headers=csrf_headers(client),
    )


def facts_of(client: TestClient) -> list[dict[str, Any]]:
    return list(post_import(client).json()["facts"])


def test_import_without_a_provider_still_succeeds_and_persists_deterministic_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default deployment has no model credentials; importing must still work."""

    monkeypatch.setattr(resume_routes, "build_llm_provider", lambda _settings: NullLlmProvider())
    client = authenticated_client("no-provider@example.test")

    response = post_import(client)

    assert response.status_code == 201
    facts = response.json()["facts"]
    assert facts
    assert all(fact["created_by"] == "deterministic_parser" for fact in facts)


def test_a_guard_accepted_model_fact_is_persisted_with_the_model_as_its_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion = (
        '[{"category":"project","statement":"参与过 RAG 检索优化",'
        '"quote":"掌握 RAG 完整流程","source_ref":"line:5"}]'
    )
    monkeypatch.setattr(
        resume_routes,
        "build_llm_provider",
        lambda _settings: ScriptedLlmProvider([completion], model="test-model-x"),
    )
    client = authenticated_client("model-fact@example.test")

    facts = facts_of(client)

    from_model = [fact for fact in facts if fact["created_by"] == "test-model-x"]
    assert len(from_model) == 1
    # The guard resolved the location itself, and the quote is stored verbatim.
    assert from_model[0]["source_location"] == "line:5"
    assert from_model[0]["source_text"] == "掌握 RAG 完整流程"
    # Guard-accepted facts still require the user to confirm them.
    assert from_model[0]["user_status"] == "pending"


def test_a_hallucinated_model_fact_never_reaches_the_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The end-to-end version of the promise: an invented quote must not persist."""

    completion = (
        '[{"category":"skill","statement":"精通 Kubernetes 集群运维",'
        '"quote":"精通 Kubernetes 集群运维","source_ref":"line:5","confidence":0.99}]'
    )
    monkeypatch.setattr(
        resume_routes,
        "build_llm_provider",
        lambda _settings: ScriptedLlmProvider([completion], model="hallucinating-model"),
    )
    client = authenticated_client("hallucination@example.test")

    facts = facts_of(client)

    assert all(fact["created_by"] != "hallucinating-model" for fact in facts)
    assert not any("Kubernetes" in fact["source_text"] for fact in facts)


def test_a_provider_that_raises_does_not_fail_the_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Exploding:
        name = "exploding"
        is_configured = True

        async def complete(self, request: LlmExtractionRequest) -> None:
            raise LlmProviderError("upstream down")

    monkeypatch.setattr(resume_routes, "build_llm_provider", lambda _settings: Exploding())
    client = authenticated_client("provider-down@example.test")

    response = post_import(client)

    assert response.status_code == 201
    assert response.json()["facts"]


def test_model_facts_are_added_to_rather_than_replacing_deterministic_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion = (
        '[{"category":"achievement","statement":"掌握 RAG 全流程",'
        '"quote":"掌握 RAG 完整流程","source_ref":"line:5"}]'
    )
    monkeypatch.setattr(
        resume_routes,
        "build_llm_provider",
        lambda _settings: ScriptedLlmProvider([completion], model="additive-model"),
    )
    client = authenticated_client("additive@example.test")

    origins = {fact["created_by"] for fact in facts_of(client)}

    assert "additive-model" in origins
    assert "deterministic_parser" in origins


def test_model_facts_from_outcome_ignores_a_missing_guard() -> None:
    class NoGuard:
        guard = None

    assert resume_routes.model_facts_from_outcome(NoGuard()) == []
