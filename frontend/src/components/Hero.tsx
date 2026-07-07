import type { SignalData } from '../types'

interface Props {
  signal: SignalData | null
  price: number | null
}

const DIR_COLOR = { LONG: 'var(--green)', SHORT: 'var(--red)', HOLD: 'var(--yellow)' }
const DIR_BG = { LONG: 'var(--green-dim)', SHORT: 'var(--red-dim)', HOLD: 'var(--yellow-dim)' }
const DIR_ARROW = { LONG: '▲', SHORT: '▼', HOLD: '◆' }

export function Hero({ signal, price }: Props) {
  const direction = (signal?.direction ?? 'HOLD') as 'LONG' | 'SHORT' | 'HOLD'
  const conf = signal?.confidence ?? 0
  const confColor = conf >= 60 ? 'var(--green)' : conf >= 30 ? 'var(--yellow)' : 'var(--text2)'
  const athOn = signal?.all_time_high_mode ?? false
  const atlOn = signal?.all_time_low_mode ?? false
  const displayPrice = signal?.last_price ?? price ?? signal?.entry_price ?? null
  const grade = signal?.entry_grade ?? 'D'

  return (
    <div style={S.grid}>
      <div style={{ ...S.metric, ...S.priceMetric }}>
        <div style={S.label}>LAST PRICE</div>
        <div style={S.price}>{displayPrice ? `$${displayPrice.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '—'}</div>
      </div>

      <div style={S.metric}>
        <div style={S.label}>SIGNAL</div>
        <div style={{
          ...S.badge,
          color: DIR_COLOR[direction],
          background: DIR_BG[direction],
          border: `1px solid ${DIR_COLOR[direction]}`,
        }}>
          {DIR_ARROW[direction]} {direction}
        </div>
      </div>

      <div style={S.metric}>
        <div style={S.label}>DIRECTION GAP</div>
        <div style={{ fontSize: 30, fontWeight: 850, color: confColor, fontVariantNumeric: 'tabular-nums' }}>{conf.toFixed(1)}%</div>
      </div>

      <div style={S.metric}>
        <div style={S.label}>GRADE / MARK</div>
        <div style={S.modeRow}>
          <span style={{ ...S.modePill, color: grade === 'A' || grade === 'B' ? 'var(--green)' : grade === 'F' ? 'var(--red)' : 'var(--yellow)', borderColor: 'currentColor' }}>{grade}</span>
          <span style={{ ...S.modePill, color: 'var(--text2)', borderColor: 'var(--border)' }}>{signal?.mark_price ? `$${signal.mark_price.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : 'MARK —'}</span>
          <span style={{ ...S.modePill, color: athOn ? 'var(--yellow)' : atlOn ? 'var(--red)' : 'var(--text2)', borderColor: athOn || atlOn ? 'currentColor' : 'var(--border)' }}>{athOn ? 'ATH' : atlOn ? 'ATL' : 'NORMAL'}</span>
        </div>
      </div>
    </div>
  )
}

const S: Record<string, React.CSSProperties> = {
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(145px, 1fr))', gap: 12, alignItems: 'stretch' },
  metric: { minWidth: 0, background: 'rgba(255,255,255,0.035)', border: '1px solid var(--border-soft)', borderRadius: 8, padding: '14px 16px' },
  priceMetric: { background: 'rgba(101,183,255,0.08)' },
  label: { fontSize: 11, fontWeight: 700, color: 'var(--text2)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 },
  price: { fontSize: 34, fontWeight: 850, fontVariantNumeric: 'tabular-nums', lineHeight: 1.05 },
  badge: { display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 18px', borderRadius: 8, fontSize: 18, fontWeight: 800 },
  modeRow: { display: 'flex', flexWrap: 'wrap', gap: 8 },
  modePill: { border: '1px solid var(--border)', borderRadius: 999, padding: '5px 9px', fontSize: 12, fontWeight: 800 },
}
