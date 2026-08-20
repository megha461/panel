import { useRef, useState } from 'react'

const LEVELS = 4

function Scale({ level }) {
  const none = level === null || level === undefined
  return (
    <div className={`scale${none ? ' none' : ''}`} aria-hidden="true">
      {Array.from({ length: LEVELS }, (_, i) => (
        <i key={i} className={!none && i < level ? 'on' : ''} />
      ))}
    </div>
  )
}

// One sentence can genuinely evidence two critical points, so the same span can
// arrive twice with different claims. Show the quote once with each claim under
// it — repeating the quote reads as padded evidence even when detection is right.
function groupCitations(items) {
  const grouped = new Map()
  for (const e of items) {
    const key = `${e.turn_index}::${e.quote}`
    if (!grouped.has(key)) {
      grouped.set(key, { turn_index: e.turn_index, quote: e.quote, against: e.against, claims: [] })
    }
    grouped.get(key).claims.push(e.claim)
  }
  return [...grouped.values()]
}

export default function Report({ report, onRestart, restartLabel = 'New interview' }) {
  // The signature: clicking a citation lights the turn it came from and brings it
  // into view, so a score can always be walked back to the thing the candidate
  // actually said.
  const [lit, setLit] = useState(null)
  const turnRefs = useRef({})
  const scrollerRef = useRef(null)

  function reveal(index) {
    setLit(index)
    const scroller = scrollerRef.current
    const target = turnRefs.current[index]
    if (!scroller || !target) return

    // Absolute target from offsetTop, not a delta from getBoundingClientRect:
    // CSS scroll-behavior animates programmatic assignment too, so a delta
    // computed from the live rect reads a mid-flight position and lands wrong
    // when citations are clicked in quick succession. `.report` is positioned,
    // so offsetTop resolves against it.
    scroller.scrollTop =
      target.offsetTop - scroller.clientHeight / 2 + target.offsetHeight / 2
  }

  const practice = report.mode === 'practice'
  const pct = Math.round(report.coverage * 100)

  return (
    <div className="report" ref={scrollerRef}>
      <div className="report-inner">
        <h1>{practice ? 'Your feedback' : 'Scorecard'}</h1>
        <p className="subhead">
          {report.role} · rubric {report.plan_hash} · session {report.session_id}
        </p>

        <div className="summary">
          <div>
            <span className="k">Overall</span>
            <span className="v">
              {report.overall === null ? '—' : report.overall}
              {report.overall !== null && <small> / 4</small>}
            </span>
          </div>
          <div>
            <span className="k">Coverage</span>
            <span className="v">
              {pct}
              <small>%</small>
            </span>
          </div>
          <div>
            <span className="k">Assessed</span>
            <span className="v">
              {report.observed_count}
              <small> / {report.total_count}</small>
            </span>
          </div>
        </div>

        <p className="verdict">{report.recommendation}</p>

        {report.competencies.map((c) => (
          <section key={c.competency_id} className={`comp${c.level === null ? ' unobserved' : ''}`}>
            <div className="comp-head">
              <h3>{c.name}</h3>
              <Scale level={c.level} />
              <span className="label">{c.level === null ? 'Not observed' : c.label}</span>
            </div>
            <p className="rationale">{c.rationale}</p>

            {(c.supporting.length > 0 || c.undermining.length > 0) && (
              <div className="evidence">
                {groupCitations([
                  ...c.supporting,
                  ...c.undermining.map((e) => ({ ...e, against: true })),
                ]).map((e, i) => (
                  <button
                    key={`${e.turn_index}-${i}`}
                    className={`cite${e.against ? ' against' : ''}`}
                    onClick={() => reveal(e.turn_index)}
                    onFocus={() => setLit(e.turn_index)}
                  >
                    <span className="tag">T{String(e.turn_index).padStart(2, '0')}</span>
                    <span>
                      <blockquote>“{e.quote}”</blockquote>
                      {e.claims.map((claim, j) => (
                        <span className="claim" key={j}>
                          {claim}
                        </span>
                      ))}
                    </span>
                  </button>
                ))}
              </div>
            )}

            {c.coaching && (
              <div className="coach">
                {c.coaching.strengths.length > 0 && (
                  <div>
                    <h4>What worked</h4>
                    <ul>
                      {c.coaching.strengths.map((s, i) => (
                        <li key={i}>{s}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {c.coaching.gaps.length > 0 && (
                  <div>
                    <h4>What was missing</h4>
                    <ul>
                      {c.coaching.gaps.map((g, i) => (
                        <li key={i}>{g}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {c.coaching.stronger_answer && (
                  <div>
                    <h4>To reach the top anchor</h4>
                    <p>{c.coaching.stronger_answer}</p>
                  </div>
                )}
                {c.coaching.drill && (
                  <div>
                    <h4>Drill</h4>
                    <p>{c.coaching.drill}</p>
                  </div>
                )}
              </div>
            )}
          </section>
        ))}

        <div className="full-transcript">
          <h2>Transcript</h2>
          {report.transcript.turns.map((turn) => (
            <div
              key={turn.index}
              ref={(el) => (turnRefs.current[turn.index] = el)}
              className={`ft-turn${lit === turn.index ? ' lit' : ''}`}
            >
              <span className="idx">T{String(turn.index).padStart(2, '0')}</span>
              <div>
                <span className="who">
                  {turn.speaker === 'candidate' ? 'Candidate' : 'Interviewer'}
                </span>
                {turn.text}
              </div>
            </div>
          ))}
        </div>

        <div className="actions">
          <button onClick={onRestart}>{restartLabel}</button>
        </div>

        <p className="footnote">
          Scores reflect evidence gathered in this interview only. Competencies marked
          not observed were never assessed and are excluded from the overall — they are
          not weaknesses. Camera video is never recorded, uploaded, or scored.
        </p>
      </div>
    </div>
  )
}
