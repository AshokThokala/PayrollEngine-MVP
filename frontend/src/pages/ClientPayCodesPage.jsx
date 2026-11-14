import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { payValue } from './PayCodesPage.jsx'

const FILTERS = [['on', 'In use'], ['all', 'All'], ['fixed', 'Salary'], ['variable', 'Variable']]
const inFilter = (f, r) => f === 'all' || (f === 'on' && r.enabled) || r.kind === f

// Client level: which pay codes this client uses, with the client's own default and payslip name.
export default function ClientPayCodesPage({ client, platform, onGo }) {
  const [rows, setRows] = useState([])
  const [filter, setFilter] = useState('on')
  const [selected, setSelected] = useState(null)
  const [form, setForm] = useState({})
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const r = await api.clientPayCodes(client.id)
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
    setForm({ enabled: r.enabled, default_value: r.default_value ?? '', payslip_label: r.payslip_label || '' })
  }
  const set = (k) => (e) => {
    setForm({ ...form, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
    if (errors[k]) setErrors({ ...errors, [k]: undefined })
  }

  async function save(e, override) {
    e?.preventDefault()
    const code = override?.code || selected
    const row = rows.find((r) => r.code === code)
    const data = override?.data || form
    setBusy(true)
    setErrors({})
    try {
      await api.setClientPayCode(client.id, code, {
        enabled: !!data.enabled, payslip_label: data.payslip_label || '',
        default_value: data.default_value === '' || data.default_value == null ? null : String(data.default_value),
      })
      const fresh = await load()
      const updated = fresh.find((r) => r.code === code)
      if (selected === code && updated) open(updated)
      setMessage({ kind: 'ok', text: `${row.name} ${data.enabled ? 'is in use' : 'is switched off'} for ${client.legal_name}.` })
    } catch (err) {
      const fe = err.fieldErrors || {}
      setErrors(fe)
      setMessage({ kind: 'error', text: fe.enabled || err.message })
    } finally {
      setBusy(false)
    }
  }

  const toggle = (r) => (e) => {
    e.stopPropagation()
    save(null, { code: r.code, data: { enabled: !r.enabled, default_value: r.default_value, payslip_label: r.payslip_label } })
  }

  const shown = rows.filter((r) => inFilter(filter, r))
  const current = rows.find((r) => r.code === selected)

  return (
    <div className="grid">
      <section className="card">
        <div className="run-head">
          <h2>{client.legal_name} <span className="tag">{rows.filter((r) => r.enabled).length} in use</span></h2>
          {platform && <button onClick={() => onGo('paycodes')}>Pay code master</button>}
        </div>
        <div className="segmented small-seg" role="tablist" aria-label="Show">
          {FILTERS.map(([k, label]) => (
            <button key={k} role="tab" aria-selected={filter === k} className={filter === k ? 'active' : ''} onClick={() => setFilter(k)}>{label}</button>
          ))}
        </div>
        {message && !current && <div className={`banner ${message.kind}`}>{message.text}</div>}
        <div className="table-wrap">
          <table className="clickable">
            <thead><tr><th>Pay code</th><th>Type</th><th className="num">Employees</th><th>Use</th></tr></thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.code} tabIndex={0} className={`${selected === r.code ? 'selected' : ''} ${r.enabled ? '' : 'dim'}`}
                    onClick={() => open(r)} onKeyDown={(e) => e.key === 'Enter' && open(r)}>
                  <td><strong>{r.payslip_label || r.name}</strong>{r.in_wages && <span className="tag locked tiny">wages</span>}</td>
                  <td className="small">{r.kind === 'fixed' ? 'Salary' : 'Variable'}</td>
                  <td className="num">{r.kind === 'fixed' ? r.employees : '—'}</td>
                  <td>
                    {r.locked ? <span className="tag locked">always</span> : (
                      <button type="button" className={`switch ${r.enabled ? 'on' : ''}`} role="switch" aria-checked={r.enabled}
                        aria-label={`Use ${r.name}`} onClick={toggle(r)} disabled={busy}><span /></button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        {!current ? (
          <>
            <h2>Client pay codes</h2>
            <ul className="steps-list">
              <li>Switch on the pay codes in <strong>{client.legal_name}</strong>'s salary structure and variable pay.</li>
              <li>Basic, DA, HRA, special allowance and conveyance are on by default.</li>
              <li>Set the client's own default (e.g. HRA 50% of basic in metros) and the name on its payslips.</li>
              <li>Then enter amounts per employee on <strong>Employee pay</strong>; variable pay is entered when calculating a payroll run.</li>
            </ul>
          </>
        ) : (
          <form className="form" onSubmit={save}>
            <div className="run-head">
              <h2>{current.name}</h2>
              <button type="button" onClick={() => setSelected(null)}>Close</button>
            </div>
            <p className="muted small">
              {current.kind === 'fixed' ? 'Salary' : 'Variable'} · {current.tax_label}{current.tax_section ? ` · ${current.tax_section}` : ''}
              {current.in_wages ? ' · counts as wages' : ''}
            </p>
            {current.description && <p className="small">{current.description}</p>}
            <label className="check">
              <input type="checkbox" checked={!!form.enabled} onChange={set('enabled')} disabled={current.locked} />
              Used by {client.legal_name}
            </label>
            {errors.enabled && <span className="field-error">{errors.enabled}</span>}
            <div className="row">
              <label>
                {current.calc === 'percent_basic' ? 'Client default % of basic' : 'Client default ₹'}
                <input inputMode="decimal" value={form.default_value ?? ''} onChange={set('default_value')}
                  placeholder={current.master_default_value != null ? `master: ${payValue(current.calc, current.master_default_value)}` : 'none'}
                  className={errors.default_value ? 'invalid' : undefined} />
                {errors.default_value && <span className="field-error">Default: {errors.default_value}</span>}
              </label>
              <label>
                Name on payslip
                <input value={form.payslip_label ?? ''} onChange={set('payslip_label')} placeholder={current.master_payslip_label || current.name} />
              </label>
            </div>
            {message && <div className={`banner ${message.kind}`}>{message.text}</div>}
            <div className="actions"><button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button></div>
          </form>
        )}
      </section>
    </div>
  )
}
