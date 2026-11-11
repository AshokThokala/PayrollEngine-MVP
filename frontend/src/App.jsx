import { useCallback, useEffect, useState } from 'react'
import { api, loadSession, saveSession, stashAdminSession, stashedAdminSession, whenLoggedOut } from './api.js'
import ClientSwitcher from './components/ClientSwitcher.jsx'
import AuthScreen from './pages/AuthScreen.jsx'
import ClientsPage from './pages/ClientsPage.jsx'
import EmployeesPage from './pages/EmployeesPage.jsx'
import EmployeePortal from './pages/EmployeePortal.jsx'
import ReportsPage from './pages/ReportsPage.jsx'
import FilingsPage from './pages/FilingsPage.jsx'
import RulesPage from './pages/RulesPage.jsx'
import RunsPage from './pages/RunsPage.jsx'
import UsersPage from './pages/UsersPage.jsx'

export default function App() {
  const [session, setSession] = useState(() => loadSession())

  const logout = useCallback(() => {
    saveSession(null)
    stashAdminSession(null)
    setSession(null)
  }, [])

  useEffect(() => {
    whenLoggedOut(() => setSession(null))
  }, [])

  const onLoggedIn = (next) => {
    saveSession(next)
    setSession(next)
  }

  // "View as employee": keep the admin's session aside, show the portal with a read-only session.
  const viewAs = async (clientId, code) => {
    const viewing = await api.viewAs(clientId, code)
    stashAdminSession(session)
    onLoggedIn(viewing)
  }

  const backToAdmin = () => {
    const admin = stashedAdminSession()
    stashAdminSession(null)
    if (admin) onLoggedIn(admin)
    else logout()
  }

  if (!session) return <AuthScreen onLoggedIn={onLoggedIn} />
  if (session.user.role === 'employee') {
    return <EmployeePortal user={session.user} onLogout={session.user.impersonated_by ? backToAdmin : logout} />
  }
  return <AdminShell user={session.user} onLogout={logout} onViewAs={viewAs} />
}

const NAV = [
  { id: 'clients', label: 'Clients', icon: '▦', platformOnly: true },
  { id: 'employees', label: 'Employees', icon: '☺', needsClient: true },
  { id: 'runs', label: 'Payroll runs', icon: '₹', needsClient: true },
  { id: 'filings', label: 'Compliance calendar', icon: '◷' },
  { id: 'reports', label: 'Reports', icon: '▤', needsClient: true },
  { id: 'users', label: 'Users and access', icon: '⚿' },
  { id: 'rules', label: 'Compliance rules', icon: '§', platformOnly: true },
]

function AdminShell({ user, onLogout, onViewAs }) {
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
          {platform && clients.length > 0 ? (
            <ClientSwitcher clients={clients} value={clientId} onChange={setClientId} />
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
              onUpdated={loadClients}
            />
          )}
          {tab === 'employees' && client && (
            <EmployeesPage client={client} onViewAs={(code) => onViewAs(client.id, code).catch((e) => setError(e.message))} />
          )}
          {tab === 'runs' && client && <RunsPage client={client} user={user.email} />}
          {tab === 'filings' && <FilingsPage clientId={clientId} clients={clients} canSeeAll={platform} />}
          {tab === 'reports' && client && <ReportsPage client={client} />}
          {tab === 'users' && <UsersPage user={user} clients={clients} />}
          {tab === 'rules' && platform && <RulesPage />}
        </main>
      </div>
    </div>
  )
}
