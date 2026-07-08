// 역할: 자동매매 실행 상태를 표시하는 카드 컴포넌트.
export function TradingStatusCard({ status, updatedAt, onModeChange, onEmergencyStop }) {
  const mode = status?.trading_mode ?? 'SIGNAL_ONLY'
  return (
    <div className="grid-auto grid-auto--end" style={{ '--min-col': '115px' }}>
      <div>
        <div className="eyebrow">MODE</div>
        <select value={mode} onChange={(e) => onModeChange(e.target.value)}>
          <option value="SIGNAL_ONLY">SIGNAL_ONLY</option>
          <option value="PAPER_TRADING">PAPER_TRADING</option>
          <option value="LIVE_TRADING">LIVE_TRADING</option>
        </select>
      </div>
      <div>
        <div className="eyebrow">AUTO TRADE</div>
        <div className={`value-lg ${status?.auto_trade_enabled ? 'tone-long' : 'tone-muted'}`}>
          {status?.auto_trade_enabled ? 'ON' : 'OFF'}
        </div>
      </div>
      <div>
        <div className="eyebrow">DATA</div>
        <div className="value-lg">{status?.demo_mode ? 'DEMO' : 'LIVE'}</div>
      </div>
      <div>
        <div className="eyebrow">UPDATED</div>
        <div className="value-lg">{updatedAt}</div>
      </div>
      <button className="btn-short" onClick={onEmergencyStop}>긴급정지</button>
    </div>
  )
}
