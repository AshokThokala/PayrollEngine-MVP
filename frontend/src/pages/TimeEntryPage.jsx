import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, money } from '../api.js'

const thisMonth = () => new Date().toISOString().slice(0, 7)
const FILTERS = [['all', 'All'], ['salaried', 'Salaried'], ['hourly', 'Hourly'], ['todo', 'Not approved']]
const STATUS_CLASS = { P: 'st-p', A: 'st-a', HD: 'st-hd', L: 'st-l', H: 'st-h', WO: 'st-wo' }
const n = (v) => Number(v || 0)
const fmtH = (v) => `${Number(n(v).toFixed(2))} h`

function weekday(month, d) {
  return new Date(`${month}-${String(d).padStart(2, '0')}T00:00:00`).getDay() // 0 = Sunday
}

// Time entry: day by day for one employee, with month totals for everyone. Feeds the payroll run.
export default function TimeEntryPage({ client, onGo }) {
  const [month, setMonth] = useState(thisMonth())
  const [data, setData] = useState(null)
  const [filter, setFilter] = useState('all')
  const [selected, setSelected] = useState(null)
  const [days, setDays] = useState({})
  const [note, setNote] = useState('')
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const d = await api.timeMonth(client.id, month)
      setData(d)
      return d
    } catch (e) {
      setMessage({ kind: 'error', text: e.message })
      return null
    }
  }, [client.id, month])

  useEffect(() => {
    setSelected(null)
    setMessage(null)
    load()
  }, [load])

  const emp = data?.employees.find((e) => e.code === selected)
  const hourly = emp?.pay_type === 'hourly'
  const open = (e) => {
    setSelected(e.code)
    setDays(JSON.parse(JSON.stringify(e.days || {})))
    setNote(e.note || '')
    setErrors({})
    setMessage(null)
  }

  const setDay = (d, key, value) => {
    const cur = { ...(days[d] || {}) }
    if (value === '' || value === null) delete cur[key]
    else cur[key] = value
    const next = { ...days }
    if (Object.keys(cur).length) next[d] = cur
    else delete next[d]
    setDays(next)
    if (errors[`day_${d}`]) setErrors({ ...errors, [`day_${d}`]: undefined })
  }

  // Quick fill: salaried = present Mon–Sat, Sunday weekly off; hourly = 8 h Mon–Sat.
  const fill = () => {
    const next = {}
    for (let d = 1; d <= data.days_in_month; d += 1) {
      const sunday = weekday(month, d) === 0
      if (hourly) { if (!sunday) next[d] = { hours: '8' } } else next[d] = { status: sunday ? 'WO' : 'P' }
    }
    setDays(next)
  }

  // Live totals for the open sheet.
  const live = useMemo(() => {
    const t = { A: 0, HD: 0, L: 0, H: 0, WO: 0, P: 0, hours: 0, ot: 0 }
    Object.values(days).forEach((x) => {
      if (x.status && t[x.status] !== undefined) t[x.status] += 1
      t.hours += n(x.hours)
      t.ot += n(x.ot)
    })
    t.lop = t.A + t.HD / 2
    return t
  }, [days])

  async function save(approve) {
    setBusy(true)
    setErrors({})
    try {
      await api.saveTime(client.id, emp.code, month, { days, note, approve })
      const d = await load()
      const fresh = d?.employees.find((x) => x.code === emp.code)
      if (fresh) open(fresh)
      setMessage({ kind: 'ok', text: `${emp.name}'s time ${approve ? 'saved and approved' : 'saved as draft'}.` })
    } catch (err) {
      setErrors(err.fieldErrors || {})
      setMessage({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  async function approveAll() {
    setBusy(true)
    try {
      const r = await api.approveTime(client.id, month, {})
      await load()
      setMessage({ kind: 'ok', text: r.changed ? `${r.changed} time sheet(s) approved.` : 'Nothing to approve.' })
    } catch (err) {
      setMessage({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  if (!data) return message ? <div className={`banner ${message.kind}`}>{message.text}</div> : <p className="muted">Loading…</p>
  const shown = data.employees.filter((e) => filter === 'all' || (filter === 'todo' ? e.status !== 'approved' : e.pay_type === filter))
  const drafts = data.employees.filter((e) => e.status === 'draft').length
  const locked = data.locked
  const firstDay = weekday(month, 1)

  return (
    <div className="stack">
      <div className="tax-head">
        <div>
          <h2>Time for {new Date(`${month}-01T00:00:00`).toLocaleString('en-IN', { month: 'long', year: 'numeric' })}</h2>
          <p className="muted small">Salaried: mark absences and overtime (no entry = full month paid). Hourly: enter hours worked.</p>
        </div>
        <div className="actions">
          <label className="field-inline"><span className="muted small">Month</span>
            <input type="month" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} />
          </label>
          {drafts > 0 && !locked && <button onClick={approveAll} disabled={busy}>Approve all ({drafts})</button>}
          <button onClick={() => onGo('runs')}>Payroll runs</button>
        </div>
      </div>
      {locked && <div className="banner warn">This month's payroll is approved, so its time is read-only.</div>}
      {message && !emp && <div className={`banner ${message.kind}`}>{message.text}</div>}

      <div className="grid wide-left">
        <section className="card">
          <div className="segmented small-seg" role="tablist" aria-label="Show">
            {FILTERS.map(([k, label]) => (
              <button key={k} role="tab" aria-selected={filter === k} className={filter === k ? 'active' : ''} onClick={() => setFilter(k)}>{label}</button>
            ))}
          </div>
          {shown.length === 0 ? <p className="muted">No employees here.</p> : (
            <div className="table-wrap">
              <table className="clickable">
                <thead><tr><th>Employee</th><th>Type</th><th className="num">Paid days / hours</th><th className="num">OT</th><th className="num">Pay from time</th><th>Status</th></tr></thead>
                <tbody>
                  {shown.map((e) => (
                    <tr key={e.code} tabIndex={0} className={selected === e.code ? 'selected' : undefined}
                        onClick={() => open(e)} onKeyDown={(ev) => ev.key === 'Enter' && open(e)}>
                      <td><strong>{e.name}</strong> <span className="muted small">{e.code}</span></td>
                      <td className="small">{e.pay_type === 'hourly' ? `Hourly · ₹${n(e.hourly_rate)}` : 'Salaried'}</td>
                      <td className="num">{e.pay_type === 'hourly' ? fmtH(e.regular_hours) : `${n(e.paid_days)}${n(e.lop_days) ? ` (−${n(e.lop_days)})` : ''}`}</td>
                      <td className="num">{n(e.ot_hours) ? fmtH(e.ot_hours) : '—'}</td>
                      <td className="num">{money(n(e.hourly_pay) + n(e.ot_pay))}</td>
                      <td>{e.status ? <span className={`tag ${e.status === 'approved' ? 'paid' : 'draft'}`}>{e.status}</span> : <span className="muted small">{e.pay_type === 'hourly' ? 'no hours' : 'full month'}</span>}</td>
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
              <h2>How time entry works</h2>
              <ul className="steps-list">
                <li><strong>Salaried</strong> — mark days absent (A), half days (HD), paid leave (L), holidays (H) and weekly offs (WO). Absent and half of each half day are loss of pay.</li>
                <li><strong>Hourly</strong> — enter hours for each day. Pay = hours × hourly rate.</li>
                <li><strong>Overtime</strong> — twice the ordinary rate (salaried: basic + DA ÷ 26 days ÷ 8 hours).</li>
                <li>Approve the time, then calculate the payroll run; it picks this up automatically.</li>
              </ul>
            </>
          ) : (
            <div className="form">
              <div className="run-head">
                <div>
                  <h2>{emp.name}</h2>
                  <p className="muted small">{emp.code} · {hourly ? `Hourly, ₹${n(emp.hourly_rate)}/h` : 'Salaried'} · OT ₹{n(emp.ot_rate)}/h
                    {emp.status && <> · <span className={`tag ${emp.status === 'approved' ? 'paid' : 'draft'}`}>{emp.status}</span></>}</p>
                </div>
                <button type="button" onClick={() => setSelected(null)}>Close</button>
              </div>
              {!locked && (
                <div className="actions">
                  <button type="button" onClick={fill}>{hourly ? 'Fill 8 h Mon–Sat' : 'Mark Mon–Sat present'}</button>
                  <button type="button" className="link" onClick={() => setDays({})}>Clear</button>
                </div>
              )}
              <div className="cal-head">{['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d) => <span key={d}>{d}</span>)}</div>
              <div className="cal">
                {Array.from({ length: firstDay }, (_, i) => <div key={`pad${i}`} className="cal-pad" />)}
                {Array.from({ length: data.days_in_month }, (_, i) => {
                  const d = String(i + 1)
                  const day = days[d] || {}
                  const err = errors[`day_${d}`]
                  return (
                    <div key={d} className={`cal-day ${STATUS_CLASS[day.status] || ''} ${err ? 'invalid' : ''}`} title={err || ''}>
                      <span className="cal-num">{d}</span>
                      {!hourly && (
                        <select value={day.status || ''} onChange={(e) => setDay(d, 'status', e.target.value)} disabled={locked}
                          aria-label={`Day ${d} status`}>
                          <option value="">—</option>
                          {Object.keys(data.statuses).map((s) => <option key={s} value={s} title={data.statuses[s]}>{s}</option>)}
                        </select>
                      )}
                      {hourly && (
                        <input inputMode="decimal" placeholder="h" value={day.hours ?? ''} disabled={locked}
                          onChange={(e) => setDay(d, 'hours', e.target.value)} aria-label={`Day ${d} hours`} />
                      )}
                      <input inputMode="decimal" placeholder="OT" className="ot" value={day.ot ?? ''} disabled={locked}
                        onChange={(e) => setDay(d, 'ot', e.target.value)} aria-label={`Day ${d} overtime hours`} />
                    </div>
                  )
                })}
              </div>
              <p className="muted small legend">
                {hourly ? 'h = regular hours, OT = overtime hours.' : Object.entries(data.statuses).map(([k, v]) => `${k} ${v}`).join(' · ')}
              </p>
              <div className="stats">
                {hourly ? (
                  <>
                    <div><span>Hours</span><strong>{fmtH(live.hours)}</strong></div>
                    <div><span>Wages</span><strong>{money(live.hours * n(emp.hourly_rate))}</strong></div>
                  </>
                ) : (
                  <>
                    <div><span>Paid days</span><strong>{data.days_in_month - live.lop}</strong></div>
                    <div><span>Loss of pay</span><strong>{live.lop} days</strong></div>
                  </>
                )}
                <div><span>Overtime</span><strong>{fmtH(live.ot)} · {money(live.ot * n(emp.ot_rate))}</strong></div>
              </div>
              <label>Note<input value={note} onChange={(e) => setNote(e.target.value)} disabled={locked} placeholder="e.g. 2 days sick leave without pay" /></label>
              {Object.values(errors).filter(Boolean).length > 0 && (
                <div className="banner error"><ul>{Object.values(errors).filter(Boolean).map((e) => <li key={e}>{e}</li>)}</ul></div>
              )}
              {message && <div className={`banner ${message.kind}`}>{message.text}</div>}
              {!locked && (
                <div className="actions">
                  <button className="primary" disabled={busy} onClick={() => save(true)}>Save and approve</button>
                  <button disabled={busy} onClick={() => save(false)}>Save draft</button>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
