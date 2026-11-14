import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'

const CATEGORIES = [
  ['all', 'All'],
  ['statutory', 'Statutory'],
  ['voluntary', 'Voluntary'],
  ['recovery', 'Recoveries'],
]
const CAT_TAG = { statutory: 'locked', voluntary: 'approved', recovery: 'pending' }
const EMPTY = { code: '', name: '', category: 'voluntary', calc: 'fixed', payslip_label: '', default_value: '',
  max_amount: '', tax_section: '', description: '', active: true }
const isPercent = (calc) => calc === 'percent_basic' || calc === 'percent_gross'
export const deductionValue = (calc, v) =>
  v === null || v === undefined || v === '' ? '—' : isPercent(calc) ? `${Number(v)}%` : `₹${new Intl.NumberFormat('en-IN').format(Number(v))}`

// Master list of deductions an employee can have (India). Click a row to edit it, like clients and employees.
export default function DeductionsPage({ canEdit }) {
  const [data, setData] = useState(null)
  const [filter, setFilter] = useState('all')
  const [selected, setSelected] = useState(null) // code, or 'new'
  const [form, setForm] = useState(EMPTY)
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      setData(await api.deductionTypes())
    } catch (e) {
      setMessage({ kind: 'error', text: e.message })
    }
  }, [])
  useEffect(() => { load() }, [load])

  const open = (t) => {
    setSelected(t ? t.code : 'new')
    setErrors({})
    setMessage(null)
    setForm(t ? { ...EMPTY, ...t, default_value: t.default_value ?? '', max_amount: t.max_amount ?? '' } : EMPTY)
  }

  const set = (k) => (e) => {
    const v = e.target.type === 'checkbox' ? e.target.checked : e.target.value
    setForm({ ...form, [k]: v })
    if (errors[k]) setErrors({ ...errors, [k]: undefined })
  }

  async function save(e) {
    e.preventDefault()
    setBusy(true)
    setErrors({})
    const body = { ...form, default_value: form.default_value === '' ? null : String(form.default_value),
      max_amount: form.max_amount === '' ? null : String(form.max_amount) }
    try {
      const t = selected === 'new' ? await api.addDeductionType(body) : await api.editDeductionType(selected, body)
      setMessage({ kind: 'ok', text: `${t.name} saved.` })
      await load()
      open(t)
      setMessage({ kind: 'ok', text: `${t.name} saved.` })
    } catch (err) {
      const fe = { ...(err.fieldErrors || {}) }
      if (fe.type_code) fe.code = fe.type_code
      setErrors(fe)
      setMessage({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  if (!data) return message ? <div className={`banner ${message.kind}`}>{message.text}</div> : <p className="muted">Loading…</p>
  const shown = data.types.filter((t) => filter === 'all' || t.category === filter)
  const current = selected && selected !== 'new' ? data.types.find((t) => t.code === selected) : null
  const statutory = current?.category === 'statutory'
  const shipped = current?.system
  const readOnly = !canEdit

  const field = (k, label, props = {}) => (
    <label>
      {label}
      <input value={form[k] ?? ''} onChange={set(k)} disabled={readOnly || props.disabled}
        className={errors[k] ? 'invalid' : undefined} aria-invalid={errors[k] ? true : undefined} {...props} />
      {errors[k] && <span className="field-error">{label}: {errors[k]}</span>}
    </label>
  )

  return (
    <div className="grid">
      <section className="card">
        <div className="run-head">
          <h2>Deduction types <span className="tag">{data.types.filter((t) => t.active).length} active</span></h2>
          {canEdit && <button className="primary" onClick={() => open(null)}>+ Add deduction</button>}
        </div>
        <div className="segmented small-seg" role="tablist" aria-label="Type">
          {CATEGORIES.map(([k, label]) => (
            <button key={k} role="tab" aria-selected={filter === k} className={filter === k ? 'active' : ''} onClick={() => setFilter(k)}>
              {label}
            </button>
          ))}
        </div>
        <div className="table-wrap">
          <table className="clickable">
            <thead><tr><th>Deduction</th><th>Type</th><th>Calculated as</th><th>Tax</th></tr></thead>
            <tbody>
              {shown.map((t) => (
                <tr key={t.code} tabIndex={0} className={`${selected === t.code ? 'selected' : ''} ${t.active ? '' : 'dim'}`}
                    onClick={() => open(t)} onKeyDown={(e) => e.key === 'Enter' && open(t)}>
                  <td><strong>{t.name}</strong>{!t.active && <span className="muted small"> · off</span>}</td>
                  <td><span className={`tag ${CAT_TAG[t.category]}`}>{t.category}</span></td>
                  <td className="small">{t.calc === 'statutory' ? 'Payroll rules' : `${t.calc_label}${t.default_value != null ? ` · ${deductionValue(t.calc, t.default_value)}` : ''}`}</td>
                  <td className="small">{t.tax_section || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        {!selected ? (
          <>
            <h2>How deductions work</h2>
            <ul className="steps-list">
              <li><strong>Statutory</strong> — PF, ESI, PT, LWF and TDS are worked out every month from the compliance rules.</li>
              <li><strong>Voluntary</strong> — what the employee opts into: VPF, NPS, insurance, donations, canteen.</li>
              <li><strong>Recoveries</strong> — advances, loan EMIs, notice pay.</li>
              <li>Give an employee a deduction on the <strong>Employees</strong> page; each payroll run takes it automatically.</li>
            </ul>
          </>
        ) : (
          <form className="form" onSubmit={save}>
            <div className="run-head">
              <h2>{selected === 'new' ? 'Add deduction' : current?.name}</h2>
              <button type="button" onClick={() => { setSelected(null); setMessage(null) }}>Close</button>
            </div>
            {statutory && (
              <p className="muted small">Worked out by payroll from the compliance rules. You can change its name and description only.</p>
            )}
            {shipped && !statutory && (
              <p className="muted small">Shipped with ClearPay4U: its code and calculation stay fixed.</p>
            )}
            <div className="row">
              {field('name', 'Name')}
              {field('code', 'Code', { disabled: selected !== 'new', placeholder: 'e.g. gym_membership' })}
            </div>
            <div className="row">
              <label>
                Type
                <select value={form.category} onChange={set('category')} disabled={readOnly || statutory}
                  className={errors.category ? 'invalid' : undefined}>
                  {statutory && <option value="statutory">Statutory</option>}
                  <option value="voluntary">Voluntary (employee opts in)</option>
                  <option value="recovery">Recovery (employer gets money back)</option>
                </select>
                {errors.category && <span className="field-error">Type: {errors.category}</span>}
              </label>
              <label>
                Calculated as
                <select value={form.calc} onChange={set('calc')} disabled={readOnly || shipped}
                  className={errors.calc ? 'invalid' : undefined}>
                  {Object.entries(data.calcs).filter(([k]) => k !== 'statutory' || statutory).map(([k, label]) => (
                    <option key={k} value={k}>{label}</option>
                  ))}
                </select>
                {errors.calc && <span className="field-error">Calculated as: {errors.calc}</span>}
              </label>
            </div>
            {!statutory && (
              <div className="row">
                {field('default_value', isPercent(form.calc) ? 'Default %' : 'Default ₹ per month', { inputMode: 'decimal', placeholder: 'optional' })}
                {field('max_amount', 'Monthly cap (₹)', { inputMode: 'decimal', placeholder: 'no cap' })}
              </div>
            )}
            <div className="row">
              {field('payslip_label', 'Name on payslip', { placeholder: form.name || 'same as name' })}
              <label>
                Tax section (old regime)
                <select value={form.tax_section} onChange={set('tax_section')} disabled={readOnly || statutory}
                  className={errors.tax_section ? 'invalid' : undefined}>
                  {data.tax_sections.map((s) => <option key={s} value={s}>{s || 'None'}</option>)}
                </select>
              </label>
            </div>
            <label>
              Description
              <textarea rows={2} value={form.description} onChange={set('description')} disabled={readOnly} />
            </label>
            {!statutory && (
              <label className="check">
                <input type="checkbox" checked={form.active} onChange={set('active')} disabled={readOnly} />
                Active (can be given to employees; switching it off stops it in future payroll runs)
              </label>
            )}
            {message && <div className={`banner ${message.kind}`}>{message.text}</div>}
            {canEdit && <div className="actions"><button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button></div>}
          </form>
        )}
      </section>
    </div>
  )
}
