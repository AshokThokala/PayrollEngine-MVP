import { useCallback, useEffect, useState } from 'react'
import { api, loadSession, saveSession, stashAdminSession, stashedAdminSession, whenLoggedOut } from './api.js'
import ChangePassword from './components/ChangePassword.jsx'
import ClientSwitcher from './components/ClientSwitcher.jsx'
import GlobalSearch from './components/GlobalSearch.jsx'
import AuthScreen from './pages/AuthScreen.jsx'
import BillingPage from './pages/BillingPage.jsx'
import ClientOnboardingPage from './pages/ClientOnboardingPage.jsx'
import ClientsPage from './pages/ClientsPage.jsx'
import EmployeesPage from './pages/EmployeesPage.jsx'
import ClientDeductionsPage from './pages/ClientDeductionsPage.jsx'
import ClientPayCodesPage from './pages/ClientPayCodesPage.jsx'
import EmployeePayPage from './pages/EmployeePayPage.jsx'
import PayCodesPage from './pages/PayCodesPage.jsx'
import DeductionsPage from './pages/DeductionsPage.jsx'
import EmployeeDeductionsPage from './pages/EmployeeDeductionsPage.jsx'
import EmployeeOnboardingPage from './pages/EmployeeOnboardingPage.jsx'
import EmployeePortal from './pages/EmployeePortal.jsx'
import InviteRegistration from './pages/InviteRegistration.jsx'
import ReportsPage from './pages/ReportsPage.jsx'
import FilingsPage from './pages/FilingsPage.jsx'
import RulesPage from './pages/RulesPage.jsx'
import TaxRulesPage from './pages/TaxRulesPage.jsx'
import TimeEntryPage from './pages/TimeEntryPage.jsx'
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

// Pages (each has an id used for navigation), grouped into menu items by what they're for.
// A menu item with several pages shows them as tabs at the top of the page.
const PAGES = {
  clients: { label: 'Clients', platformOnly: true },
  onboarding: { label: 'Client', needsClient: true },
  'employee-onboarding': { label: 'Employees', needsClient: true },
  billing: { label: 'Billing', needsClient: true },
  employees: { label: 'Employees', needsClient: true },
  'employee-pay': { label: 'Employee pay', needsClient: true },
  'client-paycodes': { label: 'Client pay codes', needsClient: true },
  paycodes: { label: 'Master list', platformOnly: true },
  'employee-deductions': { label: 'Employee deductions', needsClient: true },
  'client-deductions': { label: 'Client deductions', needsClient: true },
  deductions: { label: 'Master list', platformOnly: true },
  time: { label: 'Time entry', needsClient: true },
  runs: { label: 'Payroll runs', needsClient: true },
  reports: { label: 'Reports', needsClient: true },
  filings: { label: 'Compliance calendar' },
  tax: { label: 'Tax rules' },
  rules: { label: 'Compliance rules', platformOnly: true },
  users: { label: 'Users and access' },
}

const MENU = [
  { group: 'Clients', items: [
    { id: 'm-clients', label: 'Clients', icon: '▦', pages: ['clients'] },
    { id: 'm-onboarding', label: 'Onboarding', icon: '✓', pages: ['onboarding', 'employee-onboarding'] },
    { id: 'm-billing', label: 'Billing', icon: '◫', pages: ['billing'] },
  ] },
  { group: 'People', items: [
    { id: 'm-employees', label: 'Employees', icon: '☺', pages: ['employees'] },
    { id: 'm-pay', label: 'Pay codes', icon: '⊕', pages: ['employee-pay', 'client-paycodes', 'paycodes'] },
    { id: 'm-deductions', label: 'Deductions', icon: '⊖', pages: ['employee-deductions', 'client-deductions', 'deductions'] },
  ] },
  { group: 'Payroll', items: [
    { id: 'm-time', label: 'Time entry', icon: '◴', pages: ['time'] },
    { id: 'm-runs', label: 'Payroll runs', icon: '₹', pages: ['runs'] },
    { id: 'm-reports', label: 'Reports', icon: '▤', pages: ['reports'] },
  ] },
  { group: 'Compliance', items: [
    { id: 'm-calendar', label: 'Compliance calendar', icon: '◷', pages: ['filings'] },
    { id: 'm-rules', label: 'Tax and rules', icon: '§', pages: ['tax', 'rules'] },
  ] },
  { group: 'Settings', items: [
    { id: 'm-users', label: 'Users and access', icon: '⚿', pages: ['users'] },
  ] },
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
  const visible = (id) => platform || !PAGES[id].platformOnly
  const menu = MENU.map((g) => ({ ...g, items: g.items.map((i) => ({ ...i, pages: i.pages.filter(visible) })).filter((i) => i.pages.length) }))
    .filter((g) => g.items.length)
  const nav = Object.keys(PAGES).filter(visible).map((id) => ({ id, ...PAGES[id] })) // pages the user can open
  const current = menu.flatMap((g) => g.items).find((i) => i.pages.includes(tab))
  const [lastTab, setLastTab] = useState({}) // remembers the last tab opened in each menu item
  useEffect(() => {
    if (current) setLastTab((m) => (m[current.id] === tab ? m : { ...m, [current.id]: tab }))
  }, [tab, current])
  const disabled = (id) => PAGES[id].needsClient && !clientId

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
          {menu.map((g) => (
            <div key={g.group} className="nav-group" role="group" aria-label={g.group}>
              <span className="nav-group-label">{g.group}</span>
              {g.items.map((item) => {
                const target = lastTab[item.id] && item.pages.includes(lastTab[item.id]) ? lastTab[item.id] : item.pages.find((id) => !disabled(id)) || item.pages[0]
                return (
                  <button
                    key={item.id}
                    className={current?.id === item.id ? 'nav-item active' : 'nav-item'}
                    disabled={item.pages.every(disabled)}
                    aria-current={current?.id === item.id ? 'page' : undefined}
                    onClick={() => setTab(target)}
                  >
                    <span className="nav-icon" aria-hidden="true">{item.icon}</span>
                    <span>{item.label}</span>
                  </button>
                )
              })}
            </div>
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
          <ChangePassword />
          <button className="ghost" onClick={onLogout}>Log out</button>
        </div>
      </aside>

      <div className="main-col">
        <header className="topbar">
          <h1 className="page-title">{current?.label || PAGES[tab]?.label}</h1>
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
          {current && current.pages.length > 1 && (
            <div className="page-tabs" role="tablist" aria-label={current.label}>
              {current.pages.map((id) => (
                <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? 'active' : ''}
                  disabled={disabled(id)} onClick={() => setTab(id)}>
                  {PAGES[id].label}
                </button>
              ))}
            </div>
          )}
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
          {tab === 'time' && client && <TimeEntryPage client={client} onGo={setTab} />}
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
          {tab === 'paycodes' && platform && <PayCodesPage />}
          {tab === 'client-paycodes' && client && <ClientPayCodesPage client={client} platform={platform} onGo={setTab} />}
          {tab === 'employee-pay' && client && <EmployeePayPage client={client} onGo={setTab} />}
          {tab === 'deductions' && platform && <DeductionsPage canEdit />}
          {tab === 'client-deductions' && client && <ClientDeductionsPage client={client} platform={platform} onGo={setTab} />}
          {tab === 'employee-deductions' && client && <EmployeeDeductionsPage client={client} onGo={setTab} />}
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
