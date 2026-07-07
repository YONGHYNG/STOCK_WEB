import type { SignalData } from '../types'

interface Props { signal: SignalData | null }

function fmt(v: number | null | undefined): string {
  return v != null ? `$${v.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '—'
}
function pct(v: number | null | undefined): string {
  return v != null ? `${(v * 100).toFixed(3)}%` : '—'
}

export function RiskCards({ signal }: Props) {
  const cards = [
    { title: '분석 기준가', value: fmt(signal?.analysis_price), color: 'var(--text2)' },
    { title: '예상 진입가', value: fmt(signal?.entry_price), color: 'var(--text)' },
    { title: '손절가', value: fmt(signal?.stop_loss), color: 'var(--red)' },
    { title: '1차 익절가', value: fmt(signal?.take_profit_1), color: 'var(--green)' },
    { title: '2차 익절가', value: fmt(signal?.take_profit_2), color: 'var(--green)' },
    { title: '3차 익절가', value: fmt(signal?.take_profit_3), color: 'var(--green)' },
    { title: '순손익비', value: signal?.net_risk_reward ? `1 : ${signal.net_risk_reward}` : '—', color: 'var(--yellow)' },
    { title: '스프레드', value: pct(signal?.spread_rate), color: signal?.spread_rate && signal.spread_rate > 0.0007 ? 'var(--red)' : 'var(--text)' },
    { title: '펀딩비', value: pct(signal?.funding_rate), color: 'var(--text)' },
    { title: '포지션 수량', value: signal?.position_size_btc ? `${signal.position_size_btc.toFixed(6)} BTC` : '—', color: 'var(--text)' },
    { title: '예상 수수료', value: signal?.estimated_fee != null ? `$${signal.estimated_fee.toFixed(4)}` : '—', color: 'var(--text2)' },
    { title: '청산가', value: fmt(signal?.liquidation_price), color: 'var(--red)' },
  ]
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(128px, 1fr))', gap: 8 }}>
      {cards.map((c) => (
        <div key={c.title} style={S.card}>
          <div style={S.title}>{c.title}</div>
          <div style={{ ...S.value, color: c.color }}>{c.value}</div>
        </div>
      ))}
    </div>
  )
}

const S: Record<string, React.CSSProperties> = {
  card: { background: 'var(--card)', border: '1px solid var(--border-soft)', borderRadius: 8, padding: '12px 14px', minWidth: 0 },
  title: { fontSize: 11, color: 'var(--text2)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.06em' },
  value: { fontSize: 17, fontWeight: 850, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
}
