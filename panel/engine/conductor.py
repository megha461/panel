"""The interview state machine.

Transport-agnostic by construction: it consumes a string of candidate speech and
returns a string for the interviewer to say, plus the decision behind it. It
knows nothing about audio, sockets, or avatars — which is why the whole thing
can be tested in milliseconds with no API key.

The conductor's authority is deliberately narrow. It picks which planned
question comes next and whether to dig into the current answer. It cannot add a
competency, invent a question outside the plan, or change a rubric. Adaptivity
lives inside a frozen frame.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from pydantic import BaseModel

from panel.llm.base import Reasoner
from panel.models import (
    Decision,
    Evidence,
    InterviewPlan,
    Mode,
    Question,
    Speaker,
    Transcript,
)

# Rough pacing assumption: one question-and-answer exchange per two minutes.
MINUTES_PER_EXCHANGE = 2


class Progress(BaseModel):
    """Where the interview has got to. Any transport wants this for its UI."""

    exchanges: int
    exchange_budget: int
    competency_index: int
    competency_total: int
    competency_name: str | None = None
    closed: bool = False


@dataclass
class Step:
    """One interviewer move."""

    decision: Decision
    utterance: str
    question: Question | None = None
    is_probe: bool = False

    @property
    def done(self) -> bool:
        return self.decision is Decision.CLOSE


@dataclass
class Conductor:
    plan: InterviewPlan
    reasoner: Reasoner
    mode: Mode = Mode.PRACTICE
    session_id: str = field(default_factory=lambda: f"sess-{uuid.uuid4().hex[:8]}")

    transcript: Transcript = field(default_factory=Transcript)
    evidence: list[Evidence] = field(default_factory=list)

    _competency_i: int = 0
    _question_i: int = 0
    _probes_used: int = 0
    _exchanges: int = 0
    _closed: bool = False
    _current: Question | None = None
    _covered: dict[str, set[str]] = field(default_factory=dict)
    _spent: dict[str, int] = field(default_factory=dict)

    # -- lifecycle --------------------------------------------------------

    @property
    def exchange_budget(self) -> int:
        """Hard ceiling on exchanges, floored so every question gets one shot."""
        return max(len(self.plan.questions), self.plan.target_minutes // MINUTES_PER_EXCHANGE)

    @property
    def competency_budget(self) -> int:
        """Exchanges any one competency may consume.

        Without this the conductor is depth-first: it probes the opening
        competency until the clock runs out and never asks about the rest, which
        produces a confident score on one area and NOT OBSERVED on everything
        else. Breadth first, depth second — an interview that assessed two of
        five competencies is a worse interview, however good those two scores are.
        """
        return max(1, self.exchange_budget // max(1, len(self.plan.competencies)))

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def current_question(self) -> Question | None:
        """The question awaiting an answer. None before open() and after close."""
        return self._current

    def open(self) -> Step:
        """Greeting plus the first question."""
        question = self._question_at(0, 0)
        if question is None:  # unreachable: InterviewPlan requires >=1 question
            return self._close()

        self._current = question
        greeting = (
            f"Thanks for making the time. This is a {self.plan.target_minutes}-minute "
            f"conversation about the {self.plan.role} role. I'll ask about a few "
            "specific areas and dig into your examples as we go — concrete stories "
            "work better here than general descriptions.\n\n"
        )
        self._say(greeting + question.text, question=question)
        return Step(decision=Decision.ASK, utterance=greeting + question.text, question=question)

    def receive(self, answer: str) -> Step:
        """Take a candidate answer, return the interviewer's next move."""
        if self._closed:
            raise RuntimeError("interview is closed")
        if self._current is None:
            raise RuntimeError("receive() called before open()")

        competency = self.plan.competency(self._current.competency_id)
        turn = self.transcript.add(
            Speaker.CANDIDATE,
            answer,
            question_id=self._current.id,
            competency_id=competency.id,
            is_probe=self._probes_used > 0,
        )
        self._exchanges += 1
        self._spent[competency.id] = self._spent.get(competency.id, 0) + 1

        assessment = self.reasoner.assess_answer(
            competency=competency, question=self._current.text, answer=turn
        )
        self.evidence.extend(assessment.evidence)
        self._covered.setdefault(competency.id, set()).update(assessment.covered_points)

        return self._decide(competency.id, assessment.probe_question, assessment.missing_points)

    # -- decision logic ---------------------------------------------------

    def _decide(self, competency_id: str, probe: str | None, missing: list[str]) -> Step:
        out_of_time = self._exchanges >= self.exchange_budget
        competency_spent = self._spent.get(competency_id, 0) >= self.competency_budget

        should_probe = (
            probe is not None
            and missing
            and self._probes_used < self._current.max_probes  # type: ignore[union-attr]
            and not out_of_time
            and not competency_spent
        )
        if should_probe:
            self._probes_used += 1
            self._say(probe, question=self._current, is_probe=True)  # type: ignore[arg-type]
            return Step(
                decision=Decision.PROBE,
                utterance=probe,  # type: ignore[arg-type]
                question=self._current,
                is_probe=True,
            )

        if out_of_time:
            return self._close(ran_out=True)

        return self._advance(skip_competency=competency_spent)

    def _advance(self, skip_competency: bool = False) -> Step:
        """Next planned question, or close if the plan is exhausted.

        `skip_competency` abandons any remaining questions in the current
        competency because its time allowance is gone — the remaining budget
        belongs to competencies that have not been asked about at all.
        """
        previous = self._current
        self._probes_used = 0

        if skip_competency:
            comp_i, q_i = self._competency_i + 1, 0
        else:
            comp_i, q_i = self._competency_i, self._question_i + 1

        while True:
            if comp_i >= len(self.plan.competencies):
                return self._close()
            question = self._question_at(comp_i, q_i)
            if question is not None:
                break
            comp_i, q_i = comp_i + 1, 0

        self._competency_i, self._question_i, self._current = comp_i, q_i, question
        moved_on = previous is not None and previous.competency_id != question.competency_id
        decision = Decision.ADVANCE if moved_on else Decision.ASK

        utterance = ("That's helpful, thank you. " if moved_on else "") + question.text
        self._say(utterance, question=question)
        return Step(decision=decision, utterance=utterance, question=question)

    def _close(self, ran_out: bool = False) -> Step:
        self._closed = True
        self._current = None
        tail = (
            "We're at time, so I'll stop there."
            if ran_out
            else "That's everything I wanted to cover."
        )
        closing = (
            f"{tail} Thanks for talking these through — "
            + (
                "I'll pull together your feedback now."
                if self.mode is Mode.PRACTICE
                else "we'll be in touch about next steps."
            )
        )
        self._say(closing)
        return Step(decision=Decision.CLOSE, utterance=closing)

    # -- helpers ----------------------------------------------------------

    def _question_at(self, competency_i: int, question_i: int) -> Question | None:
        if competency_i >= len(self.plan.competencies):
            return None
        competency = self.plan.competencies[competency_i]
        questions = self.plan.questions_for(competency.id)
        if question_i >= len(questions):
            return None
        return questions[question_i]

    def _say(self, text: str, *, question: Question | None = None, is_probe: bool = False) -> None:
        self.transcript.add(
            Speaker.INTERVIEWER,
            text,
            question_id=question.id if question else None,
            competency_id=question.competency_id if question else None,
            is_probe=is_probe,
        )

    def coverage(self) -> dict[str, set[str]]:
        """Critical points evidenced so far, per competency."""
        return {c.id: self._covered.get(c.id, set()) for c in self.plan.competencies}

    @property
    def progress(self) -> Progress:
        current = self._current
        name = (
            self.plan.competency(current.competency_id).name if current is not None else None
        )
        return Progress(
            exchanges=self._exchanges,
            exchange_budget=self.exchange_budget,
            competency_index=min(self._competency_i, len(self.plan.competencies) - 1),
            competency_total=len(self.plan.competencies),
            competency_name=name,
            closed=self._closed,
        )
