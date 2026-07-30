// 역할: 프론트엔드 화면 구성과 주요 상태 관리를 담당하는 파일.
import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { getServerUrl, getWebSocketUrl, setServerUrl, tradingApi } from './api/tradingApi'
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
  paper_position: null,
  paper_account: null,
  pending_entry: null,
  api_configured: false,
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
  const [serverDraft, setServerDraft] = useState(getServerUrl())
  const [showServerSettings, setShowServerSettings] = useState(
    !localStorage.getItem('trading-server-url') && location.hostname === 'localhost',
  )
  const [connectionState, setConnectionState] = useState('확인 전')
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
    const ws = new WebSocket(getWebSocketUrl())
    ws.onmessage = (event) => handleWsMessage(JSON.parse(event.data))
    return () => ws.close()
  }, [handleWsMessage])

  useEffect(() => {
    tradingApi.getStatus()
      .then((s) => {
        dispatch({ type: 'STATUS', data: s })
        setConnectionState('연결됨')
      })
      .catch(() => setConnectionState('연결 안 됨'))
    tradingApi.getTrades().then((t) => dispatch({ type: 'TRADES', trades: t })).catch(() => {})
    tradingApi.getRiskSettings().then((s) => dispatch({ type: 'RISK_SETTINGS', settings: s })).catch(() => {})
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
      },
    })
  }

  async function emergencyStop() {
    const stopResult = await tradingApi.emergencyStop()
    if (stopResult?.has_position) {
      await tradingApi.emergencyClose()
    }
    const status = await tradingApi.getStatus()
    dispatch({ type: 'STATUS', data: status })
    tradingApi.getTrades().then((t) => dispatch({ type: 'TRADES', trades: t }))
  }

  async function emergencyResume() {
    await tradingApi.emergencyResume()
    const status = await tradingApi.getStatus()
    dispatch({ type: 'STATUS', data: status })
  }

  return (
    <div className="app-shell">
      <main className="dashboard">
        {/* <div className="server-toolbar">
          <button type="button" onClick={() => setShowServerSettings((shown) => !shown)}>
            서버 설정 · {connectionState}
          </button>
          {showServerSettings && (
            <form
              className="server-settings"
              onSubmit={(event) => {
                event.preventDefault()
                setServerUrl(serverDraft)
                location.reload()
              }}
            >
              <input
                aria-label="백엔드 서버 주소"
                value={serverDraft}
                onChange={(event) => setServerDraft(event.target.value)}
                placeholder="PC의 Tailscale IP (100.x.x.x)"
              />
              <p className="server-settings__help">
                PC와 휴대폰의 Tailscale을 켠 뒤 PC의 100.x.x.x 주소를 입력하세요.
                포트를 생략하면 8000번을 사용합니다.
              </p>
              <div className="server-settings__actions">
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      setServerUrl(serverDraft)
                      setConnectionState('확인 중')
                      await tradingApi.testConnection()
                      setConnectionState('연결됨')
                    } catch {
                      setConnectionState('연결 안 됨')
                    }
                  }}
                >
                  연결 확인
                </button>
                <button type="submit">저장 후 연결</button>
              </div>
            </form>
          )}
        </div> */}
        <Dashboard
          state={state}
          setStatusPatch={(patch) => dispatch({ type: 'STATUS', data: patch })}
          onModeChange={setMode}
          onEmergencyStop={emergencyStop}
          onEmergencyResume={emergencyResume}
        />
        {state.page === 'strategy' && <StrategySetting settings={state.riskSettings} onSaved={(s) => dispatch({ type: 'RISK_SETTINGS', settings: s })} />}
        {state.page === 'history' && (
          <TradeHistory
            trades={state.trades}
            signal={state.signal}
            pendingEntry={state.status.pending_entry}
            currentPrice={state.price ?? state.status.last_price}
          />
        )}
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
