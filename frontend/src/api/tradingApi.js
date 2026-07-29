// 역할: 프론트엔드에서 백엔드 매매 API를 호출하는 파일.
const normalizeServer = (value) => {
  let normalized = value?.trim().replace(/\/+$/, '') || ''
  if (!normalized) return ''
  if (!/^https?:\/\//i.test(normalized)) normalized = `http://${normalized}`
  const parsed = new URL(normalized)
  if (!parsed.port) parsed.port = '8000'
  return parsed.origin
}

export function getServerUrl() {
  const saved = normalizeServer(localStorage.getItem('trading-server-url'))
  if (saved) return saved
  if (location.protocol === 'http:' || location.protocol === 'https:') return ''
  return 'http://127.0.0.1:8000'
}

export function setServerUrl(value) {
  const normalized = normalizeServer(value)
  if (normalized) localStorage.setItem('trading-server-url', normalized)
  else localStorage.removeItem('trading-server-url')
}

export function getWebSocketUrl() {
  const server = getServerUrl()
  if (server) return `${server.replace(/^http/, 'ws')}/ws`
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}/ws`
}

function apiUrl(path) {
  return `${getServerUrl()}/api${path}`
}

async function request(url, options) {
  const response = await fetch(url, options)
  if (!response.ok) throw new Error(`서버 응답 오류 (${response.status})`)
  return response.json()
}

async function post(path, body = {}) {
  return request(apiUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

async function get(path) {
  return request(apiUrl(path))
}

export const tradingApi = {
  getStatus: () => get('/status'),
  getSignal: () => get('/signal'),
  getTrades: () => get('/trades'),
  getRiskSettings: () => get('/risk-settings'),
  getCredentials: () => get('/credentials'),
  saveCredentials: (credentials) => post('/credentials', credentials),
  disconnectCredentials: () => post('/credentials/disconnect'),
  saveRiskSettings: (settings) => post('/risk-settings', settings),
  setMode: (mode) => post('/mode', { mode }),
  setAutoTrade: (enabled, threshold) => post('/auto-trade', { enabled, threshold }),
  emergencyStop: () => post('/emergency-stop'),
  emergencyResume: () => post('/emergency-resume'),
  emergencyClose: () => post('/emergency-close'),
  placeOrder: (side, size) => post('/order', { side, size }),
  closePosition: () => post('/close-position'),
  runBacktest: (payload) => post('/backtest', payload),
  testConnection: () => get('/status'),
}
