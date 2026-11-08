import { cloneElement, useState } from 'react'
import { api } from '../api.js'
import InfoTip from '../components/InfoTip.jsx'

// Help text for each field on the Add client form.
const TIPS = {
  id: 'Short unique code for this client: 2–40 lowercase letters, digits or hyphens (e.g. acme-textiles). Used in run and filing IDs and cannot be changed later.',
  legal_name: 'Registered name of the business exactly as on its PAN or registration certificate. Shown on payslips and statutory reports.',
  state: 'State where the employees work. It decides which Professional Tax and Labour Welfare Fund rules apply. Only Telangana is supported for now.',
  pan: "Business's 10-character Permanent Account Number: 5 letters, 4 digits, 1 letter (e.g. AAACA1234A). Optional for now.",
  tan: '10-character Tax Deduction Account Number used to deposit TDS and file Form 24Q: 4 letters, 5 digits, 1 letter (e.g. HYDA12345B).',
  pf_code: 'EPFO establishment code from the employer\'s PF registration (e.g. TSHYD0012345000). Needed for the monthly ECR and PF challan.',
  esi_code: '17-digit ESIC employer code. Leave blank if the business is not registered under ESI.',
  pt_registration: 'Professional Tax registration number of the business, issued by the Telangana Commercial Taxes Department.',
}

function Field({ name, label, children }) {
  const tipId = `tip-${name}`
  return (
    <label>
      <span className="label-text">
        {label}
        <InfoTip id={tipId} text={TIPS[name]} />
      </span>
      {cloneElement(children, { title: TIPS[name], 'aria-describedby': tipId })}
    </label>
  )
}

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

      <section className="card allow-overflow">
        <h2>Add client</h2>
        <form onSubmit={submit} className="form">
          <Field name="id" label="Client ID">
            <input required pattern="[a-z0-9-]{2,40}" value={form.id} onChange={set('id')} />
          </Field>
          <Field name="legal_name" label="Legal name">
            <input required value={form.legal_name} onChange={set('legal_name')} />
          </Field>
          <Field name="state" label="State">
            <select value={form.state} onChange={set('state')}>
              <option value="TG">Telangana</option>
            </select>
          </Field>
          <div className="row">
            <Field name="pan" label="PAN"><input value={form.pan} onChange={set('pan')} /></Field>
            <Field name="tan" label="TAN"><input value={form.tan} onChange={set('tan')} /></Field>
          </div>
          <div className="row">
            <Field name="pf_code" label="PF code"><input value={form.pf_code} onChange={set('pf_code')} /></Field>
            <Field name="esi_code" label="ESI code"><input value={form.esi_code} onChange={set('esi_code')} /></Field>
          </div>
          <Field name="pt_registration" label="PT registration">
            <input value={form.pt_registration} onChange={set('pt_registration')} />
          </Field>
          <button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Create client'}</button>
          {message && <div className={`banner ${message.kind}`}>{message.text}</div>}
        </form>
      </section>
    </div>
  )
}
