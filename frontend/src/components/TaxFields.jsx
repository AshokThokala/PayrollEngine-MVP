import InfoTip from './InfoTip.jsx'

// Employee's income tax choices and old-regime declarations (annual ₹).
export const DECLARATIONS = [
  ['rent_paid', 'Rent paid (₹/year)', 'Annual rent for HRA exemption. Needs rent receipts; landlord PAN if rent is over ₹1 lakh a year.'],
  ['sec_80c', '80C investments (₹/year)', 'PPF, ELSS, life insurance, tuition fees, home loan principal, etc. Employee PF is added automatically.'],
  ['sec_80ccd_1b', '80CCD(1B) NPS (₹/year)', "Employee's own extra NPS contribution, over and above 80C."],
  ['sec_80d_self', '80D self/family (₹/year)', 'Health insurance premium for self, spouse and children.'],
  ['sec_80d_parents', '80D parents (₹/year)', 'Health insurance premium for parents.'],
  ['home_loan_interest', 'Home loan interest (₹/year)', 'Interest on a loan for a self-occupied house.'],
]

export const EMPTY_TAX = {
  tax_regime: 'new',
  tax_age_group: 'below_60',
  metro_city: false,
  parents_senior: false,
  declarations: {},
}

export function taxFromEmployee(emp) {
  const t = emp?.tax || EMPTY_TAX
  return { ...EMPTY_TAX, ...t, declarations: { ...(t.declarations || {}) } }
}

export default function TaxFields({ value, onChange, errors = {} }) {
  const set = (key, v) => onChange({ ...value, [key]: v })
  const setDecl = (key, v) => onChange({ ...value, declarations: { ...value.declarations, [key]: v } })
  const err = (key, label) => (errors[key] ? <span className="field-error">{label}: {errors[key]}</span> : null)
  return (
    <>
      <div className="row">
        <label>
          <span className="label-text">Tax regime<InfoTip id="tip-regime" text="New regime is the default: lower rates, standard deduction ₹75,000, few deductions. Old regime allows HRA, 80C, 80D and home loan deductions." /></span>
          <select value={value.tax_regime} onChange={(e) => set('tax_regime', e.target.value)}>
            <option value="new">New (default)</option>
            <option value="old">Old</option>
          </select>
          {err('tax_regime', 'Tax regime')}
        </label>
        <label>
          <span className="label-text">Age group<InfoTip id="tip-age" text="Decides the old-regime exemption limit and the 80D limit for self." /></span>
          <select value={value.tax_age_group} onChange={(e) => set('tax_age_group', e.target.value)}>
            <option value="below_60">Below 60</option>
            <option value="60_to_80">60 to 79</option>
            <option value="80_plus">80 and above</option>
          </select>
          {err('tax_age_group', 'Age group')}
        </label>
      </div>
      {value.tax_regime === 'old' && (
        <>
          <div className="row">
            <label className="check"><input type="checkbox" checked={value.metro_city} onChange={(e) => set('metro_city', e.target.checked)} /> Lives in a metro (Delhi, Mumbai, Kolkata, Chennai)</label>
            <label className="check"><input type="checkbox" checked={value.parents_senior} onChange={(e) => set('parents_senior', e.target.checked)} /> Parents are 60+</label>
          </div>
          {DECLARATIONS.map(([key, label, help]) => (
            <label key={key} className="row-label">
              <span className="label-text">{label}<InfoTip id={`tip-${key}`} text={help} /></span>
              <input type="number" min="0" step="1" value={value.declarations[key] ?? ''}
                className={errors[key] ? 'invalid' : undefined}
                onChange={(e) => setDecl(key, e.target.value)} />
              {err(key, label)}
            </label>
          ))}
          <p className="muted small">Declared amounts are used for monthly TDS. Collect proofs before the year-end.</p>
        </>
      )}
    </>
  )
}
