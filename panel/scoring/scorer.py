"""Post-interview scoring.

Scoring is separate from conducting on purpose. During the interview the engine
is optimising for a good conversation; here it is optimising for a defensible
judgement, with the whole transcript available and no latency pressure.

One rule is enforced structurally rather than requested politely: a competency
with no supporting evidence cannot receive a number. If the reasoner returns one
anyway, it is discarded and the competency is recorded as not observed.
"""

from __future__ import annotations

from panel.llm.base import Reasoner
from panel.models import (
    CompetencyScore,
    Evidence,
    InterviewPlan,
    Mode,
    Polarity,
    ScoredInterview,
    Transcript,
)


def score_interview(
    *,
    plan: InterviewPlan,
    transcript: Transcript,
    evidence: list[Evidence],
    reasoner: Reasoner,
    mode: Mode = Mode.PRACTICE,
    session_id: str = "session",
) -> ScoredInterview:
    scores: list[CompetencyScore] = []

    for competency in plan.competencies:
        relevant = [e for e in evidence if e.competency_id == competency.id]
        supporting = [e for e in relevant if e.polarity is Polarity.SUPPORTS]
        answers = transcript.answers_for(competency.id)

        if not supporting:
            scores.append(
                CompetencyScore(
                    competency_id=competency.id,
                    level=None,
                    rationale=(
                        "Not observed — the interview did not surface evidence for this "
                        "competency."
                    ),
                    evidence=relevant,
                )
            )
            continue

        verdict = reasoner.score(competency=competency, evidence=relevant, answers=answers)
        scores.append(
            CompetencyScore(
                competency_id=competency.id,
                level=verdict.level,
                rationale=verdict.rationale,
                evidence=relevant,
            )
        )

    return ScoredInterview(
        session_id=session_id,
        plan_id=plan.id,
        plan_hash=plan.plan_hash,
        role=plan.role,
        mode=mode,
        scores=scores,
        transcript=transcript,
    )
