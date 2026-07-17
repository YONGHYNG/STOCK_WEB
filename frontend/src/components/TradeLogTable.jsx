// 역할: 체결 기록과 매매 로그를 표로 보여주는 컴포넌트.
import { useMemo, useState } from 'react'
import { toKst } from '../utils/time'

const PAGE_SIZE = 10
const DEFAULT_MARGIN = 100
const FIXED_LEVERAGE = 20

function money(v) {
  return v != null ? `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '-'
}

function timeValue(v) {
  const n = Number(v)
  if (Number.isFinite(n)) return n
  const parsed = Date.parse(v)
  return Number.isFinite(parsed) ? parsed : 0
}

function profitAmount(trade) {
  if (trade.realized_pnl_amount != null) return Number(trade.realized_pnl_amount)
  if (trade.pnl_pct == null) return null
  return DEFAULT_MARGIN * FIXED_LEVERAGE * (Number(trade.pnl_pct) / 100)
}

export function TradeLogTable({ trades, pendingEntry, currentPrice }) {
  const [page, setPage] = useState(1)
  const [selectedDate, setSelectedDate] = useState('')
  const baseTrades = useMemo(
    () => trades
      .filter((t) => t.trade_type !== 'PLAN')
      .slice()
      .sort((a, b) => timeValue(b.entry_time) - timeValue(a.entry_time)),
    [trades],
  )
  const sortedTrades = useMemo(
    () => selectedDate
      ? baseTrades.filter((t) => toKst(t.entry_time).slice(0, 10) === selectedDate)
      : baseTrades,
    [baseTrades, selectedDate],
  )
  const totalPages = Math.max(1, Math.ceil(sortedTrades.length / PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const start = (currentPage - 1) * PAGE_SIZE
  const visibleTrades = sortedTrades.slice(start, start + PAGE_SIZE)
  const showPagination = sortedTrades.length > PAGE_SIZE
  const pagination = showPagination && (
    <div className="pagination">
      <span className="pagination__total">총 {sortedTrades.length}건</span>
      <button onClick={() => setPage(1)} disabled={currentPage === 1}>처음</button>
      <button onClick={() => setPage(Math.max(1, currentPage - 1))} disabled={currentPage === 1}>이전</button>
      <span className="pagination__status">{currentPage} / {totalPages}</span>
      <button onClick={() => setPage(Math.min(totalPages, currentPage + 1))} disabled={currentPage === totalPages}>다음</button>
      <button onClick={() => setPage(totalPages)} disabled={currentPage === totalPages}>마지막</button>
    </div>
  )

  return (
    <div className="trade-log">
      {pendingEntry && (
        <div className="pending-entry-notice" role="status">
          <span className="pending-entry-notice__badge">대기중..</span>
          <strong className={pendingEntry.direction === 'LONG' ? 'tone-long' : 'tone-short'}>
            {pendingEntry.direction}
          </strong>
          <span>
            지정가 {money(pendingEntry.entry_price)} 체결을 기다리고 있습니다.
          </span>
          <span className="pending-entry-notice__price">현재가 {money(currentPrice)}</span>
        </div>
      )}
      <div className="trade-log-filter">
        <div className="trade-log-filter__controls">
          <label>
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => {
                setSelectedDate(e.target.value)
                setPage(1)
              }}
            />
          </label>
          <button
            type="button"
            onClick={() => {
              setSelectedDate('')
              setPage(1)
            }}
            disabled={!selectedDate}
          >
            전체
          </button>
        </div>
      </div>
      <div className="data-table-wrap">
        <table className="trade-log-table">
          <thead>
            <tr>{['구분', '시간', '방향', '진입가', '손절', '익절', '수익금', '청산가', '결과', '수익률'].map((h) => <th key={h}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {pendingEntry && (
              <tr className="pending-entry-row">
                <td>대기중..</td>
                <td>대기중..</td>
                <td className={pendingEntry.direction === 'LONG' ? 'tone-long' : 'tone-short'}>{pendingEntry.direction}</td>
                <td>{money(pendingEntry.entry_price)}</td>
                <td className="tone-short">{money(pendingEntry.stop_loss)}</td>
                <td className="tone-long">{money(pendingEntry.take_profit_1)}</td>
                <td>-</td>
                <td>-</td>
                <td className="tone-wait">대기중..</td>
                <td>-</td>
              </tr>
            )}
            {sortedTrades.length === 0 && !pendingEntry && <tr><td colSpan="10" className="table-empty">거래 기록이 없습니다</td></tr>}
            {visibleTrades.map((t) => {
              const pnl = t.pnl_pct
              const dirTone = t.direction === 'LONG' ? 'tone-long' : 'tone-short'
              const pnlTone = pnl == null ? 'tone-info' : pnl >= 0 ? 'tone-long' : 'tone-short'
              const resultTone = pnl == null ? 'tone-info' : pnl >= 0 ? 'tone-long' : 'tone-short'
              const realizedProfit = profitAmount(t)
              const resultLabel = pnl == null ? '진행중' : pnl >= 0 ? '수익' : '손실'
              return (
                <tr key={t.id}>
                  <td>{t.trade_type}</td>
                  <td>{toKst(t.entry_time)}</td>
                  <td className={dirTone}>{t.direction}</td>
                  <td>{money(t.entry_price)}</td>
                  <td className="tone-short">{money(t.stop_loss)}</td>
                  <td className="tone-long">{money(t.take_profit_1)}</td>
                  <td className={pnlTone}>{realizedProfit == null ? '-' : `${realizedProfit >= 0 ? '+' : '-'}${money(Math.abs(realizedProfit))}`}</td>
                  <td>{money(t.exit_price)}</td>
                  <td className={resultTone}>{resultLabel}</td>
                  <td className={pnlTone}>{pnl == null ? '진행중' : `${pnl >= 0 ? '+' : ''}${Number(pnl).toFixed(2)}%`}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {pagination}
    </div>
  )
}
