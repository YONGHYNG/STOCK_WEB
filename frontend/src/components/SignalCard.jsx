// 역할: LONG, SHORT, HOLD 신호와 점수를 표시하는 컴포넌트.
const DIR_COLOR = { LONG: 'var(--green)', SHORT: 'var(--red)', HOLD: 'var(--yellow)' }

function money(v) {
  return v != null ? `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '-'
}

export function SignalCard({ signal, price }) {
  const direction = signal?.direction ?? 'HOLD'
  const longScore = signal?.long_score ?? signal?.long_probability ?? 50
  const shortScore = signal?.short_score ?? signal?.short_probability ?? 50
  return (
    <div style={S.wrap}>
      <div style={S.hero}>
        <div>
          <div style={S.label}>LAST PRICE</div>
          <div style={S.price}>{money(signal?.last_price ?? price ?? signal?.entry_price)}</div>
        </div>
        <div style={{ ...S.badge, color: DIR_COLOR[direction], borderColor: DIR_COLOR[direction] }}>
          {direction}
        </div>
      </div>
      <div style={S.metrics}>
        <Metric label="진입 등급" value={signal?.entry_grade ?? '-'} color={signal?.entry_grade === 'F' ? 'var(--red)' : 'var(--green)'} />
        <Metric label="분석 기준가" value={money(signal?.analysis_price)} />
        <Metric label="예상 진입가" value={money(signal?.entry_price)} />
        <Metric label="마크가" value={money(signal?.mark_price)} />
        <Metric label="LONG 점수" value={longScore.toFixed(1)} color="var(--green)" />
        <Metric label="SHORT 점수" value={shortScore.toFixed(1)} color="var(--red)" />
      </div>
    </div>
  )
}

function Metric({ label, value, color = 'var(--text)' }) {
  return (
    <div style={S.metric}>
      <div style={S.label}>{label}</div>
      <div style={{ ...S.metricValue, color }}>{value}</div>
    </div>
  )
}

const S = {
  wrap: { display: 'flex', flexDirection: 'column', gap: 12 },
  hero: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  label: { fontSize: 11, fontWeight: 800, color: 'var(--text2)', textTransform: 'uppercase' },
  price: { fontSize: 34, fontWeight: 900, fontVariantNumeric: 'tabular-nums' },
  badge: { border: '1px solid', borderRadius: 8, padding: '8px 18px', fontSize: 22, fontWeight: 900 },
  metrics: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 8 },
  metric: { background: 'rgba(255,255,255,0.035)', border: '1px solid var(--border-soft)', borderRadius: 8, padding: 10 },
  metricValue: { marginTop: 5, fontSize: 16, fontWeight: 850, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
}
