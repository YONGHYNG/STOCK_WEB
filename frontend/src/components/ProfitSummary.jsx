// 역할: 선택한 기간의 진입 횟수와 실현 수익률을 요약해서 보여주는 컴포넌트.
import { useState } from 'react'

const RANGE_OPTIONS = [1, 3, 7, 14, 30]
const DEFAULT_TAKER_FEE_RATE_PCT = 0.06
const FIXED_LEVERAGE = 20

function parseBackendTime(value) {
  if (!value) return null
  const raw = String(value).trim()
  const iso = raw.includes('T') ? raw : raw.replace(' ', 'T')
  const withZone = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`
  const date = new Date(withZone)
  return Number.isNaN(date.getTime()) ? null : date
}

function kstDateKey(value) {
  const date = value instanceof Date ? value : parseBackendTime(value)
  if (!date) return ''
  return new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
}

function kstDayNumber(value) {
  const key = kstDateKey(value)
  if (!key) return null
  const [year, month, day] = key.split('-').map(Number)
  return Math.floor(Date.UTC(year, month - 1, day) / 86400000)
}

function money(value) {
  return `$${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function ProfitSummary({ trades }) {
  const [rangeDays, setRangeDays] = useState(1)
  const [margin, setMargin] = useState(100)
  const [feeRatePct, setFeeRatePct] = useState(DEFAULT_TAKER_FEE_RATE_PCT)
  const currentDay = kstDayNumber(new Date())
  const startDay = currentDay == null ? null : currentDay - rangeDays + 1
  const actualTrades = trades.filter((t) => t.trade_type !== 'PLAN')
  const inRange = (value) => {
    const day = kstDayNumber(value)
    return day != null && startDay != null && currentDay != null && day >= startDay && day <= currentDay
  }
  const entries = actualTrades.filter((t) => inRange(t.entry_time))
  const closed = actualTrades.filter((t) => t.pnl_pct != null && inRange(t.exit_time ?? t.entry_time))
  const safeMargin = Math.max(0, Number(margin) || 0)
  const safeFeeRate = Math.max(0, Number(feeRatePct) || 0) / 100
  const settlement = closed
    .slice()
    .sort((a, b) => parseBackendTime(a.exit_time ?? a.entry_time) - parseBackendTime(b.exit_time ?? b.entry_time))
    .reduce((state, trade) => {
      const notional = state.balance * FIXED_LEVERAGE
      const profit = Math.max(notional * (Number(trade.pnl_pct) / 100), -state.balance)
      return {
        balance: state.balance + profit,
        includedFee: state.includedFee + notional * safeFeeRate * 2,
      }
    }, { balance: safeMargin, includedFee: 0 })
  const notional = safeMargin * FIXED_LEVERAGE
  const netProfit = settlement.balance - safeMargin
  const totalFee = settlement.includedFee
  const netPnlPct = safeMargin > 0 ? (netProfit / safeMargin) * 100 : 0
  const netTone = netProfit >= 0 ? 'tone-long' : 'tone-short'

  return (
    <div className="daily-summary">
      <div className="summary-range-tabs" aria-label="요약 기간">
        {RANGE_OPTIONS.map((days) => (
          <button
            key={days}
            className={rangeDays === days ? 'tab-button tab-button--active' : 'tab-button'}
            onClick={() => setRangeDays(days)}
            type="button"
          >
            {days}일
          </button>
        ))}
      </div>
      <div className="stat-box">
        <div className="eyebrow">수수료 차감 순수익금</div>
        <div className={`value-xl ${netTone}`}>{netProfit >= 0 ? '+' : '-'}{money(Math.abs(netProfit))}</div>
        <div className="value-sub">{netPnlPct >= 0 ? '+' : ''}{netPnlPct.toFixed(2)}% / 투자금 기준</div>
      </div>
      <div className="stat-box">
        <div className="eyebrow">{rangeDays}일 복리 수익률</div>
        <div className={`value-xl ${netTone}`}>{netPnlPct >= 0 ? '+' : ''}{netPnlPct.toFixed(2)}%</div>
        <div className="value-sub">수수료 차감 후 · 청산 {closed.length}건</div>
      </div>
      <div className="summary-calc">
        <label>
          <span className="eyebrow">투자금</span>
          <input
            min="0"
            step="10"
            type="number"
            value={margin}
            onChange={(e) => setMargin(e.target.value)}
          />
        </label>
        <label>
          <span className="eyebrow">수수료율(%)</span>
          <input
            min="0"
            step="0.001"
            type="number"
            value={feeRatePct}
            onChange={(e) => setFeeRatePct(e.target.value)}
          />
        </label>
      </div>
      <div className="summary-settlement">
        <div className="stat-box">
          <div className="eyebrow">{rangeDays}일 진입</div>
          <div className="stat-value">{entries.length}회</div>
        </div>
        <div className="stat-box">
          <div className="eyebrow">고정 배수</div>
          <div className="stat-value">{FIXED_LEVERAGE}배</div>
        </div>
        <div className="stat-box">
          <div className="eyebrow">명목금액</div>
          <div className="stat-value">{money(notional)}</div>
        </div>
        <div className="stat-box">
          <div className="eyebrow">포함된 왕복 수수료</div>
          <div className="stat-value tone-short">-{money(totalFee)}</div>
        </div>
      </div>
    </div>
  )
}
