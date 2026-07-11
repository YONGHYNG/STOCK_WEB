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

function firstReason(text) {
  return String(text || '')
    .split('\n')
    .map((line) => line.trim())
    .find(Boolean)
}

function directionLabel(direction) {
  if (direction === 'LONG') return '롱'
  if (direction === 'SHORT') return '숏'
  return direction || '포지션'
}

function plainReason(reason, direction) {
  const text = String(reason || '')
  const side = directionLabel(direction)
  if (!text) return `${side} 포지션을 보유 중입니다`
  if (text.includes('support_level') && text.includes('RSI < 50')) {
    return '지지선 재확인 후 아래로 밀렸고 RSI도 약해서 숏으로 진입했습니다'
  }
  if (text.includes('breakout_level') && text.includes('RSI > 50')) {
    return '돌파선을 다시 확인한 뒤 위로 버텼고 RSI도 강해서 롱으로 진입했습니다'
  }
  if (text.includes('리테스트') && text.includes('아래')) {
    return '가격이 다시 확인 구간을 찍고 아래로 꺾여 숏으로 진입했습니다'
  }
  if (text.includes('눌림') || text.includes('돌파')) {
    return '가격이 눌림 구간을 버티고 다시 올라 롱으로 진입했습니다'
  }
  if (text.includes('RSI')) {
    return `${side} 방향 조건과 RSI 흐름이 맞아서 진입했습니다`
  }
  return text
}

function statusReason(signal, status, activePosition) {
  if (activePosition) {
    return plainReason(firstReason(activePosition.entry_reason), activePosition.direction ?? activePosition.side)
  }
  if (status?.emergency_stopped) return '긴급정지 상태'
  const warnings = signal?.risk_warnings ?? signal?.warnings ?? []
  if (warnings.length) return warnings[0]
  if (signal?.strategy_signal?.startsWith('WAIT')) return signal.strategy_signal
  return '확정 진입 신호 없음'
}

export function TradingStatusCard({ status, signal, positions = [], updatedAt, onModeChange, onEmergencyStop }) {
  const mode = status?.trading_mode ?? 'PAPER_TRADING'
  const autoEnabled = mode === 'PAPER_TRADING' ? true : Boolean(status?.auto_trade_enabled)
  const livePosition = positions.find((p) => p.symbol === 'BTCUSDT')
  const paperPosition = status?.paper_position
  const activePosition = paperPosition || (livePosition ? {
    direction: livePosition.holdSide?.toUpperCase(),
    side: livePosition.holdSide?.toUpperCase(),
    entry_reason: '실거래 포지션 보유 중',
  } : null)
  const currentStrategy = activePosition
    ? `${directionLabel(activePosition.direction ?? activePosition.side)} 보유 중`
    : strategyLabel(signal?.strategy_signal ?? 'HOLD')
  const reasonLabel = activePosition ? '투자 사유' : '차단 사유'
  const reasonText = statusReason(signal, status, activePosition)

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
        <div className={`ops-status__value ${String(activePosition?.direction ?? activePosition?.side).includes('LONG') ? 'tone-long' : String(activePosition?.direction ?? activePosition?.side).includes('SHORT') ? 'tone-short' : String(currentStrategy).startsWith('WAIT') ? 'tone-wait' : ''}`}>
          {currentStrategy}
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

        <div className="ops-status ops-status--wide">
          <div className="eyebrow">{reasonLabel}</div>
          <div className="ops-status__value ops-status__value--reason">{reasonText}</div>
        </div>
      </div>

      <button className="btn-short btn-block" onClick={onEmergencyStop}>긴급정지</button>
    </div>
  )
}
