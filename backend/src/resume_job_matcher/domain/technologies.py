"""Technology detection over a skill dictionary.

Kept as a thin, backwards-compatible facade over
:mod:`resume_job_matcher.domain.skill_dictionary` so existing callers keep the
``find_technology_mentions`` entry point while the dictionary itself becomes
data that can be extended without a code change.
"""

from dataclasses import dataclass

from resume_job_matcher.domain.skill_dictionary import (
    DEFAULT_SKILL_DICTIONARY,
    SkillDictionary,
)


@dataclass(frozen=True)
class TechnologyMention:
    name: str
    source_text: str
    category: str = ""


def find_technology_mentions(
    text: str, dictionary: SkillDictionary | None = None
) -> list[TechnologyMention]:
    """Return one mention per canonical skill, in order of first appearance."""

    active_dictionary = dictionary if dictionary is not None else DEFAULT_SKILL_DICTIONARY
    return [
        TechnologyMention(
            name=mention.name,
            source_text=mention.source_text,
            category=mention.category,
        )
        for mention in active_dictionary.find_mentions(text)
    ]
