import { useEffect, useRef, useState } from 'react'
import Selfie from './Selfie.jsx'

export default function Call({ plan, step, transcript, thinking, error, onAnswer }) {
  const [draft, setDraft] = useState('')
  const transcriptRef = useRef(null)
  const composerRef = useRef(null)

  // Follow the conversation, and put the caret back after each exchange.
  useEffect(() => {
    const el = transcriptRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [transcript.length])

  useEffect(() => {
    if (!thinking) composerRef.current?.focus()
  }, [thinking, step.question_id])

  function send() {
    const text = draft.trim()
    if (!text || thinking) return
    setDraft('')
    onAnswer(text)
  }

  function onKeyDown(event) {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault()
      send()
    }
  }

  const { progress } = step

  return (
    <div className="call">
      <div className="stage">
        <div className="tile">
          {/* Slot for the realtime avatar video; a speaking indicator stands in. */}
          <div className="avatar-slot">
            <div className={`speaking${thinking ? '' : ' idle'}`} aria-hidden="true">
              <i /><i /><i /><i /><i />
            </div>
            <span className="tile-label">
              {thinking ? 'Interviewer is thinking' : 'Interviewer'}
            </span>
          </div>
          <Selfie />
        </div>

        <p className="question">
          {step.is_probe && <span className="probe-tag">Follow-up</span>}
          {step.utterance}
        </p>

        <div>
          <div className="composer">
            <textarea
              ref={composerRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              disabled={thinking}
              placeholder="Answer out loud, then type the gist — concrete examples score better than general descriptions."
              aria-label="Your answer"
            />
            <button onClick={send} disabled={thinking || !draft.trim()}>
              {thinking ? 'Sending…' : 'Answer'}
            </button>
          </div>
          <p className="hint">⌘ + Enter to send</p>
          {error && <div className="error">{error}</div>}
        </div>
      </div>

      <aside className="rail">
        <section>
          <h2>Progress</h2>
          <div className="pips" aria-hidden="true">
            {Array.from({ length: progress.competency_total }, (_, i) => (
              <i
                key={i}
                className={
                  i < progress.competency_index ? 'done' : i === progress.competency_index ? 'now' : ''
                }
              />
            ))}
          </div>
          <p className="meta">
            <b>{progress.competency_name ?? '—'}</b>
            <br />
            Area {Math.min(progress.competency_index + 1, progress.competency_total)} of{' '}
            {progress.competency_total} · exchange {progress.exchanges} of{' '}
            {progress.exchange_budget}
          </p>
        </section>

        <section>
          <h2>Assessing</h2>
          <p className="meta">{plan.competencies.join(' · ')}</p>
        </section>

        <div className="transcript" ref={transcriptRef}>
          <h2>Transcript</h2>
          {transcript.map((turn) => (
            <div key={turn.index} className={`turn ${turn.speaker}`}>
              <span className="idx">{String(turn.index).padStart(2, '0')}</span>
              <div>
                <span className="who">
                  {turn.speaker === 'candidate' ? 'You' : 'Interviewer'}
                </span>
                <div className="body">{turn.text}</div>
              </div>
            </div>
          ))}
        </div>
      </aside>
    </div>
  )
}
