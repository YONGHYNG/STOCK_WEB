// 역할: 체결 기록과 매매 로그를 표로 보여주는 컴포넌트.
import { toKst } from '../utils/time'

function money(v) {
  return v != null ? `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '-'
}

export function TradeLogTable({ trades }) {
  return (
    <div className="data-table-wrap">
      <table className="trade-log-table">
        <thead>
          <tr>{['구분', '시간', '방향', '진입가', '손절', '익절1', '익절2', '청산가', '결과', '수익률'].map((h) => <th key={h}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {trades.length === 0 && <tr><td colSpan="10" className="table-empty">거래 기록이 없습니다</td></tr>}
          {trades.map((t) => {
            const pnl = t.pnl_pct
            const dirTone = t.direction === 'LONG' ? 'tone-long' : 'tone-short'
            const pnlTone = pnl == null ? 'tone-info' : pnl >= 0 ? 'tone-long' : 'tone-short'
            const resultTone = pnl == null ? 'tone-info' : pnl >= 0 ? 'tone-long' : 'tone-short'
            return (
              <tr key={t.id}>
                <td>{t.trade_type}</td>
                <td>{toKst(t.entry_time)}</td>
                <td className={dirTone}>{t.direction}</td>
                <td>{money(t.entry_price)}</td>
                <td className="tone-short">{money(t.stop_loss)}</td>
                <td className="tone-long">{money(t.take_profit_1)}</td>
                <td className="tone-long">{money(t.take_profit_2)}</td>
                <td>{money(t.exit_price)}</td>
                <td className={resultTone}>{t.result ?? 'OPEN'}</td>
                <td className={pnlTone}>{pnl == null ? '진행중' : `${pnl >= 0 ? '+' : ''}${Number(pnl).toFixed(2)}%`}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
