// 역할: 청산된 거래의 수익률 표를 보여주는 컴포넌트.
import { toKst } from '../utils/time'

function timeValue(v) {
  const n = Number(v)
  if (Number.isFinite(n)) return n
  const parsed = Date.parse(v)
  return Number.isFinite(parsed) ? parsed : 0
}

export function ProfitSummary({ trades }) {
  // 청산 완료(pnl_pct가 있는) 거래만 표와 합계에 반영하고 최신 청산 내역부터 표시
  const closed = trades
    .filter((t) => t.pnl_pct != null)
    .slice()
    .sort((a, b) => timeValue(b.exit_time ?? b.entry_time) - timeValue(a.exit_time ?? a.entry_time))
  const total = closed.reduce((sum, t) => sum + Number(t.pnl_pct), 0)
  const totalTone = total >= 0 ? 'tone-long' : 'tone-short'

  return (
    <div>
      <div className="data-table-wrap">
        <table>
          <thead>
            <tr>{['시간', '방향', '수익률'].map((h) => <th key={h}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {closed.length === 0 && <tr><td colSpan="3" className="table-empty">청산된 거래가 없습니다</td></tr>}
            {closed.map((t) => {
              const pnl = Number(t.pnl_pct)
              const pnlTone = pnl >= 0 ? 'tone-long' : 'tone-short'
              const dirTone = t.direction === 'LONG' ? 'tone-long' : 'tone-short'
              return (
                <tr key={t.id}>
                  <td>{toKst(t.exit_time ?? t.entry_time)}</td>
                  <td className={dirTone}>{t.direction}</td>
                  <td className={pnlTone}>{pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}%</td>
                </tr>
              )
            })}
          </tbody>
          {closed.length > 0 && (
            <tfoot>
              <tr>
                <td colSpan="2">합계</td>
                <td className={totalTone}>{total >= 0 ? '+' : ''}{total.toFixed(2)}%</td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  )
}
