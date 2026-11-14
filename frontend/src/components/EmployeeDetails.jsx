import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { OPTIONS, optionLabel } from './ProfileFields.jsx'

// Personal, contact, job, statutory and bank details for one employee, edited by the employer.
// The same record is what the employee fills in during onboarding.
const SECTIONS = [
  { id: 'personal', title: 'Personal', fields: [
    ['date_of_birth', 'Date of birth', { type: 'date' }],
    ['gender', 'Gender', { options: OPTIONS.gender }],
    ['marital_status', 'Marital status', { options: OPTIONS.marital_status }],
    ['father_or_spouse_name', "Father's or spouse's name", { hint: 'Needed for PF (EPFO) and ESI registration' }],
    ['father_or_spouse_relation', 'Relation', { options: OPTIONS.father_or_spouse_relation }],
    ['nationality', 'Nationality', { placeholder: 'Indian' }],
    ['blood_group', 'Blood group', { options: OPTIONS.blood_group }],
    ['differently_abled', 'Person with disability', { options: OPTIONS.differently_abled }],
  ] },
  { id: 'contact', title: 'Contact', fields: [
    ['phone', 'Mobile number', { inputMode: 'numeric' }],
    ['personal_email', 'Personal email', { type: 'email' }],
    ['address', 'Current address', { wide: true }],
    ['city', 'City'],
    ['pincode', 'PIN code', { inputMode: 'numeric' }],
    ['permanent_address', 'Permanent address', { wide: true, sameAs: 'address' }],
    ['emergency_name', 'Emergency contact'],
    ['emergency_relation', 'Relation', { placeholder: 'e.g. Spouse' }],
    ['emergency_phone', 'Emergency number', { inputMode: 'numeric' }],
  ] },
  { id: 'job', title: 'Job', fields: [
    ['designation', 'Designation'],
    ['department', 'Department'],
    ['employment_type', 'Employment type', { options: OPTIONS.employment_type }],
    ['work_location', 'Work location'],
    ['reporting_manager', 'Reporting manager'],
    ['work_email', 'Work email', { type: 'email' }],
  ] },
  { id: 'statutory', title: 'Statutory and bank', fields: [
    ['pan', 'PAN', { style: { textTransform: 'uppercase' } }],
    ['uan', 'UAN', { inputMode: 'numeric' }],
    ['esi_ip', 'ESI IP number', { inputMode: 'numeric' }],
    ['bank_name', 'Bank name'],
    ['ifsc', 'IFSC', { style: { textTransform: 'uppercase' } }],
    ['account_number', 'Account number', { inputMode: 'numeric' }],
  ] },
]
const KEYS = SECTIONS.flatMap((s) => s.fields.map(([k]) => k))

export function ageFrom(dob) {
  if (!dob) return null
  const b = new Date(`${dob}T00:00:00`)
  const now = new Date()
  let age = now.getFullYear() - b.getFullYear()
  if (now.getMonth() < b.getMonth() || (now.getMonth() === b.getMonth() && now.getDate() < b.getDate())) age -= 1
  return Number.isFinite(age) ? age : null
}

const ONBOARDING = { draft: 'Filling in', submitted: 'Submitted for review', returned: 'Returned to employee', verified: 'Verified' }

export default function EmployeeDetails({ client, employee, onSaved }) {
  const [profile, setProfile] = useState(null)
  const [form, setForm] = useState({})
  const [section, setSection] = useState('personal')
  const [editing, setEditing] = useState(false)
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setProfile(null)
    setEditing(false)
    setMessage(null)
    api.employeeProfile(client.id, employee.code).then((p) => {
      setProfile(p)
      setForm(Object.fromEntries(KEYS.map((k) => [k, p[k] || ''])))
      onSaved?.(p)
    }).catch((e) => setMessage({ kind: 'error', text: e.message }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client.id, employee.code])

  if (!profile) return message ? <div className={`banner ${message.kind}`}>{message.text}</div> : <p className="muted small">Loading details…</p>

  const set = (k) => (e) => {
    setForm({ ...form, [k]: e.target.value })
    if (errors[k]) setErrors({ ...errors, [k]: undefined })
  }

  async function save(e) {
    e.preventDefault()
    setBusy(true)
    setErrors({})
    try {
      const p = await api.saveEmployeeProfile(client.id, employee.code, form)
      setProfile(p)
      setForm(Object.fromEntries(KEYS.map((k) => [k, p[k] || ''])))
      setEditing(false)
      setMessage({ kind: 'ok', text: 'Details saved.' })
      onSaved?.(p)
    } catch (err) {
      const fe = err.fieldErrors || {}
      setErrors(fe)
      setMessage({ kind: 'error', text: err.message })
      const first = SECTIONS.find((s) => s.fields.some(([k]) => fe[k]))
      if (first) setSection(first.id)
    } finally {
      setBusy(false)
    }
  }

  const current = SECTIONS.find((s) => s.id === section)
  const filled = (s) => s.fields.filter(([k]) => profile[k]).length

  return (
    <div className="form section emp-details">
      <div className="run-head">
        <h3>Employee details</h3>
        <div className="actions">
          <span className={`tag ${profile.status === 'verified' ? 'paid' : profile.status === 'submitted' ? 'pending' : 'draft'}`}
            title="Onboarding status">{ONBOARDING[profile.status] || profile.status}</span>
          {!editing && <button type="button" onClick={() => { setEditing(true); setMessage(null) }}>Edit details</button>}
        </div>
      </div>
      <div className="segmented small-seg" role="tablist" aria-label="Details">
        {SECTIONS.map((s) => (
          <button key={s.id} type="button" role="tab" aria-selected={section === s.id} className={section === s.id ? 'active' : ''}
            onClick={() => setSection(s.id)}>
            {s.title} <span className="muted">{filled(s)}/{s.fields.length}</span>
          </button>
        ))}
      </div>
      {!editing ? (
        <dl className="facts details-grid">
          {current.fields.map(([k, label]) => (
            <div key={k} className={`fact ${k.endsWith('address') ? 'wide' : ''}`}>
              <dt>{label}</dt>
              <dd>
                {profile[k] ? optionLabel(k, profile[k]) : <span className="muted">—</span>}
                {k === 'date_of_birth' && ageFrom(profile[k]) !== null && <span className="muted small"> · {ageFrom(profile[k])} years</span>}
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <form onSubmit={save} className="form">
          <div className="details-grid">
            {current.fields.map(([k, label, { options, wide, hint, sameAs, ...props } = {}]) => (
              <label key={k} className={wide ? 'wide' : undefined}>
                <span>{label}</span>
                {options ? (
                  <select value={form[k] || ''} onChange={set(k)} className={errors[k] ? 'invalid' : undefined}>
                    <option value="">—</option>
                    {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                ) : (
                  <input value={form[k] || ''} onChange={set(k)} className={errors[k] ? 'invalid' : undefined}
                    aria-invalid={errors[k] ? true : undefined} {...props} />
                )}
                {sameAs && (
                  <button type="button" className="link small" onClick={() => setForm({ ...form, [k]: form[sameAs] })}>Same as current address</button>
                )}
                {hint && !errors[k] && <span className="muted small">{hint}</span>}
                {errors[k] && <span className="field-error">{label}: {errors[k]}</span>}
              </label>
            ))}
          </div>
          {Object.keys(errors).some((k) => !current.fields.some(([f]) => f === k) && errors[k]) && (
            <div className="banner error">Other sections have problems too — check the tabs above.</div>
          )}
          {message?.kind === 'error' && <div className="banner error">{message.text}</div>}
          <div className="actions">
            <button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save details'}</button>
            <button type="button" onClick={() => { setEditing(false); setErrors({}); setForm(Object.fromEntries(KEYS.map((k) => [k, profile[k] || '']))) }}>Cancel</button>
          </div>
        </form>
      )}
      {message?.kind === 'ok' && <div className="banner ok">{message.text}</div>}
    </div>
  )
}
