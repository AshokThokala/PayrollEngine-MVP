import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { deductionValue } from '../pages/DeductionsPage.jsx'

const EMPTY = { deduction_code: '', value: '', start_month: '', end_month: '', note: '' }
const thisMonth = () => new Date().toISOString().slice(0, 7)
const monthLabel = (iso) => (iso ? new Date(`${iso.slice(0, 7)}-01T00:00:00`).toLocaleString('en-IN', { month: 'short', year: 'numeric' }) : '')

// Standing deductions for one employee (VPF, loan EMI, ...). Click a row to edit it.
export default function EmployeeDeductions({ client, employee }) {
  const [items, setItems] = useState([])
  const [types, setTypes] = useState([])
  const [editing, setEditing] = useState(null) // id, 'new' or null
  const [form, setForm] = useState(EMPTY)
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState(null)

  const load = useCallback(async () => {
    try {
      setItems(await api.employeeDeductions(client.id, employee.code))
    } catch (e) {
      setMessage({ kind: 'error', text: e.message })
    }
  }, [client.id, employee.code])

  useEffect(() => {
    setEditing(null)
    setMessage(null)
    load()
  }, [load])
  useEffect(() => {
    api.deductionTypes().then((d) => setTypes(d.types.filter((t) => t.calc !== 'statutory'))).catch(() => {})
  }, [])

  const type = types.find((t) => t.code === form.deduction_code)
  const percent = type && type.calc !== 'fixed'

  const open = (d) => {
    setErrors({})
    setMessage(null)
    if (d) {
      setEditing(d.id)
      setForm({ deduction_code: d.deduction_code, value: d.value, start_month: d.start_month.slice(0, 7),
        end_month: d.end_month ? d.end_month.slice(0, 7) : '', note: d.note })
    } else {
      setEditing('new')
      setForm({ ...EMPTY, start_month: thisMonth() })
    }
  }

  const set = (k) => (e) => {
    const next = { ...form, [k]: e.target.value }
    if (k === 'deduction_code' && !form.value) {
      const t = types.find((x) => x.code === e.target.value)
      if (t?.default_value != null) next.value = t.default_value
    }
    setForm(next)
    if (errors[k]) setErrors({ ...errors, [k]: undefined })
  }

  async function save(e) {
    e.preventDefault()
    setErrors({})
    const body = { ...form, value: form.value === '' ? null : String(form.value), end_month: form.end_month || null }
    try {
      if (editing === 'new') await api.addEmployeeDeduction(client.id, employee.code, body)
      else await api.editEmployeeDeduction(client.id, employee.code, editing, body)
      setEditing(null)
      setMessage({ kind: 'ok', text: 'Deduction saved. Payroll runs from its first month take it automatically.' })
      load()
    } catch (err) {
      setErrors(err.fieldErrors || {})
      setMessage({ kind: 'error', text: err.message })
    }
  }

  async function remove() {
    if (!window.confirm('Remove this deduction? Runs already calculated keep it; future runs will not.')) return
    try {
      await api.deleteEmployeeDeduction(client.id, employee.code, editing)
      setEditing(null)
      setMessage({ kind: 'ok', text: 'Deduction removed.' })
      load()
    } catch (err) {
      setMessage({ kind: 'error', text: err.message })
    }
  }

  const err = (k, label) => errors[k] && <span className="field-error">{label}: {errors[k]}</span>

  return (
    <div className="form section">
      <div className="run-head">
        <h3>Deductions</h3>
        {editing === null && <button type="button" onClick={() => open(null)}>+ Add deduction</button>}
      </div>
      <p className="muted small">PF, ESI, PT and TDS are automatic. Add voluntary deductions and recoveries here.</p>
      {items.length > 0 && (
        <table className="clickable compact">
          <thead><tr><th>Deduction</th><th className="num">Amount</th><th>Months</th></tr></thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.id} tabIndex={0} className={editing === d.id ? 'selected' : undefined}
                  onClick={() => open(d)} onKeyDown={(e) => e.key === 'Enter' && open(d)}>
                <td>{d.name}</td>
                <td className="num">{deductionValue(d.calc, d.value)}</td>
                <td className="small">{monthLabel(d.start_month)} → {d.end_month ? monthLabel(d.end_month) : 'ongoing'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {editing !== null && (
        <form className="form deduction-form" onSubmit={save}>
          <div className="row">
            <label>
              Deduction
              <select value={form.deduction_code} onChange={set('deduction_code')} disabled={editing !== 'new'}
                className={errors.deduction_code ? 'invalid' : undefined}>
                <option value="">Choose…</option>
                {['voluntary', 'recovery'].map((cat) => (
                  <optgroup key={cat} label={cat === 'voluntary' ? 'Voluntary' : 'Recoveries'}>
                    {types.filter((t) => t.category === cat && (t.active || t.code === form.deduction_code)).map((t) => (
                      <option key={t.code} value={t.code}>{t.name}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
              {err('deduction_code', 'Deduction')}
            </label>
            <label>
              {percent ? `Percent of ${type.calc === 'percent_basic' ? 'basic + DA' : 'gross'}` : 'Amount (₹ per month)'}
              <input inputMode="decimal" value={form.value} onChange={set('value')} className={errors.value ? 'invalid' : undefined} />
              {err('value', 'Amount')}
            </label>
          </div>
          <div className="row">
            <label>
              First month
              <input type="month" value={form.start_month} onChange={set('start_month')} className={errors.start_month ? 'invalid' : undefined} />
              {err('start_month', 'First month')}
            </label>
            <label>
              Last month <span className="muted small">(blank = ongoing)</span>
              <input type="month" value={form.end_month} onChange={set('end_month')} className={errors.end_month ? 'invalid' : undefined} />
              {err('end_month', 'Last month')}
            </label>
          </div>
          <label>Note<input value={form.note} onChange={set('note')} placeholder="e.g. ₹30,000 advance, 12 months" /></label>
          {type?.max_amount != null && <p className="muted small">Capped at {deductionValue('fixed', type.max_amount)} a month.</p>}
          {message?.kind === 'error' && <div className="banner error">{message.text}</div>}
          <div className="actions">
            <button className="primary">Save deduction</button>
            <button type="button" onClick={() => { setEditing(null); setMessage(null) }}>Cancel</button>
            {editing !== 'new' && <button type="button" className="link danger" onClick={remove}>Remove</button>}
          </div>
        </form>
      )}
      {message?.kind === 'ok' && <div className="banner ok">{message.text}</div>}
    </div>
  )
}
