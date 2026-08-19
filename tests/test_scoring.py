"""Scoring rules, the heuristic reasoner's signal detection, and an end-to-end run."""

from __future__ import annotations

from panel.demo_answers import DEMO_ANSWERS, scripted_candidate
from panel.engine.conductor import Conductor
from panel.llm.base import ScoreVerdict
from panel.llm.heuristic import HeuristicReasoner
from panel.models import (
    Evidence,
    InterviewType,
    Mode,
    Polarity,
    Speaker,
    Transcript,
    Turn,
)
from panel.planning.compiler import compile_plan
from panel.planning.library import competencies_for
from panel.scoring.report import coaching_report, screening_report
from panel.scoring.scorer import score_interview
from panel.transports.text import run_interview

STRONG = (
    "Our deploy pipeline was flaky and nobody owned it. I decided to instrument the "
    "runner and found a race in the cache key. That reduced failures from 30 percent "
    "to under 2 percent. Looking back I would have measured sooner rather than "
    "guessing, and instead of adding a retry we fixed the root cause."
)
WEAK = "We worked on the pipeline as a team and things generally got better over time."


def _turn(text, index=0, competency_id="ownership"):
    return Turn(index=index, speaker=Speaker.CANDIDATE, text=text, competency_id=competency_id)


class TestHeuristicSignals:
    def setup_method(self):
        self.reasoner = HeuristicReasoner()
        self.competency = competencies_for(InterviewType.BEHAVIORAL)[0]  # ownership

    def test_strong_answer_covers_more_than_weak(self):
        strong = self.reasoner.assess_answer(
            competency=self.competency, question="q", answer=_turn(STRONG)
        )
        weak = self.reasoner.assess_answer(
            competency=self.competency, question="q", answer=_turn(WEAK)
        )
        assert len(strong.covered_points) > len(weak.covered_points)
        assert strong.is_substantive and weak.is_substantive

    def test_non_answer_is_flagged_and_probed(self):
        assessment = self.reasoner.assess_answer(
            competency=self.competency, question="q", answer=_turn("I don't know.")
        )
        assert not assessment.is_substantive
        assert not assessment.evidence
        assert assessment.probe_question

    def test_evidence_quotes_come_from_the_answer(self):
        assessment = self.reasoner.assess_answer(
            competency=self.competency, question="q", answer=_turn(STRONG)
        )
        assert assessment.evidence
        for item in assessment.evidence:
            assert item.quote in STRONG
            assert item.turn_index == 0

    def test_probe_offered_only_while_points_are_missing(self):
        assessment = self.reasoner.assess_answer(
            competency=self.competency, question="q", answer=_turn(WEAK)
        )
        assert assessment.missing_points
        assert assessment.probe_question is not None

    def test_scoring_without_evidence_returns_unobserved(self):
        verdict = self.reasoner.score(competency=self.competency, evidence=[], answers=[])
        assert verdict.level is None

    def test_probes_never_echo_internal_rubric_wording(self):
        """A probe that reads a critical point aloud tells the candidate the answer."""
        from panel.planning.library import all_competencies

        for competency in all_competencies().values():
            for point in competency.critical_points:
                probe = self.reasoner._probe_for(point)
                assert point.lower() not in probe.lower(), (
                    f"probe leaked the critical point verbatim: {probe!r}"
                )

    def test_consecutive_probes_for_one_signal_are_not_identical(self):
        point = "A specific incident, not a general practice"
        first = self.reasoner._probe_for(point)
        second = self.reasoner._probe_for(point)
        assert first != second


class TestScorer:
    def setup_method(self):
        self.plan = compile_plan(role="Engineer", interview_type=InterviewType.BEHAVIORAL)
        self.reasoner = HeuristicReasoner()

    def test_competency_with_no_evidence_is_not_observed(self):
        scored = score_interview(
            plan=self.plan,
            transcript=Transcript(),
            evidence=[],
            reasoner=self.reasoner,
            mode=Mode.SCREENING,
        )
        assert all(not s.observed for s in scored.scores)
        assert scored.coverage == 0.0
        assert scored.overall(self.plan) is None

    def test_a_scored_competency_carries_its_citations(self):
        competency = self.plan.competencies[0]
        transcript = Transcript()
        transcript.add(Speaker.CANDIDATE, STRONG, competency_id=competency.id)
        evidence = [
            Evidence(
                competency_id=competency.id,
                turn_index=0,
                quote="I decided to instrument the runner",
                claim="Addresses: A specific incident, not a general practice",
            )
        ]

        scored = score_interview(
            plan=self.plan,
            transcript=transcript,
            evidence=evidence,
            reasoner=self.reasoner,
            mode=Mode.SCREENING,
        )
        score = scored.score_for(competency.id)
        assert score.observed
        assert score.evidence
        assert scored.plan_hash == self.plan.plan_hash

    def test_a_fabricated_level_is_downgraded_not_trusted(self):
        """A reasoner that scores without evidence must not produce a number."""

        class Liar(HeuristicReasoner):
            def score(self, **kw):
                return ScoreVerdict(level=4, rationale="trust me")

        scored = score_interview(
            plan=self.plan,
            transcript=Transcript(),
            evidence=[],
            reasoner=Liar(),
            mode=Mode.SCREENING,
        )
        assert all(s.level is None for s in scored.scores)

    def test_undermining_evidence_alone_does_not_produce_a_score(self):
        competency = self.plan.competencies[0]
        evidence = [
            Evidence(
                competency_id=competency.id,
                turn_index=0,
                quote="we as a team",
                claim="no personal action",
                polarity=Polarity.UNDERMINES,
            )
        ]
        scored = score_interview(
            plan=self.plan,
            transcript=Transcript(),
            evidence=evidence,
            reasoner=self.reasoner,
            mode=Mode.SCREENING,
        )
        assert scored.score_for(competency.id).level is None


class TestEndToEnd:
    def test_full_interview_runs_and_scores_with_no_api_key(self):
        reasoner = HeuristicReasoner()
        plan = compile_plan(
            role="Senior Backend Engineer",
            interview_type=InterviewType.MIXED,
            target_minutes=30,
            reasoner=reasoner,
        )
        conductor = Conductor(plan=plan, reasoner=reasoner, mode=Mode.PRACTICE)

        said: list[str] = []
        scored = run_interview(
            conductor, say=said.append, listen=scripted_candidate(conductor)
        )

        assert conductor.closed
        assert len(scored.scores) == len(plan.competencies)

        # Engine invariant — the conductor's job is to *ask* about everything it
        # planned to assess, within budget. This is a hard requirement: a
        # conductor that burns its budget on the first competency is broken
        # however good the resulting score is.
        asked = {t.competency_id for t in conductor.transcript.candidate_turns()}
        assert asked == {c.id for c in plan.competencies}

        # Reasoner recall is a separate, softer concern. The keyless heuristic
        # detects six observable signals and will miss anchors phrased outside
        # them, so it is held to a lower bar than the LLM path.
        assert scored.coverage >= 0.8, f"heuristic recall regressed: {scored.coverage:.0%}"

        # Every numeric score must be backed by a real quote from the transcript.
        transcript_text = scored.transcript.as_text()
        for score in scored.observed_scores:
            supporting = [e for e in score.evidence if e.polarity is Polarity.SUPPORTS]
            assert supporting
            for item in supporting:
                assert item.quote in transcript_text

    def test_both_reports_render(self):
        reasoner = HeuristicReasoner()
        plan = compile_plan(role="Engineer", interview_type=InterviewType.BEHAVIORAL)
        conductor = Conductor(plan=plan, reasoner=reasoner, mode=Mode.PRACTICE)
        scored = run_interview(
            conductor, say=lambda _: None, listen=scripted_candidate(conductor)
        )

        coaching = coaching_report(scored, plan, reasoner)
        screening = screening_report(scored, plan)

        assert plan.plan_hash in coaching and plan.plan_hash in screening
        assert "RECOMMENDATION" in screening
        assert "NOT OBSERVED" in screening or "Evidence:" in screening
        for competency in plan.competencies:
            assert competency.name in coaching
