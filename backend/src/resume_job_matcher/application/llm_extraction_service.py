"""Model-backed resume fact extraction, bounded by the deterministic fact guard.

Design rule: the model proposes, the guard disposes. This module never persists a
fact the guard rejected, and it degrades to the deterministic parser whenever the
provider is unconfigured, slow, or wrong — model availability must never be a hard
dependency of importing a resume.
"""

from dataclasses import dataclass, field

from resume_job_matcher.domain.fact_guard import GuardOutcome, guard_facts
from resume_job_matcher.domain.llm import (
    LlmExtractionRequest,
    LlmProvider,
    LlmProviderError,
)
from resume_job_matcher.domain.skill_dictionary import SkillDictionary

# Explicit output contract. Kept short and boring on purpose: long instructions
# invite the model to editorialise, and every extra word is a chance to invent.
SYSTEM_PROMPT = """You extract facts from a resume. You are a transcription aid, not a writer.

Rules:
1. Only report facts that are explicitly written in the source lines.
2. Every fact MUST include a "quote" copied verbatim from one source line.
   Copy the characters exactly as they appear. Do not translate, summarise, fix
   spelling, or merge two lines into one quote.
3. Never infer. If the source says "熟悉 Python" do not output "3 years of Python".
4. If nothing is extractable, return an empty JSON array.

Allowed "category" values: skill, experience, project, education, achievement, certificate.

Return ONLY a JSON array, with no prose and no markdown fences:
[{"category":"skill","statement":"熟悉 Python",
  "quote":"熟悉 Python","source_ref":"line:3","confidence":0.9}]

"source_ref" must be one of the reference labels shown in the source lines.
"confidence" is your own 0-1 estimate and is recorded but not trusted."""


@dataclass
class ExtractionOutcome:
    """Everything the caller needs to persist accepted facts and explain the rest."""

    accepted: list = field(default_factory=list)
    guard: GuardOutcome | None = None
    used_model: bool = False
    model_name: str = ""
    degraded_reason: str | None = None


def build_source_lines(lines: list[tuple[str, str]]) -> dict[str, str]:
    """Map ``(source_ref, text)`` pairs to the lookup the guard expects."""

    return {ref: text for ref, text in lines}


def build_user_prompt(lines: list[tuple[str, str]]) -> str:
    """Render numbered source lines so the model can cite a reference label."""

    rendered = "\n".join(f"[{ref}] {text}" for ref, text in lines)
    return f"Resume source lines:\n{rendered}\n\nExtract the facts as a JSON array."


def extract_facts_with_guard(
    provider: LlmProvider,
    lines: list[tuple[str, str]],
    *,
    max_output_tokens: int = 2048,
    dictionary: SkillDictionary | None = None,
) -> ExtractionOutcome:
    """Run one extraction pass. Never raises for provider faults.

    The deterministic dictionary runs first and seeds the accepted set, so a model
    outage or an empty completion still yields the skill facts the parser can prove.
    Model output is additive and must clear the guard to survive.
    """

    from resume_job_matcher.application.resume_import_service import extract_skill_facts

    source_map = build_source_lines(lines)
    accepted: list = []

    # Deterministic baseline: these facts are provable without a model.
    seen_quotes: set[tuple[str, str]] = set()
    for ref, text in lines:
        for parsed in extract_skill_facts(text, ref, dictionary):
            key = (parsed.fact_type, parsed.source_text)
            if key in seen_quotes:
                continue
            seen_quotes.add(key)
            accepted.append(parsed)

    if not provider.is_configured:
        return ExtractionOutcome(
            accepted=accepted,
            guard=GuardOutcome(accepted=[], rejected=[]),
            used_model=False,
            degraded_reason="provider_not_configured",
        )

    request = LlmExtractionRequest(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_user_prompt(lines),
        max_output_tokens=max_output_tokens,
    )

    try:
        completion = _run_provider(provider, request)
    except LlmProviderError as exc:
        return ExtractionOutcome(
            accepted=accepted,
            guard=GuardOutcome(accepted=[], rejected=[]),
            used_model=False,
            degraded_reason=f"provider_error:{type(exc).__name__}",
        )

    outcome = guard_facts(completion.text, source_map)
    return ExtractionOutcome(
        accepted=accepted,
        guard=outcome,
        used_model=True,
        model_name=completion.model,
    )


def _run_provider(provider: LlmProvider, request: LlmExtractionRequest):
    """Bridge sync callers to the async provider port."""

    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(provider.complete(request))

    # Already inside a loop (FastAPI): run in a worker thread to avoid nesting.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, provider.complete(request)).result()
