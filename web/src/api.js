// Thin client. Errors surface the server's own message — a 409 "the interview is
// already finished" is more useful to read than "Request failed".

// Empty in development, where Vite proxies /api to the local engine. In a
// deployed build VITE_API_URL points at the engine's own origin, because the
// frontend and backend are hosted separately.
const BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(BASE + path, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
  } catch {
    throw new Error(
      BASE
        ? `Can't reach the engine at ${BASE}. It may be asleep — try again in a moment.`
        : "Can't reach the engine. Is it running on port 8040?",
    )
  }

  if (response.status === 204) return null

  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(detailOf(body) || `Request failed (${response.status})`)
  }
  return body
}

function detailOf(body) {
  if (!body?.detail) return null
  if (typeof body.detail === 'string') return body.detail
  // FastAPI validation errors arrive as a list of {loc, msg}.
  if (Array.isArray(body.detail)) {
    return body.detail.map((d) => `${d.loc?.slice(-1)[0] ?? ''} ${d.msg}`.trim()).join('; ')
  }
  return null
}

export const api = {
  health: () => request('/api/health'),
  createSession: (body) =>
    request('/api/sessions', { method: 'POST', body: JSON.stringify(body) }),
  answer: (id, text) =>
    request(`/api/sessions/${id}/answer`, { method: 'POST', body: JSON.stringify({ text }) }),
  report: (id) => request(`/api/sessions/${id}/report`),
  history: (role) =>
    request(`/api/history${role ? `?role=${encodeURIComponent(role)}` : ''}`),
  pastReport: (id) => request(`/api/history/${id}`),
  trends: (planHash) => request(`/api/trends/${planHash}`),
}
