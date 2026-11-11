import { useEffect, useState } from 'react'
import { api } from '../api.js'

const PERKS = [
  ['PF, ESI, PT, LWF and TDS', 'calculated every month under the Labour Codes and the Income-tax Act 2025'],
  ['Every due date tracked', 'challans and returns on a calendar, with overdue alerts'],
  ['Maker-checker by design', 'a second person approves every payroll run'],
]

export default function AuthScreen({ onLoggedIn }) {
  const [mode, setMode] = useState('login') // login | business | employee

  return (
    <div className="auth">
      <section className="auth-hero">
        <div className="brand big">
          <span className="logo">C4U</span>
          <span>ClearPay4U<span className="tagline">zero-penalty payroll</span></span>
        </div>
        <h1>Payroll and compliance, done right every month.</h1>
        <ul className="perks">
          {PERKS.map(([title, text]) => (
            <li key={title}><span className="tick" aria-hidden="true">✓</span><span><strong>{title}</strong> — {text}</span></li>
          ))}
        </ul>
      </section>

      <section className="auth-panel">
        <div className="auth-card">
          <div className="segmented" role="tablist">
            {[['login', 'Log in'], ['business', 'Sign up a business'], ['employee', "I'm an employee"]].map(([id, label]) => (
              <button key={id} role="tab" aria-selected={mode === id} className={mode === id ? 'active' : ''}
                onClick={() => setMode(id)}>{label}</button>
            ))}
          </div>
          {mode === 'login' && <LoginForm onLoggedIn={onLoggedIn} />}
          {mode === 'business' && <BusinessSignup onLoggedIn={onLoggedIn} />}
          {mode === 'employee' && <EmployeeSignup onDone={() => setMode('login')} />}
        </div>
      </section>
    </div>
  )
}

function useForm(initial) {
  const [values, setValues] = useState(initial)
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)
  const field = (key) => ({
    value: values[key],
    onChange: (e) => {
      setValues({ ...values, [key]: e.target.value })
      if (errors[key]) setErrors({ ...errors, [key]: undefined })
    },
    className: errors[key] ? 'invalid' : undefined,
    'aria-invalid': errors[key] ? true : undefined,
  })
  const run = async (fn) => {
    setBusy(true)
    setErrors({})
    setMessage(null)
    try {
      await fn()
    } catch (err) {
      setErrors(err.fieldErrors || {})
      setMessage({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }
  return { values, errors, message, setMessage, busy, field, run }
}

function Err({ error, label }) {
  return error ? <span className="field-error">{label}: {error}</span> : null
}

function LoginForm({ onLoggedIn }) {
  const f = useForm({ email: '', password: '' })
  const submit = (e) => {
    e.preventDefault()
    f.run(async () => onLoggedIn(await api.login(f.values.email, f.values.password)))
  }
  return (
    <form className="form" onSubmit={submit}>
      <h2>Welcome back</h2>
      <label>Email<input type="email" autoComplete="email" required {...f.field('email')} /></label>
      <label>Password<input type="password" autoComplete="current-password" required {...f.field('password')} /></label>
      {f.message && <div className={`banner ${f.message.kind}`}>{f.message.text}</div>}
      <button className="primary big" disabled={f.busy}>{f.busy ? 'Logging in…' : 'Log in'}</button>
    </form>
  )
}

function BusinessSignup({ onLoggedIn }) {
  const f = useForm({ id: '', legal_name: '', state: 'TG', name: '', email: '', password: '' })
  const [states, setStates] = useState([{ code: 'TG', name: 'Telangana' }])
  useEffect(() => {
    api.listRuleStates().then((list) => setStates(list.filter((s) => s.supported))).catch(() => {})
  }, [])
  const submit = (e) => {
    e.preventDefault()
    const { id, legal_name, state, name, email, password } = f.values
    f.run(async () => onLoggedIn(await api.signupClient({ client: { id, legal_name, state }, name, email, password })))
  }
  return (
    <form className="form" onSubmit={submit}>
      <h2>Set up your business</h2>
      <label>Legal name of the business<input required {...f.field('legal_name')} /><Err error={f.errors.legal_name} label="Legal name" /></label>
      <div className="row">
        <label>Client ID (short code)<input required pattern="[a-z0-9-]{2,40}" title="2–40 lowercase letters, digits or hyphens" {...f.field('id')} /><Err error={f.errors.id} label="Client ID" /></label>
        <label>State
          <select {...f.field('state')}>
            {states.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
          </select>
          <Err error={f.errors.state} label="State" />
        </label>
      </div>
      <h3>Your admin login</h3>
      <label>Your name<input required autoComplete="name" {...f.field('name')} /><Err error={f.errors.name} label="Name" /></label>
      <label>Work email<input type="email" required autoComplete="email" {...f.field('email')} /><Err error={f.errors.email} label="Email" /></label>
      <label>Password<input type="password" required autoComplete="new-password" {...f.field('password')} /><Err error={f.errors.password} label="Password" />
        <span className="muted small">At least 8 characters with letters and a number.</span></label>
      {f.message && <div className={`banner ${f.message.kind}`}>{f.message.text}</div>}
      <button className="primary big" disabled={f.busy}>{f.busy ? 'Creating…' : 'Create business account'}</button>
    </form>
  )
}

function EmployeeSignup({ onDone }) {
  const f = useForm({ client_id: '', employee_code: '', name: '', email: '', password: '' })
  const [done, setDone] = useState(false)
  const submit = (e) => {
    e.preventDefault()
    f.run(async () => {
      await api.signupEmployee(f.values)
      setDone(true)
    })
  }
  if (done) {
    return (
      <div className="form">
        <h2>Request sent</h2>
        <div className="banner ok">Your employer's admin needs to approve your account. You can log in once they do.</div>
        <button className="primary big" onClick={onDone}>Back to log in</button>
      </div>
    )
  }
  return (
    <form className="form" onSubmit={submit}>
      <h2>See your payslips</h2>
      <p className="muted small">Ask your employer for their client ID and your employee code.</p>
      <div className="row">
        <label>Client ID<input required {...f.field('client_id')} /><Err error={f.errors.client_id} label="Client ID" /></label>
        <label>Employee code<input required {...f.field('employee_code')} /><Err error={f.errors.employee_code} label="Employee code" /></label>
      </div>
      <label>Your name<input required autoComplete="name" {...f.field('name')} /><Err error={f.errors.name} label="Name" /></label>
      <label>Email<input type="email" required autoComplete="email" {...f.field('email')} /><Err error={f.errors.email} label="Email" /></label>
      <label>Password<input type="password" required autoComplete="new-password" {...f.field('password')} /><Err error={f.errors.password} label="Password" /></label>
      {f.message && <div className={`banner ${f.message.kind}`}>{f.message.text}</div>}
      <button className="primary big" disabled={f.busy}>{f.busy ? 'Sending…' : 'Request access'}</button>
    </form>
  )
}
