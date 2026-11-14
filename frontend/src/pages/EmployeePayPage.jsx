import { useCallback, useEffect, useState } from 'react'
import { api, money } from '../api.js'

const short = (p) => p.payslip_label || p.name

// Employee level: every employee's monthly salary by pay code. Click a row to edit the amounts.
export default function EmployeePayPage({ client, onGo }) {
  const [grid, setGrid] = useState(null)
  const [showExited, setShowExited] = useState(false)
  const [selected, setSelected] = useState(null)
  const [form, setForm] = useState({})
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const g = await api.employeePay(client.id, showExited)
      setGrid(g)
      return g
    } catch (e) {
      setMessage({ kind: 'error', text: e.message })
      return null
    }
  }, [client.id, showExited])

  useEffect(() => {
    setSelected(null)
    setMessage(null)
    load()
  }, [load])

  const open = (emp) => {
    setSelected(emp.code)
    setErrors({})
    setMessage(null)
    setForm(Object.fromEntries(Object.entries(emp.components).map(([k, v]) => [k, String(Number(v))])))
  }

  if (!grid) return message ? <div className={`banner ${message.kind}`}>{message.text}</div> : <p className="muted">Loading…</p>
  const codes = grid.pay_codes
  const emp = grid.employees.find((e) => e.code === selected)
  const extra = emp ? Object.keys(emp.components).filter((k) => !codes.some((p) => p.code === k)) : []
  const total = Object.values(form).reduce((t, v) => t + (Number(v) || 0), 0)
  const wages = codes.filter((p) => p.in_wages).reduce((t, p) => t + (Number(form[p.code]) || 0), 0)
  const suggestion = (p) => {
    if (p.default_value == null) return undefined
    if (p.calc === 'percent_basic') return Number(form.basic) ? String(Math.round(Number(form.basic) * Number(p.default_value) / 100)) : `${Number(p.default_value)}% of basic`
    return String(Number(p.default_value))
  }

  async function save(e) {
    e.preventDefault()
    setBusy(true)
    setErrors({})
    try {
      const res = await api.setEmployeePay(client.id, emp.code, form)
      const g = await load()
      const fresh = g?.employees.find((x) => x.code === emp.code)
      if (fresh) open(fresh)
      setMessage({ kind: res.warnings?.length ? 'warn' : 'ok', text: res.warnings?.length ? res.warnings.join(' ') : `${emp.name}'s salary saved.` })
    } catch (err) {
      setErrors(err.fieldErrors || {})
      setMessage({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid wide-left">
      <section className="card">
        <div className="run-head">
          <h2>Employee pay <span className="tag">{grid.employees.length} employees</span></h2>
          <button onClick={() => onGo('client-paycodes')}>Client pay codes</button>
        </div>
        <label className="check small"><input type="checkbox" checked={showExited} onChange={(e) => setShowExited(e.target.checked)} /> Show employees who left</label>
        {grid.employees.length === 0 ? (
          <p className="muted">No employees yet. Add them on the Employees page.</p>
        ) : (
          <div className="table-wrap">
            <table className="clickable pay-grid">
              <thead>
                <tr>
                  <th>Employee</th>
                  {codes.map((p) => <th key={p.code} className="num" title={p.name}>{short(p)}</th>)}
                  <th className="num">Monthly total</th>
                </tr>
              </thead>
              <tbody>
                {grid.employees.map((e) => (
                  <tr key={e.code} tabIndex={0} className={`${selected === e.code ? 'selected' : ''} ${e.exited_on ? 'dim' : ''}`}
                      onClick={() => open(e)} onKeyDown={(ev) => ev.key === 'Enter' && open(e)}>
                    <td><strong>{e.name}</strong> <span className="muted small">{e.code}</span></td>
                    {codes.map((p) => <td key={p.code} className="num">{e.components[p.code] ? money(e.components[p.code]) : '—'}</td>)}
                    <td className="num"><strong>{money(e.total)}</strong></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        {!emp ? (
          <>
            <h2>Salary by pay code</h2>
            <p className="muted">Click an employee to change their monthly amounts. Columns are the salary pay codes {client.legal_name} uses; add more under <strong>Client pay codes</strong>.</p>
            {message && <div className={`banner ${message.kind}`}>{message.text}</div>}
          </>
        ) : (
          <form className="form" onSubmit={save}>
            <div className="run-head">
              <div><h2>{emp.name}</h2><p className="muted small">{emp.code} · ₹ per month</p></div>
              <button type="button" onClick={() => setSelected(null)}>Close</button>
            </div>
            {codes.map((p) => (
              <label key={p.code} className="row-label">
                <span>{p.name}{p.in_wages && <span className="tag locked tiny">wages</span>}</span>
                <input type="number" min="0" step="0.01" value={form[p.code] ?? ''} placeholder={suggestion(p)}
                  onChange={(e) => setForm({ ...form, [p.code]: e.target.value })}
                  className={errors[p.code] ? 'invalid' : undefined} />
              </label>
            ))}
            {extra.map((k) => (
              <label key={k} className="row-label">
                <span>{k} <span className="muted small">(not used by client — clear it)</span></span>
                <input type="number" min="0" step="0.01" value={form[k] ?? ''} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
              </label>
            ))}
            <div className="total">
              Total {money(total)}
              {total > 0 && wages / total < 0.5 && (
                <span className="tag warn">Wages (basic + DA) below 50% — PF and gratuity will use the higher Labour Code wage</span>
              )}
            </div>
            {message && <div className={`banner ${message.kind}`}>{message.text}</div>}
            <div className="actions"><button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save salary'}</button></div>
          </form>
        )}
      </section>
    </div>
  )
}
