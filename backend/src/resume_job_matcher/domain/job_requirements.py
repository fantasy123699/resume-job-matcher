from typing import Literal

from pydantic import BaseModel, Field


class TechnologyRequirementValue(BaseModel):
    kind: Literal["technology_requirement"] = "technology_requirement"
    name: str = Field(min_length=1, max_length=100)
