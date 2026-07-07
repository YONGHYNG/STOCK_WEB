import { useCallback, useEffect, useReducer, useRef } from 'react'
import type { SignalData, AccountInfo, Position, AppStatus, Trade, RiskSettings, WsMessage } from './types'
import { api } from './api'
import { useWebSocket } from './hooks/useWebSocket'
import { Header } from './components/Header'
import { Hero } from './components/Hero'
import { SignalBars } from './components/SignalBars'
import { RiskCards } from './components/RiskCards'
import { AccountPanel } from './components/AccountPanel'
import { TimeframeGrid } from './components/TimeframeGrid'
import { LogTab } from './components/LogTab'
import { TradeTable } from './components/TradeTable'
import { RiskSettingsTab } from './components/RiskSettingsTab'
import { BacktestTab } from './components/BacktestTab'

interface AppState {
  signal: SignalData | null
  price: number | null
  logs: string[]
  account: AccountInfo | null
  positions: Position[]
  trades: Trade[]
  riskSettings: RiskSettings | null
  status: AppStatus
  activeTab: number
  updatedAt: string
}

type Action =
  | { type: 'SIGNAL'; data: SignalData }
  | { type: 'PRICE'; price: number }
  | { type: 'LOG'; message: string }
  | { type: 'ACCOUNT'; account: AccountInfo; positions: Position[] }
  | { type: 'STATUS'; data: Partial<AppStatus> }
  | { type: 'TRADES'; trades: Trade[] }
  | { type: 'RISK_SETTINGS'; settings: RiskSettings }
  | { type: 'SET_TAB'; tab: number }

const DEFAULT_STATUS: AppStatus = {
  trading_mode: 'SIGNAL_ONLY', auto_trade_enabled: false,
  emergency_stopped: false, demo_mode: false, seeded: false,
  last_price: null, confidence_threshold: 30, order_size_btc: 0.001,
}

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SIGNAL':
      return { ...state, signal: action.data, updatedAt: new Date().toLocaleTimeString('ko-KR') }
    case 'PRICE':
      return { ...state, price: action.price, updatedAt: new Date().toLocaleTimeString('ko-KR') }
    case 'LOG':
      return { ...state, logs: [...state.logs.slice(-499), action.message] }
    case 'ACCOUNT':
      return { ...state, account: action.account, positions: action.positions }
    case 'STATUS':
      return { ...state, status: { ...state.status, ...action.data } }
    case 'TRADES':
      return { ...state, trades: action.trades }
    case 'RISK_SETTINGS':
      return { ...state, riskSettings: action.settings }
    case 'SET_TAB':
      return { ...state, activeTab: action.tab }
    default:
      return state
  }
}

const INITIAL: AppState = {
  signal: null, price: null, logs: [], account: null, positions: [],
  trades: [], riskSettings: null, status: DEFAULT_STATUS, activeTab: 0, updatedAt: '-',
}

const TABS = ['분석 로그', '투자 복기', '리스크 설정', '백테스트']

function Panel({ title, children, className = '' }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel__header">
        <h2>{title}</h2>
      </div>
      {children}
    </section>
  )
}

export default function App() {
  const [state, dispatch] = useReducer(reducer, INITIAL)
  const tradeNeedsRefresh = useRef(false)

  const handleWsMessage = useCallback((msg: WsMessage) => {
    switch (msg.type) {
      case 'signal': dispatch({ type: 'SIGNAL', data: msg.data }); break
      case 'price': dispatch({ type: 'PRICE', price: msg.data.price }); break
      case 'log': dispatch({ type: 'LOG', message: msg.data.message }); break
      case 'account': dispatch({ type: 'ACCOUNT', account: msg.data.account, positions: msg.data.positions }); break
      case 'status': dispatch({ type: 'STATUS', data: msg.data }); break
      case 'trade_update': tradeNeedsRefresh.current = true; break
    }
  }, [])

  useWebSocket(handleWsMessage)

  useEffect(() => {
    api.getStatus().then((s) => dispatch({ type: 'STATUS', data: s }))
    api.getTrades().then((t) => dispatch({ type: 'TRADES', trades: t }))
    api.getRiskSettings().then((s) => dispatch({ type: 'RISK_SETTINGS', settings: s }))
  }, [])

  useEffect(() => {
    if (state.activeTab === 1 && tradeNeedsRefresh.current) {
      tradeNeedsRefresh.current = false
      api.getTrades().then((t) => dispatch({ type: 'TRADES', trades: t }))
    }
  }, [state.activeTab])

  useEffect(() => {
    const id = setInterval(() => {
      if (tradeNeedsRefresh.current) {
        tradeNeedsRefresh.current = false
        api.getTrades().then((t) => dispatch({ type: 'TRADES', trades: t }))
      }
    }, 5000)
    return () => clearInterval(id)
  }, [])

  const directions = state.signal?.timeframe_directions ?? {}
  const activePosition = state.positions.find((p) => p.symbol === 'BTCUSDT')

  return (
    <div className="app-shell">
      <Header
        status={state.status}
        onStatusChange={(patch) => dispatch({ type: 'STATUS', data: patch })}
      />

      <main className="dashboard">
        <div className="dashboard__meta">
          <span>BTCUSDT perpetual</span>
          <span>Last update {state.updatedAt}</span>
          <span>{state.status.demo_mode ? 'Demo data' : state.status.trading_mode.replace('_', ' ')}</span>
        </div>

        <div className="top-grid">
          <Panel title="실시간 시그널" className="panel--hero">
            <Hero signal={state.signal} price={state.price} />
          </Panel>

          <Panel title="방향 점수">
            <SignalBars
              long={state.signal?.long_score ?? state.signal?.long_probability ?? 50}
              short={state.signal?.short_score ?? state.signal?.short_probability ?? 50}
            />
          </Panel>

          <Panel title="시간봉 합의">
            <TimeframeGrid directions={directions} />
          </Panel>
        </div>

        <div className="middle-grid">
          <Panel title="계정 및 주문" className="panel--account">
            <AccountPanel
              account={state.account}
              positions={state.positions}
              status={state.status}
              onStatusChange={(patch) => dispatch({ type: 'STATUS', data: patch })}
            />
          </Panel>

          <Panel title="리스크 플랜">
            <RiskCards signal={state.signal} />
          </Panel>
        </div>

        <section className="workspace-panel">
          <div className="workspace-panel__top">
            <div>
              <h2>운영 워크스페이스</h2>
              <p>
                {activePosition
                  ? `${activePosition.holdSide?.toUpperCase()} position open`
                  : 'No BTCUSDT position'}
              </p>
            </div>
            <div className="tab-bar" role="tablist" aria-label="dashboard sections">
              {TABS.map((t, i) => (
                <button
                  key={t}
                  onClick={() => dispatch({ type: 'SET_TAB', tab: i })}
                  className={state.activeTab === i ? 'tab-button tab-button--active' : 'tab-button'}
                  type="button"
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          <div className="tab-content">
            {state.activeTab === 0 && <LogTab logs={state.logs} />}
            {state.activeTab === 1 && <TradeTable trades={state.trades} />}
            {state.activeTab === 2 && <RiskSettingsTab settings={state.riskSettings} />}
            {state.activeTab === 3 && <BacktestTab />}
          </div>
        </section>
      </main>
    </div>
  )
}
