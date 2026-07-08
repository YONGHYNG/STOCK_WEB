// 역할: 대기형 전략 신호와 핵심 지표를 표시하는 컴포넌트.
const DIR_COLOR = { LONG: 'var(--green)', SHORT: 'var(--red)', HOLD: 'var(--yellow)' }

function money(v) {
  return v != null ? `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '-'
}

export function SignalCard({ signal, price }) {
  const direction = signal?.direction ?? 'HOLD'
  const summary = signal?.timeframe_summary?.['1m'] ?? signal?.timeframe_summary?.['5m'] ?? {}
  const strategySignal = signal?.strategy_signal ?? 'HOLD'
  const state = signal?.market_mode ?? 'HOLD'
  const volumeRatio = summary?.volume_ratio != null ? Number(summary.volume_ratio).toFixed(2) : '-'
  const rsi = summary?.rsi14 != null ? Number(summary.rsi14).toFixed(1) : '-'

  const metrics = [
    { label: '진입 등급', value: signal?.entry_grade ?? '-', color: signal?.entry_grade === 'F' ? 'var(--red)' : 'var(--green)' },
    { label: '전략 신호', value: strategySignal, color: strategySignal.startsWith('WAIT') ? 'var(--yellow)' : DIR_COLOR[direction] },
    { label: '상태', value: state, color: state.startsWith('WAIT') ? 'var(--yellow)' : 'var(--text)' },
    { label: '예상 진입가', value: money(signal?.entry_price) },
    { label: 'RSI14', value: rsi },
    { label: '거래량 비율', value: volumeRatio },
    { label: 'MA90 / MA200', value: `${money(summary?.ma90)} / ${money(summary?.ma200)}` },
    { label: '지지 / 돌파', value: `${money(summary?.support_level)} / ${money(summary?.breakout_level)}` },
  ]

  return (
    <div style={S.wrap}>
      <div style={S.hero}>
        <div>
          <div style={S.label}>LAST PRICE</div>
          <div style={S.price}>{money(signal?.last_price ?? price ?? signal?.entry_price)}</div>
        </div>
        <div style={{ ...S.badge, color: DIR_COLOR[direction], borderColor: DIR_COLOR[direction], background: `color-mix(in srgb, ${DIR_COLOR[direction]} 14%, transparent)` }}>
          {direction}
        </div>
      </div>
      <div style={S.metrics}>
        {metrics.map((m) => <Metric key={m.label} {...m} />)}
      </div>
    </div>
  )
}

function Metric({ label, value, color = 'var(--text)' }) {
  return (
    <div className="stat-box" style={S.metric}>
      <div style={S.label}>{label}</div>
      <div style={{ ...S.metricValue, color }}>{value}</div>
    </div>
  )
}

const S = {
  wrap: { display: 'flex', flexDirection: 'column', gap: 14 },
  hero: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    padding: '14px 16px',
    borderRadius: 10,
    border: '1px solid var(--border-soft)',
    background: 'linear-gradient(135deg, rgba(101,183,255,0.10), rgba(255,255,255,0.02))',
  },
  label: { fontSize: 11, fontWeight: 800, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: 0.3 },
  price: { fontSize: 34, fontWeight: 900, fontVariantNumeric: 'tabular-nums', marginTop: 4 },
  badge: { border: '1px solid', borderRadius: 10, padding: '8px 20px', fontSize: 22, fontWeight: 900 },
  metrics: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 8 },
  metric: {
    background: 'rgba(255,255,255,0.035)',
    border: '1px solid var(--border-soft)',
    borderRadius: 10,
    padding: 12,
    transition: 'border-color 0.15s, background 0.15s',
  },
  metricValue: { marginTop: 6, fontSize: 15, fontWeight: 850, whiteSpace: 'normal', overflowWrap: 'anywhere', lineHeight: 1.3 },
}
