import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { PROFILE_KEYS, PROFILE_SECTIONS, ProfileForm, StageTag } from './ProfileFields.jsx'

// The employee's joining form: three steps, save as you go, then submit to the employer.
export default function MyOnboarding({ readOnly, onTaxStep }) {
  const [profile, setProfile] = useState(null)
  const [values, setValues] = useState({})
  const [step, setStep] = useState(0)
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState(null)
  const [open, setOpen] = useState(true)

  const apply = (p) => {
    setProfile(p)
    setValues(Object.fromEntries(PROFILE_KEYS.map((k) => [k, p[k] || ''])))
  }

  useEffect(() => {
    api.myOnboarding().then((p) => {
      apply(p)
      setOpen(p.status !== 'verified')
    }).catch((e) => setMessage({ kind: 'error', text: e.message }))
  }, [])

  if (!profile) return message ? <div className={`banner ${message.kind}`}>{message.text}</div> : null

  const locked = readOnly || ['submitted', 'verified'].includes(profile.status)
  const filled = (s) => s.fields.every(([k, , o = {}]) => o.optional || values[k])

  async function save(submit) {
    setErrors({})
    try {
      const p = await api.saveMyOnboarding({ ...values, submit })
      apply(p)
      setMessage({ kind: 'ok', text: submit ? 'Submitted. Your employer will check your details.' : 'Saved.' })
      if (!submit && step < PROFILE_SECTIONS.length) setStep(step + 1)
    } catch (err) {
      const fe = err.fieldErrors || {}
      setErrors(fe)
      setMessage({ kind: 'error', text: err.message })
      const first = PROFILE_SECTIONS.findIndex((s) => s.fields.some(([k]) => fe[k]))
      if (first >= 0) setStep(first)
    }
  }

  const steps = [...PROFILE_SECTIONS.map((s) => s.title), 'Tax and submit']

  return (
    <section className="card onboarding-card">
      <div className="run-head">
        <div>
          <h2>Joining details</h2>
          <p className="muted small">
            {{
              draft: 'Fill these in so your employer can pay your salary and file PF, ESI and TDS for you.',
              returned: 'Your employer asked for a change — see the note below.',
              submitted: 'Submitted. Your employer is checking your details.',
              verified: 'Verified by your employer. Ask them if anything changes.',
            }[profile.status]}
          </p>
        </div>
        <div className="actions">
          <StageTag stage={profile.status} />
          <button className="link" onClick={() => setOpen(!open)}>{open ? 'Hide' : 'Show'}</button>
        </div>
      </div>
      {open && (
        <>
          {profile.status === 'returned' && profile.note && <div className="banner warn">From your employer: {profile.note}</div>}
          {message && <div className={`banner ${message.kind}`}>{message.text}</div>}
          <ol className="stepper">
            {steps.map((t, i) => (
              <li key={t} className={i === step ? 'current' : i < PROFILE_SECTIONS.length && filled(PROFILE_SECTIONS[i]) ? 'done' : ''}>
                <button type="button" onClick={() => setStep(i)}>
                  <span className="step-no">{i < PROFILE_SECTIONS.length && filled(PROFILE_SECTIONS[i]) ? '✓' : i + 1}</span>
                  <span>{t}</span>
                </button>
              </li>
            ))}
          </ol>
          {step < PROFILE_SECTIONS.length ? (
            <form className="form" onSubmit={(e) => { e.preventDefault(); save(false) }}>
              <ProfileForm section={PROFILE_SECTIONS[step]} values={values} onChange={setValues} errors={errors} disabled={locked} />
              {PROFILE_SECTIONS[step].id === 'statutory' && (
                <p className="muted small">Your PAN and bank account number are stored encrypted.</p>
              )}
              {!locked && <div className="actions"><button className="primary">Save and continue</button></div>}
            </form>
          ) : (
            <div className="form">
              <p>
                Choose your income tax regime and declare your savings in <strong>Income tax declarations</strong>{' '}
                {onTaxStep && <button className="link" onClick={onTaxStep}>(go there)</button>}. You can change them later.
              </p>
              {!locked && (
                <div className="actions">
                  <button className="primary" onClick={() => save(true)}>Submit to employer</button>
                  <span className="muted small">Everything marked * is needed.</span>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </section>
  )
}
