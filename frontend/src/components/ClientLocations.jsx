import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'

const EMPTY = { name: '', state: 'TG', address: '', city: '', pincode: '', pt_registration: '', lwf_registration: '',
  esi_code: '', se_registration: '', head_office: false, active: true }

// A client's locations (head office, branches, factories, sites). Click a row to edit it.
// An employee's location decides their state's Professional Tax and Labour Welfare Fund.
export default function ClientLocations({ clientId, states }) {
  const [rows, setRows] = useState([])
  const [editing, setEditing] = useState(null) // location id, 'new' or null
  const [form, setForm] = useState(EMPTY)
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      setRows(await api.clientLocations(clientId))
    } catch (e) {
      setMessage({ kind: 'error', text: e.message })
    }
  }, [clientId])

  useEffect(() => {
    setEditing(null)
    setMessage(null)
    load()
  }, [load])

  const open = (loc) => {
    setErrors({})
    setMessage(null)
    setEditing(loc ? loc.id : 'new')
    setForm(loc ? { ...EMPTY, ...loc } : { ...EMPTY, state: rows[0]?.state || 'TG' })
  }
  const set = (k) => (e) => {
    setForm({ ...form, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
    if (errors[k]) setErrors({ ...errors, [k]: undefined })
  }

  async function save(e) {
    e.preventDefault()
    setBusy(true)
    setErrors({})
    try {
      const loc = editing === 'new' ? await api.addLocation(clientId, form) : await api.editLocation(clientId, editing, form)
      setEditing(null)
      setMessage({ kind: 'ok', text: `${loc.name} saved.` })
      load()
    } catch (err) {
      setErrors(err.fieldErrors || {})
      setMessage({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  const field = (k, label, props = {}) => (
    <label className={props.wide ? 'wide' : undefined}>
      <span>{label}</span>
      <input value={form[k] ?? ''} onChange={set(k)} className={errors[k] ? 'invalid' : undefined}
        aria-invalid={errors[k] ? true : undefined} placeholder={props.placeholder} inputMode={props.inputMode} />
      {errors[k] && <span className="field-error">{label}: {errors[k]}</span>}
    </label>
  )
  const current = rows.find((r) => r.id === editing)

  return (
    <div className="form section">
      <div className="run-head">
        <h3>Locations <span className="tag">{rows.filter((r) => r.active).length}</span></h3>
        {editing === null && <button type="button" onClick={() => open(null)}>+ Add location</button>}
      </div>
      <p className="muted small">Where employees work. Professional Tax and LWF follow the state of each employee's location.</p>
      {rows.length > 0 && (
        <div className="table-wrap">
          <table className="clickable compact">
            <thead><tr><th>Location</th><th>State</th><th className="num">Employees</th><th /></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} tabIndex={0} className={`${editing === r.id ? 'selected' : ''} ${r.active ? '' : 'dim'}`}
                    onClick={() => open(r)} onKeyDown={(e) => e.key === 'Enter' && open(r)}>
                  <td><strong>{r.name}</strong>{r.city && <span className="muted small"> · {r.city}</span>}</td>
                  <td className="small">{r.state_name}</td>
                  <td className="num">{r.employees}</td>
                  <td>
                    {r.head_office && <span className="tag locked">head office</span>}
                    {!r.active && <span className="tag">off</span>}
                    {!r.rules_ready && <span className="tag error" title="No PT/LWF rules for this state">rules missing</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing !== null && (
        <form className="form deduction-form" onSubmit={save}>
          <h4>{editing === 'new' ? 'Add location' : current?.name}</h4>
          <div className="details-grid">
            {field('name', 'Name', { placeholder: 'e.g. Bengaluru branch' })}
            <label>
              <span>State</span>
              <select value={form.state} onChange={set('state')} className={errors.state ? 'invalid' : undefined}>
                {states.map((s) => <option key={s.code} value={s.code}>{s.name}{s.supported ? '' : ' (no rules yet)'}</option>)}
              </select>
              {errors.state && <span className="field-error">State: {errors.state}</span>}
            </label>
            {field('address', 'Address', { wide: true })}
            {field('city', 'City')}
            {field('pincode', 'PIN code', { inputMode: 'numeric' })}
            {field('pt_registration', 'PT registration')}
            {field('lwf_registration', 'LWF registration')}
            {field('esi_code', 'ESI sub-code', { placeholder: 'if the branch has its own' })}
            {field('se_registration', 'Shops & Establishments reg.')}
          </div>
          <label className="check"><input type="checkbox" checked={form.head_office} onChange={set('head_office')} /> Head office</label>
          {errors.head_office && <span className="field-error">{errors.head_office}</span>}
          {editing !== 'new' && (
            <label className="check"><input type="checkbox" checked={form.active} onChange={set('active')} /> Active</label>
          )}
          {errors.active && <span className="field-error">{errors.active}</span>}
          {current && form.state !== current.state && current.employees > 0 && (
            <div className="banner warn">The {current.employees} employee(s) here will pay {states.find((s) => s.code === form.state)?.name} PT and LWF from the next payroll run.</div>
          )}
          {message?.kind === 'error' && <div className="banner error">{message.text}</div>}
          <div className="actions">
            <button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save location'}</button>
            <button type="button" onClick={() => setEditing(null)}>Cancel</button>
          </div>
        </form>
      )}
      {message?.kind === 'ok' && <div className="banner ok">{message.text}</div>}
    </div>
  )
}
