# Panel — AI Interview Engine

**Date:** 2026-08-19
**Status:** Approved, in implementation

## Purpose

One interview engine, two modes:

- **Practice mode** — the user is the candidate. Output is coaching feedback.
- **Screening mode** — someone else is the candidate. Output is an evidence-cited scorecard.

Both run the same conduct-and-score pipeline. Only the final rendering differs.

## The core bet

Interview quality is determined by the **rubric layer**, not the model.

Published evidence on LLM-as-judge scoring:

| Setup | Correlation with human experts |
|---|---|
| Unanchored "rate 1–5" | r ≈ 0.20 |
| Behaviorally-anchored rubric | r ≈ 0.63 |
| + reference answers w/ annotated critical points | > 0.89 agreement across judge tiers |

So the architecture encodes three rules, borrowed from evidence-grounded evaluation research:

1. **Fixed criteria.** The rubric is compiled before the interview and frozen.
2. **Traceable evidence.** Every score cites transcript spans. No citation, no score.
3. **Calibrated interpretation.** Rubric levels are behavioral anchors, not adjectives.

## Architecture

The valuable core is transport-agnostic. The engine consumes text turns and emits
text turns plus a control decision. Audio, video, and avatars are I/O concerns that
wrap it — they never leak inward.

```
resume + JD + type
        |
        v
  [ PlanCompiler ] ──> InterviewPlan (versioned, content-hashed, FROZEN)
                              |
                              v
   candidate turn ──> [ Conductor ] ──> interviewer turn + decision
                              |              (ASK | PROBE | ADVANCE | CLOSE)
                              v
                        [ Transcript ]
                              |
                              v
                     [ EvidenceExtractor ] ──> Evidence[] (competency + span)
                              |
                              v
                        [ BarsScorer ] ──> CompetencyScore[] (cited)
                              |
              +---------------+---------------+
              v                               v
      [ CoachingReport ]              [ ScreeningReport ]
        (practice mode)                 (screening mode)
```

### Why transport-agnostic

- The whole engine is testable with no audio, no keys, in milliseconds.
- Rubric iteration — the thing that sets the quality ceiling — costs nothing.
- Cheap-by-default: text transport bills nothing; avatar is an explicit opt-in.
- Live coding later becomes a new *plan type*, not a rewrite.

## Components

### 1. PlanCompiler (`panel/planning/`)

Input: resume text, job description, interview type, target duration.
Output: an `InterviewPlan`.

The plan holds competencies; each competency holds behaviorally-anchored rubric
levels (1–4, each with an observable descriptor), planned questions, the critical
points a strong answer must contain, and a time budget.

The plan is content-hashed at compile time. The hash goes into every score record,
so any scorecard can be traced to the exact criteria that produced it.

`CompetencyLibrary` supplies vetted defaults so a usable plan exists with no LLM at all.

### 2. Conductor (`panel/engine/`)

A state machine over the plan. After each candidate turn it decides:

- `ASK` — move to the next planned question
- `PROBE` — the answer missed critical points or was vague; dig into this one
- `ADVANCE` — competency satisfied or time budget spent; next competency
- `CLOSE` — plan exhausted or overall time spent

Constraint: the conductor can only act **within** the frozen plan. It chooses which
question and how deep, never what to assess.

**Two budgets, not one** (added during implementation — the first build had only the
global one and was visibly wrong). A global exchange budget bounds the interview;
a per-competency budget bounds any single topic to its share. Without the second,
the conductor is depth-first: it probes the opening competency until the clock dies
and never asks about the rest, producing a confident score on one area and NOT
OBSERVED everywhere else. In a 30-minute mixed interview that meant 2 of 5
competencies assessed. Breadth first, depth second — an interview that covered two
of five competencies is a worse interview however good those two scores are.

Probe depth is additionally capped per question so one answer cannot stall a topic.

### 3. EvidenceExtractor + BarsScorer (`panel/scoring/`)

Extraction runs per answer, off the latency path. It links claims to
`(competency_id, turn_index, quoted span)`.

Scoring runs post-interview, per competency, against that competency's anchors,
consuming only extracted evidence. A competency with no evidence scores
`NOT_OBSERVED` — never a guessed number. This is what stops the model
from inventing a score for something it never asked about.

### 4. Reports (`panel/scoring/report.py`)

One `ScoredInterview`, two renderings. Practice mode gets strengths, gaps, what a
stronger answer contains, and drill suggestions. Screening mode gets a per-competency
scorecard with citations, coverage warnings, and an overall recommendation.

## Fairness / compliance stance

Personal use is outside NYC Local Law 144 and the EU AI Act. But the design keeps the
door open, because retrofitting audit trails is painful:

- Every score is evidence-cited and traceable to a frozen rubric version.
- Interviews are append-only records.
- **No webcam affect, emotion, or body-language scoring.** Weak evidence base, and
  the EU AI Act bans emotion recognition in the workplace. Video is for realism and
  self-review only — it is never a scored signal.

## Stack

- Python 3.12, Pydantic v2 domain models, SQLite storage
- Anthropic API for planning/probing/scoring, with a deterministic demo provider
- Realtime layer (phase 2): LiveKit Agents — streaming STT→LLM→TTS with turn
  detection and barge-in; avatar via LiveKit's swappable avatar plugin layer
- React + Vite frontend (phase 2)

Host constraint: Intel x86_64 Mac. No PyTorch. Local STT, if ever needed, must be
faster-whisper / whisper.cpp.

## Build order

1. Domain models + rubric library
2. LLM provider layer w/ demo mode
3. Plan compiler
4. Conductor
5. Extractor + scorer
6. Reports
7. Text transport + CLI — **verify: full interview end-to-end, no API key**
8. *(phase 2)* FastAPI + React video-call UI
9. *(phase 2)* LiveKit realtime voice + avatar
10. *(phase 3)* Live coding interview type

## Non-goals

- Body-language / affect scoring (excluded on purpose, see above)
- ATS integration, candidate sourcing, scheduling
- Multi-tenant SaaS concerns
