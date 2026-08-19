"""Claude-backed reasoner.

Structured output goes through `client.messages.parse()` with Pydantic models —
the SDK validates the shape, so the engine never parses free text.

Two rules encoded here rather than left to the prompt:

- Quotes are verified against the transcript before evidence is accepted. A
  citation the candidate did not say is dropped, not scored.
- Scoring is told it may return `null`. A competency the interview never got
  evidence for must come back unobserved, not guessed.

Any API failure falls through to the heuristic reasoner. A degraded interview
beats a crashed one, and the fallback is a real implementation.
"""

from __future__ import annotations

import re
import sys
from typing import Literal

from pydantic import BaseModel, Field

from panel.config import Settings
from panel.llm.base import AnswerAssessment, CoachingNote, ScoreVerdict
from panel.llm.heuristic import HeuristicReasoner
from panel.models import Competency, Evidence, Polarity, Turn

# Opus 5 writes longer than earlier models by default and can widen scope
# unasked. Both matter here: an interviewer that monologues wastes the
# candidate's time, and one that invents criteria breaks plan-freezing.
_STYLE = (
    "Keep every user-facing utterance short — one or two sentences, the way a "
    "real interviewer speaks. Deliver exactly what is asked at the scope asked; "
    "never assess anything outside the competency you were given."
)


class _EvidenceItem(BaseModel):
    quote: str = Field(description="Verbatim span from the candidate's answer. Do not paraphrase.")
    claim: str = Field(description="What this span demonstrates, in one clause.")
    polarity: Literal["supports", "undermines"] = "supports"


class _AssessmentOut(BaseModel):
    is_substantive: bool
    covered_points: list[str]
    missing_points: list[str]
    evidence: list[_EvidenceItem]
    probe_question: str | None = None


class _ScoreOut(BaseModel):
    level: int | None = Field(
        description="1-4 matching a rubric anchor, or null if the evidence supports no level."
    )
    rationale: str


class _QuestionsOut(BaseModel):
    questions: list[str]


class _CoachOut(BaseModel):
    strengths: list[str]
    gaps: list[str]
    stronger_answer: str
    drill: str


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


class AnthropicReasoner:
    """Claude-backed. Degrades to heuristics rather than failing the interview."""

    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=settings.api_key)
        self._model = settings.model
        self._max_tokens = settings.max_tokens
        self._fallback = HeuristicReasoner()

    # -- public interface -------------------------------------------------

    def draft_questions(
        self, *, role: str, context: str, competency: Competency, n: int
    ) -> list[str]:
        prompt = (
            f"Role being interviewed for: {role}\n\n"
            f"Context (resume and/or job description):\n{context or '(none provided)'}\n\n"
            f"Competency: {competency.name} — {competency.definition}\n"
            f"A strong answer contains:\n"
            + "\n".join(f"- {p}" for p in competency.critical_points)
            + f"\n\nWrite {n} interview questions that would surface evidence for this "
            "competency from someone in this role. Ground them in the specific context "
            "above where it helps. Each question must be answerable from experience, "
            "open-ended, and free of leading language that tells the candidate what a "
            "good answer looks like."
        )
        out = self._parse(
            _QuestionsOut,
            system=f"You design structured interviews. {_STYLE}",
            prompt=prompt,
            effort="medium",
        )
        if out is None:
            return self._fallback.draft_questions(
                role=role, context=context, competency=competency, n=n
            )
        return out.questions[:n]

    def assess_answer(
        self, *, competency: Competency, question: str, answer: Turn
    ) -> AnswerAssessment:
        prompt = (
            f"Competency under assessment: {competency.name} — {competency.definition}\n\n"
            "A strong answer contains all of these critical points:\n"
            + "\n".join(f"- {p}" for p in competency.critical_points)
            + f"\n\nQuestion asked:\n{question}\n\n"
            f"Candidate's answer:\n{answer.text}\n\n"
            "Report which critical points this answer actually evidences and which it "
            "leaves untouched. For each covered point, quote the exact span of the "
            "candidate's answer that evidences it — copy it verbatim, do not paraphrase "
            "or clean it up. Mark evidence as 'undermines' when a span actively counts "
            "against the competency.\n\n"
            "Set is_substantive false only for a genuine non-answer: a deflection, an "
            "'I don't know', or pure generality with no instance in it.\n\n"
            "If points are missing, write one short follow-up question targeting the "
            "single most valuable missing point. Ask it the way an interviewer speaks — "
            "conversational, one sentence, no preamble. If everything is covered, leave "
            "probe_question null."
        )
        out = self._parse(
            _AssessmentOut,
            system=(
                "You are an experienced interviewer assessing a single answer against "
                f"fixed criteria. {_STYLE}"
            ),
            prompt=prompt,
            effort="low",  # in the conversational path; Opus 5 is strong at low effort
        )
        if out is None:
            return self._fallback.assess_answer(
                competency=competency, question=question, answer=answer
            )

        return AnswerAssessment(
            is_substantive=out.is_substantive,
            covered_points=out.covered_points,
            missing_points=out.missing_points,
            evidence=self._verified_evidence(out.evidence, competency, answer),
            probe_question=out.probe_question,
        )

    def score(
        self, *, competency: Competency, evidence: list[Evidence], answers: list[Turn]
    ) -> ScoreVerdict:
        if not [e for e in evidence if e.polarity is Polarity.SUPPORTS]:
            return ScoreVerdict(
                level=None,
                rationale="No evidence was gathered for this competency during the interview.",
            )

        anchors = "\n".join(
            f"Level {r.level} ({r.label}): {r.descriptor}" for r in sorted(competency.rubric, key=lambda r: r.level)
        )
        cited = "\n".join(
            f'- [{e.polarity.value}] "{e.quote}" — {e.claim}' for e in evidence
        )
        prompt = (
            f"Competency: {competency.name} — {competency.definition}\n\n"
            f"Rubric anchors:\n{anchors}\n\n"
            f"Evidence extracted from the interview:\n{cited}\n\n"
            "What the candidate actually said:\n"
            + "\n\n".join(a.text for a in answers)
            + "\n\nAssign the level whose anchor the evidence actually matches. Judge "
            "against the anchor descriptors only — not against your impression of the "
            "candidate, and not against what a better answer could have been.\n\n"
            "Return null for level if the evidence is too thin to place the answer at "
            "any anchor. Unobserved is a legitimate and useful outcome; a guessed number "
            "is not. In the rationale, name the anchor you matched and point to the "
            "evidence that put it there."
        )
        out = self._parse(
            _ScoreOut,
            system=(
                "You score interview answers against behaviorally-anchored rubrics. You "
                "are strict about the difference between what was demonstrated and what "
                f"was merely claimed. {_STYLE}"
            ),
            prompt=prompt,
            effort="high",  # quality-critical: this is the number the report reports
        )
        if out is None:
            return self._fallback.score(
                competency=competency, evidence=evidence, answers=answers
            )
        if out.level is not None and not 1 <= out.level <= len(competency.rubric):
            return ScoreVerdict(level=None, rationale=f"Invalid level returned: {out.level}")
        return ScoreVerdict(level=out.level, rationale=out.rationale)

    def coach(
        self, *, competency: Competency, level: int | None, answers: list[Turn]
    ) -> CoachingNote:
        placement = (
            f"They scored level {level} ({competency.anchor(level).label})."
            if level is not None
            else "There was not enough evidence to score this competency."
        )
        top = competency.anchor(len(competency.rubric))
        prompt = (
            f"Competency: {competency.name} — {competency.definition}\n\n"
            f"{placement}\n"
            f"Top of the rubric: {top.descriptor}\n\n"
            "What they said:\n"
            + "\n\n".join(a.text for a in answers)
            + "\n\nCoach them. Be specific to what they actually said — no generic "
            "interview advice. For stronger_answer, describe concretely what they would "
            "have needed to add to reach the top anchor, referring to their own example "
            "rather than inventing a different one. For drill, give one exercise they "
            "can do in under five minutes."
        )
        out = self._parse(
            _CoachOut,
            system=f"You are a direct, specific interview coach. {_STYLE}",
            prompt=prompt,
            effort="medium",
        )
        if out is None:
            return self._fallback.coach(competency=competency, level=level, answers=answers)
        return CoachingNote(**out.model_dump())

    # -- internals --------------------------------------------------------

    def _parse(self, schema: type[BaseModel], *, system: str, prompt: str, effort: str):
        """One structured call. Returns None on any failure so callers degrade."""
        try:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                output_config={"effort": effort},
                messages=[{"role": "user", "content": prompt}],
                output_format=schema,
            )
            if response.stop_reason == "refusal":
                print("[panel] request declined; using heuristics", file=sys.stderr)
                return None
            return response.parsed_output
        except Exception as exc:  # noqa: BLE001 — any API failure degrades, never crashes
            print(f"[panel] LLM call failed ({type(exc).__name__}); using heuristics",
                  file=sys.stderr)
            return None

    @staticmethod
    def _verified_evidence(
        items: list[_EvidenceItem], competency: Competency, answer: Turn
    ) -> list[Evidence]:
        """Drop citations that aren't actually in the transcript.

        A fabricated quote is worse than no evidence — it makes an unsupported
        score look auditable. Cheap to check, so it is checked every time.
        """
        haystack = _normalize(answer.text)
        verified: list[Evidence] = []
        for item in items:
            if _normalize(item.quote) not in haystack:
                print(
                    f"[panel] dropped unverifiable quote for {competency.id}: "
                    f"{item.quote[:60]!r}",
                    file=sys.stderr,
                )
                continue
            verified.append(
                Evidence(
                    competency_id=competency.id,
                    turn_index=answer.index,
                    quote=item.quote,
                    claim=item.claim,
                    polarity=Polarity(item.polarity),
                )
            )
        return verified
