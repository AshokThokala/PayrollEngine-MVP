import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { deductionValue } from './DeductionsPage.jsx'

const FILTERS = [
  ['on', 'In use'],
  ['all', 'All'],
  ['voluntary', 'Voluntary'],
  ['recovery', 'Recoveries'],
  ['statutory', 'Statutory'],
]
const inFilter = (f, r) =>
  f === 'all' || (f === 'on' && r.enabled) || r.category === f

// Client level: which master deductions this client uses, with the client's own default, cap and payslip name.
export default function ClientDeductionsPage({ client, platform, onGo }) {
  const [rows, setRows] = useState([])
  const [filter, setFilter] = useState('on')
  const [selected, setSelected] = useState(null)
  const [form, setForm] = useState({})
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const r = await api.clientDeductions(client.id)
      setRows(r)
      return r
    } catch (e) {
      setMessage({ kind: 'error', text: e.message })
      return []
    }
  }, [client.id])

  useEffect(() => {
    setSelected(null)
    setMessage(null)
    load()
  }, [load])

  const open = (r) => {
    setSelected(r.code)
    setErrors({})
    setMessage(null)
    setForm({ enabled: r.enabled, default_value: r.default_value ?? '', max_amount: r.max_amount ?? '',
      payslip_label: r.payslip_label || '' })
  }

  const set = (k) => (e) => {
    setForm({ ...form, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
    if (errors[k]) setErrors({ ...errors, [k]: undefined })
  }

  async function save(e, override) {
    e?.preventDefault()
    const row = rows.find((r) => r.code === (override?.code || selected))
    const data = override?.data || form
    setBusy(true)
    setErrors({})
    try {
      await api.setClientDeduction(client.id, row.code, {
        enabled: !!data.enabled, payslip_label: data.payslip_label || '',
        default_value: data.default_value === '' || data.default_value == null ? null : String(data.default_value),
        max_amount: data.max_amount === '' || data.max_amount == null ? null : String(data.max_amount),
      })
      const fresh = await load()
      const updated = fresh.find((r) => r.code === row.code)
      if (selected === row.code && updated) open(updated)
      setMessage({ kind: 'ok', text: `${row.name} ${data.enabled ? 'is in use' : 'is switched off'} for ${client.legal_name}.` })
    } catch (err) {
      setErrors(err.fieldErrors || {})
      setMessage({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  // Quick on/off from the list.
  const toggle = (r) => (e) => {
    e.stopPropagation()
    save(null, { code: r.code, data: { enabled: !r.enabled, default_value: r.default_value, max_amount: r.max_amount,
      payslip_label: r.payslip_label } })
  }

  const shown = rows.filter((r) => inFilter(filter, r))
  const current = rows.find((r) => r.code === selected)
  const pct = current && current.calc !== 'fixed' && current.calc !== 'statutory'
  const inUse = rows.filter((r) => r.enabled && !r.statutory).length

  const field = (k, label, placeholder) => (
    <label>
      {label}
      <input value={form[k] ?? ''} onChange={set(k)} placeholder={placeholder} inputMode={k === 'payslip_label' ? undefined : 'decimal'}
        className={errors[k] ? 'invalid' : undefined} aria-invalid={errors[k] ? true : undefined} />
      {errors[k] && <span className="field-error">{label}: {errors[k]}</span>}
    </label>
  )

  return (
    <div className="grid">
      <section className="card">
        <div className="run-head">
          <h2>{client.legal_name} <span className="tag">{inUse} in use</span></h2>
          {platform && <button onClick={() => onGo('deductions')}>Deduction master</button>}
        </div>
        <div className="segmented small-seg five" role="tablist" aria-label="Show">
          {FILTERS.map(([k, label]) => (
            <button key={k} role="tab" aria-selected={filter === k} className={filter === k ? 'active' : ''} onClick={() => setFilter(k)}>{label}</button>
          ))}
        </div>
        {shown.length === 0 ? (
          <p className="muted">{filter === 'on' ? 'No optional deductions in use yet. Choose All and switch some on.' : 'Nothing here.'}</p>
        ) : (
          <div className="table-wrap">
            <table className="clickable">
              <thead><tr><th>Deduction</th><th>Default</th><th className="num">Employees</th><th>Use</th></tr></thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.code} tabIndex={0} className={`${selected === r.code ? 'selected' : ''} ${r.enabled ? '' : 'dim'}`}
                      onClick={() => open(r)} onKeyDown={(e) => e.key === 'Enter' && open(r)}>
                    <td><strong>{r.name}</strong></td>
                    <td className="small">{r.statutory ? 'Payroll rules' : deductionValue(r.calc, r.default_value ?? r.master_default_value)}</td>
                    <td className="num">{r.statutory ? '—' : r.employees}</td>
                    <td>
                      {r.statutory ? <span className="tag locked">always</span> : (
                        <button type="button" className={`switch ${r.enabled ? 'on' : ''}`} role="switch" aria-checked={r.enabled}
                          aria-label={`Use ${r.name}`} onClick={toggle(r)} disabled={busy}><span /></button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        {!current ? (
          <>
            <h2>Client deductions</h2>
            <ul className="steps-list">
              <li>Switch on the deductions <strong>{client.legal_name}</strong> offers its employees.</li>
              <li>Set the client's own default, monthly cap and payslip name, or leave them blank to use the master's.</li>
              <li>Then give employees deductions on <strong>Employee deductions</strong>; payroll takes them every month.</li>
              <li>PF, ESI, PT, LWF and TDS always apply from the compliance rules.</li>
            </ul>
            {message && <div className={`banner ${message.kind}`}>{message.text}</div>}
          </>
        ) : (
          <form className="form" onSubmit={save}>
            <div className="run-head">
              <h2>{current.name}</h2>
              <button type="button" onClick={() => setSelected(null)}>Close</button>
            </div>
            <p className="muted small">
              {current.category === 'statutory' ? 'Statutory' : current.category === 'voluntary' ? 'Voluntary' : 'Recovery'}
              {' · '}{current.calc_label}{current.tax_section ? ` · ${current.tax_section}` : ''}
            </p>
            {current.description && <p className="small">{current.description}</p>}
            {current.statutory ? (
              <p className="muted">Always applied from the compliance rules; nothing to set for the client.</p>
            ) : (
              <>
                <label className="check">
                  <input type="checkbox" checked={!!form.enabled} onChange={set('enabled')} />
                  Used by {client.legal_name}
                </label>
                <div className="row">
                  {field('default_value', pct ? 'Client default %' : 'Client default ₹ per month',
                    current.master_default_value != null ? `master: ${current.master_default_value}` : 'none')}
                  {field('max_amount', 'Client monthly cap (₹)',
                    current.master_max_amount != null ? `master: ${current.master_max_amount}` : 'no cap')}
                </div>
                {field('payslip_label', 'Name on payslip', current.master_payslip_label || current.name)}
                {current.employees > 0 && !form.enabled && (
                  <div className="banner warn">{current.employees} employee(s) have this deduction. Switching it off stops it in future payroll runs.</div>
                )}
                {message && <div className={`banner ${message.kind}`}>{message.text}</div>}
                <div className="actions"><button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button></div>
              </>
            )}
          </form>
        )}
      </section>
    </div>
  )
}
