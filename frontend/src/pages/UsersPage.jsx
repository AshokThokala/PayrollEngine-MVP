import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'

const ROLE = { admin: 'Admin', employee: 'Employee' }
const EMPTY = { name: '', email: '', password: '', client_id: '' }

function AddUserForm({ user, clients, onDone, onCancel }) {
  const platform = user.is_platform_admin
  const [form, setForm] = useState({ ...EMPTY, client_id: platform ? '' : user.client_id })
  const [errors, setErrors] = useState({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const set = (k) => (e) => {
    setForm({ ...form, [k]: e.target.value })
    if (errors[k]) setErrors({ ...errors, [k]: undefined })
  }

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setErrors({})
    setError('')
    try {
      const created = await api.addUser({ ...form, client_id: form.client_id || null })
      onDone(created)
    } catch (err) {
      setErrors(err.fieldErrors || {})
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const field = (k, label, props = {}) => (
    <label>
      {label}
      <input value={form[k]} onChange={set(k)} className={errors[k] ? 'invalid' : undefined}
        aria-invalid={errors[k] ? true : undefined} {...props} />
      {errors[k] && <span className="field-error">{label}: {errors[k]}</span>}
    </label>
  )

  return (
    <section className="card">
      <div className="run-head">
        <h2>Add user</h2>
        <button onClick={onCancel}>Close</button>
      </div>
      <form className="form" onSubmit={submit}>
        <div className="row">
          {field('name', 'Name', { autoComplete: 'off' })}
          {field('email', 'Email', { type: 'email', autoComplete: 'off' })}
        </div>
        <div className="row">
          <label>
            Access
            {platform ? (
              <select value={form.client_id} onChange={set('client_id')} className={errors.client_id ? 'invalid' : undefined}>
                <option value="">ClearPay4U team — platform admin (all clients)</option>
                {clients.map((c) => <option key={c.id} value={c.id}>Admin of {c.legal_name}</option>)}
              </select>
            ) : (
              <input value={`Admin of ${clients.find((c) => c.id === user.client_id)?.legal_name || user.client_id}`} disabled />
            )}
            {errors.client_id && <span className="field-error">Access: {errors.client_id}</span>}
          </label>
          {field('password', 'Temporary password', { type: 'text', autoComplete: 'new-password' })}
        </div>
        <p className="muted small">
          Admins can log in straight away. Share the temporary password privately. Employees are added through
          {' '}<strong>Employee onboarding</strong> (an email invite), not here.
        </p>
        {error && <div className="banner error">{error}</div>}
        <div className="actions"><button className="primary" disabled={busy}>{busy ? 'Adding…' : 'Add user'}</button></div>
      </form>
    </section>
  )
}

export default function UsersPage({ user, clients }) {
  const [users, setUsers] = useState([])
  const [filter, setFilter] = useState('all')
  const [message, setMessage] = useState(null)
  const [adding, setAdding] = useState(false)

  const load = useCallback(async () => {
    try {
      setUsers(await api.listUsers())
    } catch (err) {
      setMessage({ kind: 'error', text: err.message })
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const act = async (u, action) => {
    try {
      await api.userAction(u.id, action)
      setMessage({ kind: 'ok', text: `${u.name} ${action === 'disable' ? 'disabled' : action === 'approve' ? 'approved' : 'enabled'}.` })
      load()
    } catch (err) {
      setMessage({ kind: 'error', text: err.message })
    }
  }

  const resetPassword = async (u) => {
    const pw = window.prompt(`Temporary password for ${u.name} (at least 8 characters, with a letter and a number):`)
    if (!pw) return
    try {
      await api.resetPassword(u.id, pw)
      setMessage({ kind: 'ok', text: `Password reset for ${u.name}. Share it privately and ask them to change it after logging in.` })
    } catch (err) {
      setMessage({ kind: 'error', text: err.message })
    }
  }

  const clientName = (id) => (id ? clients.find((c) => c.id === id)?.legal_name || id : 'All clients')
  const pending = users.filter((u) => u.status === 'pending')
  const shown = users.filter((u) => filter === 'all' || u.status === filter)

  return (
    <div className="stack">
      {adding && (
        <AddUserForm
          user={user}
          clients={clients}
          onCancel={() => setAdding(false)}
          onDone={(created) => {
            setAdding(false)
            setMessage({ kind: 'ok', text: `${created.name} (${created.email}) added as ${created.client_id ? `admin of ${clientName(created.client_id)}` : 'platform admin'}.` })
            load()
          }}
        />
      )}
      {pending.length > 0 && (
        <section className="card highlight">
          <h2>Waiting for approval <span className="tag approved">{pending.length}</span></h2>
          <p className="muted small">Employees who signed up with their employee code. Approve only people you recognise.</p>
          <div className="cards">
            {pending.map((u) => (
              <div key={u.id} className="mini-card">
                <strong>{u.name}</strong>
                <span className="muted small">{u.email}</span>
                <span className="small">{clientName(u.client_id)} · employee {u.employee_code}</span>
                <div className="inline">
                  <button className="primary" onClick={() => act(u, 'approve')}>Approve</button>
                  <button onClick={() => act(u, 'disable')}>Reject</button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="card">
        <div className="run-head">
          <h2>Users</h2>
          <div className="actions">
            {!adding && <button className="primary" onClick={() => { setAdding(true); setMessage(null) }}>+ Add user</button>}
          <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter by status">
            <option value="all">All</option>
            <option value="active">Active</option>
            <option value="pending">Pending</option>
            <option value="disabled">Disabled</option>
          </select>
          </div>
        </div>
        {message && <div className={`banner ${message.kind}`}>{message.text}</div>}
        <div className="table-wrap">
          <table>
            <thead><tr><th>User</th><th>Role</th><th>Client</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {shown.map((u) => (
                <tr key={u.id}>
                  <td title={u.email}><strong>{u.name}</strong> <span className="muted small">{u.email}</span></td>
                  <td>{u.is_platform_admin ? 'Platform admin' : ROLE[u.role]}</td>
                  <td>{clientName(u.client_id)}</td>
                  <td><span className={`tag ${u.status === 'active' ? 'locked' : u.status === 'pending' ? 'approved' : 'error'}`}>{u.status}</span></td>
                  <td>
                    {u.id !== user.id && (u.client_id || user.is_platform_admin) && (
                      u.status === 'active'
                        ? <button className="link" onClick={() => act(u, 'disable')}>Disable</button>
                        : <button className="link" onClick={() => act(u, u.status === 'pending' ? 'approve' : 'enable')}>{u.status === 'pending' ? 'Approve' : 'Enable'}</button>
                    )}
                    {u.id !== user.id && (u.client_id || user.is_platform_admin) && (
                      <button className="link" onClick={() => resetPassword(u)}>Reset password</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
