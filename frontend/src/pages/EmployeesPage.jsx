import { useCallback, useEffect, useState } from 'react'
import { api, money, today } from '../api.js'
import TaxFields, { EMPTY_TAX, taxFromEmployee } from '../components/TaxFields.jsx'

const COMPONENTS = [
  ['basic', 'Basic'],
  ['da', 'DA'],
  ['hra', 'HRA'],
  ['conveyance', 'Conveyance'],
  ['special_allowance', 'Special allowance'],
]

const EMPTY = {
  code: '', name: '', joined_on: today(),
  basic: '', da: '', hra: '', conveyance: '', special_allowance: '',
  esi: 'auto', pf_member: true, pt_applicable: true,
}

function FieldError({ label, error }) {
  return error ? <span className="field-error">{label}: {error}</span> : null
}

export default function EmployeesPage({ client }) {
  const [employees, setEmployees] = useState([])
  const [form, setForm] = useState(EMPTY)
  const [message, setMessage] = useState(null)
  const [exiting, setExiting] = useState({})
  const [fieldErrors, setFieldErrors] = useState({})
  const [tax, setTax] = useState(EMPTY_TAX)
  const [taxEdit, setTaxEdit] = useState(null) // { code, name, value }
  const [taxErrors, setTaxErrors] = useState({})

  const load = useCallback(async () => {
    try {
      setEmployees(await api.listEmployees(client.id))
    } catch (err) {
      setMessage({ kind: 'error', text: err.message })
    }
  }, [client.id])

  useEffect(() => {
    load()
  }, [load])

  const set = (key) => (e) => {
    setForm({ ...form, [key]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
    const errorKey = COMPONENTS.some(([k]) => k === key) ? 'components' : key
    if (fieldErrors[errorKey]) setFieldErrors({ ...fieldErrors, [errorKey]: undefined })
  }
  const invalid = (key) => (fieldErrors[key] ? { className: 'invalid', 'aria-invalid': true } : {})

  const total = COMPONENTS.reduce((sum, [k]) => sum + (Number(form[k]) || 0), 0)
  const wageShare = total ? (Number(form.basic || 0) + Number(form.da || 0)) / total : 1

  const submit = async (e) => {
    e.preventDefault()
    const components = {}
    COMPONENTS.forEach(([k]) => {
      if (Number(form[k]) > 0) components[k] = Number(form[k])
    })
    setFieldErrors({})
    try {
      const res = await api.addEmployee(client.id, {
        code: form.code,
        name: form.name,
        joined_on: form.joined_on,
        components,
        pf_member: form.pf_member,
        pt_applicable: form.pt_applicable,
        esi_covered: form.esi === 'auto' ? null : form.esi === 'yes',
        tax,
      })
      setMessage(
        res.warnings.length
          ? { kind: 'warn', text: `Saved with warning: ${res.warnings.join(' ')}` }
          : { kind: 'ok', text: `${form.name} added.` },
      )
      setForm(EMPTY)
      setTax(EMPTY_TAX)
      load()
    } catch (err) {
      setFieldErrors(err.fieldErrors || {})
      setMessage({ kind: 'error', text: err.message })
    }
  }

  const saveTax = async (e) => {
    e.preventDefault()
    setTaxErrors({})
    try {
      await api.updateTax(client.id, taxEdit.code, taxEdit.value)
      setMessage({ kind: 'ok', text: `Tax details saved for ${taxEdit.name}. Recalculate the month's draft to update TDS.` })
      setTaxEdit(null)
      load()
    } catch (err) {
      setTaxErrors(err.fieldErrors || {})
      setMessage({ kind: 'error', text: err.message })
    }
  }

  const exit = async (code) => {
    const date = exiting[code]
    if (!date) return
    try {
      await api.exitEmployee(client.id, code, date)
      setExiting({ ...exiting, [code]: undefined })
      setMessage({ kind: 'ok', text: `${code} marked as exited on ${date}.` })
      load()
    } catch (err) {
      setMessage({ kind: 'error', text: err.message })
    }
  }

  return (
    <div className="grid">
      <section className="card wide">
        <h2>Employees — {client.legal_name}</h2>
        {message && <div className={`banner ${message.kind}`}>{message.text}</div>}
        {employees.length === 0 ? (
          <p className="muted">No employees yet.</p>
        ) : (
          <table>
            <thead>
              <tr><th>Code</th><th>Name</th><th>Joined</th><th>Exited</th><th className="num">Monthly pay</th><th>Tax</th><th>Exit</th></tr>
            </thead>
            <tbody>
              {employees.map((emp) => (
                <tr key={emp.code} className={emp.exited_on ? 'dim' : ''}>
                  <td>{emp.code}</td>
                  <td>{emp.name}</td>
                  <td>{emp.joined_on}</td>
                  <td>{emp.exited_on || '—'}</td>
                  <td className="num">{money(emp.monthly_total)}</td>
                  <td>
                    <span className="tag">{emp.tax?.tax_regime === 'old' ? 'Old regime' : 'New regime'}</span>
                    {' '}<button className="link" onClick={() => { setTaxErrors({}); setTaxEdit({ code: emp.code, name: emp.name, value: taxFromEmployee(emp) }) }}>Edit</button>
                  </td>
                  <td>
                    {!emp.exited_on && (
                      <span className="inline">
                        <input type="date" value={exiting[emp.code] || ''}
                          onChange={(e) => setExiting({ ...exiting, [emp.code]: e.target.value })} />
                        <button disabled={!exiting[emp.code]} onClick={() => exit(emp.code)}>Mark exit</button>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <div className="stack">
      {taxEdit && (
        <section className="card allow-overflow">
          <h2>Income tax — {taxEdit.name} ({taxEdit.code})</h2>
          <form onSubmit={saveTax} className="form">
            <TaxFields value={taxEdit.value} errors={taxErrors}
              onChange={(v) => setTaxEdit({ ...taxEdit, value: v })} />
            <div className="inline">
              <button className="primary">Save tax details</button>
              <button type="button" onClick={() => setTaxEdit(null)}>Cancel</button>
            </div>
          </form>
        </section>
      )}
      <section className="card allow-overflow">
        <h2>Add employee</h2>
        <form onSubmit={submit} className="form">
          <div className="row">
            <label>Code<input required value={form.code} onChange={set('code')} {...invalid('code')} />
              <FieldError label="Employee code" error={fieldErrors.code} /></label>
            <label>Joined on<input type="date" required value={form.joined_on} onChange={set('joined_on')} {...invalid('joined_on')} />
              <FieldError label="Joined on" error={fieldErrors.joined_on} /></label>
          </div>
          <label>Name<input required value={form.name} onChange={set('name')} {...invalid('name')} />
            <FieldError label="Name" error={fieldErrors.name} /></label>
          <fieldset>
            <legend>Monthly salary (₹)</legend>
            {COMPONENTS.map(([k, label]) => (
              <label key={k} className="row-label">{label}
                <input type="number" min="0" step="0.01" value={form[k]} onChange={set(k)} />
              </label>
            ))}
            <FieldError label="Monthly salary" error={fieldErrors.components} />
            <div className="total">
              Total {money(total)}
              {total > 0 && wageShare < 0.5 && (
                <span className="tag warn">Basic + DA below 50% — PF will use the higher Labour Code wage</span>
              )}
            </div>
          </fieldset>
          <div className="row">
            <label>ESI
              <select value={form.esi} onChange={set('esi')}>
                <option value="auto">Decide from pay</option>
                <option value="yes">Covered</option>
                <option value="no">Not covered</option>
              </select>
            </label>
            <label className="check"><input type="checkbox" checked={form.pf_member} onChange={set('pf_member')} /> PF member</label>
            <label className="check"><input type="checkbox" checked={form.pt_applicable} onChange={set('pt_applicable')} /> Professional tax</label>
          </div>
          <details>
            <summary>Income tax (regime and declarations)</summary>
            <TaxFields value={tax} onChange={setTax} errors={fieldErrors} />
          </details>
          <button className="primary" disabled={total <= 0}>Add employee</button>
        </form>
      </section>
      </div>
    </div>
  )
}
