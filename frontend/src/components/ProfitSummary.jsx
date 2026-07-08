// 역할: 시간봉별 방향 배지와 청산된 거래의 수익률 표를 보여주는 컴포넌트.
import { toKst } from '../utils/time'

const TF_LABELS = [
  ['5m', '5분'],
  ['15m', '15분'],
  ['30m', '30분'],
  ['1H', '1시간'],
  ['6H', '6시간'],
  ['1D', '1일'],
]

const DIR_TEXT = { LONG: 'BUY', SHORT: 'SHORT', HOLD: 'HOLD' }
const DIR_TONE = { LONG: 'tone-long', SHORT: 'tone-short', HOLD: 'tone-hold' }

export function ProfitSummary({ trades, directions }) {
  // 청산 완료(pnl_pct가 있는) 거래만 표와 합계에 반영
  const closed = trades.filter((t) => t.pnl_pct != null).slice().reverse()
  const total = closed.reduce((sum, t) => sum + Number(t.pnl_pct), 0)
  const totalTone = total >= 0 ? 'tone-long' : 'tone-short'

  return (
    <div>
      <div className="tf-row">
        {TF_LABELS.map(([key, label]) => {
          const dir = directions?.[key] ?? 'HOLD'
          return (
            <div key={key} className={`tf-badge ${DIR_TONE[dir] ?? 'tone-hold'}`}>
              <span className="tf-badge__label">{label}</span>
              <span>{DIR_TEXT[dir] ?? dir}</span>
            </div>
          )
        })}
      </div>
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
                  <td>{toKst(t.entry_time)}</td>
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
