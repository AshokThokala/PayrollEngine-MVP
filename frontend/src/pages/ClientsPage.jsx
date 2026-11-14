import { cloneElement, useEffect, useRef, useState } from 'react'
import ClientEmployees from '../components/ClientEmployees.jsx'
import ClientLocations from '../components/ClientLocations.jsx'
import PickerSearch, { Highlight } from '../components/PickerSearch.jsx'
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

export default function ClientsPage({ clients, onCreated, onOpen, onUpdated, onOpenEmployee, openRequest }) {
  const [mode, setMode] = useState('none') // none | add | edit
  const [selectedId, setSelectedId] = useState(null)
  const [section, setSection] = useState('details') // tab of the open client record
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
    if (!c) return
    setMode('edit')
    setSelectedId(c.id)
    setForm({ ...EMPTY, ...c })
    setFieldErrors({})
    setMessage(null)
  }

  const handled = useRef(null)
  useEffect(() => {
    if (!openRequest || handled.current === openRequest.n) return
    const c = clients.find((x) => x.id === openRequest.id)
    if (!c) return
    handled.current = openRequest.n
    select(c)
    setSection(openRequest.section || 'details')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openRequest, clients])

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

  const current = clients.find((c) => c.id === selectedId)
  const cpos = clients.findIndex((c) => c.id === selectedId)

  return (
    <div className="stack">
      <section className="card search-bar">
        <PickerSearch
          items={clients}
          match={(c, q) => c.legal_name.toLowerCase().includes(q) || c.id.includes(q) || (c.pan || '').toLowerCase().includes(q)}
          render={(c, q) => (
            <><span className="gs-icon" aria-hidden="true">▦</span>
              <span className="gs-text"><strong><Highlight text={c.legal_name} q={q} /></strong>
                <span className="muted small"><Highlight text={c.id} q={q} /> · {c.state}{c.pan ? <> · PAN <Highlight text={c.pan} q={q} /></> : null}</span></span></>
          )}
          onPick={select}
          placeholder={`Search ${clients.length} client${clients.length === 1 ? '' : 's'} by name, ID or PAN`}
          label="Search clients"
        />
        <button className="primary" onClick={startAdd}>+ Add client</button>
      </section>

      <div className="stack">
      {mode === 'none' ? (
        <section className="card empty-state record-tile">
          <h2>Find a client</h2>
          <p className="muted">{clients.length ? 'Search above to open a client: its details, locations and all its employees.' : 'No clients yet. Add your first client firm.'}</p>
        </section>
      ) : (
        <section className="card allow-overflow record-tile">
          {editing && (
            <div className="record-nav">
              <span className="muted small">Client</span>
              <span className="record-pager">
                <button type="button" disabled={cpos <= 0} onClick={() => select(clients[cpos - 1])} aria-label="Previous client">‹ Prev</button>
                <span className="muted small">{cpos + 1} of {clients.length}</span>
                <button type="button" disabled={cpos >= clients.length - 1} onClick={() => select(clients[cpos + 1])} aria-label="Next client">Next ›</button>
              </span>
            </div>
          )}
          <div className="run-head">
            <div className="emp-head">
              <span className="emp-avatar client" aria-hidden="true">{(form.legal_name || '?').slice(0, 1).toUpperCase()}</span>
              <div>
                <h2>{editing ? form.legal_name || selectedId : 'Add client'}</h2>
                {editing && (
                  <div className="chips">
                    <span className="chip">{selectedId}</span>
                    <span className="chip">{states.find((x) => x.code === form.state)?.name || form.state}</span>
                    {form.pan && <span className="chip">PAN {form.pan}</span>}
                  </div>
                )}
              </div>
            </div>
            <button type="button" onClick={() => { setMode('none'); setSelectedId(null) }}>Close</button>
          </div>
          {editing && (
            <div className="page-tabs record-tabs" role="tablist" aria-label="Client record">
              {[['details', 'Details'], ['locations', 'Locations'], ['employees', 'Employees']].map(([k, label]) => (
                <button key={k} type="button" role="tab" aria-selected={section === k} className={section === k ? 'active' : ''}
                  onClick={() => setSection(k)}>{label}</button>
              ))}
            </div>
          )}
          <form onSubmit={submit} className="form" hidden={editing && section !== 'details'}>
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
          {editing && section === 'locations' && <ClientLocations clientId={selectedId} states={states} />}
          {editing && section === 'employees' && current && (
            <ClientEmployees client={current} onOpenEmployee={onOpenEmployee} onAddEmployee={() => onOpen(current.id)} embedded />
          )}
        </section>
      )}
      </div>
    </div>
  )
}
