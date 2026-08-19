import pytest
from pydantic import ValidationError

from panel.models import (
    Competency,
    CompetencyScore,
    Evidence,
    InterviewPlan,
    InterviewType,
    Mode,
    Polarity,
    Question,
    RubricLevel,
    ScoredInterview,
    Speaker,
    Transcript,
)
from panel.planning.library import BEHAVIORAL, TECHNICAL_VERBAL


def _competency(cid="c1", weight=1.0):
    return Competency(
        id=cid,
        name="Test",
        definition="A test competency.",
        rubric=[
            RubricLevel(level=i, label=f"L{i}", descriptor=f"Observable behaviour {i}")
            for i in range(1, 5)
        ],
        critical_points=["a specific instance", "an outcome"],
        weight=weight,
    )


def _plan(competencies=None):
    comps = competencies or [_competency()]
    return InterviewPlan(
        id="p1",
        role="Engineer",
        interview_type=InterviewType.BEHAVIORAL,
        competencies=comps,
        questions=[Question(id=f"{c.id}-1", competency_id=c.id, text="Q?") for c in comps],
    )


def _evidence(cid="c1", polarity=Polarity.SUPPORTS):
    return Evidence(
        competency_id=cid, turn_index=0, quote="I decided to fix it", claim="ownership",
        polarity=polarity,
    )


class TestRubric:
    def test_rejects_incomplete_rubric(self):
        with pytest.raises(ValidationError, match="levels 1..4"):
            Competency(
                id="x",
                name="X",
                definition="d",
                rubric=[RubricLevel(level=1, label="L1", descriptor="observable thing")],
            )

    def test_rejects_duplicate_levels(self):
        with pytest.raises(ValidationError, match="levels 1..4"):
            Competency(
                id="x",
                name="X",
                definition="d",
                rubric=[
                    RubricLevel(level=lv, label="L", descriptor="observable thing")
                    for lv in (1, 2, 3, 3)
                ],
            )

    def test_library_competencies_are_all_valid(self):
        # Construction validates; this asserts the shipped library really has anchors.
        for competency in BEHAVIORAL + TECHNICAL_VERBAL:
            assert len(competency.rubric) == 4
            assert competency.critical_points
            for level in range(1, 5):
                assert len(competency.anchor(level).descriptor) > 30


class TestNoCitationNoScore:
    def test_score_without_evidence_is_rejected(self):
        with pytest.raises(ValidationError, match="every score must cite"):
            CompetencyScore(competency_id="c1", level=3)

    def test_undermining_evidence_alone_does_not_justify_a_score(self):
        with pytest.raises(ValidationError, match="every score must cite"):
            CompetencyScore(
                competency_id="c1",
                level=3,
                evidence=[_evidence(polarity=Polarity.UNDERMINES)],
            )

    def test_unobserved_needs_no_evidence(self):
        score = CompetencyScore(competency_id="c1", level=None)
        assert not score.observed


class TestPlanFreezing:
    def test_hash_is_stable_across_identical_plans(self):
        assert _plan().plan_hash == _plan().plan_hash

    def test_hash_ignores_id_and_timestamp(self):
        a, b = _plan(), _plan()
        b.id = "totally-different"
        assert a.plan_hash == b.plan_hash

    def test_hash_changes_when_an_anchor_changes(self):
        before = _plan()
        tweaked = _competency()
        tweaked.rubric[2].descriptor = "A materially different observable behaviour"
        assert _plan([tweaked]).plan_hash != before.plan_hash

    def test_rejects_question_referencing_unknown_competency(self):
        with pytest.raises(ValidationError, match="unknown competency"):
            InterviewPlan(
                id="p",
                role="r",
                interview_type=InterviewType.BEHAVIORAL,
                competencies=[_competency()],
                questions=[Question(id="q", competency_id="ghost", text="?")],
            )


class TestScoredInterview:
    def _scored(self, levels, plan):
        scores = []
        for competency, level in zip(plan.competencies, levels):
            scores.append(
                CompetencyScore(
                    competency_id=competency.id,
                    level=level,
                    evidence=[_evidence(competency.id)] if level is not None else [],
                )
            )
        return ScoredInterview(
            session_id="s",
            plan_id=plan.id,
            plan_hash=plan.plan_hash,
            role=plan.role,
            mode=Mode.PRACTICE,
            scores=scores,
            transcript=Transcript(),
        )

    def test_unobserved_excluded_from_overall_not_counted_as_zero(self):
        plan = _plan([_competency("a"), _competency("b")])
        scored = self._scored([4, None], plan)
        assert scored.overall(plan) == 4.0  # not 2.0
        assert scored.coverage == 0.5

    def test_overall_is_weighted(self):
        plan = _plan([_competency("a", weight=3.0), _competency("b", weight=1.0)])
        scored = self._scored([4, 2], plan)
        assert scored.overall(plan) == 3.5

    def test_overall_is_none_when_nothing_observed(self):
        plan = _plan([_competency("a")])
        assert self._scored([None], plan).overall(plan) is None


class TestTranscript:
    def test_answers_are_filtered_by_competency_and_speaker(self):
        transcript = Transcript()
        transcript.add(Speaker.INTERVIEWER, "Question?", competency_id="a")
        transcript.add(Speaker.CANDIDATE, "Answer for a", competency_id="a")
        transcript.add(Speaker.CANDIDATE, "Answer for b", competency_id="b")

        answers = transcript.answers_for("a")
        assert [t.text for t in answers] == ["Answer for a"]
        assert transcript.turns[0].index == 0 and transcript.turns[2].index == 2
