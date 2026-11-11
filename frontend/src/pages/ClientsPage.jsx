import { cloneElement, useEffect, useState } from 'react'
import { api } from '../api.js'
import InfoTip from '../components/InfoTip.jsx'

// Help text for each field on the Add client form.
const TIPS = {
  id: 'Short unique code for this client: 2–40 lowercase letters, digits or hyphens (e.g. acme-textiles). Used in run and filing IDs and cannot be changed later.',
  legal_name: 'Registered name of the business exactly as on its PAN or registration certificate. Shown on payslips and statutory reports.',
  state: 'State where the employees work. It decides which Professional Tax and Labour Welfare Fund rules apply. States appear here once they have rules on the Compliance rules page.',
  pan: "Business's 10-character Permanent Account Number: 5 letters, 4 digits, 1 letter (e.g. AAACA1234A). Optional for now.",
  tan: '10-character Tax Deduction Account Number used to deposit TDS and file Form 24Q: 4 letters, 5 digits, 1 letter (e.g. HYDA12345B).',
  pf_code: 'EPFO establishment code from the employer\'s PF registration (e.g. TSHYD0012345000). Needed for the monthly ECR and PF challan.',
  esi_code: '17-digit ESIC employer code. Leave blank if the business is not registered under ESI.',
  pt_registration: 'Professional Tax registration number of the business, issued by the Telangana Commercial Taxes Department.',
}

function Field({ name, label, error, children }) {
  const tipId = `tip-${name}`
  const errorId = `err-${name}`
  return (
    <label>
      <span className="label-text">
        {label}
        <InfoTip id={tipId} text={TIPS[name]} />
      </span>
      {cloneElement(children, {
        title: TIPS[name],
        'aria-describedby': error ? `${errorId} ${tipId}` : tipId,
        'aria-invalid': error ? true : undefined,
        className: error ? 'invalid' : undefined,
      })}
      {error && <span id={errorId} className="field-error">{label}: {error}</span>}
    </label>
  )
}

const EMPTY = { id: '', legal_name: '', state: 'TG', pan: '', tan: '', pf_code: '', esi_code: '', pt_registration: '' }

export default function ClientsPage({ clients, onCreated, onOpen, onUpdated }) {
  const [mode, setMode] = useState('none') // none | add | edit
  const [selectedId, setSelectedId] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)
  const [fieldErrors, setFieldErrors] = useState({})
  const [states, setStates] = useState([{ code: 'TG', name: 'Telangana', supported: true }])

  // States with compliance rules (added on the Compliance rules page) can take clients.
  useEffect(() => {
    api.listRuleStates().then((list) => setStates(list.filter((s) => s.supported))).catch(() => {})
  }, [])

  const set = (key) => (e) => {
    setForm({ ...form, [key]: e.target.value })
    if (fieldErrors[key]) setFieldErrors({ ...fieldErrors, [key]: undefined })
  }

  const startAdd = () => {
    setMode('add')
    setSelectedId(null)
    setForm(EMPTY)
    setFieldErrors({})
    setMessage(null)
  }

  const select = (c) => {
    setMode('edit')
    setSelectedId(c.id)
    setForm({ ...EMPTY, ...c })
    setFieldErrors({})
    setMessage(null)
  }

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setFieldErrors({})
    try {
      if (mode === 'add') {
        await api.createClient(form)
        setMessage({ kind: 'ok', text: `Client ${form.legal_name} created.` })
        await onCreated(form.id)
        select(form)
      } else {
        const { legal_name, pan, tan, pf_code, esi_code, pt_registration } = form
        await api.updateClient(selectedId, { legal_name, pan, tan, pf_code, esi_code, pt_registration })
        setMessage({ kind: 'ok', text: 'Changes saved.' })
        await onUpdated()
      }
    } catch (err) {
      setFieldErrors(err.fieldErrors || {})
      setMessage({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  const editing = mode === 'edit'

  return (
    <div className="grid">
      <section className="card">
        <div className="run-head">
          <h2>Clients</h2>
          <button className="primary" onClick={startAdd}>+ Add client</button>
        </div>
        {clients.length === 0 ? (
          <p className="muted">No clients yet. Add your first client firm.</p>
        ) : (
          <div className="table-wrap">
            <table className="clickable">
              <thead>
                <tr><th>Legal name</th><th>ID</th><th>State</th><th>PF code</th></tr>
              </thead>
              <tbody>
                {clients.map((c) => (
                  <tr key={c.id} tabIndex={0} className={selectedId === c.id ? 'selected' : ''}
                    onClick={() => select(c)} onKeyDown={(e) => { if (e.key === 'Enter') select(c) }}>
                    <td><strong>{c.legal_name}</strong></td>
                    <td>{c.id}</td>
                    <td>{c.state}</td>
                    <td>{c.pf_code || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted small">Click a client to view or edit its details.</p>
      </section>

      {mode === 'none' ? (
        <section className="card empty-state">
          <h2>Client details</h2>
          <p className="muted">Select a client on the left to see and edit its details.</p>
        </section>
      ) : (
        <section className="card allow-overflow">
          <div className="run-head">
            <h2>{editing ? form.legal_name || selectedId : 'Add client'}</h2>
            {editing && <button onClick={() => onOpen(selectedId)}>Open employees →</button>}
          </div>
          <form onSubmit={submit} className="form">
            <div className="row">
              <Field name="id" error={fieldErrors.id} label="Client ID">
                <input required pattern="[a-z0-9-]{2,40}" value={form.id} onChange={set('id')} disabled={editing} />
              </Field>
              <Field name="state" error={fieldErrors.state} label="State">
                <select value={form.state} onChange={set('state')} disabled={editing}>
                  {states.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
                  {editing && !states.some((s) => s.code === form.state) && <option value={form.state}>{form.state}</option>}
                </select>
              </Field>
            </div>
            <Field name="legal_name" error={fieldErrors.legal_name} label="Legal name">
              <input required value={form.legal_name} onChange={set('legal_name')} />
            </Field>
            <div className="row">
              <Field name="pan" error={fieldErrors.pan} label="PAN"><input value={form.pan} onChange={set('pan')} /></Field>
              <Field name="tan" error={fieldErrors.tan} label="TAN"><input value={form.tan} onChange={set('tan')} /></Field>
            </div>
            <div className="row">
              <Field name="pf_code" error={fieldErrors.pf_code} label="PF code"><input value={form.pf_code} onChange={set('pf_code')} /></Field>
              <Field name="esi_code" error={fieldErrors.esi_code} label="ESI code"><input value={form.esi_code} onChange={set('esi_code')} /></Field>
            </div>
            <Field name="pt_registration" error={fieldErrors.pt_registration} label="PT registration">
              <input value={form.pt_registration} onChange={set('pt_registration')} />
            </Field>
            {editing && <p className="muted small">Client ID and state can't be changed: they key the payroll history and the rules applied.</p>}
            {message && <div className={`banner ${message.kind}`}>{message.text}</div>}
            <div className="inline">
              <button className="primary" disabled={busy}>{busy ? 'Saving…' : editing ? 'Save changes' : 'Create client'}</button>
              <button type="button" onClick={() => { setMode('none'); setSelectedId(null) }}>Close</button>
            </div>
          </form>
        </section>
      )}
    </div>
  )
}
