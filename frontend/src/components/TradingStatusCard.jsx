// 역할: 자동매매 실행 상태를 표시하는 카드 컴포넌트.
export function TradingStatusCard({ status, updatedAt, onModeChange, onEmergencyStop }) {
  const mode = status?.trading_mode ?? 'SIGNAL_ONLY'
  return (
    <div className="ops-card">
      <div className="ops-card__mode">
        <label className="eyebrow" htmlFor="trading-mode">운영 모드</label>
        <select id="trading-mode" value={mode} onChange={(e) => onModeChange(e.target.value)}>
          <option value="SIGNAL_ONLY">신호만 표시</option>
          <option value="PAPER_TRADING">모의매매</option>
          <option value="LIVE_TRADING">실거래</option>
        </select>
      </div>

      <div className="grid-auto" style={{ '--min-col': '92px' }}>
        <div className="ops-status">
          <div className="eyebrow">자동매매</div>
          <div className={`ops-status__value ${status?.auto_trade_enabled ? 'tone-long' : 'tone-muted'}`}>
            {status?.auto_trade_enabled ? 'ON' : 'OFF'}
          </div>
        </div>

        <div className="ops-status">
          <div className="eyebrow">데이터</div>
          <div className="ops-status__value">{status?.demo_mode ? 'DEMO' : 'LIVE'}</div>
        </div>

        <div className="ops-status">
          <div className="eyebrow">업데이트</div>
          <div className="ops-status__value ops-status__value--time">{updatedAt}</div>
        </div>
      </div>

      <button className="btn-short btn-block" onClick={onEmergencyStop}>긴급정지</button>
    </div>
  )
}
