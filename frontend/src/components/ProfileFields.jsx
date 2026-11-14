// Choices for demographic fields (the API checks the same lists).
export const OPTIONS = {
  gender: [['male', 'Male'], ['female', 'Female'], ['transgender', 'Transgender'], ['prefer_not_to_say', 'Prefer not to say']],
  marital_status: [['single', 'Single'], ['married', 'Married'], ['widowed', 'Widowed'], ['divorced', 'Divorced'], ['separated', 'Separated']],
  father_or_spouse_relation: [['father', 'Father'], ['spouse', 'Spouse']],
  blood_group: ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'].map((b) => [b, b]),
  differently_abled: [['no', 'No'], ['yes', 'Yes']],
  employment_type: [['permanent', 'Permanent'], ['probation', 'On probation'], ['contract', 'Contract'], ['intern', 'Intern'], ['consultant', 'Consultant']],
}
export const optionLabel = (key, value) => (OPTIONS[key] || []).find(([v]) => v === value)?.[1] || value

// The joining form an employee fills in, grouped into steps. Shared by the portal and the admin review.
export const PROFILE_SECTIONS = [
  {
    id: 'personal',
    title: 'Personal and contact',
    fields: [
      ['phone', 'Mobile number', { inputMode: 'numeric', placeholder: '9876543210' }],
      ['date_of_birth', 'Date of birth', { type: 'date' }],
      ['gender', 'Gender', { options: OPTIONS.gender, optional: true }],
      ['marital_status', 'Marital status', { options: OPTIONS.marital_status, optional: true }],
      ['father_or_spouse_name', "Father's or spouse's name (for PF)", { optional: true }],
      ['father_or_spouse_relation', 'Relation', { options: OPTIONS.father_or_spouse_relation, optional: true }],
      ['personal_email', 'Personal email', { type: 'email', optional: true }],
      ['blood_group', 'Blood group', { options: OPTIONS.blood_group, optional: true }],
      ['address', 'Address', { placeholder: 'House no., street, area' }],
      ['city', 'City'],
      ['pincode', 'PIN code', { inputMode: 'numeric', placeholder: '500034' }],
      ['emergency_name', 'Emergency contact name'],
      ['emergency_relation', 'Emergency contact relation', { optional: true, placeholder: 'e.g. Spouse' }],
      ['emergency_phone', 'Emergency contact number', { inputMode: 'numeric' }],
    ],
  },
  {
    id: 'statutory',
    title: 'PAN, PF and ESI',
    fields: [
      ['pan', 'PAN', { placeholder: 'ABCDE1234F', style: { textTransform: 'uppercase' } }],
      ['uan', 'UAN (if you had PF before)', { inputMode: 'numeric', placeholder: '12 digits', optional: true }],
      ['esi_ip', 'ESI IP number (if any)', { inputMode: 'numeric', placeholder: '10 digits', optional: true }],
    ],
  },
  {
    id: 'bank',
    title: 'Salary bank account',
    fields: [
      ['bank_name', 'Bank name', { placeholder: 'HDFC Bank' }],
      ['ifsc', 'IFSC', { placeholder: 'HDFC0001234', style: { textTransform: 'uppercase' } }],
      ['account_number', 'Account number', { inputMode: 'numeric' }],
    ],
  },
]

export const PROFILE_KEYS = PROFILE_SECTIONS.flatMap((s) => s.fields.map(([k]) => k))

export const STAGES = {
  not_invited: ['Not invited', 'draft'],
  invited: ['Invited', 'pending'],
  invite_expired: ['Invite expired', 'error'],
  registered: ['Registered', 'approved'],
  pending: ['Awaiting approval', 'pending'],
  disabled: ['Disabled', 'draft'],
  draft: ['Filling in', 'approved'],
  submitted: ['Submitted', 'pending'],
  returned: ['Returned', 'error'],
  verified: ['Verified', 'paid'],
}

export function StageTag({ stage }) {
  const [label, kind] = STAGES[stage] || [stage, 'pending']
  return <span className={`tag ${kind}`}>{label}</span>
}

export function ProfileForm({ section, values, onChange, errors = {}, disabled }) {
  return (
    <fieldset className="plain profile-grid" disabled={disabled}>
      {section.fields.map(([key, label, { optional, options, ...props } = {}]) => (
        <label key={key} className={key === 'address' || key === 'permanent_address' ? 'span-2' : undefined}>
          <span>{label}{optional ? '' : ' *'}</span>
          {options ? (
            <select value={values[key] ?? ''} onChange={(e) => onChange({ ...values, [key]: e.target.value })}
              className={errors[key] ? 'invalid' : undefined} aria-invalid={errors[key] ? true : undefined}>
              <option value="">Choose…</option>
              {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          ) : (
          <input
            value={values[key] ?? ''}
            onChange={(e) => onChange({ ...values, [key]: e.target.value })}
            className={errors[key] ? 'invalid' : undefined}
            aria-invalid={errors[key] ? true : undefined}
            {...props}
          />
          )}
          {errors[key] && <span className="field-error">{label}: {errors[key]}</span>}
        </label>
      ))}
    </fieldset>
  )
}

export function ProfileFacts({ profile }) {
  return (
    <dl className="facts">
      {PROFILE_SECTIONS.flatMap((s) => s.fields).map(([key, label]) => (
        <div key={key} style={{ display: 'contents' }}>
          <dt>{label}</dt>
          <dd>{(profile[key] && optionLabel(key, profile[key])) || '—'}</dd>
        </div>
      ))}
    </dl>
  )
}
