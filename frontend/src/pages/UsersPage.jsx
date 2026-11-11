import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'

const ROLE = { admin: 'Admin', employee: 'Employee' }

export default function UsersPage({ user, clients }) {
  const [users, setUsers] = useState([])
  const [filter, setFilter] = useState('all')
  const [message, setMessage] = useState(null)

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

  const clientName = (id) => (id ? clients.find((c) => c.id === id)?.legal_name || id : 'All clients')
  const pending = users.filter((u) => u.status === 'pending')
  const shown = users.filter((u) => filter === 'all' || u.status === filter)

  return (
    <div className="stack">
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
          <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter by status">
            <option value="all">All</option>
            <option value="active">Active</option>
            <option value="pending">Pending</option>
            <option value="disabled">Disabled</option>
          </select>
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
