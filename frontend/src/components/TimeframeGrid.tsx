const TIMEFRAMES = ['5m', '15m', '30m', '1H', '6H', '1D', '1W', '1M']
const DIR_COLOR: Record<string, string> = { LONG: 'var(--green)', SHORT: 'var(--red)', HOLD: 'var(--yellow)' }
const DIR_ARROW: Record<string, string> = { LONG: '▲', SHORT: '▼', HOLD: '◆' }

interface Props { directions: Record<string, string> }

export function TimeframeGrid({ directions }: Props) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(76px, 1fr))', gap: 8 }}>
      {TIMEFRAMES.map((tf) => {
        const dir = directions[tf] ?? 'HOLD'
        const color = DIR_COLOR[dir] ?? 'var(--text2)'
        return (
          <div key={tf} style={S.cell}>
            <div style={S.tf}>{tf}</div>
            <div style={{ color, fontWeight: 850, fontSize: 13, whiteSpace: 'nowrap' }}>{DIR_ARROW[dir] ?? '-'} {dir}</div>
          </div>
        )
      })}
    </div>
  )
}

const S: Record<string, React.CSSProperties> = {
  cell: { background: 'var(--card)', border: '1px solid var(--border-soft)', borderRadius: 8, padding: '10px 12px', minHeight: 58 },
  tf: { fontSize: 11, color: 'var(--text2)', marginBottom: 4, fontWeight: 700 },
}
