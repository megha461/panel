"""One report object, several renderings.

`build_report` is the single source of truth. The CLI renders it as text; the API
serialises it as JSON. Adding the web surface must not mean a second copy of the
"how do we describe a score" logic — the two modes already differ in enough real
ways without also drifting in the incidental ones.

Practice mode answers "how do I get better at this?". Screening mode answers "what
did this person demonstrate, and how do I know?". Same evidence underneath.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from panel.llm.base import CoachingNote, Reasoner
from panel.models import Evidence, InterviewPlan, Mode, Polarity, ScoredInterview, Transcript

BAR_WIDTH = 4
NOT_OBSERVED = "Not observed"


class CompetencyReport(BaseModel):
    competency_id: str
    name: str
    definition: str
    level: int | None
    label: str
    rationale: str
    matched_anchor: str | None = None
    top_anchor: str
    critical_points: list[str] = Field(default_factory=list)
    supporting: list[Evidence] = Field(default_factory=list)
    undermining: list[Evidence] = Field(default_factory=list)
    coaching: CoachingNote | None = None

    @property
    def observed(self) -> bool:
        return self.level is not None


class Report(BaseModel):
    session_id: str
    role: str
    mode: Mode
    plan_hash: str
    overall: float | None
    coverage: float
    observed_count: int
    total_count: int
    recommendation: str
    competencies: list[CompetencyReport]
    transcript: Transcript


def build_report(
    scored: ScoredInterview, plan: InterviewPlan, reasoner: Reasoner | None = None
) -> Report:
    """Assemble the report.

    `reasoner` is only needed for practice mode — coaching notes are the one part
    that requires a fresh judgement rather than a rearrangement of what scoring
    already produced.
    """
    entries: list[CompetencyReport] = []

    for competency in plan.competencies:
        score = scored.score_for(competency.id)
        if score is None:
            continue

        observed = score.observed
        coaching = None
        if reasoner is not None and scored.mode is Mode.PRACTICE:
            coaching = reasoner.coach(
                competency=competency,
                level=score.level,
                answers=scored.transcript.answers_for(competency.id),
            )

        entries.append(
            CompetencyReport(
                competency_id=competency.id,
                name=competency.name,
                definition=competency.definition,
                level=score.level,
                label=competency.anchor(score.level).label if observed else NOT_OBSERVED,
                rationale=score.rationale,
                matched_anchor=competency.anchor(score.level).descriptor if observed else None,
                top_anchor=competency.anchor(len(competency.rubric)).descriptor,
                critical_points=list(competency.critical_points),
                supporting=[e for e in score.evidence if e.polarity is Polarity.SUPPORTS],
                undermining=[e for e in score.evidence if e.polarity is Polarity.UNDERMINES],
                coaching=coaching,
            )
        )

    return Report(
        session_id=scored.session_id,
        role=scored.role,
        mode=scored.mode,
        plan_hash=scored.plan_hash,
        overall=scored.overall(plan),
        coverage=scored.coverage,
        observed_count=len(scored.observed_scores),
        total_count=len(scored.scores),
        recommendation=_recommendation(scored, plan),
        competencies=entries,
        transcript=scored.transcript,
    )


def _recommendation(scored: ScoredInterview, plan: InterviewPlan) -> str:
    overall = scored.overall(plan)
    if overall is None:
        return "No decision — the interview gathered no scorable evidence."

    if scored.coverage < 0.5:
        return (
            f"Insufficient coverage ({int(scored.coverage * 100)}%) for a decision. "
            f"Observed competencies averaged {overall}/4; re-interview to cover the rest."
        )
    if overall >= 3.5:
        return "Strong — clear evidence at or near the top anchors."
    if overall >= 2.75:
        return "Advance — solid evidence, with specific areas to probe further."
    if overall >= 2.0:
        return "Mixed — evidence sits mostly at the developing anchors."
    return "Below bar on the competencies assessed."


# --------------------------------------------------------------------------
# Text rendering (CLI)
# --------------------------------------------------------------------------


def _bar(level: int | None) -> str:
    if level is None:
        return "· · · ·"
    return " ".join("█" if i < level else "·" for i in range(BAR_WIDTH))


def _coverage_line(report: Report) -> str:
    pct = int(round(report.coverage * 100))
    line = f"Coverage: {report.observed_count}/{report.total_count} competencies evidenced ({pct}%)"
    if report.coverage < 1.0:
        line += "\n  Unobserved competencies are excluded from the overall score."
    return line


def render_coaching_text(report: Report) -> str:
    out = [f"INTERVIEW FEEDBACK — {report.role}", "=" * 60, ""]
    out.append(
        f"Overall: {report.overall}/4 across {report.observed_count} competencies"
        if report.overall is not None
        else "Overall: not enough evidence to score."
    )
    out += [_coverage_line(report), ""]

    for entry in report.competencies:
        out += [
            "-" * 60,
            f"{entry.name}   {_bar(entry.level)}   {entry.label}",
            "",
            f"  {entry.rationale}",
            "",
        ]
        if not entry.observed:
            out += ["  This never came up. Ask for it next time you practise.", ""]
            continue

        note = entry.coaching
        if note is None:
            continue
        if note.strengths:
            out += ["  What worked:", *[f"    + {s}" for s in note.strengths], ""]
        if note.gaps:
            out += ["  What was missing:", *[f"    - {g}" for g in note.gaps], ""]
        if note.stronger_answer:
            out += ["  To reach the top of the rubric:", f"    {note.stronger_answer}", ""]
        if note.drill:
            out += ["  Drill:", f"    {note.drill}", ""]

    out += ["=" * 60, f"Rubric version: {report.plan_hash}"]
    return "\n".join(out)


def render_screening_text(report: Report) -> str:
    out = [
        f"INTERVIEW SCORECARD — {report.role}",
        "=" * 60,
        f"Session: {report.session_id}",
        f"Rubric version: {report.plan_hash}",
        "",
    ]
    out.append(
        f"Overall: {report.overall}/4 (weighted, observed competencies only)"
        if report.overall is not None
        else "Overall: insufficient evidence — no recommendation."
    )
    out += [_coverage_line(report), "", "-" * 60, ""]

    for entry in report.competencies:
        label = entry.label if entry.observed else "NOT OBSERVED"
        out += [f"{entry.name}   {_bar(entry.level)}   {label}", f"  {entry.rationale}"]
        if entry.supporting:
            out.append("  Evidence:")
            out += [f'    [turn {e.turn_index}] "{e.quote}"\n      → {e.claim}' for e in entry.supporting]
        if entry.undermining:
            out.append("  Counter-evidence:")
            out += [f'    [turn {e.turn_index}] "{e.quote}"\n      → {e.claim}' for e in entry.undermining]
        out.append("")

    out += ["-" * 60, f"RECOMMENDATION: {report.recommendation}", ""]
    out.append(
        "Scores reflect evidence gathered in this interview only. Competencies "
        "marked NOT OBSERVED were not assessed and must not be read as weaknesses."
    )
    return "\n".join(out)


# Back-compat convenience wrappers used by the CLI.


def coaching_report(scored: ScoredInterview, plan: InterviewPlan, reasoner: Reasoner) -> str:
    return render_coaching_text(build_report(scored, plan, reasoner))


def screening_report(scored: ScoredInterview, plan: InterviewPlan) -> str:
    return render_screening_text(build_report(scored, plan))
