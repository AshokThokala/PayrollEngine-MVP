import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, today } from '../api.js'
import InfoTip from '../components/InfoTip.jsx'

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
  const [open, setOpen] = useState(null) // rule group (category|scope) open in the editor

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

  // Click a rule: open its version in force (or latest) in the editor, like clients and employees.
  const openRule = (key, version) => {
    setOpen(key)
    startEdit(version)
  }

  // New version of the open rule from a later date, pre-filled from its latest version.
  const addVersionOfOpen = () => {
    cancelEdit()
    setMessage(null)
  }

  const startAdd = () => {
    setOpen(null)
    cancelEdit()
    setMessage(null)
  }

  const openVersions = useMemo(
    () => (open ? rules.filter((r) => `${r.category}|${r.scope}` === open).sort((a, b) => b.valid_from.localeCompare(a.valid_from)) : []),
    [rules, open],
  )

  // Opened from the Tax rules page on a category: open that rule once rules have loaded.
  const opened = useRef(false)
  useEffect(() => {
    if (!initialCategory || opened.current || rules.length === 0) return
    const versions = rules.filter((r) => r.category === initialCategory && r.scope === 'central')
      .sort((a, b) => b.valid_from.localeCompare(a.valid_from))
    if (versions.length) {
      opened.current = true
      openRule(`${initialCategory}|central`, versions.find((v) => !v.valid_to) || versions[0])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialCategory, rules])

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
        const updated = await api.editRule(editing.id, { params, source })
        setMessage({ kind: 'ok', text: `Updated ${spec.label} version from ${editing.valid_from}. Drafts calculated from now on use the new values; locked runs keep theirs.` })
        setEditing(updated)
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
      await load()
      setOpen(`${res.rule.category}|${res.rule.scope}`)
      setEditing(res.rule)
      setValidFrom(res.rule.valid_from)
      setSource(res.rule.source)
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
          <div className="actions">
            <button className="primary" onClick={startAdd}>+ Add rule version</button>
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">All</option>
            {scopes.map((s) => <option key={s} value={s}>{s === 'central' ? 'Central' : stateName(s)}</option>)}
          </select>
          </div>
        </div>
        <div className="table-wrap">
          <table className="clickable compact-list">
            <thead><tr><th>Rule</th><th>Scope</th><th>In force since</th><th className="num">Versions</th></tr></thead>
            <tbody>
              {grouped.map(({ key, versions }) => {
                const current = versions.find((v) => !v.valid_to) || versions[0]
                return (
                  <tr key={key} className={open === key ? 'selected' : undefined} tabIndex={0}
                      onClick={() => openRule(key, current)}
                      onKeyDown={(e) => e.key === 'Enter' && openRule(key, current)}>
                    <td>{versions[0].category_label}</td>
                    <td>{versions[0].scope === 'central' ? 'Central' : stateName(versions[0].scope)}</td>
                    <td>{current.valid_from}</td>
                    <td className="num">{versions.length}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card allow-overflow">
        <div className="run-head">
          <h2>{editing ? editing.category_label || spec?.label : open ? `New version: ${spec?.label || ''}` : 'Add rule version'}</h2>
          {open && <button onClick={() => { setOpen(null); cancelEdit(); setMessage(null) }}>Close</button>}
        </div>
        {open && openVersions.length > 0 && (
          <div className="version-tabs" role="tablist" aria-label="Versions">
            {openVersions.map((v) => (
              <button key={v.id} role="tab" aria-selected={editing?.id === v.id}
                className={editing?.id === v.id ? 'active' : ''} onClick={() => startEdit(v)}>
                {v.valid_from}{v.valid_to ? '' : ' · in force'}
              </button>
            ))}
            <button role="tab" aria-selected={!editing} className={!editing ? 'active' : ''} onClick={addVersionOfOpen}>+ New version</button>
          </div>
        )}
        {editing && (
          <p className="muted small">
            Editing corrects this version (from {editing.valid_from}). For a change in the law from a new date, use <em>+ New version</em>.
          </p>
        )}
        {message && <div className={`banner ${message.kind}`}>{message.text}</div>}
        {spec && (
          <form onSubmit={submit} className="form">
            <label>Rule type
              <select value={category} onChange={(e) => chooseCategory(e.target.value)} disabled={!!editing || !!open}>
                {categories.map((c) => <option key={c.category} value={c.category}>{c.label}</option>)}
              </select>
            </label>
            <div className="row">
              <label>Applies to
                {spec.scope === 'central' ? (
                  <input value="All India (central)" disabled />
                ) : (
                  <select value={scope} onChange={(e) => setScope(e.target.value)} disabled={!!editing || !!open}>
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
