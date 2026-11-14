import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import DeductionForm from '../components/DeductionForm.jsx'
import { monthLabel } from '../components/EmployeeDeductions.jsx'
import { deductionValue } from './DeductionsPage.jsx'

// Employee level: every standing deduction of the client's employees. Click a row to edit it.
export default function EmployeeDeductionsPage({ client, onGo }) {
  const [items, setItems] = useState([])
  const [types, setTypes] = useState([])
  const [employees, setEmployees] = useState([])
  const [filter, setFilter] = useState('')
  const [showEnded, setShowEnded] = useState(false)
  const [editing, setEditing] = useState(null)
  const [errors, setErrors] = useState({})
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    try {
      setItems(await api.allEmployeeDeductions(client.id))
    } catch (e) {
      setError(e.message)
    }
  }, [client.id])

  useEffect(() => {
    setEditing(null)
    setNotice('')
    setError('')
    load()
    api.availableDeductions(client.id).then(setTypes).catch(() => setTypes([]))
    api.listEmployees(client.id).then((list) => setEmployees(list.filter((e) => !e.exited_on))).catch(() => setEmployees([]))
  }, [client.id, load])

  const open = (d) => {
    setErrors({})
    setError('')
    setNotice('')
    setEditing(d || { employee_code: '' })
  }

  async function save(body) {
    setErrors({})
    setError('')
    const code = editing.id ? editing.employee_code : body.employee_code
    if (!code) {
      setErrors({ employee_code: 'Choose an employee' })
      setError('Check the highlighted fields')
      return
    }
    try {
      if (editing.id) await api.editEmployeeDeduction(client.id, code, editing.id, body)
      else await api.addEmployeeDeduction(client.id, code, body)
      const name = employees.find((e) => e.code === code)?.name || code
      setEditing(null)
      setNotice(`Saved for ${name}. Payroll runs from the first month take it automatically.`)
      load()
    } catch (err) {
      setErrors(err.fieldErrors || {})
      setError(err.message)
    }
  }

  async function remove() {
    if (!window.confirm('Remove this deduction? Runs already calculated keep it; future runs will not.')) return
    try {
      await api.deleteEmployeeDeduction(client.id, editing.employee_code, editing.id)
      setEditing(null)
      setNotice('Deduction removed.')
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  const thisMonth = new Date().toISOString().slice(0, 7)
  const ended = (d) => d.end_month && d.end_month.slice(0, 7) < thisMonth
  const shown = items.filter((d) => (!filter || d.deduction_code === filter) && (showEnded || !ended(d)))
  const usedCodes = [...new Set(items.map((d) => d.deduction_code))]

  return (
    <div className="grid">
      <section className="card">
        <div className="run-head">
          <h2>Employee deductions <span className="tag">{items.filter((d) => !ended(d)).length} running</span></h2>
          {editing === null && types.length > 0 && <button className="primary" onClick={() => open(null)}>+ Add deduction</button>}
        </div>
        <div className="row filters">
          <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter by deduction">
            <option value="">All deductions</option>
            {usedCodes.map((c) => <option key={c} value={c}>{items.find((d) => d.deduction_code === c).name}</option>)}
          </select>
          <label className="check"><input type="checkbox" checked={showEnded} onChange={(e) => setShowEnded(e.target.checked)} /> Show ended</label>
        </div>
        {types.length === 0 ? (
          <div className="banner warn">
            {client.legal_name} doesn't use any optional deductions yet.{' '}
            <button className="link" onClick={() => onGo('client-deductions')}>Switch some on under Client deductions</button>.
          </div>
        ) : shown.length === 0 ? (
          <p className="muted">No employee deductions{filter ? ' of this kind' : ''} yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="clickable">
              <thead><tr><th>Employee</th><th>Deduction</th><th className="num">Amount</th><th>Months</th></tr></thead>
              <tbody>
                {shown.map((d) => (
                  <tr key={d.id} tabIndex={0} className={`${editing?.id === d.id ? 'selected' : ''} ${ended(d) ? 'dim' : ''}`}
                      onClick={() => open(d)} onKeyDown={(e) => e.key === 'Enter' && open(d)}>
                    <td><strong>{d.employee_name}</strong> <span className="muted small">{d.employee_code}</span></td>
                    <td>{d.name}</td>
                    <td className="num">{deductionValue(d.calc, d.value)}</td>
                    <td className="small">{monthLabel(d.start_month)} → {d.end_month ? monthLabel(d.end_month) : 'ongoing'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        {editing === null ? (
          <>
            <h2>How it works</h2>
            <ul className="steps-list">
              <li>Pick an employee and one of the deductions {client.legal_name} uses.</li>
              <li>Enter ₹ a month (or a %), the first month, and the last month if it ends — e.g. a loan EMI.</li>
              <li>Every payroll run in those months takes it, within the client's cap.</li>
            </ul>
            {notice && <div className="banner ok">{notice}</div>}
            {error && <div className="banner error">{error}</div>}
          </>
        ) : (
          <>
            <div className="run-head">
              <h2>{editing.id ? `${editing.employee_name} · ${editing.name}` : 'Add employee deduction'}</h2>
            </div>
            <DeductionForm types={types} employees={editing.id ? null : employees} initial={editing}
              errors={errors} error={error} onSave={save} onCancel={() => setEditing(null)} onDelete={remove} />
          </>
        )}
      </section>
    </div>
  )
}
