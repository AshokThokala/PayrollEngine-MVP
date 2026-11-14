import { useCallback, useEffect, useState } from 'react'
import { api, loadSession, saveSession, stashAdminSession, stashedAdminSession, whenLoggedOut } from './api.js'
import ClientSwitcher from './components/ClientSwitcher.jsx'
import GlobalSearch from './components/GlobalSearch.jsx'
import AuthScreen from './pages/AuthScreen.jsx'
import BillingPage from './pages/BillingPage.jsx'
import ClientOnboardingPage from './pages/ClientOnboardingPage.jsx'
import ClientsPage from './pages/ClientsPage.jsx'
import EmployeesPage from './pages/EmployeesPage.jsx'
import DeductionsPage from './pages/DeductionsPage.jsx'
import EmployeeOnboardingPage from './pages/EmployeeOnboardingPage.jsx'
import EmployeePortal from './pages/EmployeePortal.jsx'
import InviteRegistration from './pages/InviteRegistration.jsx'
import ReportsPage from './pages/ReportsPage.jsx'
import FilingsPage from './pages/FilingsPage.jsx'
import RulesPage from './pages/RulesPage.jsx'
import TaxRulesPage from './pages/TaxRulesPage.jsx'
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

  // An invite link (/invite/<token>) opens the registration page, even if someone is logged in.
  const inviteToken = window.location.pathname.match(/^\/invite\/([^/]+)/)?.[1]
  if (inviteToken) {
    return (
      <InviteRegistration
        token={decodeURIComponent(inviteToken)}
        onDone={(next) => {
          if (!next) {
            window.location.assign('/')
            return
          }
          window.history.replaceState(null, '', '/')
          stashAdminSession(null)
          onLoggedIn(next)
        }}
      />
    )
  }
  if (!session) return <AuthScreen onLoggedIn={onLoggedIn} />
  if (session.user.role === 'employee') {
    return <EmployeePortal user={session.user} onLogout={session.user.impersonated_by ? backToAdmin : logout} />
  }
  return <AdminShell user={session.user} onLogout={logout} onViewAs={viewAs} />
}

const NAV = [
  { id: 'clients', label: 'Clients', icon: '▦', platformOnly: true },
  { id: 'onboarding', label: 'Client onboarding', icon: '✓', needsClient: true },
  { id: 'employees', label: 'Employees', icon: '☺', needsClient: true },
  { id: 'employee-onboarding', label: 'Employee onboarding', icon: '✉', needsClient: true },
  { id: 'runs', label: 'Payroll runs', icon: '₹', needsClient: true },
  { id: 'filings', label: 'Compliance calendar', icon: '◷' },
  { id: 'reports', label: 'Reports', icon: '▤', needsClient: true },
  { id: 'users', label: 'Users and access', icon: '⚿' },
  { id: 'billing', label: 'Billing', icon: '◫', needsClient: true },
  { id: 'rules', label: 'Compliance rules', icon: '§', platformOnly: true },
  { id: 'tax', label: 'Tax rules', icon: '%' },
  { id: 'deductions', label: 'Deduction types', icon: '−' },
]

function AdminShell({ user, onLogout, onViewAs }) {
  const platform = user.is_platform_admin
  const [clients, setClients] = useState([])
  const [clientId, setClientId] = useState(user.client_id || '')
  const [tab, setTab] = useState(platform ? 'clients' : 'employees')
  const [error, setError] = useState('')
  const [openEmployee, setOpenEmployee] = useState(null) // from search: { code, n }
  const [ruleCategory, setRuleCategory] = useState(null) // Tax rules → open Compliance rules on a category

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
          <GlobalSearch
            platform={platform}
            onPickEmployee={(cid, code) => {
              setClientId(cid)
              setOpenEmployee({ clientId: cid, code, n: Date.now() })
              setTab('employees')
            }}
          />
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
            <EmployeesPage client={client} openRequest={openEmployee} onViewAs={(code) => onViewAs(client.id, code).catch((e) => setError(e.message))} />
          )}
          {tab === 'runs' && client && <RunsPage client={client} user={user.email} />}
          {tab === 'filings' && <FilingsPage clientId={clientId} clients={clients} canSeeAll={platform} />}
          {tab === 'reports' && client && <ReportsPage client={client} />}
          {tab === 'employee-onboarding' && client && <EmployeeOnboardingPage client={client} />}
          {tab === 'onboarding' && client && (
            <ClientOnboardingPage client={client} platform={platform} tabs={nav.map((n) => n.id)} onGo={setTab} onPickClient={setClientId} />
          )}
          {tab === 'billing' && client && (
            <BillingPage client={client} platform={platform} onPickClient={setClientId} />
          )}
          {tab === 'users' && <UsersPage user={user} clients={clients} />}
          {tab === 'rules' && platform && <RulesPage key={ruleCategory || 'all'} initialCategory={ruleCategory} />}
          {tab === 'deductions' && <DeductionsPage canEdit={platform} />}
          {tab === 'tax' && (
            <TaxRulesPage
              canEdit={platform}
              onEdit={(category) => {
                setRuleCategory(category)
                setTab('rules')
              }}
            />
          )}
        </main>
      </div>
    </div>
  )
}
