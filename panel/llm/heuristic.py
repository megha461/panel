"""Keyless reasoner. Runs the full pipeline with no API key and no network.

It is not trying to imitate a language model. It detects the observable signals
the rubrics are written around — specificity, first-person agency, stated
outcomes, considered alternatives, reflection, method, prevention — and reports
honestly on what it can and cannot see. That makes it useful for development, deterministic for
tests, and a real fallback rather than a mock.
"""

from __future__ import annotations

import re

from panel.llm.base import AnswerAssessment, CoachingNote, ScoreVerdict
from panel.models import Competency, Evidence, Polarity, Turn
from panel.planning.library import QUESTION_BANK

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "for", "with",
    "at", "by", "from", "it", "its", "they", "them", "their", "that", "this",
    "is", "are", "was", "were", "be", "been", "as", "not", "no", "than", "then",
    "not", "you", "your", "what", "how", "why", "when", "which", "who", "whom",
    "did", "do", "does", "have", "has", "had", "can", "could", "would", "should",
}

# Observable markers the rubric anchors are written around.
_SIGNAL_PATTERNS: dict[str, re.Pattern[str]] = {
    # Spelled-out numerals matter as much as digits here: speech-to-text writes
    # "two days", not "2 days", and this engine is meant to run over a voice
    # transport. A digits-only pattern would go quietly blind the moment it does.
    "specificity": re.compile(
        r"\b(?:\d+(?:[.,]\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|fifteen|twenty|thirty|forty|fifty|sixty|hundred|thousand|million)"
        r"\s*(?:%|percent|ms|s|sec|seconds|minutes|hours|days|weeks|"
        r"months|x|k|m|users|requests|rows|times)\b|\b\d{4}\b",
        re.I,
    ),
    "agency": re.compile(r"\bI\s+(?:built|wrote|led|decided|proposed|fixed|found|took|"
                         r"pushed|changed|added|removed|ran|shipped|owned|raised)\b"),
    "outcome": re.compile(
        r"\b(?:resulted in|led to|reduced|increased|dropped|cut|improved|saved|"
        r"went from|ended up|so that|which meant|the result|turned out|stayed there|"
        r"took (?:about )?\w+ (?:seconds|minutes|hours|days))\b",
        re.I,
    ),
    # Closing the gap that allowed the problem, as distinct from reflecting on
    # it. Ownership's top anchor, Learning's transfer point and Debugging's
    # recurrence point are all written around this.
    "prevention": re.compile(
        r"\b(?:so (?:that )?it (?:can'?t|cannot|never)|make[s]? (?:the|it) \w+ impossible|"
        r"added? (?:an? )?(?:assertion|test|check|guardrail|monitor|alert)|"
        r"prevent\w*|stop\w* it (?:from )?(?:happening|recurring)|"
        r"never happened again|hasn'?t happened since|every time since|"
        r"changed the (?:signature|type|process)|since then)\b",
        re.I,
    ),
    # How they went about it, as distinct from what came out. Debugging and
    # fundamentals anchors are written around this and the other five miss it.
    "method": re.compile(
        r"\b(?:hypothes\w+|bisect\w*|isolat\w+|instrument\w+|narrow\w+|reproduc\w+|"
        r"profil\w+|falsif\w+|root cause|proximate|underneath|mechanism|"
        r"one at a time|step through)\b",
        re.I,
    ),
    "alternatives": re.compile(
        r"\b(?:instead of|rather than|considered|the alternative|tradeoff|trade-off|"
        r"versus|vs\.?|we could have|ruled out|rejected)\b",
        re.I,
    ),
    "reflection": re.compile(
        r"\b(?:in hindsight|looking back|next time|I'd|I would|what I learned|"
        r"the lesson|if I did it again|should have)\b",
        re.I,
    ),
}

# Which signal a critical point is really asking for, matched on the point's own wording.
_POINT_CUES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"specific|concrete|instance|incident|named|quantif|measurable|number", re.I),
     "specificity"),
    (re.compile(r"own action|their own|personally|separately from the team|owned|"
                r"beyond|past what was assigned|nobody asked", re.I),
     "agency"),
    (re.compile(r"outcome|result|impact|observable|how they knew", re.I),
     "outcome"),
    (re.compile(r"alternative|rejected|tradeoff|trade-off|constraint|instead|condition", re.I),
     "alternatives"),
    (re.compile(r"lesson|changed behaviour|changed behavior|hindsight|"
                r"would change|reflect", re.I),
     "reflection"),
    (re.compile(r"hypothesis|narrowing|strategy|mechanism|methodical|before a fix|"
                r"survives|deliberate|confirmed the cause", re.I),
     "method"),
    (re.compile(r"recurr|stops it|prevent|guardrail|outlived|transferred|"
                r"changed the system", re.I),
     "prevention"),
]

# Follow-ups in the interviewer's voice, one bank per signal. Rotated so a long
# interview never repeats a probe verbatim.
_PROBES: dict[str, tuple[str, ...]] = {
    "specificity": (
        "Can you ground that in one specific instance — what happened, and when?",
        "Pick one concrete example and walk me through it.",
    ),
    "agency": (
        "What did you personally do there, as distinct from the team?",
        "Which part of that was your own call?",
    ),
    "outcome": (
        "What was the actual outcome? How did you know it worked?",
        "How did things end up — what changed as a result?",
    ),
    "alternatives": (
        "What else did you consider, and why did you rule it out?",
        "What was the tradeoff you accepted there?",
    ),
    "reflection": (
        "Knowing what you know now, what would you do differently?",
        "What did that change about how you work?",
    ),
    "method": (
        "How did you actually go about working that out?",
        "What told you that was the right explanation and not a guess?",
    ),
    "prevention": (
        "What stops that happening again?",
        "Did anything change so the same thing can't recur?",
    ),
    "": (
        "Can you say a bit more about that?",
        "Tell me more about how that actually played out.",
    ),
}

_MIN_SUBSTANTIVE_WORDS = 12
_NON_ANSWER = re.compile(
    r"^\s*(?:i don'?t know|no idea|not sure|nothing comes to mind|pass|skip|n/?a)\b", re.I
)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in _STOPWORDS and len(w) > 2}


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _signals(text: str) -> set[str]:
    return {name for name, pat in _SIGNAL_PATTERNS.items() if pat.search(text)}


def _required_signal(point: str) -> str | None:
    for pat, signal in _POINT_CUES:
        if pat.search(point):
            return signal
    return None


def _best_quote(
    text: str, point: str, signal: str | None, used: set[str] | None = None
) -> str | None:
    """The sentence that most plausibly evidences this point.

    Prefers a span not already cited for a different point in the same answer.
    Two critical points often map to the same signal — "a stated hypothesis" and
    "a deliberate narrowing strategy" are both method — and without this the
    single highest-scoring sentence gets cited twice under different claims. That
    reads as padded evidence, which is corrosive in a report whose whole promise
    is that a citation points at the thing it says it points at.

    Falls back to the best sentence overall when no unused one evidences the
    point, since one span genuinely can support two claims.
    """
    sentences = _sentences(text)
    if not sentences:
        return None
    used = used or set()
    point_words = _words(point)

    best = best_unused = None
    best_score = best_unused_score = 0.0
    for s in sentences:
        score = len(_words(s) & point_words)
        if signal and _SIGNAL_PATTERNS[signal].search(s):
            score += 2
        if score > best_score:
            best, best_score = s, score
        if score > best_unused_score and s not in used:
            best_unused, best_unused_score = s, score

    if best_unused_score > 0:
        return best_unused
    return best if best_score > 0 else None


class HeuristicReasoner:
    """Signal-detection reasoner. Deterministic — same input, same output."""

    name = "heuristic"

    def __init__(self) -> None:
        self._probe_count = 0

    def draft_questions(
        self, *, role: str, context: str, competency: Competency, n: int
    ) -> list[str]:
        bank = QUESTION_BANK.get(competency.id, [])
        if bank:
            return bank[:n]
        return [f"Tell me about a time that shows your {competency.name.lower()}."][:n]

    def assess_answer(
        self, *, competency: Competency, question: str, answer: Turn
    ) -> AnswerAssessment:
        text = answer.text.strip()
        word_count = len(text.split())
        substantive = (
            word_count >= _MIN_SUBSTANTIVE_WORDS and not _NON_ANSWER.match(text)
        )

        if not substantive:
            return AnswerAssessment(
                is_substantive=False,
                missing_points=list(competency.critical_points),
                probe_question=(
                    "Take a moment — even a partial example helps. "
                    f"{self._nudge(competency)}"
                ),
            )

        present = _signals(text)
        cited: set[str] = set()
        covered: list[str] = []
        missing: list[str] = []
        evidence: list[Evidence] = []

        for point in competency.critical_points:
            signal = _required_signal(point)
            overlap = len(_words(text) & _words(point))
            is_covered = (signal in present) if signal else overlap >= 2
            if signal and not is_covered:
                # A strong lexical match can still carry the point.
                is_covered = overlap >= 3

            if is_covered:
                covered.append(point)
                quote = _best_quote(text, point, signal, used=cited)
                if quote:
                    cited.add(quote)
                    evidence.append(
                        Evidence(
                            competency_id=competency.id,
                            turn_index=answer.index,
                            quote=quote,
                            claim=f"Addresses: {point}",
                            polarity=Polarity.SUPPORTS,
                        )
                    )
            else:
                missing.append(point)

        probe = self._probe_for(missing[0]) if missing else None
        return AnswerAssessment(
            is_substantive=True,
            covered_points=covered,
            missing_points=missing,
            evidence=evidence,
            probe_question=probe,
        )

    def score(
        self, *, competency: Competency, evidence: list[Evidence], answers: list[Turn]
    ) -> ScoreVerdict:
        supporting = [e for e in evidence if e.polarity is Polarity.SUPPORTS]
        if not supporting:
            return ScoreVerdict(
                level=None,
                rationale="No evidence was gathered for this competency during the interview.",
            )

        points = competency.critical_points or ["evidence"]
        covered = {e.claim.removeprefix("Addresses: ") for e in supporting}
        ratio = len(covered & set(points)) / len(points)

        if ratio >= 0.85:
            level = 4
        elif ratio >= 0.6:
            level = 3
        elif ratio >= 0.3:
            level = 2
        else:
            level = 1

        anchor = competency.anchor(level)
        return ScoreVerdict(
            level=level,
            rationale=(
                f"{len(covered & set(points))} of {len(points)} critical points evidenced. "
                f"Matches the {anchor.label.lower()} anchor: {anchor.descriptor}"
            ),
        )

    def coach(
        self, *, competency: Competency, level: int | None, answers: list[Turn]
    ) -> CoachingNote:
        joined = " ".join(a.text for a in answers)
        present = _signals(joined)
        strengths, gaps = [], []

        readable = {
            "specificity": "gave concrete, quantified detail",
            "agency": "made your own actions clear and distinct from the team's",
            "outcome": "stated what actually resulted",
            "alternatives": "showed the options you weighed",
            "reflection": "reflected on what you'd change",
        }
        for signal, phrase in readable.items():
            (strengths if signal in present else gaps).append(phrase)

        return CoachingNote(
            strengths=[f"You {s}." for s in strengths],
            gaps=[f"You never {g}." for g in gaps],
            stronger_answer=(
                f"A level-4 answer on {competency.name} contains: "
                + "; ".join(competency.critical_points)
                + "."
            ),
            drill=(
                f"Re-answer one {competency.name.lower()} question in 90 seconds, "
                "forcing yourself to include a number and a sentence starting with 'I decided'."
            ),
        )

    # -- helpers ----------------------------------------------------------

    def _probe_for(self, point: str) -> str:
        """A follow-up in the interviewer's voice.

        Never echoes the critical point's own wording — those are internal
        rubric strings, and reading one aloud tells the candidate exactly which
        box to tick. Variants rotate so a long interview doesn't repeat itself
        word for word.
        """
        signal = _required_signal(point)
        variants = _PROBES.get(signal or "", _PROBES[""])
        probe = variants[self._probe_count % len(variants)]
        self._probe_count += 1
        return probe

    @staticmethod
    def _nudge(competency: Competency) -> str:
        first = competency.critical_points[0] if competency.critical_points else "a concrete example"
        return f"Start with {first.lower()}."
