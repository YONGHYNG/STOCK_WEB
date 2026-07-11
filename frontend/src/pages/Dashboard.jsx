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

export function Dashboard({ state, setStatusPatch, onModeChange, onEmergencyStop }) {
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
                signal={state.signal}
                updatedAt={state.updatedAt}
                onModeChange={onModeChange}
                onEmergencyStop={onEmergencyStop}
              />
            </SectionBlock>
            <SectionBlock title="계정 및 포지션">
              <PositionCard
                account={state.account}
                positions={state.positions}
              />
            </SectionBlock>
          </div>
        </Panel>

        <Panel title="일일 매매 요약" className="panel--profit-risk">
          <div className="panel-stack">
            <SectionBlock title="오늘 현황">
              <ProfitSummary trades={state.trades} />
            </SectionBlock>
          </div>
        </Panel>
      </div>
    </>
  )
}
