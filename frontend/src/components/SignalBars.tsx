interface Props {
  long: number
  short: number
}

export function SignalBars({ long: longPct, short: shortPct }: Props) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <Bar label="LONG SCORE" value={longPct} color="var(--green)" />
      <Bar label="SHORT SCORE" value={shortPct} color="var(--red)" />
    </div>
  )
}

function Bar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 7 }}>
        <span style={{ fontSize: 12, fontWeight: 850, color }}>{label}</span>
        <span style={{ fontSize: 13, fontWeight: 850, color, fontVariantNumeric: 'tabular-nums' }}>
          {value.toFixed(1)}%
        </span>
      </div>
      <div style={{ height: 14, background: 'var(--card2)', border: '1px solid var(--border-soft)', borderRadius: 999, overflow: 'hidden' }}>
        <div style={{ width: `${Math.max(0, Math.min(100, value))}%`, height: '100%', background: color, borderRadius: 999, transition: 'width 0.4s ease' }} />
      </div>
    </div>
  )
}
