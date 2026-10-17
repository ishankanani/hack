"""Structured outputs the AI models must return (validated with pydantic)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

CheckType = Literal[
    "equation_solutions", "expression_value", "simplify_equal", "derivative",
    "antiderivative", "definite_integral", "limit", "numeric", "none",
]


class Reading(BaseModel):
    """Step 4: what the vision model read from the photo."""
    is_math: bool = True
    readable: bool = True
    problems: list[str] = Field(default_factory=list)
    problem_text: str = ""
    problem_latex: str = ""
    confidence: float = 0.8

    @field_validator("problems")
    @classmethod
    def _trim(cls, v: list[str]) -> list[str]:
        return [p.strip() for p in v if p and p.strip()][:6]


class Step(BaseModel):
    say: str
    math: str = ""


class Check(BaseModel):
    type: CheckType = "none"
    expr: str = ""            # SymPy syntax
    variable: str = "x"
    values: list[str] = Field(default_factory=list)   # equation_solutions
    value: str = ""           # every other type: the answer to compare with
    lower: str = ""           # definite_integral
    upper: str = ""
    point: str = ""           # limit

    @field_validator("values", mode="before")
    @classmethod
    def _as_list(cls, v):
        if v is None:
            return []
        if isinstance(v, (str, int, float)):
            return [str(v)]
        return [str(x) for x in v]

    @field_validator("value", "lower", "upper", "point", "expr", mode="before")
    @classmethod
    def _as_str(cls, v):
        return "" if v is None else str(v)


class Solution(BaseModel):
    """Step 5: a full worked solution."""
    topic: str = "general"
    grade_level: str = ""
    difficulty: int = 2
    steps: list[Step] = Field(default_factory=list)
    final_answer: str = ""
    final_answer_latex: str = ""
    check: Check = Field(default_factory=Check)
    confidence: float = 0.8
    key_idea: str = ""        # the one idea to remember, shown in a highlighted note
    tip: str = ""             # a common mistake to avoid

    @field_validator("steps")
    @classmethod
    def _max_steps(cls, v: list[Step]) -> list[Step]:
        return v[:12]

    @field_validator("difficulty", mode="before")
    @classmethod
    def _difficulty(cls, v):
        try:
            return max(1, min(5, int(v)))
        except (TypeError, ValueError):
            return 2


VerifyStatus = Literal["verified", "agreed", "unchecked", "failed"]
