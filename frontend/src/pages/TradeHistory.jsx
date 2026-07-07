// 역할: 매매 기록과 손익 내역을 보여주는 화면.
import { ProfitSummary } from '../components/ProfitSummary'
import { TradeLogTable } from '../components/TradeLogTable'

export function TradeHistory({ trades, signal }) {
  return (
    <section className="workspace-panel">
      <div className="workspace-panel__top">
        <div>
          <h2>거래 기록</h2>
          <p>LIVE, PAPER, PLAN 거래 복기</p>
        </div>
      </div>
      <div style={{ display: 'grid', gap: 14 }}>
        <ProfitSummary trades={trades} directions={signal?.timeframe_directions} />
        <TradeLogTable trades={trades} />
      </div>
    </section>
  )
}
