import { useCallback, useEffect, useState } from 'react'
import { api, money, today } from '../api.js'

const lastMonth = () => {
  const d = new Date()
  d.setDate(1)
  d.setMonth(d.getMonth() - 1)
  return d.toISOString().slice(0, 7)
}
const monthName = (iso) => new Date(`${iso.slice(0, 7)}-01T00:00:00`).toLocaleString('en-IN', { month: 'long', year: 'numeric' })
const STATUS_TAG = { draft: 'draft', issued: 'pending', paid: 'paid', void: 'error' }

function PlanForm({ client, plan, catalog, onSaved }) {
  const [form, setForm] = useState({})
  const [errors, setErrors] = useState({})
  const [msg, setMsg] = useState('')

  useEffect(() => {
    setForm({
      plan: plan?.plan || 'software',
      rate_per_employee: plan?.rate_per_employee ?? '',
      minimum_fee: plan?.minimum_fee ?? '',
      onboarding_fee: plan?.onboarding_fee ?? '',
      billing_email: plan?.billing_email || '',
      starts_on: plan?.starts_on || '',
    })
  }, [plan])

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const preset = catalog.find((p) => p.plan === form.plan)

  async function save(e) {
    e.preventDefault()
    setErrors({})
    setMsg('')
    const body = { plan: form.plan, billing_email: form.billing_email }
    for (const k of ['rate_per_employee', 'minimum_fee', 'onboarding_fee']) if (form[k] !== '') body[k] = form[k]
    if (form.starts_on) body.starts_on = form.starts_on
    try {
      await api.setBillingPlan(client.id, body)
      setMsg('Plan saved.')
      onSaved()
    } catch (err) {
      setErrors(err.fieldErrors || {})
      setMsg(err.message)
    }
  }

  const field = (k, label, props = {}) => (
    <label>
      {label}
      <input value={form[k] ?? ''} onChange={set(k)} className={errors[k] ? 'invalid' : undefined} {...props} />
      {errors[k] && <span className="field-error">{label}: {errors[k]}</span>}
    </label>
  )

  return (
    <form className="form" onSubmit={save}>
      <label>
        Plan
        <select value={form.plan || 'software'} onChange={set('plan')}>
          {catalog.map((p) => <option key={p.plan} value={p.plan}>{p.label}</option>)}
        </select>
      </label>
      {field('rate_per_employee', 'Rate per employee (₹/month)', { inputMode: 'decimal', placeholder: preset?.rate_per_employee })}
      {field('minimum_fee', 'Monthly minimum (₹)', { inputMode: 'decimal', placeholder: preset?.minimum_fee })}
      {field('onboarding_fee', 'Onboarding fee (₹, one-time)', { inputMode: 'decimal', placeholder: preset?.onboarding_fee })}
      {field('billing_email', 'Billing email', { type: 'email' })}
      {field('starts_on', 'Billing starts on', { type: 'date' })}
      <p className="muted small">Leave a rate blank to use the plan's standard price. GST at 18% is added on invoices.</p>
      {msg && <div className={Object.keys(errors).length || msg !== 'Plan saved.' ? 'banner error' : 'banner ok'}>{msg}</div>}
      <button className="primary" type="submit">Save plan</button>
    </form>
  )
}

function InvoiceView({ inv, client, platform, onAction }) {
  const [paidOn, setPaidOn] = useState(today())
  const [reference, setReference] = useState('')
  return (
    <div className="invoice printable">
      <div className="invoice-head">
        <div>
          <strong className="invoice-brand">ClearPay4U</strong>
          <span className="muted small">Tax invoice</span>
        </div>
        <div className="right">
          <strong>{inv.number || 'DRAFT'}</strong>
          <span className="muted small">
            {inv.issue_date ? `Issued ${inv.issue_date} · due ${inv.due_date}` : 'Not issued yet'}
          </span>
        </div>
      </div>
      <p>
        <strong>{client.legal_name}</strong>
        {client.pan && <span className="muted small"> · PAN {client.pan}</span>}
        <br />
        <span className="muted small">Service period: {monthName(inv.period)}</span>
      </p>
      <table className="compact">
        <thead><tr><th>Description</th><th className="num">Qty</th><th className="num">Rate</th><th className="num">Amount</th></tr></thead>
        <tbody>
          {inv.lines.map((l, i) => (
            <tr key={i}>
              <td>{l.description}</td>
              <td className="num">{l.quantity}</td>
              <td className="num">{money(l.rate)}</td>
              <td className="num">{money(l.amount)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr><td colSpan={3}>Subtotal</td><td className="num">{money(inv.subtotal)}</td></tr>
          {Number(inv.igst) > 0 ? (
            <tr><td colSpan={3}>IGST 18%</td><td className="num">{money(inv.igst)}</td></tr>
          ) : (
            <>
              <tr><td colSpan={3}>CGST 9%</td><td className="num">{money(inv.cgst)}</td></tr>
              <tr><td colSpan={3}>SGST 9%</td><td className="num">{money(inv.sgst)}</td></tr>
            </>
          )}
          <tr className="total"><td colSpan={3}>Total</td><td className="num">{money(inv.total)}</td></tr>
        </tfoot>
      </table>
      {inv.status === 'paid' && <p className="small ok-text">Paid on {inv.paid_on} · ref {inv.payment_ref}</p>}
      <div className="actions no-print">
        <button onClick={() => window.print()}>Print / save PDF</button>
        {platform && inv.status === 'draft' && <button className="primary" onClick={() => onAction('issue')}>Issue invoice</button>}
        {platform && inv.status !== 'paid' && inv.status !== 'void' && (
          <button onClick={() => window.confirm('Void this invoice? Its number stays used.') && onAction('void')}>Void</button>
        )}
      </div>
      {platform && inv.status === 'issued' && (
        <form className="pay-row no-print" onSubmit={(e) => { e.preventDefault(); onAction('pay', { paid_on: paidOn, reference }) }}>
          <label className="field-inline"><span className="muted small">Paid on</span>
            <input type="date" value={paidOn} onChange={(e) => setPaidOn(e.target.value)} />
          </label>
          <label className="field-inline"><span className="muted small">UTR / reference</span>
            <input value={reference} onChange={(e) => setReference(e.target.value)} placeholder="e.g. UTR123456" />
          </label>
          <button className="primary" type="submit">Mark paid</button>
        </form>
      )}
    </div>
  )
}

export default function BillingPage({ client, platform, onPickClient }) {
  const [data, setData] = useState(null)
  const [catalog, setCatalog] = useState([])
  const [overview, setOverview] = useState([])
  const [selected, setSelected] = useState(null)
  const [month, setMonth] = useState(lastMonth())
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    try {
      const d = await api.clientBilling(client.id)
      setData(d)
      setSelected((cur) => d.invoices.find((i) => i.id === cur?.id) || d.invoices[0] || null)
      if (platform) setOverview(await api.billingOverview())
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }, [client.id, platform])

  useEffect(() => {
    setSelected(null)
    setNotice('')
    load()
  }, [load])
  useEffect(() => {
    api.billingPlans().then(setCatalog).catch(() => {})
  }, [])

  async function generate() {
    setNotice('')
    try {
      const inv = await api.generateInvoice(client.id, `${month}-01`)
      setSelected(inv)
      setNotice(`Draft invoice for ${monthName(inv.period)} ready. Check it, then issue it.`)
      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  async function act(action, body) {
    setError('')
    try {
      const inv = await api.invoiceAction(selected.id, action, body)
      setSelected(inv)
      setNotice({ issue: `Issued ${inv.number}.`, pay: `${inv.number} marked paid.`, void: `${inv.number || 'Invoice'} voided.` }[action])
      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  if (!data) return error ? <div className="banner error">{error}</div> : <p className="muted">Loading…</p>
  const plan = data.plan

  return (
    <div className="stack">
      {error && <div className="banner error">{error}</div>}
      {notice && <div className="banner ok">{notice}</div>}
      <div className="grid">
        <section className="card no-print">
          <h2>Plan</h2>
          {platform ? (
            <PlanForm client={client} plan={plan} catalog={catalog} onSaved={load} />
          ) : plan ? (
            <dl className="facts">
              <dt>Plan</dt><dd>{plan.label}</dd>
              <dt>Per employee</dt><dd>{money(plan.rate_per_employee)} / month</dd>
              <dt>Monthly minimum</dt><dd>{money(plan.minimum_fee)}</dd>
              <dt>Billing email</dt><dd>{plan.billing_email || '—'}</dd>
            </dl>
          ) : (
            <p className="muted">No billing plan yet. ClearPay4U will set one up with you.</p>
          )}
        </section>

        <section className="card">
          <div className="run-head no-print">
            <h2>Invoices</h2>
            {platform && plan && (
              <div className="actions">
                <label className="field-inline"><span className="muted small">Month</span>
                  <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
                </label>
                <button className="primary" onClick={generate}>Generate invoice</button>
              </div>
            )}
          </div>
          {platform && !plan && <p className="muted no-print">Save a plan first, then generate invoices from locked payroll months.</p>}
          {data.invoices.length === 0 ? (
            <p className="muted no-print">No invoices yet.</p>
          ) : (
            <div className="table-wrap no-print">
              <table className="clickable">
                <thead><tr><th>Number</th><th>Month</th><th>Status</th><th>Due</th><th className="num">Total</th></tr></thead>
                <tbody>
                  {data.invoices.map((i) => (
                    <tr key={i.id} className={selected?.id === i.id ? 'selected' : undefined} onClick={() => setSelected(i)}>
                      <td>{i.number || 'Draft'}</td>
                      <td>{monthName(i.period)}</td>
                      <td><span className={`tag ${STATUS_TAG[i.status]}`}>{i.status}</span></td>
                      <td>{i.due_date || '—'}</td>
                      <td className="num">{money(i.total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {selected && <InvoiceView inv={selected} client={client} platform={platform} onAction={act} />}
        </section>
      </div>

      {platform && overview.length > 0 && (
        <section className="card no-print">
          <h2>All clients</h2>
          <div className="table-wrap">
            <table className="clickable">
              <thead><tr><th>Client</th><th>Plan</th><th>Last invoice</th><th className="num">Outstanding</th><th className="num">Overdue</th></tr></thead>
              <tbody>
                {overview.map((r) => (
                  <tr key={r.client_id} className={r.client_id === client.id ? 'selected' : undefined} onClick={() => onPickClient(r.client_id)}>
                    <td>{r.client_name}</td>
                    <td>{r.plan || <span className="muted">Not set</span>}</td>
                    <td>{r.last_invoice ? monthName(r.last_invoice) : '—'}</td>
                    <td className="num">{money(r.outstanding)}</td>
                    <td className="num">{Number(r.overdue) > 0 ? <span className="error-text">{money(r.overdue)}</span> : money(0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}
