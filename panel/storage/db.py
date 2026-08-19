"""Append-only store for completed interviews.

Two things shape this schema.

**Append-only.** There is no update or delete path. A scorecard that can be
quietly edited after the fact is not a record, and the whole design rests on a
score being traceable to the criteria and the transcript that produced it.

**NULL means not observed.** `competency_scores.level` is nullable and stays
nullable all the way into SQL, so a competency the interview never reached is
never averaged as a zero. `AVG` in SQLite skips NULLs, which is exactly the
semantics the domain model already enforces.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from panel.models import InterviewPlan
from panel.scoring.report import Report

SCHEMA = """
CREATE TABLE IF NOT EXISTS interviews (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT    NOT NULL UNIQUE,
    plan_hash       TEXT    NOT NULL,
    role            TEXT    NOT NULL,
    mode            TEXT    NOT NULL,
    interview_type  TEXT    NOT NULL,
    overall         REAL,
    coverage        REAL    NOT NULL,
    observed_count  INTEGER NOT NULL,
    total_count     INTEGER NOT NULL,
    created_at      TEXT    NOT NULL,
    report_json     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS competency_scores (
    interview_id    INTEGER NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
    competency_id   TEXT    NOT NULL,
    name            TEXT    NOT NULL,
    -- NULL is "not observed", never zero. AVG() skips it, which is correct.
    level           INTEGER,
    PRIMARY KEY (interview_id, competency_id)
);

CREATE INDEX IF NOT EXISTS idx_interviews_plan_hash ON interviews(plan_hash);
CREATE INDEX IF NOT EXISTS idx_interviews_created  ON interviews(created_at);
CREATE INDEX IF NOT EXISTS idx_scores_competency   ON competency_scores(competency_id);
"""


class InterviewSummary(BaseModel):
    id: int
    session_id: str
    plan_hash: str
    role: str
    mode: str
    interview_type: str
    overall: float | None
    coverage: float
    observed_count: int
    total_count: int
    created_at: str


class CompetencyPoint(BaseModel):
    interview_id: int
    created_at: str
    level: int | None


class CompetencyTrend(BaseModel):
    competency_id: str
    name: str
    points: list[CompetencyPoint]

    @property
    def observed(self) -> list[int]:
        return [p.level for p in self.points if p.level is not None]

    @property
    def change(self) -> int | None:
        """Difference between the first and last observed level, if there are two."""
        seen = self.observed
        return None if len(seen) < 2 else seen[-1] - seen[0]


def connect(path: Path | str) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def save_interview(conn: sqlite3.Connection, report: Report, plan: InterviewPlan) -> int:
    """Record a finished interview. Idempotent on session_id.

    Re-saving the same session is a no-op rather than an error: the API scores
    lazily and more than one request can reach a finished interview.
    """
    existing = conn.execute(
        "SELECT id FROM interviews WHERE session_id = ?", (report.session_id,)
    ).fetchone()
    if existing is not None:
        return int(existing["id"])

    with conn:
        cursor = conn.execute(
            """
            INSERT INTO interviews (
                session_id, plan_hash, role, mode, interview_type,
                overall, coverage, observed_count, total_count,
                created_at, report_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.session_id,
                report.plan_hash,
                report.role,
                report.mode.value,
                plan.interview_type.value,
                report.overall,
                report.coverage,
                report.observed_count,
                report.total_count,
                datetime.now(timezone.utc).isoformat(),
                report.model_dump_json(),
            ),
        )
        interview_id = int(cursor.lastrowid)

        conn.executemany(
            """
            INSERT INTO competency_scores (interview_id, competency_id, name, level)
            VALUES (?, ?, ?, ?)
            """,
            [
                (interview_id, c.competency_id, c.name, c.level)
                for c in report.competencies
            ],
        )
    return interview_id


def list_interviews(
    conn: sqlite3.Connection, *, role: str | None = None, limit: int = 50
) -> list[InterviewSummary]:
    sql = """
        SELECT id, session_id, plan_hash, role, mode, interview_type,
               overall, coverage, observed_count, total_count, created_at
        FROM interviews
    """
    params: list[object] = []
    if role:
        sql += " WHERE role = ?"
        params.append(role)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(limit)

    return [InterviewSummary(**dict(row)) for row in conn.execute(sql, params)]


def get_report(conn: sqlite3.Connection, interview_id: int) -> Report | None:
    row = conn.execute(
        "SELECT report_json FROM interviews WHERE id = ?", (interview_id,)
    ).fetchone()
    return None if row is None else Report.model_validate_json(row["report_json"])


def trends(conn: sqlite3.Connection, plan_hash: str) -> list[CompetencyTrend]:
    """Per-competency history for one rubric version.

    Scoped to a single `plan_hash` deliberately. Two interviews compiled from
    different criteria produce scores that look comparable and are not — charting
    them on one line would launder that straight past the reader. Comparability is
    what freezing the plan bought; spending it here would waste it.
    """
    rows = conn.execute(
        """
        SELECT s.competency_id, s.name, s.level, i.id AS interview_id, i.created_at
        FROM competency_scores s
        JOIN interviews i ON i.id = s.interview_id
        WHERE i.plan_hash = ?
        ORDER BY i.created_at ASC, i.id ASC
        """,
        (plan_hash,),
    ).fetchall()

    ordered: dict[str, CompetencyTrend] = {}
    for row in rows:
        trend = ordered.get(row["competency_id"])
        if trend is None:
            trend = CompetencyTrend(
                competency_id=row["competency_id"], name=row["name"], points=[]
            )
            ordered[row["competency_id"]] = trend
        trend.points.append(
            CompetencyPoint(
                interview_id=row["interview_id"],
                created_at=row["created_at"],
                level=row["level"],
            )
        )
    return list(ordered.values())


def comparable_runs(conn: sqlite3.Connection, plan_hash: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM interviews WHERE plan_hash = ?", (plan_hash,)
    ).fetchone()
    return int(row["n"])
