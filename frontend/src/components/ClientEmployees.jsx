import { useEffect, useState } from 'react'
import { api, money } from '../api.js'
import PickerSearch, { Highlight } from './PickerSearch.jsx'

export const matchEmployee = (e, q) => e.name.toLowerCase().includes(q) || e.code.toLowerCase().includes(q)
  || (e.designation || '').toLowerCase().includes(q) || (e.department || '').toLowerCase().includes(q)

export function EmployeeSuggestion({ e, q }) {
  return (
    <><span className="gs-icon" aria-hidden="true">☺</span>
      <span className="gs-text"><strong><Highlight text={e.name} q={q} /></strong>
        <span className="muted small"><Highlight text={e.code} q={q} />
          {e.designation ? <> · <Highlight text={e.designation} q={q} /></> : null}
          {e.department ? <> · <Highlight text={e.department} q={q} /></> : null}
          {e.exited_on ? ' · left' : ''}</span></span></>
  )
}

// All employees of one client, shown when the client is opened. Click one to open their record.
export default function ClientEmployees({ client, onOpenEmployee, onAddEmployee }) {
  const [list, setList] = useState(null)
  const [showLeft, setShowLeft] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setList(null)
    setError('')
    api.listEmployees(client.id).then(setList).catch((e) => setError(e.message))
  }, [client.id])

  if (error) return <section className="card"><div className="banner error">{error}</div></section>
  if (!list) return <section className="card"><p className="muted">Loading employees…</p></section>

  const active = list.filter((e) => !e.exited_on)
  const shown = list.filter((e) => showLeft || !e.exited_on)
  const payroll = active.reduce((t, e) => t + Number(e.monthly_total || 0), 0)

  return (
    <section className="card allow-overflow">
      <div className="run-head">
        <h2>Employees <span className="tag">{active.length} active</span></h2>
        <button onClick={onAddEmployee}>+ Add employee</button>
      </div>
      <div className="stats compact-stats">
        <div><span>Active</span><strong>{active.length}</strong></div>
        <div><span>Left</span><strong>{list.length - active.length}</strong></div>
        <div><span>Monthly salaries</span><strong>{money(payroll)}</strong></div>
      </div>
      {list.length === 0 ? (
        <p className="muted">No employees yet.</p>
      ) : (
        <>
          <div className="row filters">
            <PickerSearch items={list} match={matchEmployee} render={(e, q2) => <EmployeeSuggestion e={e} q={q2} />}
              onPick={(e) => onOpenEmployee(client.id, e.code)}
              placeholder={`Search ${client.legal_name}'s employees by name, code, designation or department`}
              label={`Search ${client.legal_name} employees`} />
            <label className="check"><input type="checkbox" checked={showLeft} onChange={(e) => setShowLeft(e.target.checked)} /> Show employees who left</label>
          </div>
          <div className="table-wrap">
            <table className="clickable">
              <thead><tr><th>Employee</th><th>Designation</th><th className="num">Monthly pay</th><th>Status</th></tr></thead>
              <tbody>
                {shown.map((e) => (
                  <tr key={e.code} tabIndex={0} className={e.exited_on ? 'dim' : undefined}
                      onClick={() => onOpenEmployee(client.id, e.code)} onKeyDown={(ev) => ev.key === 'Enter' && onOpenEmployee(client.id, e.code)}>
                    <td><strong>{e.name}</strong> <span className="muted small">{e.code}</span></td>
                    <td className="small">{e.designation || <span className="muted">—</span>}{e.department ? <span className="muted"> · {e.department}</span> : ''}</td>
                    <td className="num">{e.pay_type === 'hourly' ? `₹${Number(e.hourly_rate)}/h` : money(e.monthly_total)}</td>
                    <td>{e.exited_on ? <span className="tag">Left {e.exited_on}</span> : <span className="tag locked">Active</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {shown.length === 0 && <p className="muted small">Everyone here has left; tick "Show employees who left".</p>}
        </>
      )}
    </section>
  )
}
