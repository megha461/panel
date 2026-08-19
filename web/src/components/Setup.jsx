import { useState } from 'react'

const TYPES = [
  ['mixed', 'Mixed'],
  ['behavioral', 'Behavioural'],
  ['technical_verbal', 'Technical (verbal)'],
]

export default function Setup({ onStart, starting, error }) {
  const [role, setRole] = useState('Senior Backend Engineer')
  const [interviewType, setInterviewType] = useState('mixed')
  const [minutes, setMinutes] = useState(20)
  const [mode, setMode] = useState('practice')
  const [jd, setJd] = useState('')
  const [resume, setResume] = useState('')

  function submit(event) {
    event.preventDefault()
    onStart({
      role: role.trim() || 'Software Engineer',
      interview_type: interviewType,
      minutes: Number(minutes),
      mode,
      job_description: jd,
      resume,
    })
  }

  return (
    <div className="setup-wrap">
      <form className="setup" onSubmit={submit}>
        <h1>Set up the interview</h1>
        <p className="lede">
          Questions and the rubric are compiled and frozen before the first question.
          Every score cites the transcript.
        </p>

        <div className="field">
          <label htmlFor="role">Role</label>
          <input
            id="role"
            type="text"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            placeholder="Senior Backend Engineer"
          />
        </div>

        <div className="row">
          <div className="field">
            <label htmlFor="type">Focus</label>
            <select
              id="type"
              value={interviewType}
              onChange={(e) => setInterviewType(e.target.value)}
            >
              {TYPES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="minutes">Length</label>
            <select
              id="minutes"
              value={minutes}
              onChange={(e) => setMinutes(e.target.value)}
            >
              {[10, 20, 30, 45, 60].map((m) => (
                <option key={m} value={m}>
                  {m} minutes
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="field">
          <label>Who is answering</label>
          <div className="modes">
            <button
              type="button"
              className="mode"
              aria-pressed={mode === 'practice'}
              onClick={() => setMode('practice')}
            >
              <strong>I am</strong>
              <span>Practice. You get coaching on what was missing.</span>
            </button>
            <button
              type="button"
              className="mode"
              aria-pressed={mode === 'screening'}
              onClick={() => setMode('screening')}
            >
              <strong>Someone else</strong>
              <span>Screening. You get an evidence-cited scorecard.</span>
            </button>
          </div>
        </div>

        <div className="field">
          <label htmlFor="jd">Job description — optional</label>
          <textarea
            id="jd"
            value={jd}
            onChange={(e) => setJd(e.target.value)}
            placeholder="Paste it to have questions drafted against the real role."
          />
        </div>

        <div className="field">
          <label htmlFor="resume">Résumé — optional</label>
          <textarea
            id="resume"
            value={resume}
            onChange={(e) => setResume(e.target.value)}
            placeholder="Paste it to have questions drafted against actual experience."
          />
        </div>

        <button className="primary" type="submit" disabled={starting}>
          {starting ? 'Compiling the plan…' : 'Start interview'}
        </button>

        {error && <div className="error">{error}</div>}
      </form>
    </div>
  )
}
