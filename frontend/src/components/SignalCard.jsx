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
  A: '진입 조건 충족 · A',
  B: '진입 조건 양호 · B',
  C: '추가 확인 필요 · C',
  D: '진입 조건 부족 · D',
  F: '확정 신호 대기 · F',
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
  const entrySummary = signal?.timeframe_summary?.['5m'] ?? {}
  const volumeSummary = signal?.timeframe_summary?.['1m'] ?? {}
  const trend15m = signal?.timeframe_summary?.['15m']?.direction ?? signal?.timeframe_directions?.['15m'] ?? 'HOLD'
  const atr1h = signal?.timeframe_summary?.['1H']?.atr14
  const rawPlannedDirection = pendingEntry?.direction ?? signal?.planned_direction ?? entrySummary?.plan_direction ?? direction
  const plannedDirection = ['LONG', 'SHORT'].includes(rawPlannedDirection)
    ? rawPlannedDirection
    : Number(entrySummary?.close ?? signal?.entry_price ?? 0) >= Number(entrySummary?.ema20 ?? 0)
      ? 'LONG'
      : 'SHORT'
  const activeDirection = hasPaper ? paper?.direction : livePosition?.holdSide?.toUpperCase() ?? openLiveTrade?.direction
  const displayDirection = hasPosition
    ? `${hasPaper ? 'PAPER' : 'LIVE'} ${activeDirection}`
    : direction === 'HOLD' && plannedDirection !== 'HOLD' ? `WAIT ${plannedDirection}` : direction
  const displayTone = toneClass(displayDirection)
  const strategySignal = signal?.strategy_signal ?? 'HOLD'
  const volumeRatio = volumeSummary?.volume_ratio != null ? `평균 대비 ${Number(volumeSummary.volume_ratio).toFixed(2)}배` : '-'
  const rsi = entrySummary?.rsi14 != null ? Number(entrySummary.rsi14).toFixed(1) : '-'
  const currentPrice = Number(price ?? paper?.current_price ?? signal?.last_price ?? signal?.entry_price ?? 0)
  const displayPrice = currentPrice || signal?.last_price || price || signal?.entry_price
  const previewEntry = Number(currentPrice || signal?.entry_price || 0)
  const previewGap = Number(atr1h || 0) * 1.5
  const previewStop = previewEntry && previewGap
    ? plannedDirection === 'SHORT' ? previewEntry + previewGap : previewEntry - previewGap
    : null
  const previewTakeProfit1 = previewEntry && previewGap
    ? plannedDirection === 'SHORT' ? previewEntry - previewGap : previewEntry + previewGap
    : null
  const fixedFeePct = Number(paper?.fee_pct ?? 0.06)
  const activeGrossPnl = hasPaper
    ? paperGrossPnl(activeDirection, paper?.entry_price, currentPrice || paper?.current_price)
    : 0
  const paperNotional = Number(paper?.size_btc ?? 0) * Number(paper?.entry_price ?? 0)
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

  const orderMetrics = pendingEntry ? [
    { label: '주문 진입가 · 체결 대기', value: money(pendingEntry.entry_price), tone: toneClass(pendingEntry.direction) },
    { label: '손절가', value: money(pendingEntry.stop_loss), tone: 'tone-short' },
    { label: '1차 익절가', value: money(pendingEntry.take_profit_1), tone: 'tone-long' },
  ] : !hasPosition ? [
    { label: '진입가', value: money(previewEntry || signal?.entry_price), tone: toneClass(plannedDirection) },
    { label: '손절가', value: money(signal?.stop_loss ?? previewStop), tone: 'tone-short' },
    { label: '1차 익절가', value: money(signal?.take_profit_1 ?? previewTakeProfit1), tone: 'tone-long' },
  ] : []

  const signalMetrics = hasPosition ? [] : [
    { label: '진입 판단', value: GRADE_LABELS[signal?.entry_grade] ?? '분석 대기', tone: gradeTone(signal?.entry_grade) },
    { label: '전략 신호', value: strategySignal, tone: strategySignal.startsWith('WAIT') ? 'tone-wait' : toneClass(direction) },
    { label: '추세 · 15분봉', value: trend15m, tone: toneClass(trend15m) },
    ...orderMetrics,
    { label: '거래량 · 1분봉', value: volumeRatio },
    { label: 'RSI14 · 5분봉', value: rsi },
    { label: 'ATR · 1시간봉', value: atr1h != null ? money(atr1h) : '-' },
  ]
  const activePositionMetrics = hasPaper ? positionMetrics : hasLive ? livePositionMetrics : []
  const metrics = [...activePositionMetrics, ...signalMetrics]

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
      <div className={`signal-card__metrics ${hasPosition ? 'signal-card__metrics--position' : 'signal-card__metrics--signal'}`}>
        {metrics.map((m) => <Metric key={m.label} {...m} />)}
      </div>
    </div>
  )
}

function Metric({ label, value, tone = '', className = '' }) {
  return (
    <div className={`stat-box signal-card__metric ${className}`}>
      <div className="eyebrow">{label}</div>
      <div className={`stat-value ${tone}`}>{value}</div>
    </div>
  )
}
