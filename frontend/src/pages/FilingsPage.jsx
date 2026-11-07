import { useCallback, useEffect, useState } from 'react'
import { api, money, today } from '../api.js'

const KIND_LABEL = {
  pf: 'PF (ECR + challan)',
  esi: 'ESI contribution',
  tds_deposit: 'TDS deposit',
  pt: 'Professional tax',
  lwf: 'Labour welfare fund',
  form_24q: 'Form 24Q (quarterly TDS return)',
}

export default function FilingsPage({ clientId, clients }) {
  const [allClients, setAllClients] = useState(false)
  const [filings, setFilings] = useState([])
  const [statusFilter, setStatusFilter] = useState('pending')
  const [refs, setRefs] = useState({})
  const [message, setMessage] = useState(null)

  const load = useCallback(async () => {
    try {
      setFilings(await api.listFilings(allClients ? null : clientId))
    } catch (err) {
      setMessage({ kind: 'error', text: err.message })
    }
  }, [clientId, allClients])

  useEffect(() => {
    load()
  }, [load])

  const name = (id) => clients.find((c) => c.id === id)?.legal_name || id
  const now = today()
  const shown = filings.filter((f) => statusFilter === 'all' || f.status === statusFilter)
  const overdueCount = filings.filter((f) => f.status === 'pending' && f.due_on < now).length

  const mark = async (f, status) => {
    try {
      await api.updateFiling(f.id, status, refs[f.id])
      setMessage({ kind: 'ok', text: `${KIND_LABEL[f.kind] || f.kind} for ${f.period} marked ${status}.` })
      load()
    } catch (err) {
      setMessage({ kind: 'error', text: err.message })
    }
  }

  return (
    <section className="card wide">
      <div className="run-head">
        <h2>Compliance calendar</h2>
        <div className="actions">
          <label className="check"><input type="checkbox" checked={allClients} onChange={(e) => setAllClients(e.target.checked)} /> All clients</label>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="pending">Pending</option>
            <option value="paid">Paid</option>
            <option value="filed">Filed</option>
            <option value="all">All</option>
          </select>
        </div>
      </div>
      {overdueCount > 0 && <div className="banner error">{overdueCount} pending item(s) are past their due date.</div>}
      {message && <div className={`banner ${message.kind}`}>{message.text}</div>}
      {shown.length === 0 ? (
        <p className="muted">Nothing here. Filings appear when a payroll run is locked.</p>
      ) : (
        <table>
          <thead>
            <tr><th>Due</th>{allClients && <th>Client</th>}<th>Filing</th><th>Period</th><th className="num">Amount</th><th>Status</th><th>Challan / ack ref</th><th></th></tr>
          </thead>
          <tbody>
            {shown.map((f) => {
              const overdue = f.status === 'pending' && f.due_on < now
              return (
                <tr key={f.id} className={overdue ? 'overdue' : ''}>
                  <td>{f.due_on}{overdue && <span className="tag error">overdue</span>}</td>
                  {allClients && <td>{name(f.client_id)}</td>}
                  <td>{KIND_LABEL[f.kind] || f.kind}</td>
                  <td>{f.period}</td>
                  <td className="num">{money(f.amount)}</td>
                  <td><span className={`tag ${f.status}`}>{f.status}</span></td>
                  <td>
                    {f.status === 'pending' ? (
                      <input placeholder="e.g. TRRN / CIN" value={refs[f.id] || ''}
                        onChange={(e) => setRefs({ ...refs, [f.id]: e.target.value })} />
                    ) : (f.challan_ref || '—')}
                  </td>
                  <td>
                    {f.status === 'pending' && (
                      <span className="inline">
                        {f.kind !== 'form_24q' && <button onClick={() => mark(f, 'paid')}>Paid</button>}
                        <button onClick={() => mark(f, 'filed')}>Filed</button>
                      </span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </section>
  )
}
