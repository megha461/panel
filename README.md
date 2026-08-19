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

```bash
panel practice --role "Backend Engineer" --type behavioral --minutes 20
panel screen   --role "Backend Engineer" --resume cv.txt --jd role.txt
panel demo                                    # scripted, deterministic, no key
```

`--type` is `behavioral`, `technical_verbal`, or `mixed`.

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
phrased outside those six signals may extract no evidence from a strong answer, and
because it falls back to token overlap it will sometimes attach a real quote to the
wrong critical point. Treat heuristic-mode levels as indicative, not defensible.

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

## Status

Built: domain models, rubric library, plan compiler, conductor, extractor, scorer,
both reports, text transport, CLI. 39 tests.

Next: FastAPI + React video-call UI; LiveKit realtime voice with a swappable avatar
plugin; live-coding interview type.

```bash
.venv/bin/python -m pytest
```
