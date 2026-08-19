"""Terminal interface for Panel."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel as RichPanel
from rich.prompt import Prompt

from panel.config import load_settings
from panel.demo_answers import scripted_candidate
from panel.engine.conductor import Conductor
from panel.llm import get_reasoner
from panel.models import InterviewType, Mode
from panel.planning.compiler import compile_plan
from panel.scoring.report import coaching_report, screening_report
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

    console.print()
    report = (
        coaching_report(scored, plan, reasoner)
        if mode is Mode.PRACTICE
        else screening_report(scored, plan)
    )
    console.print(report)
    return 0


def cmd_practice(args) -> int:
    return _run(args, Mode.PRACTICE)


def cmd_screen(args) -> int:
    return _run(args, Mode.SCREENING)


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

    console.print()
    console.print(coaching_report(scored, plan, reasoner))
    console.print("\n\n")
    console.print(screening_report(scored, plan))
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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
