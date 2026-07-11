// 역할: 프론트엔드 화면 구성과 주요 상태 관리를 담당하는 파일.
import { useCallback, useEffect, useReducer, useRef } from 'react'
import { tradingApi } from './api/tradingApi'
import { Dashboard } from './pages/Dashboard'
import { RiskStatus } from './pages/RiskStatus'
import { StrategySetting } from './pages/StrategySetting'
import { TradeHistory } from './pages/TradeHistory'

const DEFAULT_STATUS = {
  trading_mode: 'PAPER_TRADING',
  auto_trade_enabled: true,
  emergency_stopped: false,
  demo_mode: false,
  seeded: false,
  last_price: null,
  confidence_threshold: 30,
  order_size_btc: 0.001,
  selected_strategy: 'WAIT_PULLBACK_LONG',
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
  page: 'history',
  updatedAt: '-',
}

function reducer(state, action) {
  switch (action.type) {
    // timeZone을 명시해 컴퓨터 시스템 시간대와 무관하게 항상 한국 시간으로 표시
    case 'SIGNAL': return { ...state, signal: action.data, updatedAt: new Date().toLocaleTimeString('ko-KR', { timeZone: 'Asia/Seoul' }) }
    case 'PRICE': return { ...state, price: action.price, updatedAt: new Date().toLocaleTimeString('ko-KR', { timeZone: 'Asia/Seoul' }) }
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
  ['history', '거래 기록'],
  ['strategy', '전략 설정'],
  ['risk', '시장가 진입'],
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
    const res = await tradingApi.setMode(mode)
    dispatch({
      type: 'STATUS',
      data: {
        trading_mode: mode,
        auto_trade_enabled: mode === 'PAPER_TRADING' ? true : state.status.auto_trade_enabled,
        ...(res?.selected_strategy ? { selected_strategy: res.selected_strategy } : {}),
      },
    })
  }

  async function emergencyStop() {
    await tradingApi.emergencyStop()
    dispatch({ type: 'STATUS', data: { auto_trade_enabled: false, emergency_stopped: true } })
  }

  return (
    <div className="app-shell">
      <main className="dashboard">
        <Dashboard
          state={state}
          setStatusPatch={(patch) => dispatch({ type: 'STATUS', data: patch })}
          onModeChange={setMode}
          onEmergencyStop={emergencyStop}
        />
        {state.page === 'strategy' && <StrategySetting settings={state.riskSettings} onSaved={(s) => dispatch({ type: 'RISK_SETTINGS', settings: s })} />}
        {state.page === 'history' && <TradeHistory trades={state.trades} signal={state.signal} />}
        {state.page === 'risk' && <RiskStatus signal={state.signal} account={state.account} positions={state.positions} />}

        <nav className="bottom-tab-bar" aria-label="하단 화면 전환">
          {PAGES.map(([key, label]) => (
            <button
              key={key}
              className={state.page === key ? 'tab-button tab-button--active' : 'tab-button'}
              onClick={() => dispatch({ type: 'PAGE', page: key })}
            >
              {label}
            </button>
          ))}
        </nav>
      </main>
    </div>
  )
}
