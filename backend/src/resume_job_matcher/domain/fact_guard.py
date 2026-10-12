"""The fact guard: a deterministic refuse-to-trust layer over model output.

Why this module exists
----------------------
Resume extraction is open-domain, so a model is the only realistic recall mechanism.
But a model that invents a skill is worse than no model at all: the product promise
is "we never add a fact you did not write". Prompt instructions cannot deliver that
promise, because they are advisory.

So the guard enforces the promise in code. Every model-proposed fact must carry a
verbatim quote from the source. If the quote is not literally present, the fact is
dropped. Model self-confidence is deliberately ignored: a hallucinated quote is
usually fluent and confident, so confidence is not evidence.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, ValidationError


class RejectionReason(StrEnum):
    """Why a proposed fact never reached the database."""

    MALFORMED_JSON = "malformed_json"
    SCHEMA_MISMATCH = "schema_mismatch"
    UNKNOWN_CATEGORY = "unknown_category"
    EMPTY_STATEMENT = "empty_statement"
    MISSING_QUOTE = "missing_quote"
    QUOTE_NOT_FOUND = "quote_not_found"
    STATEMENT_NOT_GROUNDED = "statement_not_grounded"
    DUPLICATE = "duplicate"


class ProposedFact(BaseModel):
    """One fact as the model claims it, before the guard inspects it."""

    category: str = Field(min_length=1, max_length=40)
    statement: str = Field(min_length=1, max_length=500)
    quote: str = Field(min_length=1, max_length=1000)
    source_ref: str | None = Field(default=None, max_length=64)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class AcceptedFact(BaseModel):
    """A fact that survived the guard and is therefore safe to persist."""

    category: str
    statement: str
    quote: str
    source_ref: str


@dataclass(frozen=True)
class RejectedFact:
    """A dropped proposal, kept for logging and for the model-quality report."""

    category: str
    statement: str
    reason: RejectionReason


@dataclass(frozen=True)
class GuardOutcome:
    accepted: list[AcceptedFact]
    rejected: list[RejectedFact]

    @property
    def acceptance_rate(self) -> float:
        total = len(self.accepted) + len(self.rejected)
        return len(self.accepted) / total if total else 0.0


# Categories the rest of the system understands. An unrecognised category is
# rejected rather than stored, so downstream queries never meet an unknown type.
ALLOWED_CATEGORIES: frozenset[str] = frozenset(
    {
        "skill",
        "experience",
        "project",
        "education",
        "achievement",
        "certificate",
    }
)


def normalize_for_matching(text: str) -> str:
    """Collapse whitespace and unify quote/punctuation variants before comparison.

    PDF and DOCX extraction routinely yield full-width punctuation, non-breaking
    spaces and hyphen variants that are visually identical to the plain forms. A
    strict byte comparison would reject legitimate quotes, so the comparison is
    done on a normalized projection while the *stored* quote stays verbatim.

    All punctuation is mapped to a space rather than to its ASCII twin. Mapping
    ``，`` to ``,`` would make ``"Python，掌握"`` normalize to ``"python,掌握"``,
    which is not a substring of a source that spaces its punctuation differently.
    Padding punctuation removes that asymmetry.
    """

    translation = str.maketrans(
        {
            "\u00a0": " ",
            "\u3000": " ",
            "\u2018": "'",
            "\u2019": "'",
            "\u201c": '"',
            "\u201d": '"',
            "\uff08": " ",
            "\uff09": " ",
            "\uff0c": " ",
            "\u3001": " ",
            "\uff1a": " ",
            "\uff1b": " ",
            "\uff01": " ",
            "\uff1f": " ",
            "\u2014": " ",
            "\u2013": " ",
            "\u2212": " ",
            ",": " ",
            ";": " ",
            ":": " ",
            "-": " ",
            "/": " ",
            "\\": " ",
            "|": " ",
        }
    )
    return " ".join(text.translate(translation).split()).casefold()


def _extract_json_array(raw: str) -> list[Any]:
    """Read a JSON array from model output that may be wrapped in prose or fences."""

    import json

    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON array found in model output")

    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, list):
        raise ValueError("model output is not a JSON array")
    return parsed


def statement_is_grounded(statement: str, quote: str) -> bool:
    """Check that a statement does not assert more than its quote supports.

    Two independent ways a statement can outrun its quote:

    1. **Invented quantities.** A number, percentage or duration in the statement that
       does not appear in the quote is unverifiable, so it is refused. This catches
       "熟悉 Python" -> "拥有 5 年 Python 经验" and "了解 Docker" -> "部署 200 个服务".
       Numbers are compared as normalized tokens so "5年" and "5 年" agree.

    2. **Upgraded proficiency verbs.** Chinese resumes grade proficiency, and the
       ladder is meaningful: 了解 < 熟悉 < 熟练 < 精通. A statement may not claim a
       higher rung than its quote, which catches "了解 Docker 基础" -> "精通 Docker".
    """

    normalized_statement = normalize_for_matching(statement)
    normalized_quote = normalize_for_matching(quote)

    # (1) every quantity asserted must be present in the quote
    for token in _quantity_tokens(normalized_statement):
        if token not in _quantity_tokens(normalized_quote):
            return False

    # (2) the claimed proficiency may not exceed the quoted proficiency
    asserted_level = _proficiency_level(normalized_statement)
    quoted_level = _proficiency_level(normalized_quote)
    if asserted_level > quoted_level:
        return False

    return True


_QUANTITY_PATTERN = re.compile(r"\d+(?:\.\d+)?")


def _quantity_tokens(normalized_text: str) -> set[str]:
    return set(_QUANTITY_PATTERN.findall(normalized_text))


# Ordered weakest to strongest. A statement may not claim a rung above its quote.
_PROFICIENCY_LADDER: tuple[tuple[str, ...], ...] = (
    ("了解", "知道", "接触过", "听说过"),
    ("熟悉", "会用", "使用过", "掌握基础"),
    ("熟练", "熟练使用", "熟练运用", "能够独立"),
    ("精通", "深入了解", "深入掌握", "专家"),
)


def _proficiency_level(normalized_text: str) -> int:
    """Highest rung the text claims; 0 when it makes no proficiency claim."""

    level = 0
    for index, markers in enumerate(_PROFICIENCY_LADDER, start=1):
        if any(marker in normalized_text for marker in markers):
            level = index
    return level


def guard_facts(raw_completion: str, source_lines: dict[str, str]) -> GuardOutcome:
    """Keep only proposals whose quote is verifiably present in the source.

    ``source_lines`` maps a source reference (for example ``page:1,line:12``) to the
    text of that line. A quote is accepted when it appears in the line named by
    ``source_ref``; when the model omits or invents a reference, the quote is
    searched across all lines, and the guard records the line that actually matched.
    """

    accepted: list[AcceptedFact] = []
    rejected: list[RejectedFact] = []

    try:
        candidates = _extract_json_array(raw_completion)
    except ValueError:
        return GuardOutcome(
            accepted=[],
            rejected=[
                RejectedFact("<document>", raw_completion[:80], RejectionReason.MALFORMED_JSON)
            ],
        )

    normalized_sources = {ref: normalize_for_matching(text) for ref, text in source_lines.items()}
    seen: set[tuple[str, str]] = set()

    for candidate in candidates:
        try:
            proposal = ProposedFact.model_validate(candidate)
        except ValidationError:
            label = candidate.get("category", "?") if isinstance(candidate, dict) else "?"
            rejected.append(RejectedFact(str(label), "", RejectionReason.SCHEMA_MISMATCH))
            continue

        category = proposal.category.strip().casefold()
        if category not in ALLOWED_CATEGORIES:
            rejected.append(
                RejectedFact(category, proposal.statement, RejectionReason.UNKNOWN_CATEGORY)
            )
            continue

        statement = proposal.statement.strip()
        if not statement:
            rejected.append(RejectedFact(category, statement, RejectionReason.EMPTY_STATEMENT))
            continue

        quote = proposal.quote.strip()
        if not quote:
            rejected.append(RejectedFact(category, statement, RejectionReason.MISSING_QUOTE))
            continue

        normalized_quote = normalize_for_matching(quote)
        resolved_ref: str | None = None

        if proposal.source_ref is not None:
            declared = normalized_sources.get(proposal.source_ref)
            if declared is not None and normalized_quote in declared:
                resolved_ref = proposal.source_ref
            # An unknown or wrong reference is not a rejection on its own: the quote
            # is the evidence, so fall through to the full scan below.

        if resolved_ref is None:
            for ref, normalized_source in normalized_sources.items():
                if normalized_quote in normalized_source:
                    resolved_ref = ref
                    break

        if resolved_ref is None:
            rejected.append(RejectedFact(category, statement, RejectionReason.QUOTE_NOT_FOUND))
            continue

        # A real quote is necessary but not sufficient. Without this check a model can
        # pair a genuine quote with a statement the quote does not support - the exact
        # embellishment the product exists to prevent:
        #   quote "了解 Docker 基础"  ->  statement "精通 Docker"
        #   quote "熟悉 Python"       ->  statement "拥有 5 年架构经验"
        # So the statement is required to be grounded in its own quote.
        if not statement_is_grounded(statement, quote):
            rejected.append(
                RejectedFact(category, statement, RejectionReason.STATEMENT_NOT_GROUNDED)
            )
            continue

        dedupe_key = (category, normalize_for_matching(statement))
        if dedupe_key in seen:
            rejected.append(RejectedFact(category, statement, RejectionReason.DUPLICATE))
            continue

        seen.add(dedupe_key)
        accepted.append(
            AcceptedFact(
                category=category,
                statement=statement,
                quote=quote,
                source_ref=resolved_ref,
            )
        )

    return GuardOutcome(accepted=accepted, rejected=rejected)
