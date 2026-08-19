"""Two renderings of one scored interview.

Practice mode answers "how do I get better at this?". Screening mode answers
"what did this person actually demonstrate, and how do I know?". Same evidence
underneath — the difference is what the reader is deciding.
"""

from __future__ import annotations

from panel.llm.base import Reasoner
from panel.models import InterviewPlan, Polarity, ScoredInterview

BAR_WIDTH = 4


def _bar(level: int | None) -> str:
    if level is None:
        return "· · · ·"
    return " ".join("█" if i < level else "·" for i in range(BAR_WIDTH))


def _coverage_line(scored: ScoredInterview) -> str:
    observed, total = len(scored.observed_scores), len(scored.scores)
    pct = int(round(scored.coverage * 100))
    line = f"Coverage: {observed}/{total} competencies evidenced ({pct}%)"
    if scored.coverage < 1.0:
        line += "\n  Unobserved competencies are excluded from the overall score."
    return line


def coaching_report(
    scored: ScoredInterview, plan: InterviewPlan, reasoner: Reasoner
) -> str:
    """Practice mode: what to fix, grounded in what you actually said."""
    out: list[str] = [
        f"INTERVIEW FEEDBACK — {plan.role}",
        "=" * 60,
        "",
    ]

    overall = scored.overall(plan)
    if overall is not None:
        out.append(f"Overall: {overall}/4 across {len(scored.observed_scores)} competencies")
    else:
        out.append("Overall: not enough evidence to score.")
    out += [_coverage_line(scored), ""]

    for competency in plan.competencies:
        score = scored.score_for(competency.id)
        if score is None:
            continue

        label = (
            competency.anchor(score.level).label if score.observed else "Not observed"
        )
        out += [
            "-" * 60,
            f"{competency.name}   {_bar(score.level)}   {label}",
            "",
            f"  {score.rationale}",
            "",
        ]

        if not score.observed:
            out += ["  This never came up. Ask for it next time you practise.", ""]
            continue

        answers = scored.transcript.answers_for(competency.id)
        note = reasoner.coach(competency=competency, level=score.level, answers=answers)

        if note.strengths:
            out.append("  What worked:")
            out += [f"    + {s}" for s in note.strengths]
            out.append("")
        if note.gaps:
            out.append("  What was missing:")
            out += [f"    - {g}" for g in note.gaps]
            out.append("")
        if note.stronger_answer:
            out += ["  To reach the top of the rubric:", f"    {note.stronger_answer}", ""]
        if note.drill:
            out += ["  Drill:", f"    {note.drill}", ""]

    out += ["=" * 60, f"Rubric version: {scored.plan_hash}"]
    return "\n".join(out)


def screening_report(scored: ScoredInterview, plan: InterviewPlan) -> str:
    """Screening mode: the scorecard, with every claim traceable to a quote."""
    out: list[str] = [
        f"INTERVIEW SCORECARD — {plan.role}",
        "=" * 60,
        f"Session: {scored.session_id}",
        f"Rubric version: {scored.plan_hash}",
        "",
    ]

    overall = scored.overall(plan)
    out.append(
        f"Overall: {overall}/4 (weighted, observed competencies only)"
        if overall is not None
        else "Overall: insufficient evidence — no recommendation."
    )
    out += [_coverage_line(scored), "", "-" * 60, ""]

    for competency in plan.competencies:
        score = scored.score_for(competency.id)
        if score is None:
            continue

        label = competency.anchor(score.level).label if score.observed else "NOT OBSERVED"
        out += [f"{competency.name}   {_bar(score.level)}   {label}", f"  {score.rationale}"]

        supporting = [e for e in score.evidence if e.polarity is Polarity.SUPPORTS]
        against = [e for e in score.evidence if e.polarity is Polarity.UNDERMINES]

        if supporting:
            out.append("  Evidence:")
            out += [f'    [turn {e.turn_index}] "{e.quote}"\n      → {e.claim}' for e in supporting]
        if against:
            out.append("  Counter-evidence:")
            out += [f'    [turn {e.turn_index}] "{e.quote}"\n      → {e.claim}' for e in against]
        out.append("")

    out += ["-" * 60, _recommendation(scored, plan), ""]
    out.append(
        "Scores reflect evidence gathered in this interview only. Competencies "
        "marked NOT OBSERVED were not assessed and must not be read as weaknesses."
    )
    return "\n".join(out)


def _recommendation(scored: ScoredInterview, plan: InterviewPlan) -> str:
    overall = scored.overall(plan)
    if overall is None:
        return "RECOMMENDATION: No decision — the interview gathered no scorable evidence."

    if scored.coverage < 0.5:
        return (
            f"RECOMMENDATION: Insufficient coverage ({int(scored.coverage * 100)}%) for a "
            f"decision. Observed competencies averaged {overall}/4; re-interview to cover "
            "the rest."
        )

    if overall >= 3.5:
        verdict = "Strong — clear evidence at or near the top anchors."
    elif overall >= 2.75:
        verdict = "Advance — solid evidence, with specific areas to probe further."
    elif overall >= 2.0:
        verdict = "Mixed — evidence sits mostly at the developing anchors."
    else:
        verdict = "Below bar on the competencies assessed."
    return f"RECOMMENDATION: {verdict}"
