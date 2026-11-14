// Thin client for the FastAPI backend. All calls go through /api (proxied).
const BASE = '/api'

// Login session: the token is kept in memory and, when the browser allows it, in
// localStorage so a refresh keeps you signed in (tokens expire after 12 hours).
const TOKEN_KEY = 'cp4u.session'
let session = null
let onLoggedOut = () => {}

export function loadSession() {
  try {
    session = JSON.parse(localStorage.getItem(TOKEN_KEY)) || null
  } catch {
    session = null
  }
  return session
}

export function saveSession(next) {
  session = next
  try {
    if (next) localStorage.setItem(TOKEN_KEY, JSON.stringify(next))
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    // storage unavailable: the session lasts until the page is closed
  }
}

// While an admin views the portal as an employee, their own session is kept here.
const ADMIN_KEY = 'cp4u.admin-session'

export function stashAdminSession(adminSession) {
  try {
    if (adminSession) localStorage.setItem(ADMIN_KEY, JSON.stringify(adminSession))
    else localStorage.removeItem(ADMIN_KEY)
  } catch {
    // storage unavailable: returning to admin will need a fresh login
  }
}

export function stashedAdminSession() {
  try {
    return JSON.parse(localStorage.getItem(ADMIN_KEY)) || null
  } catch {
    return null
  }
}

export function whenLoggedOut(callback) {
  onLoggedOut = callback
}

async function request(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(session?.token ? { Authorization: `Bearer ${session.token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (res.status === 401 && session) {
    saveSession(null)
    onLoggedOut()
  }
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    const fieldErrors = {}
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') message = data.detail
      // The API names the field for each problem: { field, label, message }.
      ;(data.errors || []).forEach((e) => {
        if (e.field) fieldErrors[e.field.split('.')[0]] = e.message
      })
    } catch {
      // keep the status text
    }
    const error = new Error(message)
    error.fieldErrors = fieldErrors
    throw error
  }
  return res.status === 204 ? null : res.json()
}

const enc = encodeURIComponent

export const api = {
  login: (email, password) => request('POST', '/auth/login', { email, password }),
  signupClient: (body) => request('POST', '/auth/signup/client', body),
  signupEmployee: (body) => request('POST', '/auth/signup/employee', body),
  me: () => request('GET', '/auth/me'),
  listUsers: () => request('GET', '/users'),
  deductionTypes: () => request('GET', '/deduction-types'),
  addDeductionType: (body) => request('POST', '/deduction-types', body),
  editDeductionType: (code, body) => request('PUT', `/deduction-types/${enc(code)}`, body),
  clientDeductions: (clientId) => request('GET', `/clients/${enc(clientId)}/deductions`),
  setClientDeduction: (clientId, code, body) => request('PUT', `/clients/${enc(clientId)}/deductions/${enc(code)}`, body),
  availableDeductions: (clientId) => request('GET', `/clients/${enc(clientId)}/deductions/available`),
  allEmployeeDeductions: (clientId) => request('GET', `/clients/${enc(clientId)}/employee-deductions`),
  employeeDeductions: (clientId, code) => request('GET', `/clients/${enc(clientId)}/employees/${enc(code)}/deductions`),
  addEmployeeDeduction: (clientId, code, body) =>
    request('POST', `/clients/${enc(clientId)}/employees/${enc(code)}/deductions`, body),
  editEmployeeDeduction: (clientId, code, id, body) =>
    request('PUT', `/clients/${enc(clientId)}/employees/${enc(code)}/deductions/${enc(id)}`, body),
  deleteEmployeeDeduction: (clientId, code, id) =>
    request('DELETE', `/clients/${enc(clientId)}/employees/${enc(code)}/deductions/${enc(id)}`),
  addUser: (body) => request('POST', '/users', body),
  userAction: (userId, action) => request('POST', `/users/${enc(userId)}/${action}`),
  myEmployee: () => request('GET', '/me/employee'),
  myPayslips: () => request('GET', '/me/payslips'),
  updateMyTax: (body) => request('PUT', '/me/tax', body),
  listClients: () => request('GET', '/clients'),
  updateClient: (clientId, body) => request('PUT', `/clients/${enc(clientId)}`, body),
  updateEmployee: (clientId, code, body) => request('PUT', `/clients/${enc(clientId)}/employees/${enc(code)}`, body),
  viewAs: (clientId, code) => request('POST', `/clients/${enc(clientId)}/employees/${enc(code)}/view-as`),
  search: (q) => request('GET', `/search?q=${enc(q)}`),
  taxRules: (on) => request('GET', `/tax/rules${on ? `?on=${enc(on)}` : ''}`),
  taxCalculate: (body) => request('POST', '/tax/calculate', body),
  reportCatalog: () => request('GET', '/reports'),
  inviteEmployee: (clientId, code, email) =>
    request('POST', `/clients/${enc(clientId)}/employees/${enc(code)}/invite`, { email }),
  revokeInvite: (inviteId) => request('POST', `/invites/${enc(inviteId)}/revoke`),
  inviteDetails: (token) => request('GET', `/invite/${enc(token)}`),
  acceptInvite: (token, body) => request('POST', `/invite/${enc(token)}/accept`, body),
  employeeOnboarding: (clientId) => request('GET', `/clients/${enc(clientId)}/employee-onboarding`),
  employeeProfile: (clientId, code) => request('GET', `/clients/${enc(clientId)}/employees/${enc(code)}/profile`),
  reviewProfile: (clientId, code, decision, note = '') =>
    request('POST', `/clients/${enc(clientId)}/employees/${enc(code)}/profile/${decision}`, { note }),
  myOnboarding: () => request('GET', '/me/onboarding'),
  saveMyOnboarding: (body) => request('PUT', '/me/onboarding', body),
  onboarding: (clientId) => request('GET', `/clients/${enc(clientId)}/onboarding`),
  onboardingOverview: () => request('GET', '/onboarding/clients'),
  billingPlans: () => request('GET', '/billing/plans'),
  billingOverview: () => request('GET', '/billing/overview'),
  clientBilling: (clientId) => request('GET', `/clients/${enc(clientId)}/billing`),
  setBillingPlan: (clientId, body) => request('PUT', `/clients/${enc(clientId)}/billing/plan`, body),
  generateInvoice: (clientId, month) => request('POST', `/clients/${enc(clientId)}/invoices`, { month }),
  invoiceAction: (invoiceId, action, body) => request('POST', `/invoices/${enc(invoiceId)}/${action}`, body),
  getReport: (clientId, key, params = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString()
    return request('GET', `/clients/${enc(clientId)}/reports/${enc(key)}${q ? `?${q}` : ''}`)
  },
  createClient: (body) => request('POST', '/clients', body),
  listEmployees: (clientId) => request('GET', `/clients/${enc(clientId)}/employees`),
  addEmployee: (clientId, body) => request('POST', `/clients/${enc(clientId)}/employees`, body),
  exitEmployee: (clientId, code, exitOn) =>
    request('POST', `/clients/${enc(clientId)}/employees/${enc(code)}/exit`, { exit_on: exitOn }),
  listRuns: (clientId) => request('GET', `/clients/${enc(clientId)}/runs`),
  createRun: (clientId, body) => request('POST', `/clients/${enc(clientId)}/runs`, body),
  getRun: (runId) => request('GET', `/runs/${enc(runId)}`),
  approveRun: (runId) => request('POST', `/runs/${enc(runId)}/approve`),
  lockRun: (runId) => request('POST', `/runs/${enc(runId)}/lock`),
  listFilings: (clientId) =>
    request('GET', clientId ? `/filings?client_id=${enc(clientId)}` : '/filings'),
  listRuleCategories: () => request('GET', '/rules/categories'),
  listRuleStates: () => request('GET', '/rules/states'),
  listRules: () => request('GET', '/rules'),
  createRule: (body) => request('POST', '/rules', body),
  editRule: (ruleId, body) => request('PUT', `/rules/${enc(ruleId)}`, body),
  updateTax: (clientId, code, body) =>
    request('PUT', `/clients/${enc(clientId)}/employees/${enc(code)}/tax`, body),
  updateFiling: (filingId, status, challanRef) =>
    request('POST', `/filings/${enc(filingId)}`, { status, challan_ref: challanRef || null }),
}

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 })

export function money(value) {
  return value === null || value === undefined ? '—' : inr.format(Number(value))
}

export function today() {
  return new Date().toISOString().slice(0, 10)
}
