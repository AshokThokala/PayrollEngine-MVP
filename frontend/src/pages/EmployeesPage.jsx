import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import EmployeeDeductions from '../components/EmployeeDeductions.jsx'
import PickerSearch from '../components/PickerSearch.jsx'
import { EmployeeSuggestion, matchEmployee } from '../components/ClientEmployees.jsx'
import EmployeeDetails, { ageFrom } from '../components/EmployeeDetails.jsx'
import { api, money, today } from '../api.js'
import InfoTip from '../components/InfoTip.jsx'
import TaxFields, { EMPTY_TAX, taxFromEmployee } from '../components/TaxFields.jsx'

// Fallback until the client's salary pay codes load.
const DEFAULT_COMPONENTS = [
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
  basic: '', da: '', hra: '', conveyance: '', special_allowance: '', pay_type: 'salaried', hourly_rate: '', location_id: '',
  esi: 'auto', pf_member: true, eps_member: true, pf_on_full_wages: false, pt_applicable: true, lwf_applicable: true,
}

function formFrom(emp, list) {
  const f = { ...EMPTY, code: emp.code, name: emp.name, joined_on: emp.joined_on,
    pay_type: emp.pay_type || 'salaried', hourly_rate: Number(emp.hourly_rate) ? String(Number(emp.hourly_rate)) : '',
    location_id: emp.location_id || '' }
  const keys = new Set([...list.map(([k]) => k), ...Object.keys(emp.components)])
  ;[...keys].forEach((k) => { f[k] = emp.components[k] !== undefined ? String(Number(emp.components[k])) : '' })
  Object.entries(emp.flags || {}).forEach(([k, v]) => {
    if (k === 'esi_covered') f.esi = v === null ? 'auto' : v ? 'yes' : 'no'
    else f[k] = v
  })
  return f
}

function FieldError({ label, error }) {
  return error ? <span className="field-error">{label}: {error}</span> : null
}

export default function EmployeesPage({ client, onViewAs, openRequest }) {
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
  const [loadedFor, setLoadedFor] = useState(null)
  const handled = useRef(null)
  // Salary fields = the fixed pay codes this client uses (Client pay codes), with their payslip names.
  const [locations, setLocations] = useState([])
  useEffect(() => {
    api.clientLocations(client.id).then(setLocations).catch(() => setLocations([]))
  }, [client.id])
  const locationName = (id) => (locations.find((l) => l.id === id) || (!id && locations.find((l) => l.head_office)))?.name
  const [profileFacts, setProfileFacts] = useState({}) // gender and date of birth for the header, from EmployeeDetails
  useEffect(() => { setProfileFacts({}) }, [selectedCode])
  const [payCodes, setPayCodes] = useState([])
  useEffect(() => {
    api.availablePayCodes(client.id).then((list) => setPayCodes(list.filter((p) => p.kind === 'fixed'))).catch(() => setPayCodes([]))
  }, [client.id])
  const COMPONENTS = payCodes.length ? payCodes.map((p) => [p.code, p.payslip_label || p.name]) : DEFAULT_COMPONENTS
  const suggestion = (k) => {
    const p = payCodes.find((x) => x.code === k)
    if (!p || p.default_value == null) return undefined
    return p.calc === 'percent_basic'
      ? (Number(form.basic) ? String(Math.round(Number(form.basic) * Number(p.default_value) / 100)) : `${Number(p.default_value)}% of basic`)
      : String(Number(p.default_value))
  }

  const load = useCallback(async () => {
    try {
      const list = await api.listEmployees(client.id)
      setEmployees(list)
      setLoadedFor(client.id)
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
    const errorKey = FIELDS.some(([k]) => k === key) ? 'components' : key
    if (fieldErrors[errorKey]) setFieldErrors({ ...fieldErrors, [errorKey]: undefined })
  }
  const invalid = (key) => (fieldErrors[key] ? { className: 'invalid', 'aria-invalid': true } : {})

  // Pay codes shown: the client's, plus any the selected employee still has.
  const extra = mode === 'edit' && selected ? Object.keys(selected.components).filter((k) => !COMPONENTS.some(([c]) => c === k)) : []
  const FIELDS = [...COMPONENTS, ...extra.map((k) => [k, `${k} (not used by client)`])]
  const total = FIELDS.reduce((sum, [k]) => sum + (Number(form[k]) || 0), 0)
  const wageShare = total ? (Number(form.basic || 0) + Number(form.da || 0)) / total : 1
  const components = () => Object.fromEntries(FIELDS.filter(([k]) => Number(form[k]) > 0).map(([k]) => [k, Number(form[k])]))
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
    setForm(formFrom(emp, COMPONENTS))
    setTax(taxFromEmployee(emp))
    setExitOn('')
  }

  // Opened from the search box: select that employee once their client's list has loaded.
  useEffect(() => {
    if (!openRequest || handled.current === openRequest.n) return
    if (openRequest.clientId !== client.id || loadedFor !== client.id) return
    const emp = employees.find((e) => e.code === openRequest.code)
    if (!emp) return
    handled.current = openRequest.n
    setSearch('')
    select(emp)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openRequest, employees, loadedFor, client.id])

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
        components: form.pay_type === 'hourly' ? {} : components(), ...flags(), tax,
        pay_type: form.pay_type, hourly_rate: form.pay_type === 'hourly' ? Number(form.hourly_rate) || null : null,
        location_id: form.location_id || null,
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
      const hourlyNow = form.pay_type === 'hourly'
      const res = await api.updateEmployee(client.id, selectedCode, {
        name: form.name, flags: flags(), pay_type: form.pay_type, location_id: form.location_id || null,
        ...(hourlyNow ? { hourly_rate: Number(form.hourly_rate) || null } : { components: components() }),
      })
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

  const payTypeField = (
    <div className="row">
      {locations.length > 0 && (
        <label>
          Work location
          <select value={form.location_id || ''} onChange={set('location_id')} {...invalid('location_id')}>
            {mode === 'add' && <option value="">{locations.find((l) => l.head_office)?.name || 'Head office'} (default)</option>}
            {locations.filter((l) => l.active || l.id === form.location_id).map((l) => (
              <option key={l.id} value={l.id}>{l.name} · {l.state_name}</option>
            ))}
          </select>
          <FieldError label="Location" error={fieldErrors.location_id} />
        </label>
      )}
      <label>
        Pay type
        <select value={form.pay_type} onChange={set('pay_type')} {...invalid('pay_type')}>
          <option value="salaried">Salaried (monthly salary)</option>
          <option value="hourly">Hourly (paid for hours worked)</option>
        </select>
        <FieldError label="Pay type" error={fieldErrors.pay_type} />
      </label>
      {form.pay_type === 'hourly' && (
        <label>
          Hourly rate (₹)
          <input type="number" min="0" step="0.01" value={form.hourly_rate} onChange={set('hourly_rate')} {...invalid('hourly_rate')} />
          <FieldError label="Hourly rate" error={fieldErrors.hourly_rate} />
        </label>
      )}
    </div>
  )

  const salaryFields = form.pay_type === 'hourly' ? (
    <>
      {payTypeField}
      <p className="muted small">Pay comes from the hours entered on <strong>Time entry</strong> each month (hours × rate, overtime at 2×). All of it counts as wages for PF and ESI.</p>
    </>
  ) : (
    <>
    {payTypeField}
    <fieldset>
      <legend>Monthly salary (₹)</legend>
      {FIELDS.map(([k, label]) => (
        <label key={k} className="row-label">{label}
          <input type="number" min="0" step="0.01" value={form[k] ?? ''} onChange={set(k)} placeholder={suggestion(k)} />
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
    </>
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
    <div className="stack">
      <section className="card search-bar">
        <PickerSearch
          items={employees}
          match={matchEmployee}
          render={(e, q) => <EmployeeSuggestion e={e} q={q} />}
          onPick={select}
          placeholder={`Search ${employees.filter((e) => !e.exited_on).length} employees of ${client.legal_name} by name, code or designation`}
          label="Search employees"
        />
        <button className="primary" onClick={startAdd}>+ Add employee</button>
      </section>

      {mode === 'none' && (
        <section className="card empty-state">
          <h2>Find an employee</h2>
          <p className="muted">{employees.length ? 'Search above to open an employee: details, salary, statutory settings, tax and deductions. To see everyone, open the client on the Clients page.' : 'No employees yet. Add the first one.'}</p>
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
              <div className="emp-head">
                <span className="emp-avatar" aria-hidden="true">{selected.name.split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase()}</span>
                <div>
                  <h2>{selected.name}</h2>
                  <p className="muted small">
                    {[selected.designation, selected.department].filter(Boolean).join(' · ') || 'No designation yet'}
                  </p>
                  <div className="chips">
                    <span className="chip">{selected.code}</span>
                    <span className="chip">{selected.pay_type === 'hourly' ? 'Hourly' : 'Salaried'}</span>
                    <span className="chip">Joined {selected.joined_on}</span>
                    {locationName(selected.location_id) && <span className="chip">{locationName(selected.location_id)} · {selected.state}</span>}
                    {profileFacts.gender && <span className="chip">{profileFacts.gender}</span>}
                    {ageFrom(profileFacts.date_of_birth) !== null && <span className="chip">{ageFrom(profileFacts.date_of_birth)} yrs</span>}
                    {selected.exited_on && <span className="chip warn">Left {selected.exited_on}</span>}
                  </div>
                </div>
              </div>
            </div>
            <div className="actions">
              <button onClick={() => onViewAs(selected.code)} title="See the employee portal exactly as this employee does (read-only)">
                View as employee
              </button>
              <button onClick={() => { setMode('none'); setSelectedCode(null) }}>Close</button>
            </div>
          </div>
          {message && <div className={`banner ${message.kind}`}>{message.text}</div>}

          <EmployeeDetails client={client} employee={selected} onSaved={(p) => {
            setProfileFacts({ gender: p.gender ? p.gender[0].toUpperCase() + p.gender.slice(1).replace(/_/g, ' ') : '', date_of_birth: p.date_of_birth })
            setEmployees((list) => list.map((e) => (e.code === selected.code ? { ...e, designation: p.designation, department: p.department } : e)))
          }} />

          <form onSubmit={saveDetails} className="form section">
            <h3>Pay and statutory settings</h3>
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

          <EmployeeDeductions client={client} employee={selected} />

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
