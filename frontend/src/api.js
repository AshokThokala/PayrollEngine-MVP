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
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') message = data.detail
      else if (Array.isArray(data.detail)) message = data.detail.map((d) => d.msg).join('; ')
    } catch {
      // keep the status text
    }
    throw new Error(message)
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
