// 역할: 자동매매 실행 상태를 표시하는 카드 컴포넌트.
function modeLabel(mode) {
  if (mode === 'PAPER_TRADING') return 'PAPER'
  if (mode === 'LIVE_TRADING') return 'LIVE'
  if (mode === 'SIGNAL_ONLY') return 'WAIT'
  return 'STOP'
}

function modeTone(mode, stopped) {
  if (stopped) return 'ops-badge--stop'
  if (mode === 'PAPER_TRADING') return 'ops-badge--paper'
  if (mode === 'LIVE_TRADING') return 'ops-badge--live'
  return 'ops-badge--wait'
}

function strategyLabel(strategy) {
  switch (strategy) {
    case 'WAIT_PULLBACK_LONG':
      return '눌림 롱 대기'
    case 'WAIT_RETEST_SHORT':
      return '리테스트 숏 대기'
    case 'LONG':
      return '롱 확정'
    case 'SHORT':
      return '숏 확정'
    default:
      return '관망'
  }
}

function entryState(signal, status) {
  if (status?.emergency_stopped) return ['차단', '긴급정지 상태']
  const warnings = signal?.risk_warnings ?? signal?.warnings ?? []
  if (warnings.length) return ['차단', warnings[0]]
  if (signal?.direction === 'LONG' || signal?.direction === 'SHORT') return ['가능', '리스크 조건 통과 대기']
  if (signal?.strategy_signal?.startsWith('WAIT')) return ['대기', signal.strategy_signal]
  return ['대기', '확정 진입 신호 없음']
}

export function TradingStatusCard({ status, signal, updatedAt, onModeChange, onEmergencyStop }) {
  const mode = status?.trading_mode ?? 'PAPER_TRADING'
  const autoEnabled = mode === 'PAPER_TRADING' ? true : Boolean(status?.auto_trade_enabled)
  const currentStrategy = signal?.strategy_signal ?? 'HOLD'
  const [entryLabel, blockReason] = entryState(signal, status)

  return (
    <div className="ops-card">
      <div className="ops-head">
        <div className={`ops-badge ${modeTone(mode, status?.emergency_stopped)}`}>
          {status?.emergency_stopped ? 'STOP' : modeLabel(mode)}
        </div>
        <div className="ops-card__mode">
          <label className="eyebrow" htmlFor="trading-mode">운영 모드</label>
          <select id="trading-mode" value={mode} onChange={(e) => onModeChange(e.target.value)}>
            <option value="PAPER_TRADING">모의매매</option>
            <option value="LIVE_TRADING">실거래</option>
            <option value="SIGNAL_ONLY">신호만 표시</option>
          </select>
        </div>
      </div>

      <div className="ops-status ops-status--strategy">
        <div className="eyebrow">현재 전략</div>
        <div className={`ops-status__value ${String(currentStrategy).startsWith('WAIT') ? 'tone-wait' : ''}`}>
          {strategyLabel(currentStrategy)}
        </div>
      </div>

      <div className="ops-grid">
        <div className="ops-status">
          <div className="eyebrow">자동매매</div>
          <div className={`ops-status__value ${autoEnabled ? 'tone-long' : 'tone-muted'}`}>
            {autoEnabled ? 'ON' : 'OFF'}
          </div>
        </div>

        <div className="ops-status">
          <div className="eyebrow">마지막 갱신</div>
          <div className="ops-status__value ops-status__value--time">{updatedAt}</div>
        </div>

        <div className="ops-status">
          <div className="eyebrow">진입 가능 여부</div>
          <div className={`ops-status__value ${entryLabel === '가능' ? 'tone-long' : entryLabel === '차단' ? 'tone-short' : 'tone-wait'}`}>
            {entryLabel}
          </div>
        </div>

        <div className="ops-status ops-status--wide">
          <div className="eyebrow">차단 사유</div>
          <div className="ops-status__value ops-status__value--reason">{blockReason}</div>
        </div>
      </div>

      <button className="btn-short btn-block" onClick={onEmergencyStop}>긴급정지</button>
    </div>
  )
}
