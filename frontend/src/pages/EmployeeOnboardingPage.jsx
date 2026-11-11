import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { ProfileFacts, StageTag } from '../components/ProfileFields.jsx'

const fmt = (iso) => (iso ? new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '—')
const FILTERS = [
  ['all', 'All'],
  ['todo', 'Needs action'],
  ['progress', 'In progress'],
  ['verified', 'Verified'],
]
const inFilter = (f, stage) =>
  f === 'all' ||
  (f === 'todo' && ['not_invited', 'invite_expired', 'submitted'].includes(stage)) ||
  (f === 'progress' && ['invited', 'registered', 'pending', 'returned'].includes(stage)) ||
  (f === 'verified' && stage === 'verified')

export default function EmployeeOnboardingPage({ client }) {
  const [rows, setRows] = useState([])
  const [filter, setFilter] = useState('all')
  const [selected, setSelected] = useState(null)
  const [email, setEmail] = useState('')
  const [link, setLink] = useState(null)
  const [profile, setProfile] = useState(null)
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [errors, setErrors] = useState({})
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    try {
      setRows(await api.employeeOnboarding(client.id))
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }, [client.id])

  useEffect(() => {
    setSelected(null)
    load()
  }, [load])

  const row = rows.find((r) => r.employee_code === selected)

  useEffect(() => {
    setLink(null)
    setNote('')
    setErrors({})
    setProfile(null)
    setEmail(row?.email || '')
    if (row && ['submitted', 'returned', 'verified'].includes(row.stage)) {
      api.employeeProfile(client.id, row.employee_code).then(setProfile).catch((e) => setError(e.message))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, row?.stage])

  async function invite(e) {
    e.preventDefault()
    setErrors({})
    try {
      const res = await api.inviteEmployee(client.id, row.employee_code, email)
      setLink(`${window.location.origin}${res.path}`)
      setNotice(`Invite link made for ${row.name}. Copy it and send it to ${res.email}; it works once, for 7 days.`)
      await load()
    } catch (err) {
      setErrors(err.fieldErrors || {})
      setError(err.message)
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(link)
      setNotice('Link copied.')
    } catch {
      setNotice('Select the link and copy it.')
    }
  }

  async function revoke() {
    try {
      await api.revokeInvite(row.invite_id)
      setNotice('Invite cancelled; the link no longer works.')
      setLink(null)
      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  async function review(decision) {
    setErrors({})
    try {
      await api.reviewProfile(client.id, row.employee_code, decision, note)
      setNotice(decision === 'verify' ? `${row.name}'s details are verified.` : `Sent back to ${row.name} with your note.`)
      await load()
    } catch (e) {
      setErrors(e.fieldErrors || {})
      setError(e.message)
    }
  }

  const counts = FILTERS.map(([f]) => rows.filter((r) => inFilter(f, r.stage)).length)
  const shown = rows.filter((r) => inFilter(filter, r.stage))

  return (
    <div className="stack">
      {error && <div className="banner error">{error}</div>}
      {notice && <div className="banner ok">{notice}</div>}
      <div className="grid">
        <section className="card">
          <h2>Employees</h2>
          <div className="segmented small-seg" role="tablist">
            {FILTERS.map(([f, label], i) => (
              <button key={f} role="tab" aria-selected={filter === f} className={filter === f ? 'active' : ''} onClick={() => setFilter(f)}>
                {label} <span className="muted">{counts[i]}</span>
              </button>
            ))}
          </div>
          {shown.length === 0 ? (
            <p className="muted">{rows.length ? 'Nobody here.' : 'Add employees first on the Employees page.'}</p>
          ) : (
            <div className="table-wrap">
              <table className="clickable">
                <thead><tr><th>Employee</th><th>Status</th></tr></thead>
                <tbody>
                  {shown.map((r) => (
                    <tr key={r.employee_code} className={r.employee_code === selected ? 'selected' : undefined}
                        tabIndex={0} onClick={() => setSelected(r.employee_code)}
                        onKeyDown={(e) => e.key === 'Enter' && setSelected(r.employee_code)}>
                      <td><strong>{r.name}</strong><br /><span className="muted small">{r.employee_code}{r.email ? ` · ${r.email}` : ''}</span></td>
                      <td><StageTag stage={r.stage} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="card">
          {!row ? (
            <>
              <h2>How it works</h2>
              <ol className="steps-list">
                <li><strong>Invite</strong> — pick an employee and make an invite link for their email.</li>
                <li><strong>Register</strong> — they open the link, set a password and are logged in.</li>
                <li><strong>Onboard</strong> — they fill in contact details, PAN, UAN/ESI and bank account, then submit.</li>
                <li><strong>Verify</strong> — you check the details here, then verify or send them back with a note.</li>
              </ol>
            </>
          ) : (
            <>
              <div className="run-head">
                <div>
                  <h2>{row.name}</h2>
                  <p className="muted small">{row.employee_code}</p>
                </div>
                <StageTag stage={row.stage} />
              </div>

              {['not_invited', 'invited', 'invite_expired'].includes(row.stage) && (
                <form className="form" onSubmit={invite}>
                  {row.stage === 'invited' && (
                    <p className="muted small">Invite sent to {row.email}, valid until {fmt(row.invite_expires_at)}. Making a new one cancels the old link.</p>
                  )}
                  <label>
                    Employee's email
                    <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className={errors.email ? 'invalid' : undefined} placeholder="name@company.in" />
                    {errors.email && <span className="field-error">Email: {errors.email}</span>}
                  </label>
                  <div className="actions">
                    <button className="primary" type="submit">{row.stage === 'not_invited' ? 'Make invite link' : 'Make a new link'}</button>
                    {row.invite_id && row.stage === 'invited' && <button type="button" onClick={revoke}>Cancel invite</button>}
                  </div>
                  {link && (
                    <div className="copy-link">
                      <input value={link} readOnly onFocus={(e) => e.target.select()} aria-label="Invite link" />
                      <button type="button" onClick={copy}>Copy</button>
                    </div>
                  )}
                  <p className="muted small">ClearPay4U does not send emails yet: send the link yourself (email, WhatsApp). The link is shown only once.</p>
                </form>
              )}

              {['registered', 'pending'].includes(row.stage) && (
                <p className="muted">{row.name} has a login and is filling in their joining details. They appear as <em>Submitted</em> when ready for you.</p>
              )}

              {row.stage === 'returned' && <div className="banner warn">Sent back: {row.note}</div>}

              {profile && ['submitted', 'returned', 'verified'].includes(row.stage) && (
                <>
                  <ProfileFacts profile={profile} />
                  {row.stage === 'verified' && <p className="small ok-text">Verified by {profile.verified_by} on {fmt(profile.verified_at)}.</p>}
                  {row.stage === 'submitted' && (
                    <div className="form section">
                      <label>
                        Note to employee (needed to send back)
                        <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} className={errors.note ? 'invalid' : undefined}
                          placeholder="e.g. IFSC does not match the bank name" />
                        {errors.note && <span className="field-error">Note: {errors.note}</span>}
                      </label>
                      <div className="actions">
                        <button className="primary" onClick={() => review('verify')}>Verify details</button>
                        <button onClick={() => review('return')}>Send back</button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  )
}
