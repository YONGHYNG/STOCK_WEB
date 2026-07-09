// 역할: 체결 기록과 매매 로그를 표로 보여주는 컴포넌트.
import { useMemo, useState } from 'react'
import { toKst } from '../utils/time'

const PAGE_SIZE = 10

function money(v) {
  return v != null ? `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '-'
}

function timeValue(v) {
  const n = Number(v)
  if (Number.isFinite(n)) return n
  const parsed = Date.parse(v)
  return Number.isFinite(parsed) ? parsed : 0
}

export function TradeLogTable({ trades }) {
  const [page, setPage] = useState(1)
  const sortedTrades = useMemo(
    () => trades
      .filter((t) => t.trade_type !== 'PLAN')
      .slice()
      .sort((a, b) => timeValue(b.entry_time) - timeValue(a.entry_time)),
    [trades],
  )
  const totalPages = Math.max(1, Math.ceil(sortedTrades.length / PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const start = (currentPage - 1) * PAGE_SIZE
  const visibleTrades = sortedTrades.slice(start, start + PAGE_SIZE)

  return (
    <div className="trade-log">
      <div className="data-table-wrap">
        <table className="trade-log-table">
          <thead>
            <tr>{['구분', '시간', '방향', '진입가', '손절', '익절1', '익절2', '청산가', '결과', '수익률'].map((h) => <th key={h}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {sortedTrades.length === 0 && <tr><td colSpan="10" className="table-empty">거래 기록이 없습니다</td></tr>}
            {visibleTrades.map((t) => {
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

      {sortedTrades.length > PAGE_SIZE && (
        <div className="pagination">
          <button onClick={() => setPage(1)} disabled={currentPage === 1}>처음</button>
          <button onClick={() => setPage(Math.max(1, currentPage - 1))} disabled={currentPage === 1}>이전</button>
          <span className="pagination__status">{currentPage} / {totalPages}</span>
          <button onClick={() => setPage(Math.min(totalPages, currentPage + 1))} disabled={currentPage === totalPages}>다음</button>
          <button onClick={() => setPage(totalPages)} disabled={currentPage === totalPages}>마지막</button>
        </div>
      )}
    </div>
  )
}
