"""Conductor behaviour, driven by a stub reasoner so transitions are exact."""

from __future__ import annotations

import pytest

from panel.engine.conductor import Conductor
from panel.llm.base import AnswerAssessment, CoachingNote, ScoreVerdict
from panel.models import Competency, Decision, InterviewPlan, InterviewType, Question, RubricLevel, Speaker


def _competency(cid):
    return Competency(
        id=cid,
        name=cid.title(),
        definition="d",
        rubric=[
            RubricLevel(level=i, label=f"L{i}", descriptor=f"Observable behaviour {i}")
            for i in range(1, 5)
        ],
        critical_points=["point one", "point two"],
    )


def _plan(competency_ids=("alpha", "beta"), per_competency=2, minutes=60):
    comps = [_competency(c) for c in competency_ids]
    questions = [
        Question(id=f"{c.id}-{i}", competency_id=c.id, text=f"{c.id} question {i}", max_probes=1)
        for c in comps
        for i in range(1, per_competency + 1)
    ]
    return InterviewPlan(
        id="p",
        role="Engineer",
        interview_type=InterviewType.BEHAVIORAL,
        competencies=comps,
        questions=questions,
        target_minutes=minutes,
    )


class StubReasoner:
    """Returns a fixed assessment so decision logic is the only variable."""

    name = "stub"

    def __init__(self, *, complete: bool):
        self.complete = complete
        self.calls = 0

    def assess_answer(self, *, competency, question, answer):
        self.calls += 1
        if self.complete:
            return AnswerAssessment(
                is_substantive=True,
                covered_points=list(competency.critical_points),
                missing_points=[],
                probe_question=None,
            )
        return AnswerAssessment(
            is_substantive=True,
            covered_points=[],
            missing_points=list(competency.critical_points),
            probe_question="Can you be more specific?",
        )

    def draft_questions(self, **kw):
        return []

    def score(self, **kw):
        return ScoreVerdict(level=None, rationale="stub")

    def coach(self, **kw):
        return CoachingNote()


class TestFlow:
    def test_open_asks_the_first_planned_question(self):
        plan = _plan()
        conductor = Conductor(plan=plan, reasoner=StubReasoner(complete=True))
        step = conductor.open()

        assert step.decision is Decision.ASK
        assert step.question.id == "alpha-1"
        assert "alpha question 1" in step.utterance
        assert not step.done

    def test_complete_answers_never_probe(self):
        conductor = Conductor(plan=_plan(), reasoner=StubReasoner(complete=True))
        conductor.open()

        decisions = []
        step = conductor.receive("a complete answer")
        while not step.done:
            decisions.append(step.decision)
            step = conductor.receive("a complete answer")

        assert Decision.PROBE not in decisions

    def test_incomplete_answer_probes_then_moves_on_at_the_cap(self):
        conductor = Conductor(plan=_plan(), reasoner=StubReasoner(complete=False))
        conductor.open()

        first = conductor.receive("vague")
        assert first.decision is Decision.PROBE
        assert first.is_probe

        # max_probes=1, so the next incomplete answer must advance, not probe again.
        second = conductor.receive("still vague")
        assert second.decision is Decision.ASK
        assert second.question.id == "alpha-2"

    def test_advance_fires_when_crossing_into_a_new_competency(self):
        conductor = Conductor(plan=_plan(), reasoner=StubReasoner(complete=True))
        conductor.open()
        conductor.receive("answer")  # alpha-1 -> alpha-2, same competency

        crossing = conductor.receive("answer")  # alpha-2 -> beta-1
        assert crossing.decision is Decision.ADVANCE
        assert crossing.question.competency_id == "beta"

    def test_closes_after_the_last_question(self):
        plan = _plan(competency_ids=("alpha",), per_competency=1)
        conductor = Conductor(plan=plan, reasoner=StubReasoner(complete=True))
        conductor.open()

        step = conductor.receive("answer")
        assert step.decision is Decision.CLOSE
        assert step.done
        assert conductor.closed

    def test_receiving_after_close_raises(self):
        plan = _plan(competency_ids=("alpha",), per_competency=1)
        conductor = Conductor(plan=plan, reasoner=StubReasoner(complete=True))
        conductor.open()
        conductor.receive("answer")

        with pytest.raises(RuntimeError, match="closed"):
            conductor.receive("more")


class TestBudget:
    def test_every_competency_gets_asked_even_when_early_ones_could_absorb_the_budget(self):
        """Breadth before depth.

        With a reasoner that never finds anything, an unbudgeted conductor probes
        the first competency until the clock dies and never asks about the rest.
        """
        plan = _plan(competency_ids=("alpha", "beta", "gamma"), per_competency=2, minutes=30)
        conductor = Conductor(plan=plan, reasoner=StubReasoner(complete=False))

        conductor.open()
        step = conductor.receive("vague")
        while not step.done:
            step = conductor.receive("vague")

        asked = {t.competency_id for t in conductor.transcript.candidate_turns()}
        assert asked == {"alpha", "beta", "gamma"}

    def test_no_competency_exceeds_its_share_of_the_budget(self):
        plan = _plan(competency_ids=("alpha", "beta", "gamma"), per_competency=2, minutes=30)
        conductor = Conductor(plan=plan, reasoner=StubReasoner(complete=False))

        conductor.open()
        step = conductor.receive("vague")
        while not step.done:
            step = conductor.receive("vague")

        spent: dict[str, int] = {}
        for turn in conductor.transcript.candidate_turns():
            spent[turn.competency_id] = spent.get(turn.competency_id, 0) + 1
        assert max(spent.values()) <= conductor.competency_budget

    def test_time_budget_forces_close_even_with_questions_left(self):
        # 4 questions, but probing would otherwise run long; budget floors at len(questions).
        plan = _plan(per_competency=2, minutes=2)
        conductor = Conductor(plan=plan, reasoner=StubReasoner(complete=False))
        assert conductor.exchange_budget == 4

        conductor.open()
        steps = 0
        step = conductor.receive("vague")
        while not step.done:
            step = conductor.receive("vague")
            steps += 1
            assert steps < 50, "conductor failed to terminate"

        assert conductor.closed
        assert "at time" in step.utterance

    def test_budget_never_falls_below_one_pass_of_the_plan(self):
        plan = _plan(per_competency=3, minutes=2)  # 6 questions, 1 exchange of nominal budget
        conductor = Conductor(plan=plan, reasoner=StubReasoner(complete=True))
        assert conductor.exchange_budget == 6


class TestTranscript:
    def test_transcript_records_both_speakers_in_order(self):
        plan = _plan(competency_ids=("alpha",), per_competency=1)
        conductor = Conductor(plan=plan, reasoner=StubReasoner(complete=True))
        conductor.open()
        conductor.receive("my answer")

        speakers = [t.speaker for t in conductor.transcript.turns]
        assert speakers == [Speaker.INTERVIEWER, Speaker.CANDIDATE, Speaker.INTERVIEWER]
        assert conductor.transcript.turns[1].competency_id == "alpha"

    def test_conductor_cannot_assess_outside_the_plan(self):
        plan = _plan()
        conductor = Conductor(plan=plan, reasoner=StubReasoner(complete=True))
        conductor.open()
        step = conductor.receive("answer")
        while not step.done:
            step = conductor.receive("answer")

        asked = {t.competency_id for t in conductor.transcript.turns if t.competency_id}
        assert asked <= {c.id for c in plan.competencies}
