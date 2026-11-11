import { useCallback, useEffect, useState } from 'react'
import { api, getUser, setUser } from './api.js'
import ClientsPage from './pages/ClientsPage.jsx'
import EmployeesPage from './pages/EmployeesPage.jsx'
import RunsPage from './pages/RunsPage.jsx'
import FilingsPage from './pages/FilingsPage.jsx'

const TABS = [
  { id: 'clients', label: 'Clients' },
  { id: 'employees', label: 'Employees', needsClient: true },
  { id: 'runs', label: 'Payroll runs', needsClient: true },
  { id: 'filings', label: 'Compliance calendar' },
]

export default function App() {
  const [clients, setClients] = useState([])
  const [clientId, setClientId] = useState('')
  const [tab, setTab] = useState('clients')
  const [user, setUserState] = useState(getUser())
  const [error, setError] = useState('')

  const loadClients = useCallback(async () => {
    try {
      const list = await api.listClients()
      setClients(list)
      setClientId((current) => current || (list[0] && list[0].id) || '')
      setError('')
    } catch (e) {
      setError(`Cannot reach the API: ${e.message}`)
    }
  }, [])

  useEffect(() => {
    loadClients()
  }, [loadClients])

  const changeUser = (name) => {
    setUserState(name)
    setUser(name)
  }

  const client = clients.find((c) => c.id === clientId)

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          ClearPay4U <span className="tagline">zero-penalty payroll</span>
        </div>
        <label className="field-inline">
          Client
          <select value={clientId} onChange={(e) => setClientId(e.target.value)}>
            {clients.length === 0 && <option value="">No clients yet</option>}
            {clients.map((c) => (
              <option key={c.id} value={c.id}>
                {c.legal_name} ({c.state})
              </option>
            ))}
          </select>
        </label>
        <label className="field-inline" title="Placeholder sign-in: actions are recorded under this name">
          Acting as
          <input value={user} onChange={(e) => changeUser(e.target.value)} size={10} />
        </label>
      </header>

      <nav className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={tab === t.id ? 'tab active' : 'tab'}
            disabled={t.needsClient && !clientId}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {error && <div className="banner error">{error}</div>}

      <main>
        {tab === 'clients' && (
          <ClientsPage
            clients={clients}
            onCreated={async (id) => {
              await loadClients()
              setClientId(id)
            }}
            onOpen={(id) => {
              setClientId(id)
              setTab('employees')
            }}
          />
        )}
        {tab === 'employees' && client && <EmployeesPage client={client} />}
        {tab === 'runs' && client && <RunsPage client={client} user={user} />}
        {tab === 'filings' && <FilingsPage clientId={clientId} clients={clients} />}
      </main>
    </div>
  )
}
