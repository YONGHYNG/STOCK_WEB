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

function pct(value) {
  const n = Number(value ?? 0)
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toFixed(2)}%`
}

function paperPnl(direction, entry, current) {
  const e = Number(entry ?? 0)
  const c = Number(current ?? 0)
  if (!e || !c) return 0
  return direction === 'SHORT' ? ((e - c) / e) * 100 : ((c - e) / e) * 100
}

export function SignalCard({ signal, price, status }) {
  const paper = status?.paper_position
  const hasPaper = Boolean(paper)
  const direction = signal?.direction ?? 'HOLD'
  const summary = signal?.timeframe_summary?.['1m'] ?? signal?.timeframe_summary?.['5m'] ?? {}
  const plannedDirection = signal?.planned_direction ?? summary?.plan_direction ?? direction
  const activeDirection = paper?.direction
  const displayDirection = hasPaper
    ? `PAPER ${activeDirection}`
    : direction === 'HOLD' && plannedDirection !== 'HOLD' ? `WAIT ${plannedDirection}` : direction
  const displayTone = toneClass(displayDirection)
  const strategySignal = signal?.strategy_signal ?? 'HOLD'
  const state = signal?.market_mode ?? 'HOLD'
  const volumeRatio = summary?.volume_ratio != null ? `평균 대비 ${Number(summary.volume_ratio).toFixed(2)}배` : '-'
  const rsi = summary?.rsi14 != null ? Number(summary.rsi14).toFixed(1) : '-'
  const currentPrice = Number(price ?? paper?.current_price ?? signal?.last_price ?? signal?.entry_price ?? 0)
  const displayPrice = currentPrice || signal?.last_price || price || signal?.entry_price
  const activePnl = hasPaper ? paperPnl(activeDirection, paper?.entry_price, currentPrice || paper?.current_price) : 0

  const positionMetrics = hasPaper ? [
    { label: '현재 포지션', value: 'PAPER OPEN', tone: 'tone-info' },
    { label: '포지션 방향', value: activeDirection, tone: toneClass(activeDirection) },
    { label: '진입가', value: money(paper?.entry_price) },
    { label: '현재가', value: money(currentPrice || paper?.current_price) },
    { label: '손익률', value: pct(activePnl), tone: activePnl > 0 ? 'tone-long' : activePnl < 0 ? 'tone-short' : 'tone-muted' },
    { label: '손절가', value: money(paper?.stop_loss), tone: 'tone-short' },
    { label: '1차 익절', value: money(paper?.take_profit_1), tone: 'tone-long' },
    { label: '2차 익절', value: money(paper?.take_profit_2), tone: 'tone-long' },
  ] : []

  const signalMetrics = [
    { label: '진입 등급', value: signal?.entry_grade ?? '-', tone: signal?.entry_grade === 'F' ? 'tone-short' : 'tone-long' },
    { label: '전략 신호', value: strategySignal, tone: strategySignal.startsWith('WAIT') ? 'tone-wait' : toneClass(direction) },
    { label: '대기 포지션', value: plannedDirection, tone: toneClass(plannedDirection) },
    { label: '상태', value: state, tone: state.startsWith('WAIT') ? 'tone-wait' : '' },
    { label: '예상 진입가', value: money(signal?.entry_price) },
    { label: '예상 손절가', value: money(signal?.stop_loss), tone: 'tone-short' },
    { label: '예상 1차 익절', value: money(signal?.take_profit_1), tone: 'tone-long' },
    { label: '예상 2차 익절', value: money(signal?.take_profit_2), tone: 'tone-long' },
    { label: 'RSI14', value: rsi },
    { label: '1분봉 거래량 배수', value: volumeRatio },
    { label: 'MA90 / MA200', value: `${money(summary?.ma90)} / ${money(summary?.ma200)}` },
    { label: '지지 / 돌파', value: `${money(summary?.support_level)} / ${money(summary?.breakout_level)}` },
  ]
  const metrics = hasPaper ? [...positionMetrics, ...signalMetrics.slice(0, 4)] : signalMetrics

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
      <div className="signal-card__metrics">
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
