function money(v) {
  return v != null ? `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '-'
}

function pct(v) {
  return v != null ? `${(Number(v) * 100).toFixed(3)}%` : '-'
}

export function RiskStatus({ signal }) {
  const cards = [
    ['손절가', money(signal?.stop_loss), 'var(--red)'],
    ['1차 익절가', money(signal?.take_profit_1), 'var(--green)'],
    ['2차 익절가', money(signal?.take_profit_2), 'var(--green)'],
    ['3차 익절가', money(signal?.take_profit_3), 'var(--green)'],
    ['순손익비', signal?.net_risk_reward ? `1 : ${signal.net_risk_reward}` : '-', 'var(--yellow)'],
    ['스프레드', pct(signal?.spread_rate), 'var(--text)'],
    ['펀딩비', pct(signal?.funding_rate), 'var(--text)'],
    ['포지션 수량', signal?.position_size_btc ? `${signal.position_size_btc} BTC` : '-', 'var(--text)'],
    ['예상 수수료', signal?.estimated_fee != null ? `$${Number(signal.estimated_fee).toFixed(4)}` : '-', 'var(--text2)'],
    ['청산가', money(signal?.liquidation_price), 'var(--red)'],
  ]

  return (
    <section className="workspace-panel">
      <div className="workspace-panel__top">
        <div>
          <h2>리스크 상태</h2>
          <p>손절, 익절, 비용, 청산 위험</p>
        </div>
      </div>
      <div style={S.grid}>
        {cards.map(([label, value, color]) => (
          <div key={label} style={S.card}>
            <div style={S.label}>{label}</div>
            <div style={{ ...S.value, color }}>{value}</div>
          </div>
        ))}
      </div>
    </section>
  )
}

const S = {
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 8 },
  card: { background: 'var(--card)', border: '1px solid var(--border-soft)', borderRadius: 8, padding: '12px 14px' },
  label: { fontSize: 11, color: 'var(--text2)', marginBottom: 6 },
  value: { fontSize: 17, fontWeight: 850, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
}
