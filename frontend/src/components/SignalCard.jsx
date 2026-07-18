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

export function SignalCard({ signal, price, status, positions = [] }) {
  const paper = status?.paper_position
  const livePosition = positions.find((position) => position.symbol === 'BTCUSDT')
  const pendingEntry = status?.pending_entry
  const hasPaper = Boolean(paper)
  const hasLive = Boolean(livePosition)
  const hasPosition = hasPaper || hasLive
  const direction = signal?.direction ?? 'HOLD'
  const summary = signal?.timeframe_summary?.['1m'] ?? signal?.timeframe_summary?.['5m'] ?? {}
  const plannedDirection = pendingEntry?.direction ?? signal?.planned_direction ?? summary?.plan_direction ?? direction
  const hasNextPlan = plannedDirection === 'LONG' || plannedDirection === 'SHORT'
  const nextEntryPrice = hasNextPlan ? pendingEntry?.entry_price ?? signal?.entry_price : null
  const nextStopLoss = hasNextPlan ? pendingEntry?.stop_loss ?? signal?.stop_loss : null
  const nextTakeProfit1 = hasNextPlan ? pendingEntry?.take_profit_1 ?? signal?.take_profit_1 : null
  const nextTakeProfit2 = hasNextPlan ? pendingEntry?.take_profit_2 ?? signal?.take_profit_2 : null
  const activeDirection = hasPaper ? paper?.direction : livePosition?.holdSide?.toUpperCase()
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
  const fixedFeePct = Number(paper?.fee_pct ?? 0.12)
  const activeGrossPnl = hasPaper
    ? paperGrossPnl(activeDirection, paper?.entry_price, currentPrice || paper?.current_price)
    : 0
  const paperNotional = Number(status?.paper_account?.notional ?? 0)
  const activeGrossUsdt = paperNotional * activeGrossPnl / 100
  const fixedFeeUsdt = paperNotional * fixedFeePct / 100
  const activeNetUsdt = activeGrossUsdt - fixedFeeUsdt

  const positionMetrics = hasPaper ? [
    { label: '현재 포지션', value: 'PAPER OPEN', tone: 'tone-info' },
    { label: '포지션 방향', value: activeDirection, tone: toneClass(activeDirection) },
    { label: '진입가', value: money(paper?.entry_price) },
    { label: '현재가', value: money(currentPrice || paper?.current_price) },
    { label: '수수료 차감 손익', value: signedUsdt(activeNetUsdt), tone: activeNetUsdt > 0 ? 'tone-long' : activeNetUsdt < 0 ? 'tone-short' : 'tone-muted' },
    { label: '총손익 / 수수료', value: `${signedUsdt(activeGrossUsdt)} / $${fixedFeeUsdt.toFixed(2)}`, tone: activeGrossUsdt > 0 ? 'tone-long' : activeGrossUsdt < 0 ? 'tone-short' : 'tone-muted' },
    { label: '손절가', value: money(paper?.stop_loss), tone: 'tone-short' },
    { label: '1차 익절', value: money(paper?.take_profit_1), tone: 'tone-long' },
    { label: '2차 익절', value: money(paper?.take_profit_2), tone: 'tone-long' },
  ] : []

  const livePositionMetrics = hasLive ? [
    { label: '현재 포지션', value: 'LIVE OPEN', tone: 'tone-info' },
    { label: '포지션 방향', value: activeDirection, tone: toneClass(activeDirection) },
    { label: '진입가', value: money(livePosition?.openPriceAvg ?? livePosition?.averageOpenPrice) },
    { label: '현재가', value: money(livePosition?.markPrice ?? currentPrice) },
    { label: '포지션 수량', value: livePosition?.total ? `${livePosition.total} BTC` : '-' },
    { label: '미실현 손익', value: money(livePosition?.unrealizedPL), tone: Number(livePosition?.unrealizedPL ?? 0) >= 0 ? 'tone-long' : 'tone-short' },
  ] : []

  const signalMetrics = [
    { label: '진입 등급', value: GRADE_LABELS[signal?.entry_grade] ?? '-', tone: gradeTone(signal?.entry_grade) },
    { label: '전략 신호', value: strategySignal, tone: strategySignal.startsWith('WAIT') ? 'tone-wait' : toneClass(direction) },
    { label: '다음 포지션', value: plannedDirection, tone: toneClass(plannedDirection) },
    { label: '상태', value: state, tone: state.startsWith('WAIT') ? 'tone-wait' : '' },
    { label: pendingEntry ? '대기 중인 진입 지정가' : '다음 진입 지정가', value: money(nextEntryPrice), tone: toneClass(plannedDirection) },
    { label: '다음 손절가', value: money(nextStopLoss), tone: 'tone-short' },
    { label: '다음 1차 익절', value: money(nextTakeProfit1), tone: 'tone-long' },
    { label: '다음 2차 익절', value: money(nextTakeProfit2), tone: 'tone-long' },
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
