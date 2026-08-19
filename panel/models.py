"""Domain models for Panel.

Two invariants are enforced here rather than left to prompt wording, because
they are what separate a reliable scorecard from a plausible-sounding one:

1. A rubric is four behavioral anchors, not an adjective scale.
2. A numeric score must cite supporting evidence. No citation, no score.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, model_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InterviewType(str, Enum):
    BEHAVIORAL = "behavioral"
    TECHNICAL_VERBAL = "technical_verbal"
    MIXED = "mixed"


class Mode(str, Enum):
    """Who is being interviewed. Changes only the final rendering."""

    PRACTICE = "practice"
    SCREENING = "screening"


class Speaker(str, Enum):
    INTERVIEWER = "interviewer"
    CANDIDATE = "candidate"


class Decision(str, Enum):
    """What the conductor does after a candidate turn."""

    ASK = "ask"          # next planned question
    PROBE = "probe"      # dig into the current answer
    ADVANCE = "advance"  # this competency is covered, move on
    CLOSE = "close"      # interview over


class Polarity(str, Enum):
    SUPPORTS = "supports"
    UNDERMINES = "undermines"


# --------------------------------------------------------------------------
# Plan
# --------------------------------------------------------------------------

RUBRIC_LEVELS = 4
LEVEL_LABELS = {1: "Weak", 2: "Developing", 3: "Strong", 4: "Exceptional"}


class RubricLevel(BaseModel):
    """One behaviorally-anchored level.

    `descriptor` must describe observable behaviour in an answer, not a
    judgement of the person. "Names a specific decision they made and the
    tradeoff it cost" is an anchor. "Shows good judgement" is not.
    """

    level: int = Field(ge=1, le=RUBRIC_LEVELS)
    label: str
    descriptor: str = Field(min_length=10)


class Competency(BaseModel):
    id: str
    name: str
    definition: str
    rubric: list[RubricLevel]
    critical_points: list[str] = Field(
        default_factory=list,
        description="Concrete things a strong answer contains. Drives probing and scoring.",
    )
    weight: float = 1.0

    @model_validator(mode="after")
    def _check_rubric(self) -> Competency:
        levels = sorted(r.level for r in self.rubric)
        if levels != list(range(1, RUBRIC_LEVELS + 1)):
            raise ValueError(
                f"competency {self.id!r} needs exactly levels 1..{RUBRIC_LEVELS}, got {levels}"
            )
        return self

    def anchor(self, level: int) -> RubricLevel:
        return next(r for r in self.rubric if r.level == level)


class Question(BaseModel):
    id: str
    competency_id: str
    text: str
    intent: str = ""
    max_probes: int = Field(default=2, ge=0, le=4)


class InterviewPlan(BaseModel):
    """Compiled before the interview and frozen for its duration.

    The conductor may choose which question to ask and how deep to probe, but
    it can never change what is being assessed. That separation is what makes
    two runs of the same plan comparable.
    """

    id: str
    role: str
    interview_type: InterviewType
    competencies: list[Competency]
    questions: list[Question]
    target_minutes: int = 30
    source_note: str = ""
    created_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="after")
    def _check_refs(self) -> InterviewPlan:
        known = {c.id for c in self.competencies}
        for q in self.questions:
            if q.competency_id not in known:
                raise ValueError(
                    f"question {q.id!r} references unknown competency {q.competency_id!r}"
                )
        if not self.questions:
            raise ValueError("plan needs at least one question")
        return self

    @property
    def plan_hash(self) -> str:
        """Content hash of the criteria. Stamped onto every scorecard.

        Excludes id/created_at so the same criteria hash identically across runs.
        """
        payload = {
            "role": self.role,
            "interview_type": self.interview_type.value,
            "competencies": [
                c.model_dump(mode="json") for c in sorted(self.competencies, key=lambda c: c.id)
            ],
            "questions": [
                q.model_dump(mode="json") for q in sorted(self.questions, key=lambda q: q.id)
            ],
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def competency(self, cid: str) -> Competency:
        return next(c for c in self.competencies if c.id == cid)

    def questions_for(self, cid: str) -> list[Question]:
        return [q for q in self.questions if q.competency_id == cid]


# --------------------------------------------------------------------------
# Transcript
# --------------------------------------------------------------------------


class Turn(BaseModel):
    index: int
    speaker: Speaker
    text: str
    question_id: str | None = None
    competency_id: str | None = None
    is_probe: bool = False
    at: datetime = Field(default_factory=_utcnow)


class Transcript(BaseModel):
    turns: list[Turn] = Field(default_factory=list)

    def add(self, speaker: Speaker, text: str, **kw) -> Turn:
        turn = Turn(index=len(self.turns), speaker=speaker, text=text, **kw)
        self.turns.append(turn)
        return turn

    def get(self, index: int) -> Turn:
        return self.turns[index]

    def candidate_turns(self) -> list[Turn]:
        return [t for t in self.turns if t.speaker is Speaker.CANDIDATE]

    def answers_for(self, competency_id: str) -> list[Turn]:
        return [
            t
            for t in self.turns
            if t.speaker is Speaker.CANDIDATE and t.competency_id == competency_id
        ]

    def as_text(self) -> str:
        return "\n".join(f"[{t.index}] {t.speaker.value.upper()}: {t.text}" for t in self.turns)


# --------------------------------------------------------------------------
# Evidence and scoring
# --------------------------------------------------------------------------


class Evidence(BaseModel):
    """A claim tied to a specific place in the transcript.

    `quote` must be a span the candidate actually said. Verified against the
    transcript before it is allowed to influence a score.
    """

    competency_id: str
    turn_index: int
    quote: str
    claim: str
    polarity: Polarity = Polarity.SUPPORTS


class CompetencyScore(BaseModel):
    """`level is None` means NOT OBSERVED — the interview never got the evidence.

    That is a real, useful outcome and deliberately distinct from a low score.
    Collapsing the two is how AI scorecards end up confidently wrong.
    """

    competency_id: str
    level: int | None = Field(default=None, ge=1, le=RUBRIC_LEVELS)
    rationale: str = ""
    evidence: list[Evidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_citation(self) -> CompetencyScore:
        if self.level is not None:
            supporting = [e for e in self.evidence if e.polarity is Polarity.SUPPORTS]
            if not supporting:
                raise ValueError(
                    f"competency {self.competency_id!r} scored {self.level} with no "
                    "supporting evidence — every score must cite the transcript"
                )
        return self

    @property
    def observed(self) -> bool:
        return self.level is not None


class ScoredInterview(BaseModel):
    session_id: str
    plan_id: str
    plan_hash: str
    role: str
    mode: Mode
    scores: list[CompetencyScore]
    transcript: Transcript
    scored_at: datetime = Field(default_factory=_utcnow)

    @property
    def observed_scores(self) -> list[CompetencyScore]:
        return [s for s in self.scores if s.observed]

    @property
    def coverage(self) -> float:
        """Fraction of planned competencies that actually got evidence."""
        if not self.scores:
            return 0.0
        return len(self.observed_scores) / len(self.scores)

    def overall(self, plan: InterviewPlan) -> float | None:
        """Weighted mean over observed competencies only.

        Unobserved competencies are excluded rather than counted as zero —
        the interview failing to ask is not the candidate failing to answer.
        Coverage is reported separately so a thin interview is visible.
        """
        observed = self.observed_scores
        if not observed:
            return None
        total_w = sum(plan.competency(s.competency_id).weight for s in observed)
        if total_w == 0:
            return None
        weighted = sum(
            s.level * plan.competency(s.competency_id).weight  # type: ignore[operator]
            for s in observed
        )
        return round(weighted / total_w, 2)

    def score_for(self, competency_id: str) -> CompetencyScore | None:
        return next((s for s in self.scores if s.competency_id == competency_id), None)
