import { useState } from 'react'
import { api } from '../api.js'

const EMPTY = { id: '', legal_name: '', state: 'TG', pan: '', tan: '', pf_code: '', esi_code: '', pt_registration: '' }

export default function ClientsPage({ clients, onCreated, onOpen }) {
  const [form, setForm] = useState(EMPTY)
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    try {
      await api.createClient(form)
      setMessage({ kind: 'ok', text: `Client ${form.legal_name} created.` })
      const id = form.id
      setForm(EMPTY)
      await onCreated(id)
    } catch (err) {
      setMessage({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid">
      <section className="card">
        <h2>Clients</h2>
        {clients.length === 0 ? (
          <p className="muted">No clients yet. Add your first client firm.</p>
        ) : (
          <table>
            <thead>
              <tr><th>ID</th><th>Legal name</th><th>State</th><th>PF code</th><th>ESI code</th><th></th></tr>
            </thead>
            <tbody>
              {clients.map((c) => (
                <tr key={c.id}>
                  <td>{c.id}</td>
                  <td>{c.legal_name}</td>
                  <td>{c.state}</td>
                  <td>{c.pf_code || '—'}</td>
                  <td>{c.esi_code || '—'}</td>
                  <td><button className="link" onClick={() => onOpen(c.id)}>Employees →</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h2>Add client</h2>
        <form onSubmit={submit} className="form">
          <label>Client ID (lowercase, e.g. acme)
            <input required pattern="[a-z0-9-]{2,40}" value={form.id} onChange={set('id')} />
          </label>
          <label>Legal name<input required value={form.legal_name} onChange={set('legal_name')} /></label>
          <label>State
            <select value={form.state} onChange={set('state')}>
              <option value="TG">Telangana</option>
            </select>
          </label>
          <div className="row">
            <label>PAN<input value={form.pan} onChange={set('pan')} /></label>
            <label>TAN<input value={form.tan} onChange={set('tan')} /></label>
          </div>
          <div className="row">
            <label>PF code<input value={form.pf_code} onChange={set('pf_code')} /></label>
            <label>ESI code<input value={form.esi_code} onChange={set('esi_code')} /></label>
          </div>
          <label>PT registration<input value={form.pt_registration} onChange={set('pt_registration')} /></label>
          <button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Create client'}</button>
          {message && <div className={`banner ${message.kind}`}>{message.text}</div>}
        </form>
      </section>
    </div>
  )
}
