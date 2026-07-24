// 역할: 대기형 전략 신호와 핵심 지표를 표시하는 컴포넌트.
function money(v) {
  return v != null ? `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '-'
}

function toneClass(value) {
  if (String(value).includes('LONG')) return 'tone-long'
  if (String(value).includes('SHORT')) return 'tone-short'
  if (String(value).startsWith('WAIT')) return 'tone-wait'
  return 'tone-hold'
}

function signedUsdt(value) {
  const n = Number(value ?? 0)
  const sign = n > 0 ? '+' : n < 0 ? '-' : ''
  return `${sign}$${Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

const GRADE_LABELS = {
  A: 'A · 최상',
  B: 'B · 양호',
  C: 'C · 진입 대기',
  D: 'D · 조건 미흡',
  F: 'F · 위험/계산 불가',
}

function gradeTone(grade) {
  if (grade === 'A' || grade === 'B') return 'tone-long'
  if (grade === 'C') return 'tone-wait'
  if (grade === 'D') return 'tone-muted'
  return 'tone-short'
}

function paperGrossPnl(direction, entry, current) {
  const e = Number(entry ?? 0)
  const c = Number(current ?? 0)
  if (!e || !c) return 0
  return direction === 'SHORT' ? ((e - c) / e) * 100 : ((c - e) / e) * 100
}

export function SignalCard({ signal, price, status, positions = [], trades = [] }) {
  const openTrade = trades.find((trade) => trade.trade_type !== 'PLAN' && trade.exit_price == null)
  const openPaperTrade = openTrade?.trade_type === 'PAPER' ? openTrade : null
  const openLiveTrade = openTrade?.trade_type === 'LIVE' ? openTrade : null
  const paper = status?.paper_position ?? (openPaperTrade ? {
    id: openPaperTrade.id,
    direction: openPaperTrade.direction,
    entry_price: openPaperTrade.entry_price,
    stop_loss: openPaperTrade.stop_loss,
    take_profit_1: openPaperTrade.take_profit_1,
    take_profit_2: openPaperTrade.take_profit_2,
    fee_pct: 0.06,
  } : null)
  const livePosition = positions.find((position) => position.symbol === 'BTCUSDT')
  const pendingEntry = status?.pending_entry
  const hasPaper = Boolean(paper)
  const hasLive = Boolean(livePosition || openLiveTrade)
  const hasPosition = hasPaper || hasLive
  const direction = signal?.direction ?? 'HOLD'
  const summary = signal?.timeframe_summary?.['1m'] ?? signal?.timeframe_summary?.['5m'] ?? {}
  const plannedDirection = pendingEntry?.direction ?? signal?.planned_direction ?? summary?.plan_direction ?? direction
  const hasPlannedDirection = plannedDirection === 'LONG' || plannedDirection === 'SHORT'
  const nextEntryPrice = pendingEntry?.entry_price ?? (hasPlannedDirection ? signal?.entry_price : null)
  const nextStopLoss = pendingEntry?.stop_loss ?? (hasPlannedDirection ? signal?.stop_loss : null)
  const nextTakeProfit1 = pendingEntry?.take_profit_1 ?? (hasPlannedDirection ? signal?.take_profit_1 : null)
  const nextTakeProfit2 = pendingEntry?.take_profit_2 ?? (hasPlannedDirection ? signal?.take_profit_2 : null)
  const activeDirection = hasPaper ? paper?.direction : livePosition?.holdSide?.toUpperCase() ?? openLiveTrade?.direction
  const displayDirection = hasPosition
    ? `${hasPaper ? 'PAPER' : 'LIVE'} ${activeDirection}`
    : direction === 'HOLD' && plannedDirection !== 'HOLD' ? `WAIT ${plannedDirection}` : direction
  const displayTone = toneClass(displayDirection)
  const strategySignal = signal?.strategy_signal ?? 'HOLD'
  const state = signal?.market_mode ?? 'HOLD'
  const volumeRatio = summary?.volume_ratio != null ? `평균 대비 ${Number(summary.volume_ratio).toFixed(2)}배` : '-'
  const rsi = summary?.rsi14 != null ? Number(summary.rsi14).toFixed(1) : '-'
  const currentPrice = Number(price ?? paper?.current_price ?? signal?.last_price ?? signal?.entry_price ?? 0)
  const displayPrice = currentPrice || signal?.last_price || price || signal?.entry_price
  const fixedFeePct = Number(paper?.fee_pct ?? 0.06)
  const activeGrossPnl = hasPaper
    ? paperGrossPnl(activeDirection, paper?.entry_price, currentPrice || paper?.current_price)
    : 0
  const paperNotional = Number(status?.paper_account?.notional ?? 0)
  const activeGrossUsdt = paperNotional * activeGrossPnl / 100
  const fixedFeeUsdt = paperNotional * fixedFeePct / 100
  const activeNetUsdt = activeGrossUsdt - fixedFeeUsdt
  const liveEntryPrice = Number(livePosition?.openPriceAvg ?? livePosition?.averageOpenPrice ?? openLiveTrade?.entry_price ?? 0)
  const liveCurrentPrice = Number(currentPrice || livePosition?.markPrice || 0)
  const liveSize = Number(livePosition?.total ?? 0)
  const liveGrossUsdt = hasLive && liveEntryPrice && liveCurrentPrice
    ? (activeDirection === 'SHORT' ? liveEntryPrice - liveCurrentPrice : liveCurrentPrice - liveEntryPrice) * liveSize
    : Number(livePosition?.unrealizedPL ?? 0)
  const liveFeeUsdt = Math.abs(Number(livePosition?.deductedFee ?? 0))
  const liveNetUsdt = liveGrossUsdt - liveFeeUsdt

  const positionMetrics = hasPaper ? [
    { label: '현재 포지션', value: 'PAPER OPEN', tone: 'tone-info' },
    { label: '포지션 방향', value: activeDirection, tone: toneClass(activeDirection) },
    { label: '현재 진입가', value: money(paper?.entry_price) },
    { label: '현재가', value: money(currentPrice || paper?.current_price) },
    { label: '실시간 수익 / 고정 수수료', value: `${signedUsdt(activeGrossUsdt)} / $${fixedFeeUsdt.toFixed(2)}`, tone: activeGrossUsdt > 0 ? 'tone-long' : activeGrossUsdt < 0 ? 'tone-short' : 'tone-muted' },
    { label: '수수료 차감 실제수익', value: signedUsdt(activeNetUsdt), tone: activeNetUsdt > 0 ? 'tone-long' : activeNetUsdt < 0 ? 'tone-short' : 'tone-muted' },
    { label: '현재 손절가', value: money(paper?.stop_loss), tone: 'tone-short' },
    { label: '현재 1차 익절가', value: money(paper?.take_profit_1), tone: 'tone-long' },
    { label: '현재 2차 익절가', value: money(paper?.take_profit_2), tone: 'tone-long' },
  ] : []

  const livePositionMetrics = hasLive ? [
    { label: '현재 포지션', value: 'LIVE OPEN', tone: 'tone-info' },
    { label: '포지션 방향', value: activeDirection, tone: toneClass(activeDirection) },
    { label: '현재 진입가', value: money(liveEntryPrice) },
    { label: '현재가', value: money(liveCurrentPrice) },
    { label: '포지션 수량', value: livePosition?.total ? `${livePosition.total} BTC` : '-' },
    { label: '실시간 수익 / 현재 수수료', value: `${signedUsdt(liveGrossUsdt)} / $${liveFeeUsdt.toFixed(2)}`, tone: liveGrossUsdt >= 0 ? 'tone-long' : 'tone-short' },
    { label: '수수료 차감 실제수익', value: signedUsdt(liveNetUsdt), tone: liveNetUsdt >= 0 ? 'tone-long' : 'tone-short' },
    { label: '현재 손절가', value: money(livePosition?.stopLoss || openLiveTrade?.stop_loss), tone: 'tone-short' },
    { label: '현재 1차 익절가', value: money(livePosition?.takeProfit || openLiveTrade?.take_profit_1), tone: 'tone-long' },
    { label: '현재 2차 익절가', value: money(openLiveTrade?.take_profit_2), tone: 'tone-long' },
  ] : []

  const signalMetrics = [
    { label: '진입 등급', value: GRADE_LABELS[signal?.entry_grade] ?? '-', tone: gradeTone(signal?.entry_grade) },
    { label: '전략 신호', value: strategySignal, tone: strategySignal.startsWith('WAIT') ? 'tone-wait' : toneClass(direction) },
    { label: '다음 포지션', value: plannedDirection, tone: toneClass(plannedDirection) },
    { label: '상태', value: state, tone: state.startsWith('WAIT') ? 'tone-wait' : '' },
    { label: pendingEntry ? '예상 진입가 · 대기중' : '실시간 예상 진입가', value: money(nextEntryPrice), tone: toneClass(plannedDirection) },
    { label: '예상 손절가', value: money(nextStopLoss), tone: 'tone-short' },
    { label: '실시간 예상 1차 익절가', value: money(nextTakeProfit1), tone: 'tone-long' },
    { label: '예상 2차 익절', value: money(nextTakeProfit2), tone: 'tone-long' },
    { label: 'RSI14', value: rsi },
    { label: '1분봉 거래량 배수', value: volumeRatio },
    { label: 'MA90 / MA200', value: `${money(summary?.ma90)} / ${money(summary?.ma200)}` },
    { label: '지지 / 돌파', value: `${money(summary?.support_level)} / ${money(summary?.breakout_level)}` },
  ]
  const metrics = hasPaper ? positionMetrics : hasLive ? livePositionMetrics : signalMetrics

  return (
    <div className="signal-card">
      <div className="signal-card__hero">
        <div>
          <div className="eyebrow">LAST PRICE</div>
          <div className="signal-card__price">{money(displayPrice)}</div>
        </div>
        <div className={`signal-card__badge ${displayTone}`}>
          {displayDirection}
        </div>
      </div>
      <div className={`signal-card__metrics ${hasPosition ? 'signal-card__metrics--position' : ''}`}>
        {metrics.map((m) => <Metric key={m.label} {...m} />)}
      </div>
    </div>
  )
}

function Metric({ label, value, tone = '' }) {
  return (
    <div className="stat-box signal-card__metric">
      <div className="eyebrow">{label}</div>
      <div className={`stat-value ${tone}`}>{value}</div>
    </div>
  )
}
