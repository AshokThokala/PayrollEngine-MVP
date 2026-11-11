import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, today } from '../api.js'
import InfoTip from '../components/InfoTip.jsx'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const inr = new Intl.NumberFormat('en-IN')

// ---- converting between stored values and what the form shows ----------------

function pct(v) {
  return Number((Number(v) * 100).toFixed(6)).toString()
}

function toDisplay(type, value) {
  if (value === undefined || value === null) return type.endsWith('slabs') ? [] : ''
  switch (type) {
    case 'percent': return pct(value)
    case 'months':
    case 'text_list': return value.join(', ')
    case 'amount_slabs':
      return value.map((s) => ({ upto: s.upto === null ? '' : String(s.upto), value: String(s.amount) }))
    case 'rate_slabs':
      return value.map((s) => ({ upto: s.upto === null ? '' : String(s.upto), value: pct(s.rate) }))
    default: return String(value)
  }
}

function toParam(type, display) {
  const num = (v) => (v === '' || v === undefined ? '' : Number(v))
  switch (type) {
    case 'percent': return display === '' ? '' : Number((Number(display) / 100).toFixed(8))
    case 'mmdd': return display.trim()
    case 'months': return display.split(',').map((x) => x.trim()).filter(Boolean).map(Number)
    case 'text_list': return display.split(',').map((x) => x.trim()).filter(Boolean)
    case 'amount_slabs':
    case 'rate_slabs': {
      const key = type === 'rate_slabs' ? 'rate' : 'amount'
      return display.map((row, i) => ({
        upto: i === display.length - 1 ? null : num(row.upto),
        [key]: key === 'rate' ? (row.value === '' ? '' : Number((Number(row.value) / 100).toFixed(8))) : num(row.value),
      }))
    }
    default: return num(display)
  }
}

function summary(type, value) {
  if (value === undefined || value === null) return '—'
  switch (type) {
    case 'percent': return `${pct(value)}%`
    case 'money': return `₹${inr.format(value)}`
    case 'months': return value.map((m) => MONTHS[m - 1]).join(', ')
    case 'text_list': return value.join(', ')
    case 'amount_slabs':
    case 'rate_slabs':
      return value.map((s, i) => {
        const v = type === 'rate_slabs' ? `${pct(s.rate)}%` : `₹${inr.format(s.amount)}`
        if (s.upto === null) return `above ₹${inr.format(value[i - 1]?.upto ?? 0)}: ${v}`
        return `up to ₹${inr.format(s.upto)}: ${v}`
      }).join(' · ')
    default: return String(value)
  }
}

// ---- page ------------------------------------------------------------------------

export default function RulesPage({ initialCategory }) {
  const [categories, setCategories] = useState([])
  const [states, setStates] = useState([])
  const [rules, setRules] = useState([])
  const [filter, setFilter] = useState('all')
  const [category, setCategory] = useState(initialCategory || 'pf')
  const [scope, setScope] = useState('central')
  const [validFrom, setValidFrom] = useState(today())
  const [values, setValues] = useState({})
  const [source, setSource] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(null) // a rule version being corrected

  const load = useCallback(async () => {
    try {
      const [c, st, r] = await Promise.all([api.listRuleCategories(), api.listRuleStates(), api.listRules()])
      setCategories(c)
      setStates(st)
      setRules(r)
    } catch (err) {
      setMessage({ kind: 'error', text: err.message })
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const spec = categories.find((c) => c.category === category)
  const stateName = (code) => states.find((s) => s.code === code)?.name || code

  // Start the form from the latest version of the same rule, if there is one.
  const latest = useMemo(
    () => rules.filter((r) => r.category === category && r.scope === scope)
      .sort((a, b) => b.valid_from.localeCompare(a.valid_from))[0],
    [rules, category, scope],
  )
  const base = editing || latest
  useEffect(() => {
    if (!spec) return
    const v = {}
    spec.fields.forEach((f) => {
      v[f.key] = toDisplay(f.type, base?.params[f.key])
      if (f.type.endsWith('slabs') && v[f.key].length === 0) v[f.key] = [{ upto: '', value: '' }]
    })
    setValues(v)
    setFieldErrors({})
  }, [spec, base])

  const startEdit = (rule) => {
    setEditing(rule)
    setCategory(rule.category)
    setScope(rule.scope)
    setValidFrom(rule.valid_from)
    setSource(rule.source)
    setMessage(null)
  }

  const cancelEdit = () => {
    setEditing(null)
    setSource('')
    setValidFrom(today())
  }

  const chooseCategory = (c) => {
    setCategory(c)
    const s = categories.find((x) => x.category === c)
    setScope(s?.scope === 'central' ? 'central' : 'TG')
  }

  const setValue = (key, v) => {
    setValues({ ...values, [key]: v })
    if (fieldErrors[key]) setFieldErrors({ ...fieldErrors, [key]: undefined })
  }

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setFieldErrors({})
    const params = {}
    spec.fields.forEach((f) => { params[f.key] = toParam(f.type, values[f.key]) })
    try {
      if (editing) {
        await api.editRule(editing.id, { params, source })
        setMessage({ kind: 'ok', text: `Updated ${spec.label} version from ${editing.valid_from}. Drafts calculated from now on use the new values; locked runs keep theirs.` })
        setEditing(null)
        setSource('')
        setValidFrom(today())
        load()
        return
      }
      const res = await api.createRule({ scope, category, valid_from: validFrom, params, source })
      setMessage({
        kind: 'ok',
        text: `Saved ${spec.label} for ${scope === 'central' ? 'all India' : stateName(scope)} from ${res.rule.valid_from}.`
          + (res.closed ? ` The previous version (from ${res.closed.valid_from}) now ends on ${res.closed.valid_to}.` : ''),
      })
      setSource('')
      load()
    } catch (err) {
      setFieldErrors(err.fieldErrors || {})
      setMessage({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  const grouped = useMemo(() => {
    const shown = rules.filter((r) => filter === 'all' || r.scope === filter)
    const groups = {}
    shown.forEach((r) => {
      const key = `${r.category}|${r.scope}`
      ;(groups[key] = groups[key] || []).push(r)
    })
    return Object.entries(groups).map(([key, versions]) => ({
      key,
      versions: versions.sort((a, b) => b.valid_from.localeCompare(a.valid_from)),
    }))
  }, [rules, filter])

  const scopes = ['central', ...new Set(rules.filter((r) => r.scope !== 'central').map((r) => r.scope))]

  return (
    <div className="grid">
      <section className="card">
        <div className="run-head">
          <h2>Compliance rules</h2>
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">All</option>
            {scopes.map((s) => <option key={s} value={s}>{s === 'central' ? 'Central' : stateName(s)}</option>)}
          </select>
        </div>
        <p className="muted small">Each rule has dated versions. Payroll uses the version in force on the last day of the pay month; locked runs keep the values they were calculated with.</p>
        {grouped.map(({ key, versions }) => {
          const cat = categories.find((c) => c.category === versions[0].category)
          return (
            <div key={key} className="rule-group">
              <h3>{versions[0].category_label} <span className="tag">{versions[0].scope === 'central' ? 'Central' : stateName(versions[0].scope)}</span></h3>
              {versions.map((r) => (
                <div key={r.id} className={r.valid_to ? 'rule-version dim' : 'rule-version'}>
                  <div className="rule-dates">
                    {r.valid_from} → {r.valid_to || <span className="tag locked">in force</span>}
                  </div>
                  <ul className="rule-values">
                    {(cat?.fields || []).map((f) => (
                      <li key={f.key}><span className="muted">{f.label}:</span> {summary(f.type, r.params[f.key])}</li>
                    ))}
                  </ul>
                  <div className="muted small">
                    Source: {r.source || '—'} · added by {r.created_by}
                    {' · '}<button type="button" className="link" onClick={() => startEdit(r)}>Edit</button>
                  </div>
                </div>
              ))}
            </div>
          )
        })}
      </section>

      <section className="card allow-overflow">
        <h2>{editing ? 'Edit rule version' : 'Add rule version'}</h2>
        {editing && (
          <div className="banner warn">
            Correcting the version that starts {editing.valid_from}. Use this to fix a mistake.
            For a change in the law from a new date, add a new version instead.
            {' '}<button type="button" className="link" onClick={cancelEdit}>Cancel editing</button>
          </div>
        )}
        {message && <div className={`banner ${message.kind}`}>{message.text}</div>}
        {spec && (
          <form onSubmit={submit} className="form">
            <label>Rule type
              <select value={category} onChange={(e) => chooseCategory(e.target.value)} disabled={!!editing}>
                {categories.map((c) => <option key={c.category} value={c.category}>{c.label}</option>)}
              </select>
            </label>
            <div className="row">
              <label>Applies to
                {spec.scope === 'central' ? (
                  <input value="All India (central)" disabled />
                ) : (
                  <select value={scope} onChange={(e) => setScope(e.target.value)} disabled={!!editing}>
                    {states.map((s) => <option key={s.code} value={s.code}>{s.name}{s.supported ? '' : ' (no rules yet)'}</option>)}
                  </select>
                )}
                {fieldErrors.scope && <span className="field-error">{fieldErrors.scope}</span>}
              </label>
              <label>Effective from
                <input type="date" required value={validFrom} onChange={(e) => setValidFrom(e.target.value)} disabled={!!editing}
                  className={fieldErrors.valid_from ? 'invalid' : undefined} />
                {fieldErrors.valid_from && <span className="field-error">Effective from: {fieldErrors.valid_from}</span>}
              </label>
            </div>
            <p className="muted small">
              {editing
                ? `Dates stay ${editing.valid_from} → ${editing.valid_to || 'in force'}; only the values and source change.`
                : latest
                  ? `Pre-filled from the version in force since ${latest.valid_from}. It will end the day before your new date.`
                  : 'No earlier version for this rule — this will be the first.'}
            </p>

            {spec.fields.map((f) => (
              <RuleField key={f.key} field={f} value={values[f.key] ?? ''} error={fieldErrors[f.key]}
                onChange={(v) => setValue(f.key, v)} />
            ))}

            <label>
              <span className="label-text">Source<InfoTip id="tip-source" text="Notification, circular, G.O. or section of the act this version comes from, so it can be verified later." /></span>
              <input value={source} onChange={(e) => setSource(e.target.value)} className={fieldErrors.source ? 'invalid' : undefined} />
              {fieldErrors.source && <span className="field-error">Source: {fieldErrors.source}</span>}
            </label>
            <button className="primary" disabled={busy}>{busy ? 'Saving…' : editing ? 'Save changes' : 'Save rule version'}</button>
          </form>
        )}
      </section>
    </div>
  )
}

function RuleField({ field, value, error, onChange }) {
  const tipId = `tip-rule-${field.key}`
  const cls = error ? 'invalid' : undefined
  let input
  if (field.type.endsWith('slabs')) {
    const isRate = field.type === 'rate_slabs'
    const rows = Array.isArray(value) ? value : []
    const update = (i, key, v) => onChange(rows.map((r, j) => (j === i ? { ...r, [key]: v } : r)))
    input = (
      <table className="compact slabs">
        <thead><tr><th>Up to (₹)</th><th>{isRate ? 'Rate (%)' : 'Amount (₹)'}</th><th></th></tr></thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              <td>{i === rows.length - 1
                ? <span className="muted">No limit</span>
                : <input type="number" min="0" step="any" value={row.upto} onChange={(e) => update(i, 'upto', e.target.value)} />}</td>
              <td><input type="number" min="0" step="any" value={row.value} onChange={(e) => update(i, 'value', e.target.value)} /></td>
              <td>{rows.length > 1 && <button type="button" className="link" onClick={() => onChange(rows.filter((_, j) => j !== i))}>Remove</button>}</td>
            </tr>
          ))}
        </tbody>
        <tfoot><tr><td colSpan={3}>
          <button type="button" onClick={() => onChange([...rows.slice(0, -1), { upto: '', value: '' }, ...rows.slice(-1)])}>Add slab</button>
        </td></tr></tfoot>
      </table>
    )
  } else if (field.type === 'percent') {
    input = <span className="inline"><input type="number" min="0" max="100" step="any" value={value} onChange={(e) => onChange(e.target.value)} className={cls} /> %</span>
  } else if (['money', 'integer', 'day', 'month'].includes(field.type)) {
    input = <input type="number" min="0" step="any" value={value} onChange={(e) => onChange(e.target.value)} className={cls} />
  } else {
    const hint = { mmdd: 'MM-DD, e.g. 04-30', months: 'Month numbers, comma-separated, e.g. 6, 12', text_list: 'Comma-separated' }[field.type]
    input = <input value={value} placeholder={hint} onChange={(e) => onChange(e.target.value)} className={cls} />
  }
  return (
    <label>
      <span className="label-text">{field.label}<InfoTip id={tipId} text={field.help} /></span>
      {input}
      {error && <span className="field-error">{field.label}: {error}</span>}
    </label>
  )
}
