import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { deductionValue } from '../pages/DeductionsPage.jsx'
import DeductionForm from './DeductionForm.jsx'

export const monthLabel = (iso) =>
  (iso ? new Date(`${iso.slice(0, 7)}-01T00:00:00`).toLocaleString('en-IN', { month: 'short', year: 'numeric' }) : '')

// Standing deductions on one employee's record. Click a row to edit it.
export default function EmployeeDeductions({ client, employee }) {
  const [items, setItems] = useState([])
  const [types, setTypes] = useState([])
  const [editing, setEditing] = useState(null) // a deduction, {} for new, or null
  const [errors, setErrors] = useState({})
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    try {
      setItems(await api.employeeDeductions(client.id, employee.code))
    } catch (e) {
      setError(e.message)
    }
  }, [client.id, employee.code])

  useEffect(() => {
    setEditing(null)
    setNotice('')
    load()
  }, [load])
  useEffect(() => {
    api.availableDeductions(client.id).then(setTypes).catch(() => setTypes([]))
  }, [client.id])

  const open = (d) => {
    setErrors({})
    setError('')
    setNotice('')
    setEditing(d || { employee_code: employee.code })
  }

  async function save(body) {
    try {
      if (editing.id) await api.editEmployeeDeduction(client.id, employee.code, editing.id, body)
      else await api.addEmployeeDeduction(client.id, employee.code, body)
      setEditing(null)
      setNotice('Deduction saved. Payroll runs from its first month take it automatically.')
      load()
    } catch (err) {
      setErrors(err.fieldErrors || {})
      setError(err.message)
    }
  }

  async function remove() {
    if (!window.confirm('Remove this deduction? Runs already calculated keep it; future runs will not.')) return
    try {
      await api.deleteEmployeeDeduction(client.id, employee.code, editing.id)
      setEditing(null)
      setNotice('Deduction removed.')
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="form section">
      <div className="run-head">
        <h3>Deductions</h3>
        {editing === null && types.length > 0 && <button type="button" onClick={() => open(null)}>+ Add deduction</button>}
      </div>
      <p className="muted small">
        {types.length
          ? 'PF, ESI, PT and TDS are automatic. Add the voluntary deductions and recoveries this client uses.'
          : 'PF, ESI, PT and TDS are automatic. Switch on other deductions for this client under Client deductions first.'}
      </p>
      {items.length > 0 && (
        <table className="clickable compact">
          <thead><tr><th>Deduction</th><th className="num">Amount</th><th>Months</th></tr></thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.id} tabIndex={0} className={editing?.id === d.id ? 'selected' : undefined}
                  onClick={() => open(d)} onKeyDown={(e) => e.key === 'Enter' && open(d)}>
                <td>{d.name}</td>
                <td className="num">{deductionValue(d.calc, d.value)}</td>
                <td className="small">{monthLabel(d.start_month)} → {d.end_month ? monthLabel(d.end_month) : 'ongoing'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {editing !== null && (
        <DeductionForm types={types} initial={editing}
          errors={errors} error={error} onSave={save} onCancel={() => setEditing(null)} onDelete={remove} />
      )}
      {notice && <div className="banner ok">{notice}</div>}
    </div>
  )
}
