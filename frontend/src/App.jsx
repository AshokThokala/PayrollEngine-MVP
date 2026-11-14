import { useCallback, useEffect, useState } from 'react'
import { api, loadSession, saveSession, stashAdminSession, stashedAdminSession, whenLoggedOut } from './api.js'
import ChangePassword from './components/ChangePassword.jsx'
import ClientSwitcher from './components/ClientSwitcher.jsx'
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
    { id: 'm-clients', label: 'Clients', icon: '▦', pages: ['clients'], about: 'Companies you run payroll for: registrations, state and contacts.' },
    { id: 'm-onboarding', label: 'Onboarding', icon: '✓', pages: ['onboarding', 'employee-onboarding'], about: 'Get a client and its employees ready for their first payroll.' },
    { id: 'm-billing', label: 'Billing', icon: '◫', pages: ['billing'], about: 'Plans, monthly invoices with GST, and payments.' },
  ] },
  { group: 'People', items: [
    { id: 'm-employees', label: 'Employees', icon: '☺', pages: ['employees'], about: 'Employee records, salary, statutory settings and tax details.' },
    { id: 'm-pay', label: 'Pay codes', icon: '⊕', pages: ['employee-pay', 'client-paycodes', 'paycodes'], about: 'What employees are paid: salary components and variable pay.' },
    { id: 'm-deductions', label: 'Deductions', icon: '⊖', pages: ['employee-deductions', 'client-deductions', 'deductions'], about: 'Voluntary deductions and recoveries on top of PF, ESI, PT and TDS.' },
  ] },
  { group: 'Payroll', items: [
    { id: 'm-time', label: 'Time entry', icon: '◴', pages: ['time'], about: 'Attendance for salaried staff and hours for hourly staff, month by month.' },
    { id: 'm-runs', label: 'Payroll runs', icon: '₹', pages: ['runs'], about: 'Calculate, review, approve and lock each month\'s payroll.' },
    { id: 'm-reports', label: 'Reports', icon: '▤', pages: ['reports'], about: 'Salary register, statutory summaries and exports.' },
  ] },
  { group: 'Compliance', items: [
    { id: 'm-calendar', label: 'Compliance calendar', icon: '◷', pages: ['filings'], about: 'PF, ESI, PT and TDS due dates, so nothing is filed late.' },
    { id: 'm-rules', label: 'Tax and rules', icon: '§', pages: ['tax', 'rules'], about: 'Income tax slabs and the dated statutory rules payroll uses.' },
  ] },
  { group: 'Settings', items: [
    { id: 'm-users', label: 'Users and access', icon: '⚿', pages: ['users'], about: 'Who can log in, their role and which client they see.' },
  ] },
]

// Remember sidebar choices in this browser (storage can be unavailable, e.g. private mode).
function useStored(key, initial) {
  const [value, setValue] = useState(() => {
    try {
      const raw = window.localStorage.getItem(key)
      return raw === null ? initial : JSON.parse(raw)
    } catch {
      return initial
    }
  })
  useEffect(() => {
    try { window.localStorage.setItem(key, JSON.stringify(value)) } catch { /* not saved; fine */ }
  }, [key, value])
  return [value, setValue]
}

function AdminShell({ user, onLogout, onViewAs }) {
  const platform = user.is_platform_admin
  const [clients, setClients] = useState([])
  const [clientId, setClientId] = useState(user.client_id || '')
  const [tab, setTab] = useState(platform ? 'clients' : 'employees')
  const [error, setError] = useState('')
  const [openEmployee, setOpenEmployee] = useState(null) // from search: { code, n }
  const [openClient, setOpenClient] = useState(null) // { id, section, n }: open a client record on a tab
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
  const [railOnly, setRailOnly] = useStored('cp4u.sidebar.collapsed', false) // icons only
  const [menuHidden, setMenuHidden] = useStored('cp4u.sidebar.hidden', false) // no sidebar at all
  // Ctrl/⌘ + B shows or hides the menu.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key.toLowerCase() === 'b' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault()
        setMenuHidden((h) => !h)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [setMenuHidden])
  const [closedGroups, setClosedGroups] = useStored('cp4u.sidebar.closedGroups', [])
  const toggleGroup = (g) => setClosedGroups((list) => (list.includes(g) ? list.filter((x) => x !== g) : [...list, g]))
  const currentGroup = menu.find((g) => g.items.some((i) => i.id === current?.id))?.group

  return (
    <div className={`shell${railOnly ? ' rail' : ''}${menuHidden ? ' menu-hidden' : ''}`}>
      <aside className="sidebar" hidden={menuHidden} aria-hidden={menuHidden || undefined}>
        <div className="brand">
          <span className="logo">C4U</span>
          <span className="brand-text">
            ClearPay4U
            <span className="tagline">zero-penalty payroll</span>
          </span>
          <button type="button" className="rail-toggle" onClick={() => setRailOnly(!railOnly)}
            aria-label={railOnly ? 'Expand menu' : 'Collapse menu'} title={railOnly ? 'Expand menu' : 'Collapse menu'}
            aria-expanded={!railOnly}>
            {railOnly ? '»' : '«'}
          </button>
        </div>
        <nav className="side-nav" aria-label="Main">
          {menu.map((g) => {
            const closed = closedGroups.includes(g.group) && !railOnly
            return (
            <div key={g.group} className={closed ? 'nav-group closed' : 'nav-group'} role="group" aria-label={g.group}>
              <button type="button" className="nav-group-label" onClick={() => toggleGroup(g.group)} aria-expanded={!closed}
                title={closed ? `Show ${g.group}` : `Hide ${g.group}`}>
                <span>{g.group}</span>
                {closed && currentGroup === g.group && <span className="dot" aria-label="current page is here" />}
                <span className="chev" aria-hidden="true">{closed ? '▸' : '▾'}</span>
              </button>
              {g.items.map((item) => {
                const target = lastTab[item.id] && item.pages.includes(lastTab[item.id]) ? lastTab[item.id] : item.pages.find((id) => !disabled(id)) || item.pages[0]
                return (
                  <button
                    key={item.id}
                    className={current?.id === item.id ? 'nav-item active' : 'nav-item'}
                    disabled={item.pages.every(disabled)}
                    aria-current={current?.id === item.id ? 'page' : undefined}
                    onClick={() => setTab(target)}
                    title={railOnly ? item.label : undefined}
                  >
                    <span className="nav-icon" aria-hidden="true">{item.icon}</span>
                    <span className="nav-label">{item.label}</span>
                  </button>
                )
              })}
            </div>
            )
          })}
        </nav>
        <div className="side-footer">
          <div className="who" title={railOnly ? user.name : undefined}>
            <span className="avatar" aria-hidden="true">{user.name.slice(0, 1).toUpperCase()}</span>
            <span className="who-text">
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
          <button type="button" className="menu-toggle" onClick={() => setMenuHidden(!menuHidden)}
            aria-label={menuHidden ? 'Show menu' : 'Hide menu'} title={`${menuHidden ? 'Show' : 'Hide'} menu (Ctrl+B)`}
            aria-expanded={!menuHidden}>
            <span aria-hidden="true">{menuHidden ? '☰' : '⇤'}</span>
          </button>
          {menuHidden && <span className="logo topbar-logo" aria-hidden="true">C4U</span>}
          <h1 className="page-title">{current?.label || PAGES[tab]?.label}</h1>
          <span className="topbar-spacer" />
          {platform && clients.length > 0 ? (
            <ClientSwitcher clients={clients} value={clientId} onChange={setClientId} />
          ) : (
            client && <span className="client-chip">{client.legal_name}</span>
          )}
        </header>

        {error && <div className="banner error">{error}</div>}

        <main>
          {current && (
            <div className="page-head">
              <span className="page-icon" aria-hidden="true">{current.icon}</span>
              <div className="page-head-text">
                <nav className="crumbs" aria-label="You are here">
                  <span>{currentGroup}</span>
                  <span aria-hidden="true">›</span>
                  <span>{current.label}</span>
                  {current.pages.length > 1 && <><span aria-hidden="true">›</span><strong>{PAGES[tab].label}</strong></>}
                  {PAGES[tab].needsClient && client && <span className="crumb-client">· {client.legal_name}</span>}
                </nav>
                <p className="page-about">{current.about}</p>
              </div>
            </div>
          )}
          {current && current.pages.length > 1 && (
            <div className="page-tabs" role="tablist" aria-label={current.label}>
              {current.pages.map((id) => (
                <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? 'active' : ''}
                  disabled={disabled(id)} onClick={() => setTab(id)}>
                  {PAGES[id].label}
                  {PAGES[id].platformOnly && <span className="tab-badge">team</span>}
                </button>
              ))}
            </div>
          )}
          {PAGES[tab]?.needsClient && !client && (
            <div className="empty-page card">
              <span className="page-icon" aria-hidden="true">▦</span>
              <h2>Choose a client</h2>
              <p className="muted">This page works on one client at a time. Pick one with the client switcher at the top right.</p>
            </div>
          )}
          <div className="page-body" key={tab}>
          {tab === 'clients' && platform && (
            <ClientsPage
              clients={clients}
              openRequest={openClient}
              onOpenEmployee={(cid, code) => {
                setClientId(cid)
                setOpenEmployee({ clientId: cid, code, n: Date.now() })
                setTab('employees')
              }}
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
            <EmployeesPage client={client} openRequest={openEmployee}
              onOpenClient={platform ? (id) => { setOpenClient({ id, section: 'employees', n: Date.now() }); setTab('clients') } : undefined}
              onViewAs={(code) => onViewAs(client.id, code).catch((e) => setError(e.message))} />
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
          </div>
        </main>
      </div>
    </div>
  )
}
