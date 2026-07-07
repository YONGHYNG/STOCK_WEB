const BASE = '/api'

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return res.json()
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(BASE + path)
  return res.json()
}

export const api = {
  getStatus: () => get<import('./types').AppStatus>('/status'),
  getTrades: () => get<import('./types').Trade[]>('/trades'),
  getRiskSettings: () => get<import('./types').RiskSettings>('/risk-settings'),
  saveRiskSettings: (s: import('./types').RiskSettings) => post('/risk-settings', s),
  setMode: (mode: string) => post('/mode', { mode }),
  setAutoTrade: (enabled: boolean, threshold?: number) => post('/auto-trade', { enabled, threshold }),
  emergencyStop: () => post<{ ok: boolean; has_position: boolean }>('/emergency-stop', {}),
  emergencyClose: () => post('/emergency-close', {}),
  placeOrder: (side: string, size: number) => post('/order', { side, size }),
  closePosition: () => post('/close-position', {}),
  getCredentials: () => get<{ api_key: string; has_secret: boolean; has_passphrase: boolean }>('/credentials'),
  saveCredentials: (api_key: string, secret_key: string, passphrase: string) =>
    post('/credentials', { api_key, secret_key, passphrase }),
  runBacktest: (payload: {
    start_ts: number; end_ts: number; timeframe: string;
    initial_capital: number; fee_rate: number; slippage: number; order_size_pct: number;
  }) => post<{ ok: boolean; result?: Record<string, number>; trade_log?: unknown[]; error?: string }>('/backtest', payload),
}
