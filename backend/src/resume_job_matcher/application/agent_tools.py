"""Tools the agent may call, backed by real project data.

Each tool answers from the skill dictionary or from the resume source lines actually
supplied for the run — no tool fabricates an answer, and every tool returns a string
that names its own evidence so the model can quote it instead of paraphrasing.
"""

from collections.abc import Sequence

from resume_job_matcher.domain.react_agent import Tool, ToolRegistry
from resume_job_matcher.domain.skill_dictionary import SkillDictionary


def build_default_tools(
    dictionary: SkillDictionary,
    source_lines: Sequence[tuple[str, str]],
) -> ToolRegistry:
    """Assemble the standard toolset for a resume question."""

    def lookup_skill(payload: dict[str, object]) -> str:
        query = str(payload.get("query", "")).strip()
        if not query:
            return "Error: 'query' is required."
        lowered = query.casefold()
        matches = [
            entry.canonical_name
            for entry in dictionary.entries
            if lowered in entry.canonical_name.casefold()
            or any(lowered in alias.casefold() for alias in entry.aliases)
        ]
        if not matches:
            return f"No canonical skill matches '{query}'. It is not in the dictionary."
        categories = {name: dictionary.category_of(name) for name in matches[:20]}
        return f"Canonical skills matching '{query}': {categories}"

    def find_in_resume(payload: dict[str, object]) -> str:
        term = str(payload.get("term", "")).strip()
        if not term:
            return "Error: 'term' is required."
        lowered = term.casefold()
        hits = [f"[{ref}] {text}" for ref, text in source_lines if lowered in text.casefold()]
        if not hits:
            return f"'{term}' does not appear anywhere in the resume source."
        return "Matching source lines:\n" + "\n".join(hits)

    def count_skills(_payload: dict[str, object]) -> str:
        names = dictionary.canonical_names
        return f"The dictionary holds {len(names)} canonical skills."

    return ToolRegistry(
        [
            Tool(
                name="lookup_skill",
                description=(
                    "Look up whether a technology is a canonical skill, by name or alias. "
                    'Input: {"query": "spring"}'
                ),
                handler=lookup_skill,
            ),
            Tool(
                name="find_in_resume",
                description=(
                    "Find resume source lines containing a term. This is the only tool "
                    'that proves what the resume says. Input: {"term": "Python"}'
                ),
                handler=find_in_resume,
            ),
            Tool(
                name="count_skills",
                description="Report how many canonical skills the dictionary holds.",
                handler=count_skills,
            ),
        ]
    )
