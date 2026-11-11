import { useEffect, useState } from 'react'
import { api } from '../api.js'

// Opened from an invite link: the employee sets a name and password and is logged in.
export default function InviteRegistration({ token, onDone }) {
  const [invite, setInvite] = useState(null)
  const [problem, setProblem] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.inviteDetails(token)
      .then((i) => {
        setInvite(i)
        setName(i.employee_name)
      })
      .catch((e) => setProblem(e.message))
  }, [token])

  async function submit(e) {
    e.preventDefault()
    setErrors({})
    setMessage('')
    if (password !== confirm) {
      setErrors({ confirm: 'The passwords do not match' })
      return
    }
    setBusy(true)
    try {
      onDone(await api.acceptInvite(token, { name, password }))
    } catch (err) {
      setErrors(err.fieldErrors || {})
      setMessage(err.message)
    } finally {
      setBusy(false)
    }
  }

  const err = (k, label) => errors[k] && <span className="field-error">{label}: {errors[k]}</span>

  return (
    <div className="auth">
      <section className="auth-hero">
        <div className="brand big">
          <span className="logo">C4U</span>
          <span>ClearPay4U<span className="tagline">zero-penalty payroll</span></span>
        </div>
        <h1>{invite ? `Welcome to ${invite.client_name}'s payroll.` : 'Join your employer on ClearPay4U.'}</h1>
        <ul className="perks">
          <li><span className="tick" aria-hidden="true">1</span><span><strong>Create your login</strong> — takes a minute</span></li>
          <li><span className="tick" aria-hidden="true">2</span><span><strong>Fill in your joining details</strong> — contact, PAN, UAN and bank</span></li>
          <li><span className="tick" aria-hidden="true">3</span><span><strong>See your payslips</strong> and declare your tax savings</span></li>
        </ul>
      </section>
      <section className="auth-panel">
        <div className="auth-card">
          <h2>Create your account</h2>
          {problem ? (
            <>
              <div className="banner error">{problem}</div>
              <button className="primary" onClick={() => onDone(null)}>Go to log in</button>
            </>
          ) : !invite ? (
            <p className="muted">Checking your invite…</p>
          ) : (
            <form className="form" onSubmit={submit}>
              <p className="muted small">
                Employee code <strong>{invite.employee_code}</strong> · link valid until{' '}
                {new Date(invite.expires_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
              </p>
              <label>Email<input value={invite.email} readOnly disabled /></label>
              <label>
                Your name
                <input value={name} onChange={(e) => setName(e.target.value)} className={errors.name ? 'invalid' : undefined} autoComplete="name" />
                {err('name', 'Your name')}
              </label>
              <label>
                Password
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                  className={errors.password ? 'invalid' : undefined} autoComplete="new-password" />
                {err('password', 'Password')}
              </label>
              <label>
                Confirm password
                <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)}
                  className={errors.confirm ? 'invalid' : undefined} autoComplete="new-password" />
                {err('confirm', 'Confirm password')}
              </label>
              <p className="muted small">At least 8 characters, with a letter and a number.</p>
              {message && <div className="banner error">{message}</div>}
              <button className="primary big" disabled={busy}>{busy ? 'Creating…' : 'Create account and continue'}</button>
            </form>
          )}
        </div>
      </section>
    </div>
  )
}
