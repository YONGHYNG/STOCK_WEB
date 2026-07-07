import type { Trade } from '../types'

interface Props { trades: Trade[] }

function fmt(v: number | null | undefined) {
  return v != null ? `$${v.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '—'
}

export function TradeTable({ trades }: Props) {
  return (
    <div className="data-table-wrap">
      <table style={S.table}>
        <thead>
          <tr>
            {['구분', '진입시각', '방향', '진입가', '손절가', '익절1', '익절2', '청산가', '결과', '수익률', '진입이유', '수익이유', '손실이유'].map((h) => (
              <th key={h} style={S.th}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {trades.length === 0 && (
            <tr>
              <td colSpan={13} style={{ ...S.td, color: 'var(--text2)', textAlign: 'center', padding: 28 }}>거래 기록이 없습니다</td>
            </tr>
          )}
          {trades.map((t) => {
            const pnl = t.pnl_pct
            const pnlColor = pnl == null ? 'var(--blue)' : pnl >= 0 ? 'var(--green)' : 'var(--red)'
            const pnlStr = pnl == null ? '진행중' : `${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}%`
            const resultColor: Record<string, string> = { TP1: 'var(--green)', TP2: 'var(--green)', SL: 'var(--red)', SIGNAL_CHANGE: 'var(--yellow)', OPEN: 'var(--blue)' }
            const dirColor = t.direction === 'LONG' ? 'var(--green)' : t.direction === 'SHORT' ? 'var(--red)' : 'var(--yellow)'
            const typeColor = t.trade_type === 'PAPER'
              ? 'var(--purple)'
              : t.trade_type === 'PLAN'
                ? 'var(--yellow)'
                : 'var(--blue)'
            return (
              <tr key={t.id} style={S.tr}>
                <td style={{ ...S.td, color: typeColor }}>{t.trade_type}</td>
                <td style={{ ...S.td, color: 'var(--text2)' }}>{(t.entry_time || '').slice(0, 16)}</td>
                <td style={{ ...S.td, color: dirColor }}>{t.direction}</td>
                <td style={S.td}>{fmt(t.entry_price)}</td>
                <td style={{ ...S.td, color: 'var(--red)' }}>{fmt(t.stop_loss)}</td>
                <td style={{ ...S.td, color: 'var(--green)' }}>{fmt(t.take_profit_1)}</td>
                <td style={{ ...S.td, color: 'var(--green)' }}>{fmt(t.take_profit_2)}</td>
                <td style={S.td}>{fmt(t.exit_price)}</td>
                <td style={{ ...S.td, color: resultColor[t.result ?? ''] ?? 'var(--text2)' }}>{t.result ?? 'OPEN'}</td>
                <td style={{ ...S.td, color: pnlColor }}>{pnlStr}</td>
                <td style={{ ...S.td, color: 'var(--text2)', maxWidth: 160 }} title={t.entry_reason ?? ''}>{(t.entry_reason ?? '—').slice(0, 40)}</td>
                <td style={{ ...S.td, color: 'var(--green)', maxWidth: 160 }} title={t.profit_reason ?? ''}>{(t.profit_reason ?? '—').slice(0, 40)}</td>
                <td style={{ ...S.td, color: 'var(--red)', maxWidth: 160 }} title={t.loss_reason ?? ''}>{(t.loss_reason ?? '—').slice(0, 40)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

const S: Record<string, React.CSSProperties> = {
  table: { width: '100%', minWidth: 1120, borderCollapse: 'collapse', fontSize: 12, tableLayout: 'fixed' },
  th: { padding: '8px 9px', textAlign: 'left', color: 'var(--text2)', fontWeight: 800, borderBottom: '1px solid var(--border)', whiteSpace: 'nowrap', background: 'var(--card)', position: 'sticky', top: 0 },
  td: { padding: '7px 9px', borderBottom: '1px solid var(--border-soft)', color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
  tr: {},
}
