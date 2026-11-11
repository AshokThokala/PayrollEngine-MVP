import { useCallback, useEffect, useState } from 'react'
import { api, money } from '../api.js'

const thisMonth = () => new Date().toISOString().slice(0, 7)
const currentFy = () => {
  const d = new Date()
  return d.getMonth() >= 3 ? d.getFullYear() : d.getFullYear() - 1
}

function cell(col, value) {
  if (value === null || value === undefined || value === '') return '—'
  if (col.type === 'money') return money(value)
  if (col.type === 'status') {
    const kind = { overdue: 'error', paid: 'paid', filed: 'filed', locked: 'locked', approved: 'approved', draft: 'draft' }[value] || 'pending'
    return <span className={`tag ${kind}`}>{value}</span>
  }
  return String(value)
}

function toCsv(report) {
  const esc = (v) => {
    const s = v === null || v === undefined ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const head = report.columns.map((c) => esc(c.label)).join(',')
  const rows = report.rows.map((r) => report.columns.map((c) => esc(r[c.key])).join(','))
  return [head, ...rows].join('\n')
}

export default function ReportsPage({ client }) {
  const [catalog, setCatalog] = useState([])
  const [key, setKey] = useState('salary_register')
  const [month, setMonth] = useState(thisMonth())
  const [fy, setFy] = useState(currentFy())
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api.reportCatalog().then(setCatalog).catch((e) => setError(e.message))
  }, [])

  const spec = catalog.find((r) => r.key === key)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setReport(await api.getReport(client.id, key, { month: `${month}-01`, fy }))
    } catch (e) {
      setError(e.message)
      setReport(null)
    } finally {
      setLoading(false)
    }
  }, [client.id, key, month, fy])

  useEffect(() => {
    load()
  }, [load])

  const download = () => {
    const blob = new Blob([toCsv(report)], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${client.id}-${key}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const chart = report?.chart
  const max = chart ? Math.max(1, ...report.rows.map((r) => Number(r[chart.y]) || 0)) : 1

  return (
    <div className="reports">
      <aside className="card report-list">
        <h2>Reports</h2>
        <ul className="list">
          {catalog.map((r) => (
            <li key={r.key}>
              <button className={key === r.key ? 'list-item report-item active' : 'list-item report-item'} onClick={() => setKey(r.key)}>
                <strong>{r.title}</strong>
                <span className="muted small">{r.description}</span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="card">
        <div className="run-head">
          <div>
            <h2>{report?.title || spec?.title || 'Report'}</h2>
            {report?.subtitle && <p className="muted small">{report.subtitle}</p>}
          </div>
          <div className="actions">
            {spec?.params.includes('month') && (
              <label className="field-inline"><span className="muted small">Month</span>
                <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} /></label>
            )}
            {spec?.params.includes('fy') && (
              <label className="field-inline"><span className="muted small">Financial year</span>
                <select value={fy} onChange={(e) => setFy(Number(e.target.value))}>
                  {[0, 1, 2, 3].map((i) => currentFy() - i).map((y) => (
                    <option key={y} value={y}>{y}-{String(y + 1).slice(2)}</option>
                  ))}
                </select></label>
            )}
            <button onClick={download} disabled={!report || report.rows.length === 0}>Download CSV</button>
          </div>
        </div>

        {error && <div className="banner error">{error}</div>}
        {loading && <p className="muted">Loading…</p>}

        {report && chart && report.rows.length > 0 && (
          <div className="bars" role="img" aria-label={`${report.title}: employer cost by month`}>
            {report.rows.map((r) => (
              <div key={r[chart.x]} className="bar-col" title={`${r[chart.x]}: ${money(r[chart.y])}`}>
                <div className="bar" style={{ height: `${(Number(r[chart.y]) / max) * 100}%` }} />
                <span className="bar-label">{r[chart.x]}</span>
              </div>
            ))}
          </div>
        )}

        {report && (report.rows.length === 0 ? (
          <p className="muted">No data for this selection yet.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr>{report.columns.map((c) => (
                <th key={c.key} className={c.type === 'money' || c.type === 'number' ? 'num' : ''}>{c.label}</th>
              ))}</tr></thead>
              <tbody>
                {report.rows.map((r, i) => (
                  <tr key={i}>{report.columns.map((c) => (
                    <td key={c.key} className={c.type === 'money' || c.type === 'number' ? 'num' : ''}>{cell(c, r[c.key])}</td>
                  ))}</tr>
                ))}
              </tbody>
              {Object.keys(report.totals || {}).length > 0 && (
                <tfoot><tr>{report.columns.map((c, i) => (
                  <td key={c.key} className={c.type === 'money' || c.type === 'number' ? 'num' : ''}>
                    {i === 0 ? <strong>Total</strong> : report.totals[c.key] !== undefined ? <strong>{cell(c, report.totals[c.key])}</strong> : ''}
                  </td>
                ))}</tr></tfoot>
              )}
            </table>
          </div>
        ))}
      </section>
    </div>
  )
}
