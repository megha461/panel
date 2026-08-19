"""Realtime voice transport: LiveKit Agents driving the same Conductor.

⚠️ STATUS: written against livekit-agents 1.6.10 with the API surface verified by
introspection, but **never executed against a live room** — that needs LiveKit
Cloud plus STT, TTS, and avatar credentials. Treat it as reviewed scaffolding,
not as tested code. The credential gate below is tested; the call path is not.

The one design decision worth stating: **there is no LLM in the voice loop.**

LiveKit's usual shape is STT → LLM → TTS, where the model decides what to say.
That is exactly wrong here. The conductor has already decided what to say, from a
frozen plan; dropping a model into the loop would let it improvise questions
outside that plan and quietly break the guarantee that two candidates were asked
against identical criteria. `AgentSession` takes `llm` as optional, so the wiring
is STT → Conductor → TTS: speech in, engine decides, speech out.

The reasoner still runs — for judging answers and scoring — just off the speech
path, where its latency doesn't stall the conversation.
"""

from __future__ import annotations

import asyncio
import logging
import os

from panel.engine.conductor import Conductor
from panel.llm import get_reasoner
from panel.models import InterviewType, Mode
from panel.planning.compiler import compile_plan
from panel.scoring.report import build_report, render_coaching_text, render_screening_text
from panel.scoring.scorer import score_interview

log = logging.getLogger("panel.realtime")

# What a live call needs beyond the engine itself. Each value says what it buys,
# so a missing-credentials error is actionable rather than just a list of names.
REQUIRED_CREDENTIALS: dict[str, str] = {
    "LIVEKIT_URL": "LiveKit Cloud project URL (wss://…)",
    "LIVEKIT_API_KEY": "LiveKit API key",
    "LIVEKIT_API_SECRET": "LiveKit API secret",
    "DEEPGRAM_API_KEY": "speech-to-text",
    "CARTESIA_API_KEY": "text-to-speech",
    "ANTHROPIC_API_KEY": "answer assessment and scoring",
}

# Avatar providers, selected with PANEL_AVATAR. 'none' runs voice-only, which is
# the sane default: avatars bill $0.10–$0.37 per active minute.
AVATAR_CREDENTIALS: dict[str, str] = {
    "tavus": "TAVUS_API_KEY",
    "anam": "ANAM_API_KEY",
    "simli": "SIMLI_API_KEY",
    "hedra": "HEDRA_API_KEY",
}


def missing_credentials() -> dict[str, str]:
    """Credentials that are absent, mapped to what they would enable."""
    missing = {k: v for k, v in REQUIRED_CREDENTIALS.items() if not os.environ.get(k)}

    avatar = os.environ.get("PANEL_AVATAR", "none").lower()
    if avatar != "none":
        key = AVATAR_CREDENTIALS.get(avatar)
        if key is None:
            missing[f"PANEL_AVATAR={avatar}"] = (
                "unknown avatar provider; expected one of "
                + ", ".join(sorted(AVATAR_CREDENTIALS))
                + ", or 'none'"
            )
        elif not os.environ.get(key):
            missing[key] = f"{avatar} talking-head avatar"
    return missing


def check_ready() -> None:
    """Fail early and legibly rather than part-way through a call."""
    missing = missing_credentials()
    if not missing:
        return
    lines = "\n".join(f"  {name}  — {why}" for name, why in sorted(missing.items()))
    raise RuntimeError(
        "The realtime transport needs credentials that are not set:\n"
        f"{lines}\n\n"
        "Set PANEL_AVATAR=none to run voice-only (no avatar bill), or use the "
        "text transport — `panel practice` — which needs no credentials at all."
    )


def _build_conductor() -> Conductor:
    reasoner = get_reasoner()
    plan = compile_plan(
        role=os.environ.get("PANEL_ROLE", "Software Engineer"),
        interview_type=InterviewType(os.environ.get("PANEL_TYPE", "mixed")),
        target_minutes=int(os.environ.get("PANEL_MINUTES", "30")),
        reasoner=reasoner,
    )
    mode = Mode(os.environ.get("PANEL_MODE", "practice"))
    log.info("plan compiled: %s competencies, rubric %s", len(plan.competencies), plan.plan_hash)
    return Conductor(plan=plan, reasoner=reasoner, mode=mode)


async def _attach_avatar(session, room) -> bool:
    """Attach a talking-head avatar if one is configured. Voice-only otherwise."""
    provider = os.environ.get("PANEL_AVATAR", "none").lower()
    if provider == "none":
        return False

    # Imported here so the module works with only the providers actually installed.
    if provider == "tavus":
        from livekit.plugins import tavus

        avatar = tavus.AvatarSession(replica_id=os.environ["TAVUS_REPLICA_ID"])
    elif provider == "anam":
        from livekit.plugins import anam

        avatar = anam.AvatarSession(persona_id=os.environ["ANAM_PERSONA_ID"])
    elif provider == "simli":
        from livekit.plugins import simli

        avatar = simli.AvatarSession(face_id=os.environ["SIMLI_FACE_ID"])
    else:
        from livekit.plugins import hedra

        avatar = hedra.AvatarSession(avatar_id=os.environ["HEDRA_AVATAR_ID"])

    await avatar.start(session, room=room)
    log.info("avatar attached: %s", provider)
    return True


async def entrypoint(ctx) -> None:
    """LiveKit job entrypoint. One room, one interview."""
    from livekit.agents import Agent, AgentSession, RoomInputOptions
    from livekit.plugins import cartesia, deepgram, silero

    check_ready()
    await ctx.connect()

    conductor = _build_conductor()

    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        tts=cartesia.TTS(),
        vad=silero.VAD.load(),
        # No `llm`: the conductor decides every word the interviewer says.
    )

    finished = asyncio.Event()
    busy = asyncio.Lock()

    @session.on("user_input_transcribed")
    def _on_transcript(event) -> None:
        # Partial transcripts arrive continuously while the candidate is still
        # talking; only a final one is a completed answer.
        if not event.is_final or not event.transcript.strip():
            return
        asyncio.create_task(_advance(event.transcript))

    async def _advance(answer: str) -> None:
        # One turn at a time: a second final transcript arriving mid-assessment
        # would otherwise drive the state machine twice for one answer.
        if busy.locked():
            log.warning("dropped an overlapping transcript while assessing")
            return
        async with busy:
            # The reasoner does network I/O; keep it off the event loop so audio
            # and barge-in stay responsive.
            step = await asyncio.to_thread(conductor.receive, answer)
            await session.say(step.utterance).wait_for_playout()
            if step.done:
                finished.set()

    avatar_on = await _attach_avatar(session, ctx.room)

    await session.start(
        agent=Agent(instructions="Unused — the conductor supplies every utterance."),
        room=ctx.room,
        # The avatar publishes the audio track when present, so the room should
        # not also receive it directly.
        room_input_options=RoomInputOptions(audio_enabled=not avatar_on),
    )

    opening = conductor.open()
    await session.say(opening.utterance).wait_for_playout()

    await finished.wait()
    _write_report(conductor)


def _write_report(conductor: Conductor) -> None:
    scored = score_interview(
        plan=conductor.plan,
        transcript=conductor.transcript,
        evidence=conductor.evidence,
        reasoner=conductor.reasoner,
        mode=conductor.mode,
        session_id=conductor.session_id,
    )
    report = build_report(scored, conductor.plan, conductor.reasoner)
    text = (
        render_coaching_text(report)
        if conductor.mode is Mode.PRACTICE
        else render_screening_text(report)
    )
    print(text)


def main() -> None:
    """Run as a LiveKit worker: `python -m panel.transports.realtime start`."""
    from livekit.agents import WorkerOptions, cli

    check_ready()
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))


if __name__ == "__main__":
    main()
