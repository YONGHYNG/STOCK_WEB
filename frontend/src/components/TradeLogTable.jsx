// 역할: 체결 기록과 매매 로그를 표로 보여주는 컴포넌트.
function money(v) {
  return v != null ? `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '-'
}

export function TradeLogTable({ trades }) {
  return (
    <div className="data-table-wrap">
      <table style={S.table}>
        <thead>
          <tr>{['구분', '시간', '방향', '진입가', '손절', '익절1', '익절2', '청산가', '결과', '수익률'].map((h) => <th key={h} style={S.th}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {trades.length === 0 && <tr><td colSpan="10" style={S.empty}>거래 기록이 없습니다</td></tr>}
          {trades.map((t) => {
            const pnl = t.pnl_pct
            const dirColor = t.direction === 'LONG' ? 'var(--green)' : 'var(--red)'
            const pnlColor = pnl == null ? 'var(--blue)' : pnl >= 0 ? 'var(--green)' : 'var(--red)'
            return (
              <tr key={t.id}>
                <td style={S.td}>{t.trade_type}</td>
                <td style={S.td}>{String(t.entry_time ?? '').slice(0, 16)}</td>
                <td style={{ ...S.td, color: dirColor }}>{t.direction}</td>
                <td style={S.td}>{money(t.entry_price)}</td>
                <td style={{ ...S.td, color: 'var(--red)' }}>{money(t.stop_loss)}</td>
                <td style={{ ...S.td, color: 'var(--green)' }}>{money(t.take_profit_1)}</td>
                <td style={{ ...S.td, color: 'var(--green)' }}>{money(t.take_profit_2)}</td>
                <td style={S.td}>{money(t.exit_price)}</td>
                <td style={S.td}>{t.result ?? 'OPEN'}</td>
                <td style={{ ...S.td, color: pnlColor }}>{pnl == null ? '진행중' : `${pnl >= 0 ? '+' : ''}${Number(pnl).toFixed(2)}%`}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

const S = {
  table: { width: '100%', minWidth: 900, borderCollapse: 'collapse', fontSize: 12, tableLayout: 'fixed' },
  th: { padding: '8px 9px', textAlign: 'left', color: 'var(--text2)', borderBottom: '1px solid var(--border)', background: 'var(--card)' },
  td: { padding: '7px 9px', borderBottom: '1px solid var(--border-soft)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
  empty: { padding: 28, textAlign: 'center', color: 'var(--text2)' },
}
