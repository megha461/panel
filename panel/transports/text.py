"""Text transport.

The whole loop is nine lines because the engine does the work. A realtime
transport (LiveKit + avatar) substitutes different `say` and `listen` callables
and changes nothing else — which is the point of keeping the engine
transport-agnostic.
"""

from __future__ import annotations

from typing import Callable

from panel.engine.conductor import Conductor
from panel.models import ScoredInterview
from panel.scoring.scorer import score_interview


def run_interview(
    conductor: Conductor,
    *,
    say: Callable[[str], None],
    listen: Callable[[], str],
) -> ScoredInterview:
    """Drive an interview to completion, then score it.

    `say` renders an interviewer utterance. `listen` blocks until the candidate
    has answered and returns what they said.
    """
    step = conductor.open()
    say(step.utterance)

    while not step.done:
        answer = listen()
        step = conductor.receive(answer)
        say(step.utterance)

    return score_interview(
        plan=conductor.plan,
        transcript=conductor.transcript,
        evidence=conductor.evidence,
        reasoner=conductor.reasoner,
        mode=conductor.mode,
        session_id=conductor.session_id,
    )
