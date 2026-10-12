"""Parse job descriptions into source-backed, classified technology requirements.

Classification is section-aware and clause-level:

- A section header on its own line sets the default necessity for the lines that
  follow it, so ``加分项`` followed by a bare requirement list is still treated
  as preferred rather than mandatory.
- Each clause is evaluated separately, so one comma-separated line can contain
  both mandatory and preferred items.
- Clauses under a benefits section (``我们提供``) do not produce requirements at
  all, because mentioning a technology there does not mean the job requires it.
"""

from dataclasses import dataclass

from resume_job_matcher.domain.job_requirements import TechnologyRequirementValue
from resume_job_matcher.domain.requirement_patterns import (
    ClauseCategory,
    Necessity,
    classify_clause,
    detect_section,
    split_clauses,
)
from resume_job_matcher.domain.skill_dictionary import SkillDictionary
from resume_job_matcher.domain.technologies import find_technology_mentions

PARSER_VERSION = "deterministic-job-requirements-v2"


@dataclass(frozen=True)
class ParsedRequirement:
    requirement_type: str
    value: TechnologyRequirementValue
    source_text: str
    source_location: str
    category: ClauseCategory = "skill"


def parse_job_requirements(
    content: str, dictionary: SkillDictionary | None = None
) -> list[ParsedRequirement]:
    requirements: list[ParsedRequirement] = []
    seen: set[str] = set()
    section_necessity: Necessity | None = "required"

    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        section = detect_section(line)
        if section is not None:
            section_necessity = section.necessity
            line = section.remainder
            if not line:
                continue
        for clause in split_clauses(line):
            classification = classify_clause(clause, section_necessity)
            if not classification.is_requirement:
                continue
            for mention in find_technology_mentions(clause, dictionary):
                if mention.name in seen:
                    continue
                seen.add(mention.name)
                requirements.append(
                    ParsedRequirement(
                        requirement_type=classification.necessity,
                        value=TechnologyRequirementValue(name=mention.name),
                        source_text=clause,
                        source_location=f"line:{line_number}",
                        category=classification.category,
                    )
                )
    return requirements
