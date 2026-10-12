"""A minimal ReAct loop over the provider port.

Why this exists
---------------
The extraction service asks the model exactly one question and validates the answer.
That is safe but passive: the model cannot choose to look anything up. A ReAct loop
(Reason + Act) lets the model decide which tool to call, observe the result, and
iterate — which is the smallest honest form of "task planning, tool calling, memory
management" that the role descriptions ask for.

The safety contract is not relaxed. Every tool observation is returned to the model
as data, the loop is bounded by a step ceiling, and the guard still runs over the
final answer, so a model that calls tools cannot use them to smuggle in a fact that
is not in the source.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from resume_job_matcher.domain.llm import (
    LlmExtractionRequest,
    LlmProvider,
    LlmProviderError,
)

MAX_STEPS_CEILING = 12


class StepKind(StrEnum):
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"
    FINAL = "final"


@dataclass(frozen=True)
class AgentStep:
    """One turn of the loop, retained so a run can be explained after the fact."""

    index: int
    kind: StepKind
    tool_name: str | None = None
    tool_input: dict[str, object] | None = None
    content: str = ""


@dataclass
class AgentRun:
    """The full transcript plus the stopping reason."""

    steps: list[AgentStep] = field(default_factory=list)
    final_answer: str = ""
    stopped_reason: str = "incomplete"

    @property
    def tools_used(self) -> list[str]:
        return [step.tool_name for step in self.steps if step.tool_name]


@dataclass(frozen=True)
class Tool:
    """A capability the model may choose to invoke."""

    name: str
    description: str
    handler: Callable[[dict[str, object]], str]

    def describe(self) -> str:
        return f"- {self.name}: {self.description}"


class ToolRegistry:
    """Names the model is allowed to call. Anything else is rejected, not guessed."""

    def __init__(self, tools: Sequence[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def __len__(self) -> int:
        return len(self._tools)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def describe(self) -> str:
        return "\n".join(tool.describe() for tool in self._tools.values())

    def invoke(self, name: str, payload: dict[str, object]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: unknown tool '{name}'. Available: {', '.join(self._tools)}"
        try:
            return tool.handler(payload)
        except Exception as exc:  # a failing tool is an observation, not a crash
            return f"Error: tool '{name}' failed: {type(exc).__name__}: {exc}"


def build_react_prompt(tools: ToolRegistry, question: str) -> str:
    """The whole protocol in one place, so behaviour is easy to reason about."""

    return f"""You are an agent that answers questions about a resume using tools.

Available tools:
{tools.describe()}

Respond with exactly one JSON object per turn, and nothing else.

To call a tool:
{{"thought": "why you need this", "action": "tool_name", "action_input": {{...}}}}

To finish:
{{"thought": "why you are done", "final_answer": "your answer"}}

Rules:
- Call at most one tool per turn.
- Base your final answer only on tool observations. Do not invent facts.
- If the tools cannot answer the question, say so in final_answer.

Question: {question}"""


def _parse_turn(raw: str) -> dict[str, object] | None:
    """Read one JSON object out of a completion that may carry prose or fences."""

    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def run_react_loop(
    provider: LlmProvider,
    tools: ToolRegistry,
    question: str,
    *,
    max_steps: int = 6,
    max_output_tokens: int = 1024,
) -> AgentRun:
    """Alternate model reasoning and tool execution until an answer or a ceiling.

    The loop never raises for provider faults or malformed turns: a broken turn is
    recorded as an observation and the model gets another chance, up to ``max_steps``.
    """

    if max_steps < 1 or max_steps > MAX_STEPS_CEILING:
        raise ValueError(f"max_steps must be between 1 and {MAX_STEPS_CEILING}")

    run = AgentRun()
    # Memory: the running transcript is fed back on every turn, which is what lets
    # the model build on its own earlier observations.
    transcript: list[str] = []
    system_prompt = build_react_prompt(tools, question)

    for index in range(max_steps):
        request = LlmExtractionRequest(
            system_prompt=system_prompt,
            user_prompt="\n".join(transcript) if transcript else "Begin.",
            max_output_tokens=max_output_tokens,
        )
        try:
            completion = _complete(provider, request)
        except LlmProviderError as exc:
            run.stopped_reason = f"provider_error:{type(exc).__name__}"
            return run

        turn = _parse_turn(completion.text)
        if turn is None:
            run.steps.append(
                AgentStep(index=index, kind=StepKind.OBSERVATION, content="unparseable turn")
            )
            transcript.append(
                "Observation: your last reply was not valid JSON. "
                'Reply with {"thought":...,"action":...} or {"thought":...,"final_answer":...}.'
            )
            continue

        thought = str(turn.get("thought", ""))
        if thought:
            run.steps.append(AgentStep(index=index, kind=StepKind.THOUGHT, content=thought))

        final_answer = turn.get("final_answer")
        if isinstance(final_answer, str) and final_answer.strip():
            run.steps.append(
                AgentStep(index=index, kind=StepKind.FINAL, content=final_answer.strip())
            )
            run.final_answer = final_answer.strip()
            run.stopped_reason = "answered"
            return run

        action = turn.get("action")
        if not isinstance(action, str) or not action.strip():
            transcript.append('Observation: reply must contain either "action" or "final_answer".')
            continue

        raw_input = turn.get("action_input")
        tool_input = raw_input if isinstance(raw_input, dict) else {}
        observation = tools.invoke(action.strip(), tool_input)

        run.steps.append(
            AgentStep(
                index=index,
                kind=StepKind.ACTION,
                tool_name=action.strip(),
                tool_input=tool_input,
                content=observation,
            )
        )
        run.steps.append(AgentStep(index=index, kind=StepKind.OBSERVATION, content=observation))
        transcript.append(
            f"You called {action.strip()} with {json.dumps(tool_input, ensure_ascii=False)}.\n"
            f"Observation: {observation}"
        )

    run.stopped_reason = "max_steps_reached"
    return run


def _complete(provider: LlmProvider, request: LlmExtractionRequest):
    """Bridge the sync loop to the async provider port."""

    import asyncio
    import concurrent.futures

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(provider.complete(request))

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, provider.complete(request)).result()
