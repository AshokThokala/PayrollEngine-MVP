import { useEffect, useState } from 'react'
import { api } from '../api.js'

function Progress({ percent, label }) {
  return (
    <div className="progress" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <div className="progress-fill" style={{ width: `${percent}%` }} />
    </div>
  )
}

export default function ClientOnboardingPage({ client, platform, tabs, onGo, onPickClient }) {
  const [check, setCheck] = useState(null)
  const [all, setAll] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    setCheck(null)
    api.onboarding(client.id).then(setCheck).catch((e) => setError(e.message))
    if (platform) api.onboardingOverview().then(setAll).catch((e) => setError(e.message))
  }, [client.id, platform])

  return (
    <div className="stack">
      {error && <div className="banner error">{error}</div>}
      {check && (
        <section className="card">
          <div className="run-head">
            <div>
              <h2>{check.client_name}</h2>
              <p className="muted small">
                {check.live ? 'Ready: every onboarding step is complete.' : `Next: ${check.next_step}`}
              </p>
            </div>
            <span className={`tag ${check.live ? 'paid' : 'pending'}`}>
              {check.done} of {check.total} done
            </span>
          </div>
          <Progress percent={check.percent} label={`${check.client_name} onboarding progress`} />
          <ol className="checklist">
            {check.steps.map((s, i) => (
              <li key={s.key} className={s.done ? 'done' : ''}>
                <span className="check-mark" aria-hidden="true">{s.done ? '✓' : i + 1}</span>
                <div className="check-body">
                  <strong>{s.title}</strong>
                  <span className="muted small">{s.description}</span>
                  <span className={s.done ? 'small ok-text' : 'small warn-text'}>{s.detail}</span>
                </div>
                {!s.done && tabs.includes(s.action) && (
                  <button className="primary" onClick={() => onGo(s.action)}>Go</button>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}

      {platform && all.length > 0 && (
        <section className="card">
          <h2>All clients</h2>
          <p className="muted small">Least complete first. Click a client to open its checklist.</p>
          <div className="table-wrap">
            <table className="clickable">
              <thead>
                <tr><th>Client</th><th>Progress</th><th>Next step</th></tr>
              </thead>
              <tbody>
                {all.map((r) => (
                  <tr key={r.client_id} className={r.client_id === client.id ? 'selected' : undefined}
                      onClick={() => onPickClient(r.client_id)}>
                    <td>{r.client_name}</td>
                    <td className="progress-cell">
                      <Progress percent={r.percent} label={`${r.client_name} progress`} />
                      <span className="muted small">{r.done}/{r.total}</span>
                    </td>
                    <td>{r.live ? <span className="tag paid">live</span> : r.next_step}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}
