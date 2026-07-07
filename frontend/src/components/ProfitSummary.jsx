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
const DIR_COLOR = { LONG: 'var(--green)', SHORT: 'var(--red)', HOLD: 'var(--yellow)' }

export function ProfitSummary({ trades, directions }) {
  // 청산 완료(pnl_pct가 있는) 거래만 표와 합계에 반영
  const closed = trades.filter((t) => t.pnl_pct != null).slice().reverse()
  const total = closed.reduce((sum, t) => sum + Number(t.pnl_pct), 0)
  const totalColor = total >= 0 ? 'var(--green)' : 'var(--red)'

  return (
    <div>
      <div style={S.tfRow}>
        {TF_LABELS.map(([key, label]) => {
          const dir = directions?.[key] ?? 'HOLD'
          return (
            <div key={key} style={{ ...S.tfBadge, borderColor: DIR_COLOR[dir], color: DIR_COLOR[dir] }}>
              <span style={S.tfLabel}>{label}</span>
              <span>{DIR_TEXT[dir] ?? dir}</span>
            </div>
          )
        })}
      </div>
      <div className="data-table-wrap">
        <table style={S.table}>
          <thead>
            <tr>{['시간', '방향', '수익률'].map((h) => <th key={h} style={S.th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {closed.length === 0 && <tr><td colSpan="3" style={S.empty}>청산된 거래가 없습니다</td></tr>}
            {closed.map((t) => {
              const pnl = Number(t.pnl_pct)
              const pnlColor = pnl >= 0 ? 'var(--green)' : 'var(--red)'
              const dirColor = t.direction === 'LONG' ? 'var(--green)' : 'var(--red)'
              return (
                <tr key={t.id}>
                  <td style={S.td}>{toKst(t.entry_time)}</td>
                  <td style={{ ...S.td, color: dirColor }}>{t.direction}</td>
                  <td style={{ ...S.td, color: pnlColor }}>{pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}%</td>
                </tr>
              )
            })}
          </tbody>
          {closed.length > 0 && (
            <tfoot>
              <tr>
                <td style={S.totalLabel} colSpan="2">합계</td>
                <td style={{ ...S.totalLabel, color: totalColor }}>{total >= 0 ? '+' : ''}{total.toFixed(2)}%</td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  )
}

const S = {
  tfRow: { display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 },
  tfBadge: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, border: '1px solid', borderRadius: 6, padding: '4px 8px', fontSize: 11, fontWeight: 800, lineHeight: 1.2, background: 'rgba(255,255,255,0.03)' },
  tfLabel: { fontSize: 10, fontWeight: 700, color: 'var(--text2)' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 12 },
  th: { padding: '8px 9px', textAlign: 'left', color: 'var(--text2)', borderBottom: '1px solid var(--border)', background: 'var(--card)' },
  td: { padding: '7px 9px', borderBottom: '1px solid var(--border-soft)' },
  totalLabel: { padding: '8px 9px', fontWeight: 900, borderTop: '1px solid var(--border)', background: 'var(--card)' },
  empty: { padding: 20, textAlign: 'center', color: 'var(--text2)' },
}
