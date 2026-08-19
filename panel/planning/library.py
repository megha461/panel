"""Built-in competency library with behaviorally-anchored rubrics.

Every descriptor here describes something observable in an *answer* — what the
candidate said or failed to say. None of them describe the person. That
distinction is the whole reason anchored rubrics score reliably: "names the
tradeoff they accepted and what it cost" can be checked against a transcript,
"shows good judgement" cannot.

This library exists so a usable plan can be built with no LLM at all. The plan
compiler enriches it with role context when a key is available.
"""

from __future__ import annotations

from panel.models import Competency, InterviewType, RubricLevel


def _rubric(weak: str, developing: str, strong: str, exceptional: str) -> list[RubricLevel]:
    return [
        RubricLevel(level=1, label="Weak", descriptor=weak),
        RubricLevel(level=2, label="Developing", descriptor=developing),
        RubricLevel(level=3, label="Strong", descriptor=strong),
        RubricLevel(level=4, label="Exceptional", descriptor=exceptional),
    ]


BEHAVIORAL: list[Competency] = [
    Competency(
        id="ownership",
        name="Ownership",
        definition="Takes responsibility for outcomes beyond the boundary of assigned tasks.",
        rubric=_rubric(
            weak=(
                "Speaks only in the plural about team activity; no personal action is "
                "identifiable. Or names a responsibility held without any instance of "
                "exercising it."
            ),
            developing=(
                "Names a personal action, but it stays inside assigned duties. Ownership "
                "stops at the task boundary; hand-offs are described as the end of their "
                "involvement."
            ),
            strong=(
                "Names a specific problem they took on that nobody assigned them, the "
                "action they personally took, and the outcome it produced."
            ),
            exceptional=(
                "As Strong, and they changed the system rather than the instance — a "
                "process, guardrail, test, or norm that outlived the incident and "
                "prevented recurrence."
            ),
        ),
        critical_points=[
            "A specific incident, not a general practice",
            "Their own action stated separately from the team's",
            "An outcome that is observable or measurable",
            "Evidence they went past what was assigned",
        ],
    ),
    Competency(
        id="conflict",
        name="Handling Disagreement",
        definition="Navigates technical or interpersonal disagreement toward a decision.",
        rubric=_rubric(
            weak=(
                "Avoids the premise — claims no real disagreements occur, or describes "
                "conflict resolved purely by deferring to authority or seniority."
            ),
            developing=(
                "Describes a disagreement and a resolution, but represents only their own "
                "position; the other party's reasoning is absent or characterised as simply "
                "wrong."
            ),
            strong=(
                "States the other party's position in terms that party would accept, names "
                "what evidence or argument moved the decision, and reports where it landed "
                "including when it landed against them."
            ),
            exceptional=(
                "As Strong, and they describe changing their own position on evidence, or "
                "establishing a mechanism (a spike, a written doc, agreed criteria) that "
                "converted opinion conflict into a decidable question."
            ),
        ),
        critical_points=[
            "A concrete disagreement with a named stake",
            "The counterparty's reasoning represented fairly",
            "How the decision was actually reached",
            "What they did after a decision that went against them",
        ],
    ),
    Competency(
        id="problem_solving",
        name="Structured Problem Solving",
        definition="Decomposes an ambiguous problem and reasons toward a solution methodically.",
        rubric=_rubric(
            weak=(
                "Jumps to a solution with no problem definition. Cannot say why that "
                "approach over another, or what would have shown it was wrong."
            ),
            developing=(
                "Describes a reasonable approach in sequence, but the framing was handed to "
                "them. No alternatives were considered and no constraints are named."
            ),
            strong=(
                "Defines the problem before solving it, names at least one alternative "
                "considered and why it lost, and states the constraints that shaped the "
                "choice."
            ),
            exceptional=(
                "As Strong, and they identify the assumption the whole approach rested on "
                "and how they tested it — including a case where the first framing was "
                "wrong and they reframed."
            ),
        ),
        critical_points=[
            "The problem stated before the solution",
            "At least one rejected alternative with a reason",
            "Named constraints (time, data, people, risk)",
            "How they knew it was working",
        ],
    ),
    Competency(
        id="learning",
        name="Learning From Failure",
        definition="Extracts transferable lessons from things that went wrong.",
        rubric=_rubric(
            weak=(
                "No failure offered, or the failure is external — the deadline, the spec, "
                "another team. No personal contribution to the outcome is identified."
            ),
            developing=(
                "Owns a failure but the lesson is generic ('communicate more', 'test more') "
                "with no account of what specifically would be done differently."
            ),
            strong=(
                "Names a failure with their own contribution to it, the specific decision "
                "they would change, and a later situation where they applied the lesson."
            ),
            exceptional=(
                "As Strong, and they distinguish the surface cause from the underlying one, "
                "and can say what conditions would make the same mistake likely again."
            ),
        ),
        critical_points=[
            "A real failure with real cost",
            "Their own contribution owned without deflection",
            "A specific changed behaviour, not a platitude",
            "Evidence the lesson transferred to a later situation",
        ],
    ),
    Competency(
        id="communication",
        name="Communication",
        definition="Conveys complex work clearly and calibrates to the listener.",
        rubric=_rubric(
            weak=(
                "Answers are hard to follow: undefined jargon, no through-line, or the "
                "point arrives only after prompting. Listener has to reconstruct the story."
            ),
            developing=(
                "Understandable but unstructured — chronological narration where the "
                "significant part is not signposted. Detail is uniform regardless of "
                "importance."
            ),
            strong=(
                "Leads with the point, then supports it. Detail is proportionate to "
                "significance. Technical terms are defined when the listener may not share "
                "them."
            ),
            exceptional=(
                "As Strong, and they actively check understanding or adjust depth mid-answer "
                "in response to the interviewer, and can compress the same story to one "
                "sentence on request."
            ),
        ),
        critical_points=[
            "A clear through-line from situation to outcome",
            "Point stated before supporting detail",
            "Jargon defined or avoided",
            "Length proportionate to the question",
        ],
    ),
]


TECHNICAL_VERBAL: list[Competency] = [
    Competency(
        id="systems_tradeoffs",
        name="Systems Design Tradeoffs",
        definition="Reasons about design options in terms of what each one costs.",
        rubric=_rubric(
            weak=(
                "Names technologies without reasons — a stack list rather than a design. "
                "Cannot say what the choice costs or when it would be wrong."
            ),
            developing=(
                "Gives a workable design and can justify components individually, but "
                "treats choices as independent; no tension between them is acknowledged."
            ),
            strong=(
                "States the dominant constraint, names the tradeoff each major choice "
                "accepts, and identifies the load or failure condition at which the design "
                "stops working."
            ),
            exceptional=(
                "As Strong, and they quantify — rough numbers for scale, latency budget, or "
                "cost — and name the cheapest design that would satisfy the actual "
                "requirement before proposing anything larger."
            ),
        ),
        critical_points=[
            "The binding constraint identified explicitly",
            "A tradeoff named with what it costs",
            "The breaking point of the design",
            "Rough quantification of scale or latency",
        ],
    ),
    Competency(
        id="debugging",
        name="Debugging Methodology",
        definition="Isolates the cause of a defect systematically rather than by guesswork.",
        rubric=_rubric(
            weak=(
                "Describes changing things until the symptom stopped. No hypothesis, no way "
                "of telling which change was responsible."
            ),
            developing=(
                "Uses tools and reads errors, but the search is unordered — no strategy for "
                "narrowing the space, and the root cause is found largely by familiarity."
            ),
            strong=(
                "Forms a hypothesis, names the observation that would falsify it, and "
                "narrows the search space deliberately (bisection, isolation, "
                "instrumentation) before changing code."
            ),
            exceptional=(
                "As Strong, and they distinguish the proximate cause from why it was "
                "possible, and describe closing the gap that let it ship — a test, an "
                "assertion, a type, a monitor."
            ),
        ),
        critical_points=[
            "A stated hypothesis before a fix",
            "A deliberate narrowing strategy",
            "How they confirmed the cause rather than assumed it",
            "What stops it recurring",
        ],
    ),
    Competency(
        id="fundamentals",
        name="Depth of Fundamentals",
        definition="Understands what sits under the abstractions they use daily.",
        rubric=_rubric(
            weak=(
                "Correct vocabulary, no model underneath. One 'why' question past the "
                "definition and the answer stops or becomes circular."
            ),
            developing=(
                "Holds an accurate mental model at one level down, but cannot connect it to "
                "consequences in their own work."
            ),
            strong=(
                "Explains the mechanism a level below the abstraction and links it to an "
                "observable consequence — a cost, a limit, a failure mode they have hit."
            ),
            exceptional=(
                "As Strong, and they state the boundary of their own knowledge precisely and "
                "reason correctly from first principles past it, rather than bluffing or "
                "stopping."
            ),
        ),
        critical_points=[
            "Mechanism explained, not just definition",
            "Connected to an observable consequence",
            "Survives a follow-up 'why'",
            "Honest, precise boundary on what they know",
        ],
    ),
    Competency(
        id="code_judgement",
        name="Code Quality Judgement",
        definition="Judges when to invest in structure and when structure is waste.",
        rubric=_rubric(
            weak=(
                "Cites rules without conditions ('always write tests', 'never repeat "
                "yourself') and applies them uniformly regardless of context."
            ),
            developing=(
                "Has real preferences and can defend them, but frames quality as an absolute "
                "rather than a tradeoff against time, risk, or lifespan."
            ),
            strong=(
                "Names the conditions under which they would and would not invest — "
                "lifespan, blast radius, how likely the requirement is to change — with a "
                "concrete instance of each."
            ),
            exceptional=(
                "As Strong, and they describe deliberately incurring debt with a recorded "
                "reason and a trigger for repaying it, or removing abstraction that was not "
                "earning its cost."
            ),
        ),
        critical_points=[
            "Conditions stated, not universal rules",
            "A case where they chose *not* to invest",
            "Blast radius or lifespan as a factor",
            "A concrete instance behind each claim",
        ],
    ),
]


QUESTION_BANK: dict[str, list[str]] = {
    "ownership": [
        "Tell me about something that was going wrong that nobody had asked you to fix. What did you do?",
        "Describe a time you were accountable for an outcome that depended on people you didn't manage.",
    ],
    "conflict": [
        "Tell me about a technical decision you disagreed with. Walk me through how it played out.",
        "Describe a time you were overruled. What did you do next?",
    ],
    "problem_solving": [
        "Walk me through the most ambiguous problem you've been handed. How did you get traction on it?",
        "Tell me about a time your first approach to a problem turned out to be wrong.",
    ],
    "learning": [
        "Tell me about something you shipped that didn't work out. What happened?",
        "What's a mistake you've made that changed how you work?",
    ],
    "communication": [
        "Tell me about a time you had to explain something technical to someone who didn't share your background.",
        "Describe a situation where you realised partway through that you'd lost your audience.",
    ],
    "systems_tradeoffs": [
        "Take a system you've worked on and walk me through its design. Why is it shaped that way?",
        "Suppose that system's traffic went up a hundredfold overnight. What breaks first?",
    ],
    "debugging": [
        "Tell me about the hardest bug you've tracked down. How did you find it?",
        "Describe a bug that only showed up in production. How did you approach it?",
    ],
    "fundamentals": [
        "Pick something you use every day and explain what's actually happening underneath it.",
        "What's something you understood only superficially until it broke on you?",
    ],
    "code_judgement": [
        "Tell me about a time you deliberately wrote code you weren't proud of. Why?",
        "How do you decide when a piece of code is worth refactoring?",
    ],
}


def competencies_for(interview_type: InterviewType) -> list[Competency]:
    if interview_type is InterviewType.BEHAVIORAL:
        return list(BEHAVIORAL)
    if interview_type is InterviewType.TECHNICAL_VERBAL:
        return list(TECHNICAL_VERBAL)
    # Mixed: the behavioural core plus the two highest-signal technical ones.
    picks = {"ownership", "problem_solving", "communication"}
    tech_picks = {"systems_tradeoffs", "debugging"}
    return [c for c in BEHAVIORAL if c.id in picks] + [
        c for c in TECHNICAL_VERBAL if c.id in tech_picks
    ]


def all_competencies() -> dict[str, Competency]:
    return {c.id: c for c in BEHAVIORAL + TECHNICAL_VERBAL}
