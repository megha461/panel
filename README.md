# Panel

An AI interview engine with two modes over one pipeline:

- **Practice** — you're the candidate. Output is coaching feedback.
- **Screening** — someone else is. Output is an evidence-cited scorecard.

Runs with no API key.

```bash
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/panel demo
```

## Why it's built this way

Interview quality is set by the **rubric layer**, not the model. Published results on
LLM-as-judge scoring:

| Setup | Correlation with human experts |
|---|---|
| Unanchored "rate 1–5" | r ≈ 0.20 |
| Behaviorally-anchored rubric | r ≈ 0.63 |
| + reference answers with annotated critical points | > 0.89 across judge tiers |

So three rules are structural rather than requested politely in a prompt:

1. **Criteria are frozen.** The plan is compiled and content-hashed before the
   interview. The conductor picks which planned question to ask and how deep to
   probe; it cannot add a competency or edit an anchor mid-interview. Two runs
   against the same `plan_hash` were assessed identically — that's what makes
   scores comparable and a scorecard auditable.
2. **No citation, no score.** `CompetencyScore` raises if given a level without
   supporting evidence. Quotes from the LLM path are verified against the
   transcript and dropped if not found — a fabricated citation is worse than none,
   because it makes an unsupported score look defensible.
3. **Not-observed is distinct from low.** A competency the interview never
   surfaced evidence for scores `None`, is excluded from the overall (not counted
   as zero), and is reported separately. Coverage is always shown.

## Usage

### Terminal

```bash
panel practice --role "Backend Engineer" --type behavioral --minutes 20
panel screen   --role "Backend Engineer" --resume cv.txt --jd role.txt
panel demo
```

`--type` is `behavioral`, `technical_verbal`, or `mixed`.

### History

```bash
panel history
```

Completed interviews are recorded to SQLite (`data/panel.db`), append-only — there
is no update or delete path, because a scorecard you can quietly edit afterwards
isn't a record. `panel history` lists past runs and shows per-competency progress;
the web UI has the same view.

**Progress is only shown within one `plan_hash`.** Two interviews compiled from
different criteria produce scores that look comparable and aren't, and charting
them on one line would launder that past you. Comparability is what freezing the
plan bought — spending it here would waste it.

Not-observed stays NULL all the way into SQL, so `AVG` skips it. A competency the
interview never reached is never averaged in as a zero.

### Video-call UI

```bash
./dev.sh
```

Engine on :8040, web app on :5193. The call is a real video-call layout — your
camera in the corner, an interviewer tile, live transcript, timer — with answers
typed until the voice layer lands. Your camera stream stays in the browser: it is
never uploaded, recorded, or scored.

The report inverts to a paper surface, because it is a different object from the
conversation: a record you file rather than a call you sit in. Every score carries
its citations, and clicking one jumps to the exact turn it came from.

## Architecture

The engine consumes text turns and emits text turns plus a control decision. Audio,
video, and avatars are transports that wrap it — they never leak inward. That's why
the full suite runs in under half a second with no key and no network.

```
resume + JD ─→ [PlanCompiler] ─→ InterviewPlan (hashed, FROZEN)
                                        │
        candidate turn ─→ [Conductor] ─→ interviewer turn + ASK|PROBE|ADVANCE|CLOSE
                                        │
                                  [Transcript] ─→ [BarsScorer] ─→ cited scores
                                                        │
                                    ┌───────────────────┴──────────────────┐
                              CoachingReport                        ScreeningReport
```

## Demo mode

With no `ANTHROPIC_API_KEY`, a heuristic reasoner runs the same interfaces. It is
signal detection, not an imitation of a language model — it looks for the six
observable markers the rubrics are written around (specificity, first-person
agency, stated outcomes, considered alternatives, reflection, method) and reports
honestly on what it can't see.

**Its recall and precision are both genuinely lower than the LLM path.** Anchors
phrased outside those seven signals may extract no evidence from a strong answer,
and because it falls back to token overlap it can still attach a quote to the wrong
critical point. Treat heuristic-mode levels as indicative, not defensible.

It will not, however, cite one span under two different claims: quote selection
prefers a span not already used for another point in the same answer, and where a
sentence genuinely evidences two points the report shows it once with both claims.

It exists so the rubric layer — where quality actually lives — can be iterated for
free, and so the tests are deterministic. It is not the product.

## Compliance stance

Personal use sits outside NYC Local Law 144 and the EU AI Act, but the audit surface
is built in because retrofitting it is painful: scores are evidence-cited, traceable
to a frozen rubric version, and interviews are append-only.

**No webcam affect, emotion, or body-language scoring** — deliberately excluded. It's
the weakest-evidence part of commercial AI interviewing and the EU AI Act bans
emotion recognition in the workplace. Video is for realism and self-review, never a
scored signal.

## Realtime voice — scaffolded, not verified

`panel/transports/realtime.py` drives the same conductor over LiveKit Agents. It is
written against livekit-agents 1.6.10 with the API surface verified by
introspection, but **it has never been run against a live room** — that needs paid
credentials this machine doesn't have. The credential gate is tested; the call path
is not. Treat it as reviewed scaffolding.

The design decision in it is worth knowing: **there is no LLM in the voice loop.**
LiveKit's usual shape is STT → LLM → TTS, with the model choosing what to say. That
would let it improvise questions outside the frozen plan and break the guarantee
that two candidates were assessed against identical criteria. `AgentSession` takes
`llm` as optional, so the wiring is STT → Conductor → TTS. The reasoner still runs,
just off the speech path where its latency can't stall the conversation.

To try it:

```bash
pip install -e ".[realtime]"
```

Then set `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `DEEPGRAM_API_KEY`,
`CARTESIA_API_KEY`, `ANTHROPIC_API_KEY`. Missing ones are reported by name with what
each buys. Avatars are off by default (`PANEL_AVATAR=none`) because they bill
$0.10–$0.37 per active minute; set `tavus`, `anam`, `simli`, or `hedra` plus that
provider's key to turn one on.

## Status

Verified: domain models, rubric library, plan compiler, conductor, extractor,
scorer, both reports, text transport, CLI, HTTP API, video-call UI, persistence
and history. 81 tests.

Scaffolded but unverified: realtime voice + avatar.

Not started: live-coding interview type.

Known limitation: an interview *in progress* lives only in memory, so restarting
the server loses it. Finished interviews are persisted. Resuming a half-finished
interview isn't supported.

```bash
.venv/bin/python -m pytest
```
