import { useCallback, useEffect, useState } from 'react'
import { api, money } from '../api.js'
import PayslipView from '../components/PayslipView.jsx'
import TaxFields, { taxFromEmployee } from '../components/TaxFields.jsx'

const monthName = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })

// What an employee sees: their own profile, final payslips and tax declarations.
export default function EmployeePortal({ user, onLogout }) {
  const [me, setMe] = useState(null)
  const [slips, setSlips] = useState([])
  const [open, setOpen] = useState(null)
  const [tax, setTax] = useState(null)
  const [taxErrors, setTaxErrors] = useState({})
  const [message, setMessage] = useState(null)

  const load = useCallback(async () => {
    try {
      const [m, p] = await Promise.all([api.myEmployee(), api.myPayslips()])
      setMe(m)
      setSlips(p)
      setTax(taxFromEmployee(m.employee))
      setOpen((cur) => cur ?? p[0]?.run_id ?? null)
    } catch (err) {
      setMessage({ kind: 'error', text: err.message })
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const saveTax = async (e) => {
    e.preventDefault()
    setTaxErrors({})
    try {
      await api.updateMyTax(tax)
      setMessage({ kind: 'ok', text: 'Tax details saved. They apply from the next payroll run.' })
      load()
    } catch (err) {
      setTaxErrors(err.fieldErrors || {})
      setMessage({ kind: 'error', text: err.message })
    }
  }

  const latest = slips[0]?.payslip
  const viewingAs = user.impersonated_by

  return (
    <div className="portal">
      <header className="portal-top">
        <div className="brand">
          <span className="logo">C4U</span>
          <span>ClearPay4U<span className="tagline">{me ? me.client_name : 'zero-penalty payroll'}</span></span>
        </div>
        <div className="inline">
          <span className="muted small hide-sm">{viewingAs ? `Viewing as ${user.name}` : user.email}</span>
          <button className="ghost light" onClick={onLogout}>{viewingAs ? 'Back to admin' : 'Log out'}</button>
        </div>
      </header>

      {viewingAs && (
        <div className="view-as-bar" role="status">
          <span>You're viewing as <strong>{user.name}</strong> (read-only). Recorded in the audit log.</span>
          <button onClick={onLogout}>Back to admin</button>
        </div>
      )}
      <main className="portal-main">
        <h1 className="greeting">Hello, {user.name.split(' ')[0]}</h1>
        {message && <div className={`banner ${message.kind}`}>{message.text}</div>}

        <div className="stats">
          <div><span>Latest net pay</span><strong>{latest ? money(latest.net_pay) : '—'}</strong></div>
          <div><span>Gross</span><strong>{latest ? money(latest.gross) : '—'}</strong></div>
          <div><span>Income tax this month</span><strong>{latest ? money(latest.deductions.find((d) => d.code === 'tds')?.amount || 0) : '—'}</strong></div>
          <div><span>Tax regime</span><strong>{me?.employee.tax.tax_regime === 'old' ? 'Old' : 'New'}</strong></div>
        </div>

        <div className="grid">
          <section className="card">
            <h2>Payslips</h2>
            {slips.length === 0 ? (
              <p className="muted">No payslips yet. They appear here once your employer finalises a month's payroll.</p>
            ) : (
              <ul className="list">
                {slips.map((s) => (
                  <li key={s.run_id}>
                    <button className={open === s.run_id ? 'list-item active' : 'list-item'} onClick={() => setOpen(s.run_id)}>
                      <span>{monthName(s.period)}</span>
                      <span className="num">{money(s.payslip.net_pay)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {me && (
              <dl className="facts">
                <dt>Employee code</dt><dd>{me.employee.code}</dd>
                <dt>Joined</dt><dd>{me.employee.joined_on}</dd>
                <dt>Monthly salary</dt><dd>{money(me.employee.monthly_total)}</dd>
              </dl>
            )}
          </section>

          <section className="card wide">
            {slips.filter((s) => s.run_id === open).map((s) => (
              <div key={s.run_id}>
                <h2>Payslip — {monthName(s.period)}</h2>
                <div className="stats">
                  <div><span>Gross</span><strong>{money(s.payslip.gross)}</strong></div>
                  <div><span>Deductions</span><strong>{money(s.payslip.total_deductions)}</strong></div>
                  <div><span>Net pay</span><strong>{money(s.payslip.net_pay)}</strong></div>
                </div>
                <PayslipView slip={s.payslip} />
              </div>
            ))}
            {tax && (
              <form className="form section" onSubmit={saveTax}>
                <h2>Income tax declarations</h2>
                <p className="muted small">Choose your regime and declare your investments so the right tax is deducted each month.</p>
                <fieldset className="plain" disabled={!!viewingAs}>
                  <TaxFields value={tax} onChange={setTax} errors={taxErrors} />
                </fieldset>
                {viewingAs
                  ? <p className="muted small">Read-only while viewing as this employee. Edit tax details from the Employees page.</p>
                  : <button className="primary">Save tax details</button>}
              </form>
            )}
          </section>
        </div>
      </main>
    </div>
  )
}
