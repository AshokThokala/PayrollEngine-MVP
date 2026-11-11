import { useCallback, useEffect, useState } from 'react'
import { api, loadSession, saveSession, whenLoggedOut } from './api.js'
import AuthScreen from './pages/AuthScreen.jsx'
import ClientsPage from './pages/ClientsPage.jsx'
import EmployeesPage from './pages/EmployeesPage.jsx'
import EmployeePortal from './pages/EmployeePortal.jsx'
import FilingsPage from './pages/FilingsPage.jsx'
import RulesPage from './pages/RulesPage.jsx'
import RunsPage from './pages/RunsPage.jsx'
import UsersPage from './pages/UsersPage.jsx'

export default function App() {
  const [session, setSession] = useState(() => loadSession())

  const logout = useCallback(() => {
    saveSession(null)
    setSession(null)
  }, [])

  useEffect(() => {
    whenLoggedOut(() => setSession(null))
  }, [])

  const onLoggedIn = (next) => {
    saveSession(next)
    setSession(next)
  }

  if (!session) return <AuthScreen onLoggedIn={onLoggedIn} />
  if (session.user.role === 'employee') return <EmployeePortal user={session.user} onLogout={logout} />
  return <AdminShell user={session.user} onLogout={logout} />
}

const NAV = [
  { id: 'clients', label: 'Clients', icon: '▦', platformOnly: true },
  { id: 'employees', label: 'Employees', icon: '☺', needsClient: true },
  { id: 'runs', label: 'Payroll runs', icon: '₹', needsClient: true },
  { id: 'filings', label: 'Compliance calendar', icon: '◷' },
  { id: 'users', label: 'Users and access', icon: '⚿' },
  { id: 'rules', label: 'Compliance rules', icon: '§', platformOnly: true },
]

function AdminShell({ user, onLogout }) {
  const platform = user.is_platform_admin
  const [clients, setClients] = useState([])
  const [clientId, setClientId] = useState(user.client_id || '')
  const [tab, setTab] = useState(platform ? 'clients' : 'employees')
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

  const client = clients.find((c) => c.id === clientId)
  const nav = NAV.filter((n) => platform || !n.platformOnly)

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="logo">C4U</span>
          <span>
            ClearPay4U
            <span className="tagline">zero-penalty payroll</span>
          </span>
        </div>
        <nav className="side-nav" aria-label="Main">
          {nav.map((n) => (
            <button
              key={n.id}
              className={tab === n.id ? 'nav-item active' : 'nav-item'}
              disabled={n.needsClient && !clientId}
              aria-current={tab === n.id ? 'page' : undefined}
              onClick={() => setTab(n.id)}
            >
              <span className="nav-icon" aria-hidden="true">{n.icon}</span>
              <span>{n.label}</span>
            </button>
          ))}
        </nav>
        <div className="side-footer">
          <div className="who">
            <span className="avatar" aria-hidden="true">{user.name.slice(0, 1).toUpperCase()}</span>
            <span>
              <strong>{user.name}</strong>
              <span className="muted small">{platform ? 'Platform admin' : 'Client admin'}</span>
            </span>
          </div>
          <button className="ghost" onClick={onLogout}>Log out</button>
        </div>
      </aside>

      <div className="main-col">
        <header className="topbar">
          <h1 className="page-title">{nav.find((n) => n.id === tab)?.label}</h1>
          {platform ? (
            <label className="field-inline">
              <span className="muted small">Client</span>
              <select value={clientId} onChange={(e) => setClientId(e.target.value)}>
                {clients.length === 0 && <option value="">No clients yet</option>}
                {clients.map((c) => (
                  <option key={c.id} value={c.id}>{c.legal_name} ({c.state})</option>
                ))}
              </select>
            </label>
          ) : (
            client && <span className="client-chip">{client.legal_name}</span>
          )}
        </header>

        {error && <div className="banner error">{error}</div>}

        <main>
          {tab === 'clients' && platform && (
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
          {tab === 'runs' && client && <RunsPage client={client} user={user.email} />}
          {tab === 'filings' && <FilingsPage clientId={clientId} clients={clients} canSeeAll={platform} />}
          {tab === 'users' && <UsersPage user={user} clients={clients} />}
          {tab === 'rules' && platform && <RulesPage />}
        </main>
      </div>
    </div>
  )
}
