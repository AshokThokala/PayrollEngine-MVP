import { useState } from 'react'
import { api } from '../api.js'

// "Change password" link that opens a small dialog. Used by admins and employees.
export default function ChangePassword({ className = 'ghost' }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ current_password: '', new_password: '', confirm: '' })
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)

  const close = () => {
    setOpen(false)
    setForm({ current_password: '', new_password: '', confirm: '' })
    setErrors({})
    setMessage(null)
  }

  async function submit(e) {
    e.preventDefault()
    setErrors({})
    if (form.new_password !== form.confirm) {
      setErrors({ confirm: 'The new passwords do not match' })
      return
    }
    setBusy(true)
    try {
      await api.changePassword({ current_password: form.current_password, new_password: form.new_password })
      setMessage({ kind: 'ok', text: 'Password changed.' })
      setForm({ current_password: '', new_password: '', confirm: '' })
    } catch (err) {
      setErrors(err.fieldErrors || {})
      setMessage({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  const field = (k, label, auto) => (
    <label>
      {label}
      <input type="password" autoComplete={auto} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })}
        className={errors[k] ? 'invalid' : undefined} />
      {errors[k] && <span className="field-error">{label}: {errors[k]}</span>}
    </label>
  )

  return (
    <>
      <button type="button" className={className} onClick={() => setOpen(true)}>Change password</button>
      {open && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && close()}>
          <div className="modal card" role="dialog" aria-modal="true" aria-label="Change password">
            <div className="run-head"><h2>Change password</h2><button type="button" onClick={close}>Close</button></div>
            <form className="form" onSubmit={submit}>
              {field('current_password', 'Current password', 'current-password')}
              {field('new_password', 'New password', 'new-password')}
              {field('confirm', 'Confirm new password', 'new-password')}
              <p className="muted small">At least 8 characters, with a letter and a number.</p>
              {message && <div className={`banner ${message.kind}`}>{message.text}</div>}
              <div className="actions"><button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Change password'}</button></div>
            </form>
          </div>
        </div>
      )}
    </>
  )
}
