import { useEffect, useState } from 'react'
import { api } from '../api.js'

const LEVELS = 4

function when(iso) {
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? iso.slice(0, 16).replace('T', ' ')
    : d.toLocaleString(undefined, {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      })
}

function Delta({ points }) {
  const seen = points.filter((p) => p.level !== null).map((p) => p.level)
  if (seen.length < 2) return <span className="delta flat">—</span>
  const change = seen[seen.length - 1] - seen[0]
  if (change === 0) return <span className="delta flat">no change</span>
  return (
    <span className={`delta ${change > 0 ? 'up' : 'down'}`}>
      {change > 0 ? '+' : ''}
      {change}
    </span>
  )
}

export default function History({ onOpen, onBack }) {
  const [interviews, setInterviews] = useState(null)
  const [trends, setTrends] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const list = await api.history()
        if (cancelled) return
        setInterviews(list.interviews)
        if (list.interviews.length > 0) {
          // Trends are scoped to one rubric; the newest run picks which.
          const t = await api.trends(list.interviews[0].plan_hash)
          if (!cancelled) setTrends(t)
        }
      } catch (err) {
        if (!cancelled) setError(err.message)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="report">
      <div className="report-inner">
        <h1>Interviews</h1>
        <p className="subhead">Every completed interview, most recent first</p>

        {error && <div className="error">{error}</div>}
        {interviews === null && !error && <p className="rationale">Loading…</p>}

        {interviews?.length === 0 && (
          <p className="verdict">
            Nothing recorded yet. Finish an interview and it lands here — two runs
            against the same rubric are enough to see a trend.
          </p>
        )}

        {trends && trends.runs > 1 && (
          <section className="trends">
            <h2>
              Progress across {trends.runs} runs · rubric {trends.plan_hash}
            </h2>
            {trends.competencies.map((c) => (
              <div className="trend-row" key={c.competency_id}>
                <span className="trend-name">{c.name}</span>
                <span className="trend-runs">
                  {c.points.map((p, i) => (
                    <span
                      key={i}
                      className={`trend-cell${p.level === null ? ' none' : ''}`}
                      title={
                        p.level === null
                          ? 'Not observed in this run'
                          : `Level ${p.level} of ${LEVELS}`
                      }
                    >
                      {p.level === null ? '·' : p.level}
                    </span>
                  ))}
                </span>
                <Delta points={c.points} />
              </div>
            ))}
            <p className="footnote">{trends.note}</p>
          </section>
        )}

        {trends && trends.runs === 1 && (
          <p className="verdict">
            One run against rubric {trends.plan_hash}. Do another with the same role
            and focus to see whether anything moved.
          </p>
        )}

        {interviews?.length > 0 && (
          <table className="history">
            <thead>
              <tr>
                <th>When</th>
                <th>Role</th>
                <th>Mode</th>
                <th>Overall</th>
                <th>Coverage</th>
                <th>Rubric</th>
              </tr>
            </thead>
            <tbody>
              {interviews.map((row) => (
                <tr key={row.id} onClick={() => onOpen(row.id)} tabIndex={0}
                    onKeyDown={(e) => e.key === 'Enter' && onOpen(row.id)}>
                  <td>{when(row.created_at)}</td>
                  <td>{row.role}</td>
                  <td>{row.mode}</td>
                  <td className="num">{row.overall === null ? '—' : `${row.overall}/4`}</td>
                  <td className="num">{Math.round(row.coverage * 100)}%</td>
                  <td className="hash">{row.plan_hash}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div className="actions">
          <button onClick={onBack}>New interview</button>
        </div>
      </div>
    </div>
  )
}
