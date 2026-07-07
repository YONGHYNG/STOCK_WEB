import { useState } from 'react'
import type { AppStatus } from '../types'
import { api } from '../api'
import { CredentialsModal } from './CredentialsModal'

interface Props {
  status: AppStatus
  onStatusChange: (patch: Partial<AppStatus>) => void
}

const MODE_LABELS: Record<string, string> = {
  SIGNAL_ONLY: '신호 분석만',
  PAPER_TRADING: '모의매매',
  LIVE_TRADING: '실거래',
}

export function Header({ status, onStatusChange }: Props) {
  const [showCreds, setShowCreds] = useState(false)
  const [emergency, setEmergency] = useState(false)

  const handleMode = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const mode = e.target.value
    if (mode === 'LIVE_TRADING') {
      if (!confirm('LIVE_TRADING 모드로 전환합니다. 실제 Bitget 주문이 발생합니다. 계속하시겠습니까?')) {
        e.target.value = status.trading_mode
        return
      }
    }
    await api.setMode(mode)
    onStatusChange({ trading_mode: mode })
  }

  const handleEmergency = async () => {
    if (!confirm('긴급정지: 자동매매를 즉시 중단합니다. 계속하시겠습니까?')) return
    setEmergency(true)
    const res = await api.emergencyStop()
    onStatusChange({ auto_trade_enabled: false, emergency_stopped: true })
    if (res.has_position && confirm('포지션이 감지됩니다. 시장가로 청산하시겠습니까?')) {
      await api.emergencyClose()
    }
  }

  const statusDot = status.demo_mode ? '#e3b341' : status.emergency_stopped ? '#f85149' : '#3fb950'
  const statusLabel = status.demo_mode ? 'DEMO' : status.emergency_stopped ? 'STOPPED' : 'LIVE'

  return (
    <header style={S.header}>
      <div>
        <div style={S.symbol}>₿ BTCUSDT PERPETUAL</div>
        <div style={S.sub}>Bitget Futures · Multi-Timeframe Signal Monitor</div>
      </div>

      <div style={S.controls}>
        <span style={{ ...S.dot, color: statusDot }}>● {statusLabel}</span>

        <select value={status.trading_mode} onChange={handleMode} style={S.select}>
          {Object.entries(MODE_LABELS).map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>

        <button onClick={() => setShowCreds(true)} style={S.btn}>API 연동</button>

        <button
          onClick={handleEmergency}
          style={{ ...S.btn, ...(emergency || status.emergency_stopped ? S.btnRed : {}) }}
        >
          긴급정지
        </button>
      </div>

      {showCreds && <CredentialsModal onClose={() => setShowCreds(false)} />}
    </header>
  )
}

const S: Record<string, React.CSSProperties> = {
  header: { position: 'sticky', top: 0, zIndex: 20, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, padding: '13px max(18px, calc((100vw - 1480px) / 2 + 18px))', background: 'rgba(17, 24, 32, 0.94)', borderBottom: '1px solid var(--border-soft)', backdropFilter: 'blur(14px)', flexWrap: 'wrap' },
  symbol: { fontSize: 18, fontWeight: 850, color: 'var(--text)' },
  sub: { fontSize: 12, color: 'var(--text2)', marginTop: 2 },
  controls: { display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8, flexWrap: 'wrap' },
  dot: { fontWeight: 700, fontSize: 13 },
  select: { fontSize: 13, padding: '5px 8px' },
  btn: { padding: '6px 12px', minHeight: 32 },
  btnRed: { background: 'var(--red)', borderColor: 'var(--red)', color: '#fff', fontWeight: 900 },
}
