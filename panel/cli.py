"""Terminal interface for Panel."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel as RichPanel
from rich.prompt import Prompt
from rich.table import Table

from panel.config import load_settings
from panel.demo_answers import scripted_candidate
from panel.engine.conductor import Conductor
from panel.llm import get_reasoner
from panel.models import InterviewType, Mode
from panel.planning.compiler import compile_plan
from panel.scoring.report import build_report, render_coaching_text, render_screening_text
from panel.storage import db
from panel.transports.text import run_interview

console = Console()


def _read(path: str | None) -> str:
    if not path:
        return ""
    return Path(path).read_text(encoding="utf-8")


def _build(args, mode: Mode):
    settings = load_settings()
    reasoner = get_reasoner(settings)

    if settings.demo_mode:
        console.print(
            "[yellow]No ANTHROPIC_API_KEY — running on the built-in heuristic reasoner. "
            "Everything works; question drafting and scoring are rule-based.[/yellow]\n"
        )

    plan = compile_plan(
        role=args.role,
        interview_type=InterviewType(args.type),
        resume=_read(getattr(args, "resume", None)),
        job_description=_read(getattr(args, "jd", None)),
        target_minutes=args.minutes,
        reasoner=reasoner,
    )

    console.print(
        RichPanel(
            f"[bold]{plan.role}[/bold] · {plan.interview_type.value} · "
            f"{plan.target_minutes} min\n"
            f"{len(plan.competencies)} competencies, {len(plan.questions)} questions\n"
            f"Rubric version [cyan]{plan.plan_hash}[/cyan]",
            title="Interview plan (frozen)",
        )
    )
    return plan, reasoner


def _say(text: str) -> None:
    console.print(f"\n[bold cyan]Interviewer:[/bold cyan] {text}\n")


def _listen() -> str:
    return Prompt.ask("[bold green]You[/bold green]")


def _run(args, mode: Mode) -> int:
    plan, reasoner = _build(args, mode)
    conductor = Conductor(plan=plan, reasoner=reasoner, mode=mode)

    scored = run_interview(conductor, say=_say, listen=_listen)

    # Build the report once, then record and render it — a terminal interview
    # belongs in the history the same as a browser one.
    report = build_report(scored, plan, reasoner)
    conn = db.connect(load_settings().db_path)
    try:
        db.save_interview(conn, report, plan)
        runs = db.comparable_runs(conn, plan.plan_hash)
    finally:
        conn.close()

    console.print()
    console.print(
        render_coaching_text(report)
        if mode is Mode.PRACTICE
        else render_screening_text(report)
    )
    if runs > 1:
        console.print(
            f"\n[dim]Run {runs} against rubric {plan.plan_hash}. "
            "`panel history` shows the progression.[/dim]"
        )
    return 0


def cmd_practice(args) -> int:
    return _run(args, Mode.PRACTICE)


def cmd_screen(args) -> int:
    return _run(args, Mode.SCREENING)


def cmd_history(args) -> int:
    """Past interviews, and progress within a single rubric version."""
    settings = load_settings()
    conn = db.connect(settings.db_path)
    try:
        interviews = db.list_interviews(conn, role=args.role, limit=args.limit)
        if not interviews:
            console.print(
                "[yellow]No interviews recorded yet.[/yellow] Finish one with "
                "`panel practice` and it will appear here."
            )
            return 0

        table = Table(box=box.SIMPLE, header_style="", pad_edge=False)
        table.add_column("When", no_wrap=True)
        table.add_column("Role", no_wrap=True, max_width=24)
        table.add_column("Mode", no_wrap=True)
        table.add_column("Overall", no_wrap=True, justify="right")
        table.add_column("Coverage", no_wrap=True, justify="right")
        table.add_column("Rubric", no_wrap=True)
        for row in interviews:
            table.add_row(
                row.created_at[:16].replace("T", " "),
                row.role,
                row.mode,
                "—" if row.overall is None else f"{row.overall}/4",
                f"{int(row.coverage * 100)}%",
                row.plan_hash,
            )
        console.print(table)

        # Progress is only meaningful within one rubric version.
        latest = interviews[0].plan_hash
        runs = db.comparable_runs(conn, latest)
        if runs < 2:
            console.print(
                f"\n[dim]Rubric {latest} has {runs} run. Two or more against the "
                "same rubric are needed before progress means anything.[/dim]"
            )
            return 0

        console.print(f"\n[bold]Progress across {runs} runs of rubric {latest}[/bold]")
        for trend in db.trends(conn, latest):
            marks = " ".join(
                "·" if point.level is None else str(point.level) for point in trend.points
            )
            change = trend.change
            delta = "" if change is None else f"  {change:+d}" if change else "  ="
            console.print(f"  {trend.name:<28} {marks}{delta}")
        console.print(
            "\n[dim]· = not observed in that run. Only runs against this rubric "
            "are shown; other versions are not comparable.[/dim]"
        )
        return 0
    finally:
        conn.close()


def cmd_demo(args) -> int:
    """Scripted end-to-end run — no key, no typing, deterministic."""
    plan, reasoner = _build(args, Mode.PRACTICE)
    conductor = Conductor(plan=plan, reasoner=reasoner, mode=Mode.PRACTICE)

    answer_for = scripted_candidate(conductor)

    def scripted() -> str:
        answer = answer_for()
        console.print(f"[green]Candidate:[/green] {answer}\n")
        return answer

    scored = run_interview(conductor, say=_say, listen=scripted)

    # Both renderings from one report, so the demo shows how the two modes differ
    # without pretending they came from different interviews.
    report = build_report(scored, plan, reasoner)
    console.print()
    console.print(render_coaching_text(report))
    console.print("\n\n")
    console.print(render_screening_text(report))
    console.print(
        "\n[dim]Not recorded: the demo answers are scripted, and mixing them into "
        "your history would corrupt the progress trend it exists to show.[/dim]"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="panel", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(sub):
        sub.add_argument("--role", default="Software Engineer")
        sub.add_argument(
            "--type",
            default=InterviewType.MIXED.value,
            choices=[t.value for t in InterviewType],
        )
        sub.add_argument("--minutes", type=int, default=30)
        sub.add_argument("--resume", help="Path to a resume text file")
        sub.add_argument("--jd", help="Path to a job description text file")
        return sub

    add_common(
        subparsers.add_parser("practice", help="You are the candidate; get coaching")
    ).set_defaults(func=cmd_practice)
    add_common(
        subparsers.add_parser("screen", help="Someone else is the candidate; get a scorecard")
    ).set_defaults(func=cmd_screen)
    add_common(
        subparsers.add_parser("demo", help="Scripted end-to-end run, no key required")
    ).set_defaults(func=cmd_demo)

    history = subparsers.add_parser("history", help="Past interviews and progress")
    history.add_argument("--role", help="Only show interviews for this role")
    history.add_argument("--limit", type=int, default=20)
    history.set_defaults(func=cmd_history)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
