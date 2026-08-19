"""HTTP surface over the interview engine.

The API is a transport, exactly like the CLI. It holds sessions and moves text in
and out; every decision about what to ask, what counts as evidence, and how to
score still lives in the engine. Adding the browser must not add a second place
where interview logic can drift.

Sessions live in memory. For personal use that's the right trade — the cost is
that a server restart loses an interview in progress, which is stated on the
health endpoint rather than left to be discovered.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from panel.config import load_settings
from panel.engine.conductor import Conductor, Progress
from panel.llm import get_reasoner
from panel.llm.base import Reasoner
from panel.models import Decision, InterviewPlan, InterviewType, Mode, Transcript
from panel.planning.compiler import compile_plan
from panel.scoring.report import Report, build_report
from panel.scoring.scorer import score_interview

app = FastAPI(title="Panel", version="0.1.0")

# The Vite dev server. Same-origin in production, where the API serves the build.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5193", "http://127.0.0.1:5193"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@dataclass
class Session:
    conductor: Conductor
    plan: InterviewPlan
    reasoner: Reasoner
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    report: Report | None = None


SESSIONS: dict[str, Session] = {}


# --------------------------------------------------------------------------
# Wire models
# --------------------------------------------------------------------------


class HealthOut(BaseModel):
    status: str = "ok"
    demo_mode: bool
    model: str | None
    reasoner: str
    note: str


class PlanSummary(BaseModel):
    role: str
    interview_type: InterviewType
    target_minutes: int
    plan_hash: str
    competencies: list[str]
    question_count: int
    source_note: str


class NewSession(BaseModel):
    role: str = Field(default="Software Engineer", min_length=1, max_length=120)
    interview_type: InterviewType = InterviewType.MIXED
    minutes: int = Field(default=30, ge=5, le=120)
    mode: Mode = Mode.PRACTICE
    resume: str = ""
    job_description: str = ""


class StepOut(BaseModel):
    decision: Decision
    utterance: str
    done: bool
    is_probe: bool = False
    question_id: str | None = None
    competency_id: str | None = None
    progress: Progress


class SessionOut(BaseModel):
    session_id: str
    mode: Mode
    plan: PlanSummary
    step: StepOut


class AnswerIn(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


class SessionState(BaseModel):
    session_id: str
    mode: Mode
    plan: PlanSummary
    progress: Progress
    transcript: Transcript
    has_report: bool


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _plan_summary(plan: InterviewPlan) -> PlanSummary:
    return PlanSummary(
        role=plan.role,
        interview_type=plan.interview_type,
        target_minutes=plan.target_minutes,
        plan_hash=plan.plan_hash,
        competencies=[c.name for c in plan.competencies],
        question_count=len(plan.questions),
        source_note=plan.source_note,
    )


def _step_out(step, conductor: Conductor) -> StepOut:
    return StepOut(
        decision=step.decision,
        utterance=step.utterance,
        done=step.done,
        is_probe=step.is_probe,
        question_id=step.question.id if step.question else None,
        competency_id=step.question.competency_id if step.question else None,
        progress=conductor.progress,
    )


def _session(session_id: str) -> Session:
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(404, "No such session. It may have been lost on restart.")
    return session


def _finalise(session: Session) -> Report:
    """Score once, then serve the cached report."""
    if session.report is None:
        scored = score_interview(
            plan=session.plan,
            transcript=session.conductor.transcript,
            evidence=session.conductor.evidence,
            reasoner=session.reasoner,
            mode=session.conductor.mode,
            session_id=session.conductor.session_id,
        )
        session.report = build_report(scored, session.plan, session.reasoner)
    return session.report


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@app.get("/api/health", response_model=HealthOut)
def health() -> HealthOut:
    settings = load_settings()
    return HealthOut(
        demo_mode=settings.demo_mode,
        model=None if settings.demo_mode else settings.model,
        reasoner="heuristic" if settings.demo_mode else "anthropic",
        note=(
            "Sessions are held in memory; restarting the server loses interviews in "
            "progress."
        ),
    )


@app.post("/api/sessions", response_model=SessionOut, status_code=201)
def create_session(body: NewSession) -> SessionOut:
    settings = load_settings()
    reasoner = get_reasoner(settings)

    plan = compile_plan(
        role=body.role,
        interview_type=body.interview_type,
        resume=body.resume,
        job_description=body.job_description,
        target_minutes=body.minutes,
        reasoner=reasoner,
    )
    conductor = Conductor(plan=plan, reasoner=reasoner, mode=body.mode)
    step = conductor.open()

    session_id = f"s-{uuid.uuid4().hex[:10]}"
    SESSIONS[session_id] = Session(conductor=conductor, plan=plan, reasoner=reasoner)

    return SessionOut(
        session_id=session_id,
        mode=body.mode,
        plan=_plan_summary(plan),
        step=_step_out(step, conductor),
    )


@app.post("/api/sessions/{session_id}/answer", response_model=StepOut)
def answer(session_id: str, body: AnswerIn) -> StepOut:
    session = _session(session_id)
    if session.conductor.closed:
        raise HTTPException(409, "This interview is already finished.")

    step = session.conductor.receive(body.text)
    if step.done:
        _finalise(session)
    return _step_out(step, session.conductor)


@app.get("/api/sessions/{session_id}", response_model=SessionState)
def get_session(session_id: str) -> SessionState:
    session = _session(session_id)
    return SessionState(
        session_id=session_id,
        mode=session.conductor.mode,
        plan=_plan_summary(session.plan),
        progress=session.conductor.progress,
        transcript=session.conductor.transcript,
        has_report=session.report is not None,
    )


@app.get("/api/sessions/{session_id}/report", response_model=Report)
def report(session_id: str) -> Report:
    session = _session(session_id)
    if not session.conductor.closed:
        raise HTTPException(409, "The interview is still in progress.")
    return _finalise(session)


@app.delete("/api/sessions/{session_id}", status_code=204)
def end_session(session_id: str) -> None:
    SESSIONS.pop(session_id, None)
