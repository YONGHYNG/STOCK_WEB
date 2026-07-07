import { ProfitChart } from '../components/ProfitChart'
import { TradeLogTable } from '../components/TradeLogTable'

export function TradeHistory({ trades }) {
  return (
    <section className="workspace-panel">
      <div className="workspace-panel__top">
        <div>
          <h2>거래 기록</h2>
          <p>LIVE, PAPER, PLAN 거래 복기</p>
        </div>
      </div>
      <div style={{ display: 'grid', gap: 14 }}>
        <ProfitChart trades={trades} />
        <TradeLogTable trades={trades} />
      </div>
    </section>
  )
}
