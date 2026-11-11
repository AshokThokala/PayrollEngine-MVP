import { useEffect, useState } from 'react'
import { api, money, today } from '../api.js'

const inr = new Intl.NumberFormat('en-IN')
const rs = (v) => `₹${inr.format(Number(v))}`
const pct = (v) => `${Number((Number(v) * 100).toFixed(2))}%`
const lakh = (v) => {
  const n = Number(v)
  if (n >= 10000000) return `₹${Number((n / 10000000).toFixed(2))} cr`
  if (n >= 100000) return `₹${Number((n / 100000).toFixed(2))} lakh`
  return rs(n)
}
const mmdd = (v) => {
  if (!v) return '—'
  const [m, d] = v.split('-').map(Number)
  return new Date(2000, m - 1, d).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}
const fmtDate = (iso) => (iso ? new Date(`${iso}T00:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : 'no end date')

const surchargeText = (slabs) =>
  slabs.map((s, i) => [s, slabs[i - 1]?.upto ?? 0]).filter(([s]) => Number(s.rate) > 0)
    .map(([s, from]) => `${pct(s.rate)} above ${lakh(from)}`).join(' · ')

const AGE_SLABS = [
  ['slabs_below_60', 'Below 60'],
  ['slabs_60_to_80', '60 to 79'],
  ['slabs_80_plus', '80 and above'],
]

function SlabTable({ slabs, caption }) {
  return (
    <table className="compact slab-table">
      {caption && <caption>{caption}</caption>}
      <thead><tr><th>Taxable income</th><th className="num">Rate</th></tr></thead>
      <tbody>
        {slabs.map((s, i) => {
          const from = i === 0 ? 0 : slabs[i - 1].upto
          return (
            <tr key={i}>
              <td>{s.upto === null ? `Above ${lakh(from)}` : i === 0 ? `Up to ${lakh(s.upto)}` : `${lakh(from)} – ${lakh(s.upto)}`}</td>
              <td className="num">{Number(s.rate) === 0 ? 'Nil' : pct(s.rate)}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function Facts({ rows }) {
  return (
    <dl className="facts">
      {rows.map(([label, value]) => (
        <div key={label} style={{ display: 'contents' }}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  )
}

function VersionLine({ v }) {
  return (
    <p className="muted small">
      In force {fmtDate(v.valid_from)} → {fmtDate(v.valid_to)}
      {v.source && <><br />{v.source}</>}
    </p>
  )
}

// ---- calculator ---------------------------------------------------------------------

const CALC_FIELDS = [
  ['annual_gross', 'Yearly gross salary', true],
  ['basic_da', 'Yearly basic + DA'],
  ['hra_received', 'Yearly HRA received'],
  ['employee_pf', 'Employee PF (year)'],
  ['professional_tax', 'Professional tax (year)'],
]
const DECL_FIELDS = [
  ['rent_paid', 'Rent paid'],
  ['sec_80c', '80C investments'],
  ['sec_80ccd_1b', '80CCD(1B) NPS'],
  ['sec_80d_self', '80D self/family'],
  ['sec_80d_parents', '80D parents'],
  ['home_loan_interest', 'Home loan interest'],
]
const START = { annual_gross: '1500000', basic_da: '600000', hra_received: '300000', employee_pf: '72000', professional_tax: '2400',
  age_group: 'below_60', metro_city: false, parents_senior: false }

function Breakdown({ r, best }) {
  return (
    <div className={best ? 'regime-result best' : 'regime-result'}>
      <div className="run-head">
        <h3>{r.regime === 'new' ? 'New regime' : 'Old regime'}</h3>
        {best && <span className="tag paid">Lower tax</span>}
      </div>
      <div className="big-number">{money(r.total_tax)}<span className="muted small"> a year · {money(r.monthly_tds)} a month</span></div>
      <table className="compact">
        <tbody>
          <tr><td>Gross salary</td><td className="num">{money(r.gross)}</td></tr>
          {r.deductions.map((d) => (
            <tr key={d.label} className="muted"><td>− {d.label}</td><td className="num">{money(d.amount)}</td></tr>
          ))}
          <tr className="subtotal"><td>Taxable income</td><td className="num">{money(r.taxable_income)}</td></tr>
          {r.slabs.filter((s) => Number(s.taxed) > 0).map((s, i) => (
            <tr key={i} className="muted">
              <td>{money(s.taxed)} at {Number(s.rate) === 0 ? 'nil' : pct(s.rate)}</td>
              <td className="num">{money(s.tax)}</td>
            </tr>
          ))}
          <tr className="subtotal"><td>Tax on slabs</td><td className="num">{money(r.tax_on_slabs)}</td></tr>
          {Number(r.rebate) > 0 && <tr><td>− Rebate</td><td className="num">{money(r.rebate)}</td></tr>}
          {Number(r.surcharge) > 0 && <tr><td>+ Surcharge</td><td className="num">{money(r.surcharge)}</td></tr>}
          <tr><td>+ Health and education cess</td><td className="num">{money(r.cess)}</td></tr>
          <tr className="total"><td>Income tax for the year</td><td className="num">{money(r.total_tax)}</td></tr>
        </tbody>
      </table>
      <p className="muted small">Effective rate {pct(r.effective_rate)} of gross.</p>
    </div>
  )
}

function Calculator({ on }) {
  const [values, setValues] = useState(START)
  const [result, setResult] = useState(null)
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState('')

  const set = (k) => (e) => setValues({ ...values, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })

  async function run(e) {
    e?.preventDefault()
    setErrors({})
    setMessage('')
    try {
      setResult(await api.taxCalculate({ ...values, on }))
    } catch (err) {
      setErrors(err.fieldErrors || {})
      setMessage(err.message)
      setResult(null)
    }
  }

  useEffect(() => {
    run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [on])

  const input = ([k, label, required]) => (
    <label key={k}>
      {label}{required ? ' *' : ''} (₹)
      <input inputMode="decimal" value={values[k] ?? ''} onChange={set(k)} className={errors[k] ? 'invalid' : undefined} placeholder="0" />
      {errors[k] && <span className="field-error">{label}: {errors[k]}</span>}
    </label>
  )

  return (
    <section className="card">
      <h2>Compare regimes</h2>
      <p className="muted small">Enter one year's salary. The old regime uses the declarations; the new regime ignores them (only the standard deduction applies).</p>
      <form className="form" onSubmit={run}>
        <div className="calc-grid">{CALC_FIELDS.map(input)}</div>
        <h3 className="sub">Old-regime declarations (₹ a year)</h3>
        <div className="calc-grid">{DECL_FIELDS.map(input)}</div>
        <div className="calc-grid">
          <label>
            Age
            <select value={values.age_group} onChange={set('age_group')}>
              <option value="below_60">Below 60</option>
              <option value="60_to_80">60 to 79</option>
              <option value="80_plus">80 and above</option>
            </select>
          </label>
          <label className="check"><input type="checkbox" checked={values.metro_city} onChange={set('metro_city')} /> Lives in a metro (HRA 50%)</label>
          <label className="check"><input type="checkbox" checked={values.parents_senior} onChange={set('parents_senior')} /> Parents 60 or older</label>
        </div>
        {message && <div className="banner error">{message}</div>}
        <div className="actions"><button className="primary">Calculate</button></div>
      </form>
      {result && (
        <>
          <div className="banner ok verdict">
            The <strong>{result.better === 'new' ? 'new' : 'old'} regime</strong> is lower
            {Number(result.saving) > 0 ? <> by <strong>{money(result.saving)}</strong> a year</> : ' — both come to the same tax'}.
          </div>
          <div className="regime-compare">
            <Breakdown r={result.new} best={result.better === 'new'} />
            <Breakdown r={result.old} best={result.better === 'old'} />
          </div>
          <p className="muted small">An estimate for salary income only: perquisites, employer NPS, other income and a previous employer's salary are not included.</p>
        </>
      )}
    </section>
  )
}

// ---- page -----------------------------------------------------------------------------

export default function TaxRulesPage({ canEdit, onEdit }) {
  const [on, setOn] = useState(today())
  const [data, setData] = useState(null)
  const [age, setAge] = useState('slabs_below_60')
  const [error, setError] = useState('')

  useEffect(() => {
    if (!on) return
    api.taxRules(on).then((d) => { setData(d); setError('') }).catch((e) => setError(e.message))
  }, [on])

  if (!data) return error ? <div className="banner error">{error}</div> : <p className="muted">Loading…</p>
  const n = data.regimes.new.params
  const o = data.regimes.old.params
  const due = data.due_dates

  return (
    <div className="stack">
      <div className="tax-head">
        <div>
          <h2>Income tax on salary — Tax Year {data.tax_year}</h2>
          <p className="muted small">Income-tax Act 2025. TDS on salary is worked out each month from these rules (s.392). The new regime is the default.</p>
        </div>
        <div className="actions">
          <label className="field-inline"><span className="muted small">Rules in force on</span>
            <input type="date" value={on} onChange={(e) => setOn(e.target.value)} />
          </label>
        </div>
      </div>
      {error && <div className="banner error">{error}</div>}

      <div className="regime-compare">
        <section className="card">
          <div className="run-head">
            <h2>New regime <span className="tag paid">default</span></h2>
            {canEdit && <button onClick={() => onEdit('income_tax_new_regime')}>Change</button>}
          </div>
          <VersionLine v={data.regimes.new} />
          <SlabTable slabs={n.slabs} />
          <Facts rows={[
            ['Standard deduction', rs(n.standard_deduction)],
            ['Rebate', `Up to ${rs(n.rebate_max)} if taxable income ≤ ${lakh(n.rebate_income_limit)}, with marginal relief above it`],
            ['Surcharge', surchargeText(n.surcharge_slabs)],
            ['Cess', `${pct(n.cess_rate)} on tax + surcharge`],
            ['Deductions', 'Only the standard deduction (no HRA, 80C, 80D or home loan interest)'],
          ]} />
        </section>

        <section className="card">
          <div className="run-head">
            <h2>Old regime</h2>
            {canEdit && <button onClick={() => onEdit('income_tax_old_regime')}>Change</button>}
          </div>
          <VersionLine v={data.regimes.old} />
          <div className="segmented three" role="tablist" aria-label="Age group">
            {AGE_SLABS.map(([k, label]) => (
              <button key={k} role="tab" aria-selected={age === k} className={age === k ? 'active' : ''} onClick={() => setAge(k)}>{label}</button>
            ))}
          </div>
          <SlabTable slabs={o[age]} />
          <Facts rows={[
            ['Standard deduction', rs(o.standard_deduction)],
            ['Rebate', `Up to ${rs(o.rebate_max)} if taxable income ≤ ${lakh(o.rebate_income_limit)}`],
            ['Surcharge', surchargeText(o.surcharge_slabs)],
            ['Cess', `${pct(o.cess_rate)} on tax + surcharge`],
          ]} />
        </section>
      </div>

      <div className="regime-compare">
        <section className="card">
          <h2>Old-regime deduction limits</h2>
          <table className="compact">
            <thead><tr><th>Deduction</th><th className="num">Limit (₹/year)</th></tr></thead>
            <tbody>
              <tr><td>80C — PF, PPF, ELSS, life insurance, tuition, home loan principal</td><td className="num">{rs(o.limit_80c)}</td></tr>
              <tr><td>80CCD(1B) — own extra NPS contribution</td><td className="num">{rs(o.limit_80ccd_1b)}</td></tr>
              <tr><td>80D — health insurance, self and family</td><td className="num">{rs(o.limit_80d_self)} ({rs(o.limit_80d_self_senior)} if 60+)</td></tr>
              <tr><td>80D — health insurance, parents</td><td className="num">{rs(o.limit_80d_parents)} ({rs(o.limit_80d_parents_senior)} if 60+)</td></tr>
              <tr><td>Home loan interest — self-occupied house</td><td className="num">{rs(o.limit_home_loan_interest)}</td></tr>
              <tr><td>Professional tax paid</td><td className="num">{rs(2500)}</td></tr>
              <tr><td>HRA exemption — least of HRA received, rent − 10% of salary, or {pct(o.hra_metro_share)} of salary (metro) / {pct(o.hra_non_metro_share)} (other cities)</td><td className="num">formula</td></tr>
            </tbody>
          </table>
        </section>

        <section className="card">
          <div className="run-head">
            <h2>TDS deposit and returns</h2>
            {canEdit && <button onClick={() => onEdit('filing_due_dates')}>Change</button>}
          </div>
          <table className="compact">
            <tbody>
              <tr><td>TDS deposit (April to February)</td><td className="num">{due.tds_due_day}th of the next month</td></tr>
              <tr><td>TDS deposit for March</td><td className="num">{mmdd(due.tds_march_due)}</td></tr>
              <tr><td>Form 24Q — Q1 (Apr–Jun)</td><td className="num">{mmdd(due.form_24q_q1_due)}</td></tr>
              <tr><td>Form 24Q — Q2 (Jul–Sep)</td><td className="num">{mmdd(due.form_24q_q2_due)}</td></tr>
              <tr><td>Form 24Q — Q3 (Oct–Dec)</td><td className="num">{mmdd(due.form_24q_q3_due)}</td></tr>
              <tr><td>Form 24Q — Q4 (Jan–Mar)</td><td className="num">{mmdd(due.form_24q_q4_due)}</td></tr>
            </tbody>
          </table>
          <p className="muted small">Late deposit: interest 1.5% a month. Late Form 24Q: ₹200 a day fee. The compliance calendar tracks these for each client.</p>
        </section>
      </div>

      <Calculator on={on} />

      <section className="card">
        <h2>Version history</h2>
        <p className="muted small">Every change is a new dated version; past payslips keep the version they used.</p>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Regime</th><th>From</th><th>To</th><th>Source</th><th>Added by</th></tr></thead>
            <tbody>
              {data.history.map((h) => (
                <tr key={h.id}>
                  <td>{h.regime === 'new' ? 'New' : 'Old'}</td>
                  <td>{fmtDate(h.valid_from)}</td>
                  <td>{h.valid_to ? fmtDate(h.valid_to) : <span className="tag paid">current</span>}</td>
                  <td className="small">{h.source || '—'}</td>
                  <td className="small">{h.created_by || 'seed'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
