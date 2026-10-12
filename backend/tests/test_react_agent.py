"""Tests for the ReAct loop and its tools.

The loop is the part that must not become a hole in the safety story: a model that
can call tools must still not be able to assert a fact that the tools never returned.
"""

import pytest

from resume_job_matcher.application.agent_tools import build_default_tools
from resume_job_matcher.domain.llm import NullLlmProvider, ScriptedLlmProvider
from resume_job_matcher.domain.react_agent import (
    MAX_STEPS_CEILING,
    StepKind,
    Tool,
    ToolRegistry,
    build_react_prompt,
    run_react_loop,
)
from resume_job_matcher.domain.skill_dictionary import DEFAULT_SKILL_DICTIONARY, SkillDictionary

SOURCE_LINES = [
    ("line:1", "个人优势"),
    ("line:2", "熟练使用 Python、FastAPI，掌握 RAG 完整流程"),
    ("line:3", "南通大学 本科 通信工程 2023-2027"),
]


@pytest.fixture
def tools() -> ToolRegistry:
    return build_default_tools(DEFAULT_SKILL_DICTIONARY, SOURCE_LINES)


# --- tool execution -------------------------------------------------------------


def test_find_in_resume_returns_the_actual_source_line(tools: ToolRegistry) -> None:
    observation = tools.invoke("find_in_resume", {"term": "FastAPI"})

    assert "[line:2]" in observation
    assert "熟练使用 Python、FastAPI" in observation


def test_find_in_resume_admits_when_a_term_is_absent(tools: ToolRegistry) -> None:
    observation = tools.invoke("find_in_resume", {"term": "Kubernetes"})

    assert "does not appear" in observation


def test_lookup_skill_resolves_an_alias_to_its_canonical_name(tools: ToolRegistry) -> None:
    observation = tools.invoke("lookup_skill", {"query": "spring boot"})

    assert "Spring Boot" in observation


def test_lookup_skill_reports_a_non_skill_rather_than_guessing(tools: ToolRegistry) -> None:
    observation = tools.invoke("lookup_skill", {"query": "advanced wizardry"})

    assert "not in the dictionary" in observation


def test_unknown_tool_is_refused_with_the_available_list(tools: ToolRegistry) -> None:
    observation = tools.invoke("delete_everything", {})

    assert "unknown tool" in observation
    assert "lookup_skill" in observation


def test_a_raising_tool_becomes_an_observation_not_a_crash() -> None:
    def explode(_payload: dict[str, object]) -> str:
        raise ValueError("boom")

    registry = ToolRegistry([Tool(name="explode", description="fails", handler=explode)])

    observation = registry.invoke("explode", {})

    assert "ValueError" in observation
    assert "boom" in observation


# --- loop behaviour -------------------------------------------------------------


def _scripted(*turns: str) -> ScriptedLlmProvider:
    return ScriptedLlmProvider(list(turns))


def test_loop_calls_a_tool_then_answers_using_its_observation(tools: ToolRegistry) -> None:
    call_turn = (
        '{"thought":"check the resume","action":"find_in_resume",'
        '"action_input":{"term":"FastAPI"}}'
    )
    provider = _scripted(
        call_turn,
        '{"thought":"I have the line","final_answer":"The resume lists FastAPI on line 2."}',
    )

    run = run_react_loop(provider, tools, "Does the resume mention FastAPI?")

    assert run.stopped_reason == "answered"
    assert run.tools_used == ["find_in_resume"]
    assert "line 2" in run.final_answer
    # The observation is fed back, which is what makes the second turn grounded.
    assert "[line:2]" in provider.requests[1].user_prompt


def test_loop_chain_multiple_tools() -> None:
    registry = ToolRegistry(
        [
            Tool(name="first", description="returns one", handler=lambda _p: "result-one"),
            Tool(name="second", description="returns two", handler=lambda _p: "result-two"),
        ]
    )
    provider = _scripted(
        '{"thought":"a","action":"first","action_input":{}}',
        '{"thought":"b","action":"second","action_input":{}}',
        '{"thought":"done","final_answer":"both"}',
    )

    run = run_react_loop(provider, registry, "chain")

    assert run.tools_used == ["first", "second"]
    assert run.final_answer == "both"


def test_loop_stops_at_the_step_ceiling_instead_of_spinning(tools: ToolRegistry) -> None:
    provider = _scripted(*['{"thought":"again","action":"count_skills","action_input":{}}'] * 3)

    run = run_react_loop(provider, tools, "loop forever", max_steps=3)

    assert run.stopped_reason == "max_steps_reached"
    assert len(run.tools_used) == 3


def test_a_malformed_turn_is_corrected_rather_than_fatal(tools: ToolRegistry) -> None:
    provider = _scripted(
        "I think the answer is probably FastAPI.",
        '{"thought":"properly now","final_answer":"FastAPI is present."}',
    )

    run = run_react_loop(provider, tools, "q")

    assert run.stopped_reason == "answered"
    assert any(step.content == "unparseable turn" for step in run.steps)
    # The model is told exactly how to recover.
    assert "not valid JSON" in provider.requests[1].user_prompt


def test_provider_failure_degrades_without_raising(tools: ToolRegistry) -> None:
    run = run_react_loop(NullLlmProvider(), tools, "q")

    assert run.stopped_reason.startswith("provider_error")
    assert run.final_answer == ""


def test_fenced_json_turns_are_accepted(tools: ToolRegistry) -> None:
    provider = _scripted(
        '```json\n{"thought":"t","final_answer":"fenced answer"}\n```',
    )

    run = run_react_loop(provider, tools, "q")

    assert run.final_answer == "fenced answer"


def test_step_ceiling_is_enforced() -> None:
    with pytest.raises(ValueError, match="max_steps"):
        run_react_loop(_scripted(), ToolRegistry([]), "q", max_steps=MAX_STEPS_CEILING + 1)


def test_transcript_records_thoughts_actions_and_observations(tools: ToolRegistry) -> None:
    provider = _scripted(
        '{"thought":"需要查证","action":"find_in_resume","action_input":{"term":"Python"}}',
        '{"thought":"已完成","final_answer":"有"}',
    )

    run = run_react_loop(provider, tools, "q")

    kinds = [step.kind for step in run.steps]
    assert StepKind.THOUGHT in kinds
    assert StepKind.ACTION in kinds
    assert StepKind.OBSERVATION in kinds
    assert StepKind.FINAL in kinds


def test_prompt_lists_every_tool_and_forbids_invention(tools: ToolRegistry) -> None:
    prompt = build_react_prompt(tools, "question")

    for name in tools.names:
        assert name in prompt
    assert "Do not invent facts" in prompt


# --- the safety property that must survive tool use -----------------------------


def test_the_agent_cannot_assert_what_the_tools_never_returned(tools: ToolRegistry) -> None:
    """Tools must not become a laundering route for a fabricated fact."""

    provider = _scripted(
        '{"thought":"look","action":"find_in_resume","action_input":{"term":"Kubernetes"}}',
        '{"thought":"absent","final_answer":"The resume does not list Kubernetes."}',
    )

    run = run_react_loop(provider, tools, "Does the resume list Kubernetes?")

    observation = next(step.content for step in run.steps if step.kind is StepKind.OBSERVATION)
    assert "does not appear" in observation
    # The final answer is consistent with the evidence the tool actually produced.
    assert "does not list" in run.final_answer


def test_an_empty_registry_is_still_a_valid_agent() -> None:
    provider = _scripted('{"thought":"no tools","final_answer":"cannot answer"}')

    run = run_react_loop(provider, ToolRegistry([]), "q")

    assert run.final_answer == "cannot answer"


def test_dictionary_tool_reflects_the_loaded_dictionary() -> None:
    small = SkillDictionary(
        [entry for entry in DEFAULT_SKILL_DICTIONARY.entries if entry.canonical_name == "Python"]
    )
    registry = build_default_tools(small, SOURCE_LINES)

    assert "1 canonical skills" in registry.invoke("count_skills", {})
    assert len(registry) == 3
