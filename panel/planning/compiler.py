"""Compile an interview plan, then freeze it.

Everything the interview will assess is decided here, before a single question
is asked. The conductor may choose which planned question to ask and how deep to
probe, but it cannot add a competency or rewrite an anchor mid-interview.

That constraint is the point. Two candidates run against the same plan hash were
assessed against identical criteria, which is what makes their scores
comparable — and what makes a scorecard auditable after the fact.
"""

from __future__ import annotations

import uuid

from panel.llm.base import Reasoner
from panel.models import Competency, InterviewPlan, InterviewType, Question
from panel.planning.library import QUESTION_BANK, competencies_for

# Enough to reach level 3-4 on a competency without the interview stalling on it.
QUESTIONS_PER_COMPETENCY = 2


def compile_plan(
    *,
    role: str,
    interview_type: InterviewType = InterviewType.MIXED,
    resume: str = "",
    job_description: str = "",
    target_minutes: int = 30,
    reasoner: Reasoner | None = None,
    competencies: list[Competency] | None = None,
) -> InterviewPlan:
    """Build a frozen plan.

    With a reasoner, questions are drafted against the actual resume and JD.
    Without one, the vetted question bank is used. The rubric is identical
    either way — only the questions become role-specific, because the rubric is
    what has to stay stable for scores to mean anything.
    """
    comps = competencies or competencies_for(interview_type)
    context = _context(resume, job_description)

    questions: list[Question] = []
    for comp in comps:
        texts = _questions_for(comp, role, context, reasoner)
        for i, text in enumerate(texts):
            questions.append(
                Question(
                    id=f"{comp.id}-{i + 1}",
                    competency_id=comp.id,
                    text=text,
                    intent=f"Surface evidence for {comp.name}",
                )
            )

    return InterviewPlan(
        id=f"plan-{uuid.uuid4().hex[:8]}",
        role=role,
        interview_type=interview_type,
        competencies=comps,
        questions=questions,
        target_minutes=target_minutes,
        source_note=_source_note(resume, job_description, reasoner),
    )


def _context(resume: str, job_description: str) -> str:
    parts = []
    if job_description.strip():
        parts.append(f"JOB DESCRIPTION:\n{job_description.strip()}")
    if resume.strip():
        parts.append(f"CANDIDATE RESUME:\n{resume.strip()}")
    return "\n\n".join(parts)


def _questions_for(
    comp: Competency, role: str, context: str, reasoner: Reasoner | None
) -> list[str]:
    if reasoner is not None and context:
        drafted = reasoner.draft_questions(
            role=role, context=context, competency=comp, n=QUESTIONS_PER_COMPETENCY
        )
        if drafted:
            return drafted[:QUESTIONS_PER_COMPETENCY]

    bank = QUESTION_BANK.get(comp.id)
    if bank:
        return bank[:QUESTIONS_PER_COMPETENCY]
    return [f"Tell me about a time that shows your {comp.name.lower()}."]


def _source_note(resume: str, job_description: str, reasoner: Reasoner | None) -> str:
    if not (resume.strip() or job_description.strip()):
        return "Generic plan — no resume or job description supplied."
    engine = reasoner.name if reasoner else "none"
    have = " and ".join(
        filter(None, ["resume" if resume.strip() else "", "job description" if job_description.strip() else ""])
    )
    return f"Questions drafted from {have} (reasoner: {engine})."
