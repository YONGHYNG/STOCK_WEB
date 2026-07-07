// 역할: 자동매매 실행 상태를 표시하는 카드 컴포넌트.
export function TradingStatusCard({ status, updatedAt, onModeChange, onEmergencyStop }) {
  const mode = status?.trading_mode ?? 'SIGNAL_ONLY'
  return (
    <div style={S.grid}>
      <div>
        <div style={S.label}>MODE</div>
        <select value={mode} onChange={(e) => onModeChange(e.target.value)} style={S.select}>
          <option value="SIGNAL_ONLY">SIGNAL_ONLY</option>
          <option value="PAPER_TRADING">PAPER_TRADING</option>
          <option value="LIVE_TRADING">LIVE_TRADING</option>
        </select>
      </div>
      <div>
        <div style={S.label}>AUTO TRADE</div>
        <div style={{ ...S.value, color: status?.auto_trade_enabled ? 'var(--green)' : 'var(--text2)' }}>
          {status?.auto_trade_enabled ? 'ON' : 'OFF'}
        </div>
      </div>
      <div>
        <div style={S.label}>DATA</div>
        <div style={S.value}>{status?.demo_mode ? 'DEMO' : 'LIVE'}</div>
      </div>
      <div>
        <div style={S.label}>UPDATED</div>
        <div style={S.value}>{updatedAt}</div>
      </div>
      <button onClick={onEmergencyStop} style={S.stop}>긴급정지</button>
    </div>
  )
}

const S = {
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 10, alignItems: 'end' },
  label: { fontSize: 11, fontWeight: 800, color: 'var(--text2)', marginBottom: 6 },
  value: { fontSize: 18, fontWeight: 850 },
  select: { width: '100%' },
  stop: { color: 'var(--red)', borderColor: 'var(--red)' },
}
