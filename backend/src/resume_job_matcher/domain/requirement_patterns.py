"""Clause-level classification of Chinese and English job-description text.

The previous implementation decided ``required`` vs ``bonus`` by scanning a
whole line for four substrings, which misclassifies the very common layout
where the section header sits on its own line::

    加分项
    1. 熟悉 Kubernetes

Here no bonus marker appears on the requirement line, so the requirement was
reported as mandatory. This module tracks the active section so clauses inherit
its necessity, and evaluates markers per clause so a single comma-separated line
can carry both mandatory and preferred items.
"""

import re
from dataclasses import dataclass
from typing import Literal

Necessity = Literal["required", "bonus"]
ClauseCategory = Literal[
    "skill",
    "experience",
    "education",
    "soft_skill",
    "responsibility",
    "benefits",
]

CLAUSE_SPLIT_PATTERN = re.compile(r"[。；;，,\n]+")

SECTION_PATTERNS: tuple[tuple[re.Pattern[str], ClauseCategory, Necessity | None], ...] = (
    (
        re.compile(
            r"加分项|优先条件|以下条件优先|加分条件|nice\s+to\s+have|preferred\s+qualifications"
        ),
        "skill",
        "bonus",
    ),
    (
        re.compile(
            r"任职要求|职位要求|岗位要求|任职资格|任职条件|岗位需求|职位需求"
            r"|requirements?|qualifications?"
        ),
        "skill",
        "required",
    ),
    (
        re.compile(
            r"岗位职责|工作职责|职位描述|工作内容|主要职责|职位职责"
            r"|responsibilit|what\s+you\s+will\s+do|job\s+description"
        ),
        "responsibility",
        "required",
    ),
    (
        re.compile(r"我们提供|福利待遇|薪酬福利|薪资待遇|benefits|we\s+offer|perks"),
        "benefits",
        None,
    ),
)

_BONUS_MARKER = re.compile(
    r"加分|优先|更佳|为佳|尤佳|从优"
    r"|\bbonus\b|\bplus\b|\bpreferred\b|\bnice\s+to\s+have\b|\bis\s+a\s+plus\b",
    re.IGNORECASE,
)

_REQUIRED_MARKER = re.compile(
    r"熟悉|掌握|精通|了解|理解|会用|会用|具备|具有|要求|必须|至少|需具备|需要"
    r"|\bproficien|\bfamiliar\b|\bexperience\s+with\b|\bknowledge\s+of\b"
    r"|\brequired\b|\bmust\s+have\b|\bexpertise\b",
    re.IGNORECASE,
)

_CATEGORY_PATTERNS: tuple[tuple[re.Pattern[str], ClauseCategory], ...] = (
    (
        re.compile(
            r"本科|硕士|博士|专科|研究生|学历|统招|全日制|应届|在校"
            r"|985|211|双一流|\bdegree\b|\bbachelor\b|\bmaster\b|\bphd\b"
        ),
        "education",
    ),
    (
        re.compile(
            r"\d+\s*年(以上|及以上)?|工作年限|实习经历|项目经验"
            r"|\byears?\s+of\s+experience\b"
        ),
        "experience",
    ),
    (
        re.compile(
            r"沟通|团队|协作|学习能力|责任心|抗压|表达|自驱|主动性|沟通能力"
            r"|\bcommunication\b|\bteamwork\b|\bself-motivated\b"
        ),
        "soft_skill",
    ),
)


@dataclass(frozen=True)
class SectionSignal:
    """A section header detected at the start of a line."""

    category: ClauseCategory
    necessity: Necessity | None
    header: str
    remainder: str


@dataclass(frozen=True)
class ClauseClassification:
    """How one clause of a job description should be treated."""

    necessity: Necessity
    category: ClauseCategory
    matched_marker: str | None
    is_requirement: bool


def detect_section(line: str) -> SectionSignal | None:
    """Detect a section header, including headers sharing a line with content."""

    stripped = line.strip()
    if not stripped:
        return None
    for pattern, category, necessity in SECTION_PATTERNS:
        match = pattern.search(stripped)
        if match is None:
            continue
        # A header only counts near the beginning of the line; otherwise we are
        # inside prose that merely mentions the words.
        if match.start() > 12:
            continue
        remainder = stripped[match.end() :].lstrip("：: 　-—·")
        return SectionSignal(
            category=category,
            necessity=necessity,
            header=match.group(0),
            remainder=remainder,
        )
    return None


def split_clauses(text: str) -> list[str]:
    return [clause.strip() for clause in CLAUSE_SPLIT_PATTERN.split(text) if clause.strip()]


def classify_clause(
    clause: str, section_necessity: Necessity | None = "required"
) -> ClauseClassification:
    """Classify one clause, with explicit markers overriding the section default."""

    necessity: Necessity = section_necessity or "required"
    matched_marker: str | None = None

    # "优先" is more specific than "熟悉", so an explicit bonus marker wins.
    bonus_match = _BONUS_MARKER.search(clause)
    if bonus_match is not None:
        necessity = "bonus"
        matched_marker = bonus_match.group(0)
    else:
        required_match = _REQUIRED_MARKER.search(clause)
        if required_match is not None:
            matched_marker = required_match.group(0)

    category: ClauseCategory = "skill"
    for pattern, candidate in _CATEGORY_PATTERNS:
        if pattern.search(clause):
            category = candidate
            break

    return ClauseClassification(
        necessity=necessity,
        category=category,
        matched_marker=matched_marker,
        is_requirement=section_necessity is not None,
    )
