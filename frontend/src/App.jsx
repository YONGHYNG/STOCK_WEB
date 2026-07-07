// 역할: 프론트엔드 화면 구성과 주요 상태 관리를 담당하는 파일.
import { useCallback, useEffect, useReducer, useRef } from 'react'
import { tradingApi } from './api/tradingApi'
import { Dashboard } from './pages/Dashboard'
import { RiskStatus } from './pages/RiskStatus'
import { StrategySetting } from './pages/StrategySetting'
import { TradeHistory } from './pages/TradeHistory'

const DEFAULT_STATUS = {
  trading_mode: 'SIGNAL_ONLY',
  auto_trade_enabled: false,
  emergency_stopped: false,
  demo_mode: false,
  seeded: false,
  last_price: null,
  confidence_threshold: 30,
  order_size_btc: 0.001,
}

const INITIAL = {
  signal: null,
  price: null,
  logs: [],
  account: null,
  positions: [],
  trades: [],
  riskSettings: null,
  status: DEFAULT_STATUS,
  page: 'dashboard',
  updatedAt: '-',
}

function reducer(state, action) {
  switch (action.type) {
    case 'SIGNAL': return { ...state, signal: action.data, updatedAt: new Date().toLocaleTimeString('ko-KR') }
    case 'PRICE': return { ...state, price: action.price, updatedAt: new Date().toLocaleTimeString('ko-KR') }
    case 'LOG': return { ...state, logs: [...state.logs.slice(-499), action.message] }
    case 'ACCOUNT': return { ...state, account: action.account, positions: action.positions }
    case 'STATUS': return { ...state, status: { ...state.status, ...action.data } }
    case 'TRADES': return { ...state, trades: action.trades }
    case 'RISK_SETTINGS': return { ...state, riskSettings: action.settings }
    case 'PAGE': return { ...state, page: action.page }
    default: return state
  }
}

const PAGES = [
  ['dashboard', '대시보드'],
  ['strategy', '전략 설정'],
  ['history', '거래 기록'],
  ['risk', '리스크 상태'],
]

export default function App() {
  const [state, dispatch] = useReducer(reducer, INITIAL)
  const tradeNeedsRefresh = useRef(false)

  const handleWsMessage = useCallback((msg) => {
    if (msg.type === 'signal') dispatch({ type: 'SIGNAL', data: msg.data })
    if (msg.type === 'price') dispatch({ type: 'PRICE', price: msg.data.price })
    if (msg.type === 'log') dispatch({ type: 'LOG', message: msg.data.message })
    if (msg.type === 'account') dispatch({ type: 'ACCOUNT', account: msg.data.account, positions: msg.data.positions })
    if (msg.type === 'status') dispatch({ type: 'STATUS', data: msg.data })
    if (msg.type === 'trade_update') tradeNeedsRefresh.current = true
  }, [])

  useEffect(() => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws`)
    ws.onmessage = (event) => handleWsMessage(JSON.parse(event.data))
    return () => ws.close()
  }, [handleWsMessage])

  useEffect(() => {
    tradingApi.getStatus().then((s) => dispatch({ type: 'STATUS', data: s }))
    tradingApi.getTrades().then((t) => dispatch({ type: 'TRADES', trades: t }))
    tradingApi.getRiskSettings().then((s) => dispatch({ type: 'RISK_SETTINGS', settings: s }))
  }, [])

  useEffect(() => {
    const id = setInterval(() => {
      if (tradeNeedsRefresh.current) {
        tradeNeedsRefresh.current = false
        tradingApi.getTrades().then((t) => dispatch({ type: 'TRADES', trades: t }))
      }
    }, 5000)
    return () => clearInterval(id)
  }, [])

  async function setMode(mode) {
    await tradingApi.setMode(mode)
    dispatch({ type: 'STATUS', data: { trading_mode: mode } })
  }

  async function emergencyStop() {
    await tradingApi.emergencyStop()
    dispatch({ type: 'STATUS', data: { auto_trade_enabled: false, emergency_stopped: true } })
  }

  const activePosition = state.positions.find((p) => p.symbol === 'BTCUSDT')

  return (
    <div className="app-shell">
      <main className="dashboard">
        <div className="dashboard__meta">
          <span>BTCUSDT perpetual</span>
          <span>{activePosition ? `${activePosition.holdSide?.toUpperCase()} position open` : 'No BTCUSDT position'}</span>
          <span>{state.status.demo_mode ? 'Demo data' : state.status.trading_mode.replace('_', ' ')}</span>
        </div>

        <div className="workspace-panel" style={{ marginBottom: 14 }}>
          <div className="workspace-panel__top">
            <div>
              <h2>Trading Workspace</h2>
              <p>Bitget BTCUSDT USDT-M futures</p>
            </div>
            <div className="tab-bar">
              {PAGES.map(([key, label]) => (
                <button
                  key={key}
                  className={state.page === key ? 'tab-button tab-button--active' : 'tab-button'}
                  onClick={() => dispatch({ type: 'PAGE', page: key })}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {state.page === 'dashboard' && (
          <Dashboard
            state={state}
            setStatusPatch={(patch) => dispatch({ type: 'STATUS', data: patch })}
            onModeChange={setMode}
            onEmergencyStop={emergencyStop}
          />
        )}
        {state.page === 'strategy' && <StrategySetting settings={state.riskSettings} onSaved={(s) => dispatch({ type: 'RISK_SETTINGS', settings: s })} />}
        {state.page === 'history' && <TradeHistory trades={state.trades} />}
        {state.page === 'risk' && <RiskStatus signal={state.signal} />}
      </main>
    </div>
  )
}
