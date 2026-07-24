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

export function TradeLogTable({ trades, signal, pendingEntry, currentPrice }) {
  const [page, setPage] = useState(1)
  const [selectedDate, setSelectedDate] = useState('')
  const summary = signal?.timeframe_summary?.['1m'] ?? signal?.timeframe_summary?.['5m'] ?? {}
  const expectedDirection = signal?.planned_direction ?? summary?.plan_direction ?? signal?.direction
  const expectedEntryPrice = summary?.planned_entry ?? signal?.entry_price
  const expectedEntry = !pendingEntry
    && (expectedDirection === 'LONG' || expectedDirection === 'SHORT')
    && Number(expectedEntryPrice) > 0
    ? {
        mode: '예상',
        direction: expectedDirection,
        entry_price: expectedEntryPrice,
        stop_loss: signal?.stop_loss ?? summary?.planned_stop_loss,
        take_profit_1: signal?.take_profit_1 ?? summary?.planned_take_profit_1,
      }
    : null
  const displayedEntry = pendingEntry ?? expectedEntry
  const isPendingOrder = Boolean(pendingEntry)
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
      {displayedEntry && (
        <div className="pending-entry-notice" role="status">
          <span className="pending-entry-notice__badge">
            {isPendingOrder ? '대기중..' : '예상 진입가'}
          </span>
          <strong className={displayedEntry.direction === 'LONG' ? 'tone-long' : 'tone-short'}>
            {displayedEntry.direction}
          </strong>
          <span>
            {isPendingOrder
              ? `지정가 ${money(displayedEntry.entry_price)} 체결을 기다리고 있습니다.`
              : `현재 전략의 예상 진입가는 ${money(displayedEntry.entry_price)}입니다.`}
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
            {displayedEntry && (
              <tr className="pending-entry-row">
                <td>{displayedEntry.mode}</td>
                <td>{isPendingOrder ? '대기중..' : '실시간 예상'}</td>
                <td className={displayedEntry.direction === 'LONG' ? 'tone-long' : 'tone-short'}>{displayedEntry.direction}</td>
                <td>{money(displayedEntry.entry_price)}</td>
                <td className="tone-short">{money(displayedEntry.stop_loss)}</td>
                <td className="tone-long">{money(displayedEntry.take_profit_1)}</td>
                <td>-</td>
                <td>-</td>
                <td className="tone-wait">{isPendingOrder ? '대기중..' : '예상'}</td>
                <td>-</td>
              </tr>
            )}
            {sortedTrades.length === 0 && !displayedEntry && <tr><td colSpan="10" className="table-empty">거래 기록이 없습니다</td></tr>}
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
