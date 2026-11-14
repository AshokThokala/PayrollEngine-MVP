import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'

const FILTERS = [['all', 'All'], ['fixed', 'Salary'], ['variable', 'Variable']]
const TAX_TAG = { taxable: 'draft', partly_exempt: 'approved', exempt: 'paid' }
const EMPTY = { code: '', name: '', kind: 'fixed', tax: 'taxable', calc: 'fixed', default_value: '', payslip_label: '',
  tax_section: '', description: '', core: false, active: true }
export const payValue = (calc, v) =>
  v === null || v === undefined || v === '' ? '—' : calc === 'percent_basic' ? `${Number(v)}% of basic` : `₹${new Intl.NumberFormat('en-IN').format(Number(v))}`

// Master list of pay codes (earnings) for Indian payroll. Click a row to edit it.
export default function PayCodesPage() {
  const [data, setData] = useState(null)
  const [filter, setFilter] = useState('all')
  const [selected, setSelected] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const d = await api.payCodes()
      setData(d)
      return d
    } catch (e) {
      setMessage({ kind: 'error', text: e.message })
      return null
    }
  }, [])
  useEffect(() => { load() }, [load])

  const open = (p) => {
    setSelected(p ? p.code : 'new')
    setErrors({})
    setMessage(null)
    setForm(p ? { ...EMPTY, ...p, default_value: p.default_value ?? '' } : EMPTY)
  }
  const set = (k) => (e) => {
    setForm({ ...form, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
    if (errors[k]) setErrors({ ...errors, [k]: undefined })
  }

  async function save(e) {
    e.preventDefault()
    setBusy(true)
    setErrors({})
    const body = { ...form, default_value: form.default_value === '' ? null : String(form.default_value) }
    try {
      const p = selected === 'new' ? await api.addPayCode(body) : await api.editPayCode(selected, body)
      await load()
      open(p)
      setMessage({ kind: 'ok', text: `${p.name} saved.` })
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
  const shown = data.codes.filter((p) => filter === 'all' || p.kind === filter)
  const current = selected && selected !== 'new' ? data.codes.find((p) => p.code === selected) : null

  const field = (k, label, props = {}) => (
    <label>
      {label}
      <input value={form[k] ?? ''} onChange={set(k)} className={errors[k] ? 'invalid' : undefined}
        aria-invalid={errors[k] ? true : undefined} {...props} />
      {errors[k] && <span className="field-error">{label}: {errors[k]}</span>}
    </label>
  )

  return (
    <div className="grid">
      <section className="card">
        <div className="run-head">
          <h2>Pay codes <span className="tag">{data.codes.filter((p) => p.active).length} active</span></h2>
          <button className="primary" onClick={() => open(null)}>+ Add pay code</button>
        </div>
        <div className="segmented three" role="tablist" aria-label="Type">
          {FILTERS.map(([k, label]) => (
            <button key={k} role="tab" aria-selected={filter === k} className={filter === k ? 'active' : ''} onClick={() => setFilter(k)}>{label}</button>
          ))}
        </div>
        <div className="table-wrap">
          <table className="clickable">
            <thead><tr><th>Pay code</th><th>Type</th><th>Tax</th><th>Default</th></tr></thead>
            <tbody>
              {shown.map((p) => (
                <tr key={p.code} tabIndex={0} className={`${selected === p.code ? 'selected' : ''} ${p.active ? '' : 'dim'}`}
                    onClick={() => open(p)} onKeyDown={(e) => e.key === 'Enter' && open(p)}>
                  <td>
                    <strong>{p.name}</strong>
                    {p.in_wages && <span className="tag locked tiny">wages</span>}
                    {p.core && <span className="tag tiny">core</span>}
                  </td>
                  <td className="small">{p.kind === 'fixed' ? 'Salary' : 'Variable'}</td>
                  <td><span className={`tag ${TAX_TAG[p.tax]}`}>{p.tax.replace('_', ' ')}</span></td>
                  <td className="small">{payValue(p.calc, p.default_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        {!selected ? (
          <>
            <h2>How pay codes work</h2>
            <ul className="steps-list">
              <li><strong>Salary</strong> pay codes make up the monthly structure: basic, DA, HRA, allowances, reimbursements.</li>
              <li><strong>Variable</strong> pay codes are entered for a payroll month: bonus, incentive, arrears, leave encashment.</li>
              <li><span className="tag locked tiny">wages</span> Basic, DA and retaining allowance are wages under the Code on Wages; together they must be at least 50% of pay.</li>
              <li><span className="tag tiny">core</span> pay codes are on for every client; clients switch the others on under <strong>Client pay codes</strong>.</li>
            </ul>
          </>
        ) : (
          <form className="form" onSubmit={save}>
            <div className="run-head">
              <h2>{selected === 'new' ? 'Add pay code' : current?.name}</h2>
              <button type="button" onClick={() => setSelected(null)}>Close</button>
            </div>
            {current?.system && <p className="muted small">Shipped with ClearPay4U: its code and type stay fixed.</p>}
            <div className="row">
              {field('name', 'Name')}
              {field('code', 'Code', { disabled: selected !== 'new', placeholder: 'e.g. night_allowance' })}
            </div>
            <div className="row">
              <label>
                Type
                <select value={form.kind} onChange={set('kind')} disabled={current?.system} className={errors.kind ? 'invalid' : undefined}>
                  <option value="fixed">Salary (every month)</option>
                  <option value="variable">Variable (entered for a month)</option>
                </select>
                {errors.kind && <span className="field-error">Type: {errors.kind}</span>}
              </label>
              <label>
                Tax treatment
                <select value={form.tax} onChange={set('tax')}>
                  {Object.entries(data.tax).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </select>
              </label>
            </div>
            <div className="row">
              <label>
                Default calculation
                <select value={form.calc} onChange={set('calc')} disabled={form.kind === 'variable'} className={errors.calc ? 'invalid' : undefined}>
                  {Object.entries(data.calcs).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </select>
                {errors.calc && <span className="field-error">Default calculation: {errors.calc}</span>}
              </label>
              {field('default_value', form.calc === 'percent_basic' ? 'Default %' : 'Default ₹', { inputMode: 'decimal', placeholder: 'optional' })}
            </div>
            <div className="row">
              {field('payslip_label', 'Name on payslip', { placeholder: form.name || 'same as name' })}
              {field('tax_section', 'Tax section', { placeholder: 'e.g. 10(13A)' })}
            </div>
            <label>Description<textarea rows={2} value={form.description} onChange={set('description')} /></label>
            {form.kind === 'fixed' && (
              <label className="check"><input type="checkbox" checked={form.core} onChange={set('core')} /> On for every client (core)</label>
            )}
            <label className="check">
              <input type="checkbox" checked={form.active} onChange={set('active')} disabled={form.code === 'basic'} />
              Active
            </label>
            {errors.active && <span className="field-error">Active: {errors.active}</span>}
            {current?.in_wages && <p className="muted small">Counts as wages for PF, gratuity and bonus (Code on Wages rule).</p>}
            {message && <div className={`banner ${message.kind}`}>{message.text}</div>}
            <div className="actions"><button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button></div>
          </form>
        )}
      </section>
    </div>
  )
}
