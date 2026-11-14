import { Fragment, useCallback, useEffect, useState } from 'react'
import { api, money } from '../api.js'
import PayslipView from '../components/PayslipView.jsx'

function thisMonth() {
  return new Date().toISOString().slice(0, 7)
}

const STATUS_HELP = {
  draft: 'Draft — review, then approve',
  approved: 'Approved — lock to freeze it and schedule filings',
  locked: 'Locked — cannot be changed',
}

export default function RunsPage({ client, user }) {
  const [runs, setRuns] = useState([])
  const [employees, setEmployees] = useState([])
  const [month, setMonth] = useState(thisMonth())
  const [inputs, setInputs] = useState({})
  const [selectedId, setSelectedId] = useState(null)
  const [selected, setSelected] = useState(null) // full run with payslips
  const [open, setOpen] = useState({})
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)
  const [variable, setVariable] = useState([]) // variable pay codes this client uses (bonus, arrears, ...)
  useEffect(() => {
    api.availablePayCodes(client.id).then((l) => setVariable(l.filter((p) => p.kind === 'variable'))).catch(() => setVariable([]))
  }, [client.id])

  const load = useCallback(async () => {
    try {
      const [r, e] = await Promise.all([api.listRuns(client.id), api.listEmployees(client.id)])
      setRuns(r)
      setEmployees(e.filter((emp) => !emp.exited_on || emp.exited_on.slice(0, 7) >= month))
      setSelectedId((cur) => (cur && r.some((x) => x.id === cur) ? cur : r[0]?.id || null))
    } catch (err) {
      setMessage({ kind: 'error', text: err.message })
    }
  }, [client.id, month])

  useEffect(() => {
    load()
  }, [load])

  // The list has totals only; load the chosen run's payslips on demand.
  useEffect(() => {
    if (!selectedId) {
      setSelected(null)
      return
    }
    let stale = false
    api.getRun(selectedId).then((run) => { if (!stale) setSelected(run) }).catch((err) => {
      if (!stale) setMessage({ kind: 'error', text: err.message })
    })
    return () => { stale = true }
  }, [selectedId, runs])

  const setInput = (code, key, value) =>
    setInputs({ ...inputs, [code]: { ...(inputs[code] || {}), [key]: value } })

  const act = async (fn, okText) => {
    setBusy(true)
    try {
      const result = await fn()
      setMessage({ kind: 'ok', text: typeof okText === 'function' ? okText(result) : okText })
      await load()
      return result
    } catch (err) {
      setMessage({ kind: 'error', text: err.message })
      return null
    } finally {
      setBusy(false)
    }
  }

  const createDraft = async (e) => {
    e.preventDefault()
    const body = { period: `${month}-01`, inputs: {} }
    Object.entries(inputs).forEach(([code, v]) => {
      const entry = {}
      if (v.paid_days !== undefined && v.paid_days !== '') entry.paid_days = Number(v.paid_days)
      if (v.overtime) entry.overtime = Number(v.overtime)
      const extra = Object.fromEntries(variable.filter((p) => Number(v[`pay:${p.code}`]) > 0).map((p) => [p.code, Number(v[`pay:${p.code}`])]))
      if (Object.keys(extra).length) entry.other_earnings = extra
      if (Object.keys(entry).length) body.inputs[code] = entry
    })
    const run = await act(() => api.createRun(client.id, body), `Draft for ${month} calculated.`)
    if (run) {
      setSelected(run)
      setSelectedId(run.id)
    }
  }

  return (
    <div className="grid">
      <section className="card">
        <h2>Calculate payroll</h2>
        <form onSubmit={createDraft} className="form">
          <label>Pay month<input type="month" required value={month} onChange={(e) => setMonth(e.target.value)} /></label>
          {employees.length > 0 && (
            <details>
              <summary>Attendance and overtime (optional)</summary>
              <p className="muted small">Leave paid days blank for a full month; joiners and leavers are prorated automatically.</p>
              <table className="compact">
                <thead><tr><th>Employee</th><th>Paid days</th><th>Overtime ₹</th></tr></thead>
                <tbody>
                  {employees.map((emp) => (
                    <tr key={emp.code}>
                      <td>{emp.code} · {emp.name}</td>
                      <td><input type="number" min="0" max="31" step="0.5" value={inputs[emp.code]?.paid_days ?? ''}
                        onChange={(e) => setInput(emp.code, 'paid_days', e.target.value)} /></td>
                      <td><input type="number" min="0" step="1" value={inputs[emp.code]?.overtime ?? ''}
                        onChange={(e) => setInput(emp.code, 'overtime', e.target.value)} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
          {employees.length > 0 && (
            <details>
              <summary>Variable pay this month (optional)</summary>
              {variable.length === 0 ? (
                <p className="muted small">No variable pay codes in use. Switch on bonus, incentive or arrears under Client pay codes.</p>
              ) : (
                <div className="table-wrap">
                  <table className="compact">
                    <thead><tr><th>Employee</th>{variable.map((p) => <th key={p.code}>{p.payslip_label || p.name} ₹</th>)}</tr></thead>
                    <tbody>
                      {employees.map((emp) => (
                        <tr key={emp.code}>
                          <td>{emp.code} · {emp.name}</td>
                          {variable.map((p) => (
                            <td key={p.code}><input type="number" min="0" step="1" value={inputs[emp.code]?.[`pay:${p.code}`] ?? ''}
                              onChange={(e) => setInput(emp.code, `pay:${p.code}`, e.target.value)} aria-label={`${p.name} for ${emp.name}`} /></td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </details>
          )}
          <button className="primary" disabled={busy || employees.length === 0}>
            {employees.length === 0 ? 'Add employees first' : 'Calculate draft'}
          </button>
        </form>

        <h3>Runs</h3>
        {runs.length === 0 ? <p className="muted">No runs yet.</p> : (
          <ul className="list">
            {runs.map((r) => (
              <li key={r.id}>
                <button className={selectedId === r.id ? 'list-item active' : 'list-item'} onClick={() => setSelectedId(r.id)}>
                  <span>{r.period.slice(0, 7)}</span>
                  <span className={`tag ${r.status}`}>{r.status}</span>
                  <span className="num">{money(r.total_net)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card wide">
        {message && <div className={`banner ${message.kind}`}>{message.text}</div>}
        {!selected ? <p className="muted">Calculate a draft or pick a run.</p> : (
          <>
            <div className="run-head">
              <div>
                <h2>{client.legal_name} — {selected.period.slice(0, 7)}</h2>
                <p className="muted small">
                  {STATUS_HELP[selected.status]} · prepared by {selected.prepared_by}
                  {selected.approved_by && ` · approved by ${selected.approved_by}`}
                </p>
              </div>
              <div className="actions">
                {selected.status === 'draft' && (
                  <button className="primary" disabled={busy}
                    onClick={() => act(() => api.approveRun(selected.id), 'Run approved.')}>
                    Approve
                  </button>
                )}
                {selected.status === 'approved' && (
                  <button className="primary" disabled={busy}
                    onClick={() => act(() => api.lockRun(selected.id), (f) => `Run locked. ${f.length} filings added to the compliance calendar.`)}>
                    Lock run
                  </button>
                )}
              </div>
            </div>

            <div className="stats">
              <div><span>Gross</span><strong>{money(selected.total_gross)}</strong></div>
              <div><span>Net pay</span><strong>{money(selected.total_net)}</strong></div>
              <div><span>Employer cost</span><strong>{money(selected.total_employer_cost)}</strong></div>
              <div><span>Employees</span><strong>{selected.slips.length}</strong></div>
            </div>

            {selected.flags.length > 0 && (
              <div className="banner warn">
                <strong>Review before approving</strong>
                <ul>{selected.flags.map((f) => <li key={f}>{f}</li>)}</ul>
              </div>
            )}

            <table>
              <thead>
                <tr><th>Employee</th><th className="num">Gross</th><th className="num">Deductions</th><th className="num">Net pay</th><th className="num">Employer cost</th><th></th></tr>
              </thead>
              <tbody>
                {selected.slips.map((s) => (
                  <Fragment key={s.employee_code}>
                    <tr>
                      <td>{s.employee_code}</td>
                      <td className="num">{money(s.gross)}</td>
                      <td className="num">{money(s.total_deductions)}</td>
                      <td className="num"><strong>{money(s.net_pay)}</strong></td>
                      <td className="num">{money(s.employer_cost)}</td>
                      <td><button className="link" onClick={() => setOpen({ ...open, [s.employee_code]: !open[s.employee_code] })}>
                        {open[s.employee_code] ? 'Hide' : 'Payslip'}
                      </button></td>
                    </tr>
                    {open[s.employee_code] && (
                      <tr className="detail">
                        <td colSpan={6}><PayslipView slip={s} /></td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>
    </div>
  )
}
