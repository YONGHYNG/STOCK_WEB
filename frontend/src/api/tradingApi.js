const BASE = '/api'

async function post(path, body = {}) {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return res.json()
}

async function get(path) {
  const res = await fetch(BASE + path)
  return res.json()
}

export const tradingApi = {
  getStatus: () => get('/status'),
  getSignal: () => get('/signal'),
  getTrades: () => get('/trades'),
  getRiskSettings: () => get('/risk-settings'),
  saveRiskSettings: (settings) => post('/risk-settings', settings),
  setMode: (mode) => post('/mode', { mode }),
  setAutoTrade: (enabled, threshold) => post('/auto-trade', { enabled, threshold }),
  emergencyStop: () => post('/emergency-stop'),
  emergencyClose: () => post('/emergency-close'),
  placeOrder: (side, size) => post('/order', { side, size }),
  closePosition: () => post('/close-position'),
  runBacktest: (payload) => post('/backtest', payload),
}
