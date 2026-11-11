// Thin client for the FastAPI backend. All calls go through /api (proxied).
const BASE = '/api'

export function getUser() {
  try {
    return localStorage.getItem('payroll.user') || 'ops1'
  } catch {
    return 'ops1'
  }
}

export function setUser(name) {
  try {
    localStorage.setItem('payroll.user', name)
  } catch {
    // storage unavailable: the name lasts for this page only
  }
}

async function request(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-User': getUser() },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
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
  listClients: () => request('GET', '/clients'),
  createClient: (body) => request('POST', '/clients', body),
  listEmployees: (clientId) => request('GET', `/clients/${enc(clientId)}/employees`),
  addEmployee: (clientId, body) => request('POST', `/clients/${enc(clientId)}/employees`, body),
  exitEmployee: (clientId, code, exitOn) =>
    request('POST', `/clients/${enc(clientId)}/employees/${enc(code)}/exit`, { exit_on: exitOn }),
  listRuns: (clientId) => request('GET', `/clients/${enc(clientId)}/runs`),
  createRun: (clientId, body) => request('POST', `/clients/${enc(clientId)}/runs`, body),
  approveRun: (runId) => request('POST', `/runs/${enc(runId)}/approve`),
  lockRun: (runId) => request('POST', `/runs/${enc(runId)}/lock`),
  listFilings: (clientId) =>
    request('GET', clientId ? `/filings?client_id=${enc(clientId)}` : '/filings'),
  listRuleCategories: () => request('GET', '/rules/categories'),
  listRuleStates: () => request('GET', '/rules/states'),
  listRules: () => request('GET', '/rules'),
  createRule: (body) => request('POST', '/rules', body),
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
