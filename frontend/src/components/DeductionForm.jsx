import { useEffect, useState } from 'react'
import { deductionValue } from '../pages/DeductionsPage.jsx'

const thisMonth = () => new Date().toISOString().slice(0, 7)

// Add or edit one standing employee deduction. `types` are the deductions the client uses.
// Pass `employees` to show an employee picker (client-wide page); leave it out on an employee's own record.
export default function DeductionForm({ types, employees, initial, errors = {}, error, busy, onSave, onCancel, onDelete }) {
  const isNew = !initial?.id
  const [form, setForm] = useState({})

  useEffect(() => {
    setForm(initial?.id
      ? { employee_code: initial.employee_code, deduction_code: initial.deduction_code, value: initial.value ?? '',
          start_month: initial.start_month.slice(0, 7), end_month: initial.end_month ? initial.end_month.slice(0, 7) : '',
          note: initial.note || '' }
      : { employee_code: initial?.employee_code || '', deduction_code: '', value: '', start_month: thisMonth(),
          end_month: '', note: '' })
  }, [initial])

  const type = types.find((t) => t.code === form.deduction_code)
  const percent = type && type.calc !== 'fixed'

  const set = (k) => (e) => {
    const next = { ...form, [k]: e.target.value }
    if (k === 'deduction_code') {
      const t = types.find((x) => x.code === e.target.value)
      if (t?.default_value != null && (!form.value || isNew)) next.value = t.default_value
    }
    setForm(next)
  }

  const err = (k, label) => errors[k] && <span className="field-error">{label}: {errors[k]}</span>

  const submit = (e) => {
    e.preventDefault()
    onSave({ ...form, value: form.value === '' ? null : String(form.value), end_month: form.end_month || null })
  }

  return (
    <form className="form deduction-form" onSubmit={submit}>
      {employees && (
        <label>
          Employee
          <select value={form.employee_code || ''} onChange={set('employee_code')} disabled={!isNew}
            className={errors.employee_code ? 'invalid' : undefined}>
            <option value="">Choose…</option>
            {employees.map((e) => <option key={e.code} value={e.code}>{e.name} ({e.code})</option>)}
          </select>
          {err('employee_code', 'Employee')}
        </label>
      )}
      <div className="row">
        <label>
          Deduction
          <select value={form.deduction_code || ''} onChange={set('deduction_code')} disabled={!isNew}
            className={errors.deduction_code ? 'invalid' : undefined}>
            <option value="">Choose…</option>
            {['voluntary', 'recovery'].map((cat) => (
              <optgroup key={cat} label={cat === 'voluntary' ? 'Voluntary' : 'Recoveries'}>
                {types.filter((t) => t.category === cat).map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
              </optgroup>
            ))}
            {!isNew && !type && <option value={form.deduction_code}>{initial?.name} (not used by client)</option>}
          </select>
          {err('deduction_code', 'Deduction')}
        </label>
        <label>
          {percent ? `Percent of ${type.calc === 'percent_basic' ? 'basic + DA' : 'gross'}` : 'Amount (₹ per month)'}
          <input inputMode="decimal" value={form.value ?? ''} onChange={set('value')} className={errors.value ? 'invalid' : undefined} />
          {err('value', 'Amount')}
        </label>
      </div>
      <div className="row">
        <label>
          First month
          <input type="month" value={form.start_month || ''} onChange={set('start_month')} className={errors.start_month ? 'invalid' : undefined} />
          {err('start_month', 'First month')}
        </label>
        <label>
          Last month <span className="muted small">(blank = ongoing)</span>
          <input type="month" value={form.end_month || ''} onChange={set('end_month')} className={errors.end_month ? 'invalid' : undefined} />
          {err('end_month', 'Last month')}
        </label>
      </div>
      <label>Note<input value={form.note || ''} onChange={set('note')} placeholder="e.g. ₹30,000 advance, 12 months" /></label>
      {type?.max_amount != null && <p className="muted small">Capped at {deductionValue('fixed', type.max_amount)} a month for this client.</p>}
      {error && <div className="banner error">{error}</div>}
      <div className="actions">
        <button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save deduction'}</button>
        <button type="button" onClick={onCancel}>Cancel</button>
        {!isNew && onDelete && <button type="button" className="link danger" onClick={onDelete}>Remove</button>}
      </div>
    </form>
  )
}
