from typing import Literal

from pydantic import BaseModel, Field


class SectionFactValue(BaseModel):
    """The first parser stores source-backed sections, not inferred claims."""

    kind: Literal["section"] = "section"
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=100_000)


class SkillFactValue(BaseModel):
    """A technology explicitly named in the user's skills section."""

    kind: Literal["skill"] = "skill"
    name: str = Field(min_length=1, max_length=100)


type FactValue = SectionFactValue | SkillFactValue


def parse_fact_value(value: dict[str, str]) -> FactValue:
    if value.get("kind") == "skill":
        return SkillFactValue.model_validate(value)
    return SectionFactValue.model_validate(value)
