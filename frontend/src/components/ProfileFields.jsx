// The joining form an employee fills in, grouped into steps. Shared by the portal and the admin review.
export const PROFILE_SECTIONS = [
  {
    id: 'personal',
    title: 'Personal and contact',
    fields: [
      ['phone', 'Mobile number', { inputMode: 'numeric', placeholder: '9876543210' }],
      ['date_of_birth', 'Date of birth', { type: 'date' }],
      ['address', 'Address', { placeholder: 'House no., street, area' }],
      ['city', 'City'],
      ['pincode', 'PIN code', { inputMode: 'numeric', placeholder: '500034' }],
      ['emergency_name', 'Emergency contact name'],
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
      {section.fields.map(([key, label, { optional, ...props } = {}]) => (
        <label key={key} className={key === 'address' ? 'span-2' : undefined}>
          <span>{label}{optional ? '' : ' *'}</span>
          <input
            value={values[key] ?? ''}
            onChange={(e) => onChange({ ...values, [key]: e.target.value })}
            className={errors[key] ? 'invalid' : undefined}
            aria-invalid={errors[key] ? true : undefined}
            {...props}
          />
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
          <dd>{profile[key] || '—'}</dd>
        </div>
      ))}
    </dl>
  )
}
