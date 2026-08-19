"""The reasoning interface the engine depends on.

Deliberately domain-level rather than a raw `complete(prompt) -> str` wrapper.
The conductor asks "was this answer substantive and what did it miss?", not
"here is a prompt". That keeps prompt engineering out of the state machine and
makes the keyless heuristic implementation a real peer of the LLM one rather
than a stub that has to be worked around.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from panel.models import Competency, Evidence, Turn


class AnswerAssessment(BaseModel):
    """What the engine learns from a single candidate answer.

    Evidence is produced here, during the interview, rather than re-derived
    afterwards — the answer is already being read to decide whether to probe.
    """

    is_substantive: bool = Field(
        description="False for non-answers: deflections, 'I don't know', or pure generality."
    )
    covered_points: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    probe_question: str | None = Field(
        default=None,
        description="A follow-up targeting the most valuable missing point, or None if covered.",
    )


class ScoreVerdict(BaseModel):
    level: int | None = Field(
        default=None, description="1-4, or None when the evidence does not support any level."
    )
    rationale: str = ""


class CoachingNote(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    stronger_answer: str = ""
    drill: str = ""


class Reasoner(Protocol):
    """Everything the engine needs a judgement call for."""

    name: str

    def draft_questions(
        self, *, role: str, context: str, competency: Competency, n: int
    ) -> list[str]:
        """Role-specific questions for a competency. Falls back to the bank."""
        ...

    def assess_answer(
        self, *, competency: Competency, question: str, answer: Turn
    ) -> AnswerAssessment:
        ...

    def score(
        self, *, competency: Competency, evidence: list[Evidence], answers: list[Turn]
    ) -> ScoreVerdict:
        ...

    def coach(
        self, *, competency: Competency, level: int | None, answers: list[Turn]
    ) -> CoachingNote:
        ...
