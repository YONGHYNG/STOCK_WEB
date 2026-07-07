export function ProfitChart({ trades }) {
  const closed = trades.filter((t) => t.pnl_pct != null).slice().reverse()
  let equity = 0
  const points = closed.map((t) => {
    equity += Number(t.pnl_pct)
    return equity
  })
  const min = Math.min(0, ...points)
  const max = Math.max(1, ...points)
  const path = points.map((p, i) => {
    const x = points.length <= 1 ? 0 : (i / (points.length - 1)) * 100
    const y = 48 - ((p - min) / (max - min || 1)) * 44
    return `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`
  }).join(' ')

  return (
    <div>
      <svg viewBox="0 0 100 52" preserveAspectRatio="none" style={S.svg}>
        <path d="M 0 48 L 100 48" stroke="var(--border)" strokeWidth="0.8" />
        {path && <path d={path} fill="none" stroke="var(--blue)" strokeWidth="1.6" />}
      </svg>
      <div style={S.caption}>누적 실현 수익률 {equity >= 0 ? '+' : ''}{equity.toFixed(2)}%</div>
    </div>
  )
}

const S = {
  svg: { width: '100%', height: 130, background: 'rgba(255,255,255,0.026)', border: '1px solid var(--border-soft)', borderRadius: 8 },
  caption: { marginTop: 8, color: 'var(--text2)', fontSize: 12 },
}
