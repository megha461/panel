import { useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import Setup from './components/Setup.jsx'
import Call from './components/Call.jsx'
import Report from './components/Report.jsx'

const IDLE = 'idle'
const RUNNING = 'running'
const DONE = 'done'

function clock(seconds) {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

export default function App() {
  const [phase, setPhase] = useState(IDLE)
  const [health, setHealth] = useState(null)
  const [session, setSession] = useState(null)
  const [plan, setPlan] = useState(null)
  const [step, setStep] = useState(null)
  const [transcript, setTranscript] = useState([])
  const [report, setReport] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [elapsed, setElapsed] = useState(0)
  const startedAt = useRef(null)

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null))
  }, [])

  useEffect(() => {
    if (phase !== RUNNING) return
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt.current) / 1000))
    }, 1000)
    return () => clearInterval(id)
  }, [phase])

  async function start(body) {
    setBusy(true)
    setError(null)
    try {
      const created = await api.createSession(body)
      setSession(created.session_id)
      setPlan(created.plan)
      setStep(created.step)
      setTranscript([
        { index: 0, speaker: 'interviewer', text: created.step.utterance },
      ])
      startedAt.current = Date.now()
      setElapsed(0)
      setPhase(RUNNING)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function answer(text) {
    setBusy(true)
    setError(null)
    setTranscript((prev) => [
      ...prev,
      { index: prev.length, speaker: 'candidate', text },
    ])
    try {
      const next = await api.answer(session, text)
      setStep(next)
      setTranscript((prev) => [
        ...prev,
        { index: prev.length, speaker: 'interviewer', text: next.utterance },
      ])
      if (next.done) {
        setReport(await api.report(session))
        setPhase(DONE)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  function restart() {
    setPhase(IDLE)
    setSession(null)
    setPlan(null)
    setStep(null)
    setTranscript([])
    setReport(null)
    setError(null)
    setElapsed(0)
  }

  const overTime = plan ? elapsed > plan.target_minutes * 60 : false

  return (
    <div className="shell">
      <header className="topbar">
        <span className="wordmark">Panel</span>
        {plan && <span className="role">{plan.role}</span>}
        <span className="spacer" />
        {plan && <span className="mono">rubric {plan.plan_hash}</span>}
        {phase === RUNNING && (
          <span className={`clock${overTime ? ' over' : ''}`}>{clock(elapsed)}</span>
        )}
      </header>

      {health?.demo_mode && phase !== DONE && (
        <div className="banner">
          No API key set — running the built-in reasoner. The interview works end to
          end; scores are indicative rather than defensible.
        </div>
      )}

      {phase === IDLE && <Setup onStart={start} starting={busy} error={error} />}

      {phase === RUNNING && step && (
        <Call
          plan={plan}
          step={step}
          transcript={transcript}
          thinking={busy}
          error={error}
          onAnswer={answer}
        />
      )}

      {phase === DONE && report && <Report report={report} onRestart={restart} />}
    </div>
  )
}
