// 역할: 실시간 매매 현황을 보여주는 대시보드 화면.
import { PositionCard } from '../components/PositionCard'
import { ProfitChart } from '../components/ProfitChart'
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

export function Dashboard({ state, setStatusPatch, onModeChange, onEmergencyStop }) {
  return (
    <>
      <div className="top-grid">
        <Panel title="실시간 시그널" className="panel--hero">
          <SignalCard signal={state.signal} price={state.price} />
        </Panel>
        <Panel title="운영 상태">
          <TradingStatusCard
            status={state.status}
            updatedAt={state.updatedAt}
            onModeChange={onModeChange}
            onEmergencyStop={onEmergencyStop}
          />
        </Panel>
        <Panel title="수익 곡선">
          <ProfitChart trades={state.trades} />
        </Panel>
      </div>
      <div className="middle-grid">
        <Panel title="계정 및 포지션" className="panel--account">
          <PositionCard
            account={state.account}
            positions={state.positions}
            status={state.status}
            onStatusPatch={setStatusPatch}
          />
        </Panel>
        <Panel title="위험 경고">
          {(state.signal?.risk_warnings ?? []).length === 0 ? (
            <div style={{ color: 'var(--text2)' }}>현재 표시할 위험 경고가 없습니다.</div>
          ) : (
            <div style={{ display: 'grid', gap: 8 }}>
              {state.signal.risk_warnings.map((w, i) => (
                <div key={`${w}-${i}`} style={S.warning}>{w}</div>
              ))}
            </div>
          )}
        </Panel>
      </div>
    </>
  )
}

const S = {
  warning: { border: '1px solid var(--red)', background: 'var(--red-dim)', color: 'var(--text)', borderRadius: 8, padding: '10px 12px' },
}
