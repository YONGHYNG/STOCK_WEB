// 역할: 실시간 매매 현황을 보여주는 대시보드 화면.
import { PositionCard } from '../components/PositionCard'
import { ProfitSummary } from '../components/ProfitSummary'
import { SignalCard } from '../components/SignalCard'
import { TradingStatusCard } from '../components/TradingStatusCard'

function Panel({ title, children, className = '' }) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel__header"><h2>{title}</h2></div>
      {children}
    </section>
  )
}

function SectionBlock({ title, children }) {
  return (
    <div className="section-block">
      <div className="section-block__title">{title}</div>
      {children}
    </div>
  )
}

function WarningList({ warnings }) {
  if (warnings.length === 0) {
    return <div className="clear-card">현재 표시할 위험 경고가 없습니다.</div>
  }
  return (
    <div className="warning-list">
      {warnings.map((w, i) => (
        <div key={`${w}-${i}`} className="warning-card">{w}</div>
      ))}
    </div>
  )
}

export function Dashboard({ state, setStatusPatch, onModeChange, onEmergencyStop }) {
  const warnings = state.signal?.risk_warnings ?? []
  const latestWarnings = warnings.slice().reverse()

  return (
    <>
      <div className="top-grid">
        <Panel title="실시간 시그널" className="panel--hero">
          <SignalCard signal={state.signal} price={state.price} />
        </Panel>

        <Panel title="운영 · 계정 · 포지션" className="panel--operations">
          <div className="panel-stack">
            <SectionBlock title="운영 상태">
              <TradingStatusCard
                status={state.status}
                updatedAt={state.updatedAt}
                onModeChange={onModeChange}
                onEmergencyStop={onEmergencyStop}
              />
            </SectionBlock>
            <SectionBlock title="계정 및 포지션">
              <PositionCard
                account={state.account}
                positions={state.positions}
                status={state.status}
                onStatusPatch={setStatusPatch}
              />
            </SectionBlock>
          </div>
        </Panel>

        <Panel title="수익률 · 위험 경고" className="panel--profit-risk">
          <div className="panel-stack">
            <SectionBlock title="수익률">
              <ProfitSummary trades={state.trades} />
            </SectionBlock>
            <SectionBlock title={`위험 경고 ${warnings.length ? `(${warnings.length})` : ''}`}>
              <WarningList warnings={latestWarnings} />
            </SectionBlock>
          </div>
        </Panel>
      </div>
    </>
  )
}
