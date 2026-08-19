"""Persistence rules — append-only, and NULL means not observed all the way down."""

from __future__ import annotations

import sqlite3

import pytest

from panel.demo_answers import scripted_candidate
from panel.engine.conductor import Conductor
from panel.llm.heuristic import HeuristicReasoner
from panel.models import InterviewType, Mode
from panel.planning.compiler import compile_plan
from panel.scoring.report import build_report
from panel.scoring.scorer import score_interview
from panel.storage import db
from panel.transports.text import run_interview


def _finished_interview(minutes=20, mode=Mode.PRACTICE, role="Backend Engineer"):
    reasoner = HeuristicReasoner()
    plan = compile_plan(
        role=role,
        interview_type=InterviewType.BEHAVIORAL,
        target_minutes=minutes,
        reasoner=reasoner,
    )
    conductor = Conductor(plan=plan, reasoner=reasoner, mode=mode)
    scored = run_interview(
        conductor, say=lambda _: None, listen=scripted_candidate(conductor)
    )
    return build_report(scored, plan, reasoner), plan


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "panel.db")
    yield connection
    connection.close()


class TestSaving:
    def test_saves_summary_and_per_competency_rows(self, conn):
        report, plan = _finished_interview()
        interview_id = db.save_interview(conn, report, plan)

        assert interview_id > 0
        summaries = db.list_interviews(conn)
        assert len(summaries) == 1
        assert summaries[0].plan_hash == plan.plan_hash
        assert summaries[0].role == "Backend Engineer"

        rows = conn.execute("SELECT * FROM competency_scores").fetchall()
        assert len(rows) == len(plan.competencies)

    def test_resaving_the_same_session_is_a_no_op(self, conn):
        report, plan = _finished_interview()
        first = db.save_interview(conn, report, plan)
        second = db.save_interview(conn, report, plan)

        assert first == second
        assert len(db.list_interviews(conn)) == 1
        rows = conn.execute("SELECT COUNT(*) AS n FROM competency_scores").fetchone()
        assert rows["n"] == len(plan.competencies)

    def test_round_trips_the_full_report(self, conn):
        report, plan = _finished_interview()
        interview_id = db.save_interview(conn, report, plan)

        loaded = db.get_report(conn, interview_id)
        assert loaded is not None
        assert loaded.session_id == report.session_id
        assert loaded.plan_hash == report.plan_hash
        assert len(loaded.competencies) == len(report.competencies)
        # Citations must survive the round trip, or the audit trail is decorative.
        original = [e.quote for c in report.competencies for e in c.supporting]
        restored = [e.quote for c in loaded.competencies for e in c.supporting]
        assert restored == original
        assert loaded.transcript.turns

    def test_missing_interview_returns_none(self, conn):
        assert db.get_report(conn, 999) is None


class TestNotObservedStaysNull:
    def test_unobserved_competency_is_stored_as_null_not_zero(self, conn):
        # A very short interview cannot reach every competency.
        report, plan = _finished_interview(minutes=10)
        interview_id = db.save_interview(conn, report, plan)

        unobserved = [c.competency_id for c in report.competencies if c.level is None]
        if not unobserved:
            pytest.skip("this run happened to observe everything")

        row = conn.execute(
            "SELECT level FROM competency_scores WHERE interview_id = ? AND competency_id = ?",
            (interview_id, unobserved[0]),
        ).fetchone()
        assert row["level"] is None

    def test_sql_average_skips_unobserved_rather_than_counting_zero(self, conn):
        report, plan = _finished_interview()
        interview_id = db.save_interview(conn, report, plan)
        # Force a known mix: one 4, one NULL.
        conn.execute("DELETE FROM competency_scores WHERE interview_id = ?", (interview_id,))
        conn.executemany(
            "INSERT INTO competency_scores (interview_id, competency_id, name, level) VALUES (?,?,?,?)",
            [(interview_id, "a", "A", 4), (interview_id, "b", "B", None)],
        )
        conn.commit()

        avg = conn.execute(
            "SELECT AVG(level) AS avg FROM competency_scores WHERE interview_id = ?",
            (interview_id,),
        ).fetchone()["avg"]
        assert avg == 4.0  # not 2.0


class TestAppendOnly:
    def test_there_is_no_update_or_delete_in_the_public_api(self):
        exported = set(dir(db))
        assert not {name for name in exported if name.startswith(("update_", "delete_"))}

    def test_a_saved_session_id_cannot_be_duplicated(self, conn):
        report, plan = _finished_interview()
        db.save_interview(conn, report, plan)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO interviews (session_id, plan_hash, role, mode,
                   interview_type, overall, coverage, observed_count, total_count,
                   created_at, report_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (report.session_id, "x", "r", "practice", "behavioral", 1.0, 1.0, 1, 1, "now", "{}"),
            )


class TestTrends:
    def test_tracks_a_competency_across_runs_of_the_same_rubric(self, conn):
        first, plan = _finished_interview()
        second, plan2 = _finished_interview()
        assert plan.plan_hash == plan2.plan_hash  # same criteria

        db.save_interview(conn, first, plan)
        db.save_interview(conn, second, plan2)

        series = db.trends(conn, plan.plan_hash)
        assert series
        assert all(len(t.points) == 2 for t in series)
        assert db.comparable_runs(conn, plan.plan_hash) == 2

    def test_runs_under_a_different_rubric_are_excluded(self, conn):
        behavioral, plan_a = _finished_interview()

        reasoner = HeuristicReasoner()
        plan_b = compile_plan(
            role="Backend Engineer",
            interview_type=InterviewType.TECHNICAL_VERBAL,
            reasoner=reasoner,
        )
        conductor = Conductor(plan=plan_b, reasoner=reasoner, mode=Mode.PRACTICE)
        scored = run_interview(
            conductor, say=lambda _: None, listen=scripted_candidate(conductor)
        )
        technical = build_report(scored, plan_b, reasoner)

        db.save_interview(conn, behavioral, plan_a)
        db.save_interview(conn, technical, plan_b)

        assert plan_a.plan_hash != plan_b.plan_hash
        assert db.comparable_runs(conn, plan_a.plan_hash) == 1
        assert all(len(t.points) == 1 for t in db.trends(conn, plan_a.plan_hash))

    def test_change_needs_two_observed_points(self, conn):
        trend = db.CompetencyTrend(
            competency_id="c",
            name="C",
            points=[
                db.CompetencyPoint(interview_id=1, created_at="a", level=2),
                db.CompetencyPoint(interview_id=2, created_at="b", level=None),
            ],
        )
        assert trend.change is None

        trend.points.append(
            db.CompetencyPoint(interview_id=3, created_at="c", level=4)
        )
        assert trend.change == 2

    def test_filtering_by_role(self, conn):
        a, plan_a = _finished_interview(role="Backend Engineer")
        b, plan_b = _finished_interview(role="Data Scientist")
        db.save_interview(conn, a, plan_a)
        db.save_interview(conn, b, plan_b)

        assert len(db.list_interviews(conn, role="Data Scientist")) == 1
        assert len(db.list_interviews(conn)) == 2
