import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, money, today } from '../api.js'
import InfoTip from '../components/InfoTip.jsx'
import TaxFields, { EMPTY_TAX, taxFromEmployee } from '../components/TaxFields.jsx'

const COMPONENTS = [
  ['basic', 'Basic'],
  ['da', 'DA'],
  ['hra', 'HRA'],
  ['conveyance', 'Conveyance'],
  ['special_allowance', 'Special allowance'],
]

const FLAGS = [
  ['pf_member', 'PF member', 'Deduct Provident Fund.'],
  ['eps_member', 'Pension (EPS) member', 'Untick once the employee turns 58.'],
  ['pf_on_full_wages', 'PF on full wages', 'Voluntary PF above the wage ceiling (joint option).'],
  ['pt_applicable', 'Professional tax', 'Deduct the state professional tax.'],
  ['lwf_applicable', 'Labour welfare fund', 'Deduct the state LWF in its months.'],
]

const EMPTY = {
  code: '', name: '', joined_on: today(),
  basic: '', da: '', hra: '', conveyance: '', special_allowance: '',
  esi: 'auto', pf_member: true, eps_member: true, pf_on_full_wages: false, pt_applicable: true, lwf_applicable: true,
}

function formFrom(emp) {
  const f = { ...EMPTY, code: emp.code, name: emp.name, joined_on: emp.joined_on }
  COMPONENTS.forEach(([k]) => { f[k] = emp.components[k] !== undefined ? String(Number(emp.components[k])) : '' })
  Object.entries(emp.flags || {}).forEach(([k, v]) => {
    if (k === 'esi_covered') f.esi = v === null ? 'auto' : v ? 'yes' : 'no'
    else f[k] = v
  })
  return f
}

function FieldError({ label, error }) {
  return error ? <span className="field-error">{label}: {error}</span> : null
}

export default function EmployeesPage({ client, onViewAs }) {
  const [employees, setEmployees] = useState([])
  const [mode, setMode] = useState('none') // none | add | edit
  const [selectedCode, setSelectedCode] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [tax, setTax] = useState(EMPTY_TAX)
  const [exitOn, setExitOn] = useState('')
  const [search, setSearch] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})
  const [taxErrors, setTaxErrors] = useState({})
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const list = await api.listEmployees(client.id)
      setEmployees(list)
      return list
    } catch (err) {
      setMessage({ kind: 'error', text: err.message })
      return []
    }
  }, [client.id])

  useEffect(() => {
    load()
    setMode('none')
    setSelectedCode(null)
  }, [load])

  const selected = employees.find((e) => e.code === selectedCode)
  const shown = useMemo(() => {
    const q = search.trim().toLowerCase()
    return employees.filter((e) => !q || e.name.toLowerCase().includes(q) || e.code.toLowerCase().includes(q))
  }, [employees, search])

  const set = (key) => (e) => {
    setForm({ ...form, [key]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
    const errorKey = COMPONENTS.some(([k]) => k === key) ? 'components' : key
    if (fieldErrors[errorKey]) setFieldErrors({ ...fieldErrors, [errorKey]: undefined })
  }
  const invalid = (key) => (fieldErrors[key] ? { className: 'invalid', 'aria-invalid': true } : {})

  const total = COMPONENTS.reduce((sum, [k]) => sum + (Number(form[k]) || 0), 0)
  const wageShare = total ? (Number(form.basic || 0) + Number(form.da || 0)) / total : 1
  const components = () => Object.fromEntries(COMPONENTS.filter(([k]) => Number(form[k]) > 0).map(([k]) => [k, Number(form[k])]))
  const flags = () => ({
    ...Object.fromEntries(FLAGS.map(([k]) => [k, form[k]])),
    esi_covered: form.esi === 'auto' ? null : form.esi === 'yes',
  })

  const reset = () => { setFieldErrors({}); setTaxErrors({}); setMessage(null) }

  const startAdd = () => {
    reset()
    setMode('add')
    setSelectedCode(null)
    setForm(EMPTY)
    setTax(EMPTY_TAX)
  }

  const select = (emp) => {
    reset()
    setMode('edit')
    setSelectedCode(emp.code)
    setForm(formFrom(emp))
    setTax(taxFromEmployee(emp))
    setExitOn('')
  }

  const run = async (fn) => {
    setBusy(true)
    setFieldErrors({})
    setTaxErrors({})
    try {
      await fn()
    } catch (err) {
      setFieldErrors(err.fieldErrors || {})
      setTaxErrors(err.fieldErrors || {})
      setMessage({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  const add = (e) => {
    e.preventDefault()
    run(async () => {
      const res = await api.addEmployee(client.id, {
        code: form.code, name: form.name, joined_on: form.joined_on,
        components: components(), ...flags(), tax,
      })
      const list = await load()
      const created = list.find((x) => x.code === res.employee.code)
      if (created) select(created)
      setMessage(res.warnings.length
        ? { kind: 'warn', text: `Added with a warning: ${res.warnings.join(' ')}` }
        : { kind: 'ok', text: `${res.employee.name} added.` })
    })
  }

  const saveDetails = (e) => {
    e.preventDefault()
    run(async () => {
      const res = await api.updateEmployee(client.id, selectedCode, { name: form.name, components: components(), flags: flags() })
      await load()
      setMessage(res.warnings.length
        ? { kind: 'warn', text: `Saved with a warning: ${res.warnings.join(' ')}` }
        : { kind: 'ok', text: 'Details saved. Recalculate this month\'s draft to apply them.' })
    })
  }

  const saveTax = (e) => {
    e.preventDefault()
    run(async () => {
      await api.updateTax(client.id, selectedCode, tax)
      await load()
      setMessage({ kind: 'ok', text: 'Tax details saved. Recalculate this month\'s draft to update TDS.' })
    })
  }

  const markExit = () => run(async () => {
    await api.exitEmployee(client.id, selectedCode, exitOn)
    await load()
    setMessage({ kind: 'ok', text: `Marked as exited on ${exitOn}.` })
  })

  const salaryFields = (
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
  )

  const statutoryFields = (
    <fieldset>
      <legend>Statutory settings</legend>
      <label className="row-label">ESI
        <select value={form.esi} onChange={set('esi')}>
          <option value="auto">Decide from pay</option>
          <option value="yes">Covered</option>
          <option value="no">Not covered</option>
        </select>
      </label>
      {FLAGS.map(([k, label, help]) => (
        <label key={k} className="check">
          <input type="checkbox" checked={!!form[k]} onChange={set(k)} />
          <span className="label-text">{label}<InfoTip id={`tip-${k}`} text={help} /></span>
        </label>
      ))}
    </fieldset>
  )

  return (
    <div className="grid">
      <section className="card">
        <div className="run-head">
          <h2>Employees <span className="tag">{employees.filter((e) => !e.exited_on).length} active</span></h2>
          <button className="primary" onClick={startAdd}>+ Add employee</button>
        </div>
        <input className="search" placeholder="Search by name or code" value={search}
          onChange={(e) => setSearch(e.target.value)} aria-label="Search employees" />
        {shown.length === 0 ? (
          <p className="muted">{employees.length ? 'No employees match.' : 'No employees yet.'}</p>
        ) : (
          <div className="table-wrap">
            <table className="clickable">
              <thead><tr><th>Name</th><th>Code</th><th className="num">Monthly pay</th><th>Status</th></tr></thead>
              <tbody>
                {shown.map((emp) => (
                  <tr key={emp.code} tabIndex={0}
                    className={`${emp.exited_on ? 'dim' : ''} ${selectedCode === emp.code ? 'selected' : ''}`}
                    onClick={() => select(emp)} onKeyDown={(e) => { if (e.key === 'Enter') select(emp) }}>
                    <td><strong>{emp.name}</strong></td>
                    <td>{emp.code}</td>
                    <td className="num">{money(emp.monthly_total)}</td>
                    <td>{emp.exited_on ? <span className="tag">Left {emp.exited_on}</span> : <span className="tag locked">Active</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted small">Click an employee to view or edit.</p>
      </section>

      {mode === 'none' && (
        <section className="card empty-state">
          <h2>Employee details</h2>
          <p className="muted">Select an employee on the left to see and edit their salary, statutory settings and tax, or add a new one.</p>
          <button onClick={startAdd}>+ Add employee</button>
        </section>
      )}

      {mode === 'add' && (
        <section className="card allow-overflow">
          <h2>Add employee</h2>
          {message && <div className={`banner ${message.kind}`}>{message.text}</div>}
          <form onSubmit={add} className="form">
            <div className="row">
              <label>Code<input required value={form.code} onChange={set('code')} {...invalid('code')} />
                <FieldError label="Employee code" error={fieldErrors.code} /></label>
              <label>Joined on<input type="date" required value={form.joined_on} onChange={set('joined_on')} {...invalid('joined_on')} />
                <FieldError label="Joined on" error={fieldErrors.joined_on} /></label>
            </div>
            <label>Name<input required value={form.name} onChange={set('name')} {...invalid('name')} />
              <FieldError label="Name" error={fieldErrors.name} /></label>
            {salaryFields}
            {statutoryFields}
            <details>
              <summary>Income tax (regime and declarations)</summary>
              <TaxFields value={tax} onChange={setTax} errors={taxErrors} />
            </details>
            <div className="inline">
              <button className="primary" disabled={busy || total <= 0}>Add employee</button>
              <button type="button" onClick={() => setMode('none')}>Cancel</button>
            </div>
          </form>
        </section>
      )}

      {mode === 'edit' && selected && (
        <section className="card allow-overflow">
          <div className="run-head">
            <div>
              <h2>{selected.name}</h2>
              <p className="muted small">{selected.code} · joined {selected.joined_on}{selected.exited_on ? ` · left ${selected.exited_on}` : ''}</p>
            </div>
            <div className="actions">
              <button onClick={() => onViewAs(selected.code)} title="See the employee portal exactly as this employee does (read-only)">
                View as employee
              </button>
              <button onClick={() => { setMode('none'); setSelectedCode(null) }}>Close</button>
            </div>
          </div>
          {message && <div className={`banner ${message.kind}`}>{message.text}</div>}

          <form onSubmit={saveDetails} className="form">
            <label>Name<input required value={form.name} onChange={set('name')} {...invalid('name')} />
              <FieldError label="Name" error={fieldErrors.name} /></label>
            {salaryFields}
            {statutoryFields}
            <div className="inline">
              <button className="primary" disabled={busy || total <= 0}>Save details</button>
              <span className="muted small">A salary change is kept as a new version.</span>
            </div>
          </form>

          <form onSubmit={saveTax} className="form section">
            <h3>Income tax</h3>
            <TaxFields value={tax} onChange={setTax} errors={taxErrors} />
            <div><button className="primary" disabled={busy}>Save tax details</button></div>
          </form>

          {!selected.exited_on && (
            <div className="form section">
              <h3>Exit</h3>
              <div className="inline">
                <input type="date" value={exitOn} onChange={(e) => setExitOn(e.target.value)} aria-label="Exit date"
                  className={fieldErrors.exit_on ? 'invalid' : undefined} />
                <button disabled={!exitOn || busy} onClick={markExit}>Mark as exited</button>
              </div>
              <FieldError label="Exit date" error={fieldErrors.exit_on} />
            </div>
          )}
        </section>
      )}
    </div>
  )
}
