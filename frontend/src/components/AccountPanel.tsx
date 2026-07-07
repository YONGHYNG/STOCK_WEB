import { useEffect, useState } from 'react'
import type { AccountInfo, Position, AppStatus } from '../types'
import { api } from '../api'

interface Props {
  account: AccountInfo | null
  positions: Position[]
  status: AppStatus
  onStatusChange: (patch: Partial<AppStatus>) => void
}

export function AccountPanel({ account, positions, status, onStatusChange }: Props) {
  const [orderSize, setOrderSize] = useState(status.order_size_btc)
  const [placing, setPlacing] = useState(false)
  const [autoEnabled, setAutoEnabled] = useState(status.auto_trade_enabled)
  const [threshold, setThreshold] = useState(status.confidence_threshold)

  useEffect(() => {
    setOrderSize(status.order_size_btc)
    setAutoEnabled(status.auto_trade_enabled)
    setThreshold(status.confidence_threshold)
  }, [status.auto_trade_enabled, status.confidence_threshold, status.order_size_btc])

  const equity = parseFloat(String(account?.accountEquity ?? account?.equity ?? 0))
  const available = parseFloat(String(account?.available ?? account?.crossMaxAvailable ?? 0))
  const upl = parseFloat(String(account?.unrealizedPL ?? 0))
  const uplColor = upl >= 0 ? 'var(--green)' : 'var(--red)'

  const btcPos = positions.find((p) => p.symbol === 'BTCUSDT')

  const placeOrder = async (side: 'LONG' | 'SHORT') => {
    setPlacing(true)
    await api.placeOrder(side, orderSize)
    setPlacing(false)
  }

  const handleAutoToggle = async (checked: boolean) => {
    if (checked && status.trading_mode === 'LIVE_TRADING') {
      if (!confirm('실거래(LIVE_TRADING) 모드에서 자동매매를 활성화합니다. 계속하시겠습니까?')) return
    }
    await api.setAutoTrade(checked, threshold)
    setAutoEnabled(checked)
    onStatusChange({ auto_trade_enabled: checked })
  }

  const handleThresholdChange = async (v: number) => {
    setThreshold(v)
    await api.setAutoTrade(autoEnabled, v)
    onStatusChange({ confidence_threshold: v })
  }

  return (
    <div style={S.grid}>
      <div style={S.col}>
        <div style={S.label}>가용 잔고 (USDT)</div>
        {account ? (
          <>
            <div style={S.bigVal}>${equity.toLocaleString('en-US', { minimumFractionDigits: 2 })}</div>
            <div style={{ fontSize: 12, color: 'var(--text2)', marginTop: 4 }}>
              가용: ${available.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              &nbsp;&nbsp;미실현:&nbsp;<span style={{ color: uplColor }}>{upl >= 0 ? '+' : ''}{upl.toFixed(2)}</span>
            </div>
          </>
        ) : (
          <div style={{ color: 'var(--text2)' }}>연동 안 됨</div>
        )}
      </div>

      <div style={S.col}>
        <div style={S.label}>현재 포지션</div>
        {btcPos ? (
          <>
            <div style={{ fontSize: 16, fontWeight: 700, color: btcPos.holdSide?.toUpperCase() === 'LONG' ? 'var(--green)' : 'var(--red)' }}>
              {btcPos.holdSide?.toUpperCase()} {btcPos.total} BTC
            </div>
            <div style={{ fontSize: 12, color: 'var(--text2)', marginTop: 4 }}>
              진입가: ${parseFloat(String(btcPos.averageOpenPrice ?? 0)).toLocaleString('en-US', { minimumFractionDigits: 2 })} · 레버리지: {btcPos.leverage}x
            </div>
          </>
        ) : (
          <div style={{ color: 'var(--text2)' }}>—</div>
        )}
      </div>

      <div style={S.col}>
        <div style={S.label}>수동 주문</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <span style={{ fontSize: 12, color: 'var(--text2)' }}>수량 (BTC)</span>
          <input
            type="number" min="0.001" max="100" step="0.001"
            value={orderSize}
            onChange={(e) => setOrderSize(parseFloat(e.target.value))}
            style={{ width: 90 }}
          />
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <button onClick={() => placeOrder('LONG')} disabled={placing || !account} style={{ color: 'var(--green)', borderColor: 'var(--green)' }}>▲ LONG</button>
          <button onClick={() => placeOrder('SHORT')} disabled={placing || !account} style={{ color: 'var(--red)', borderColor: 'var(--red)' }}>▼ SHORT</button>
          <button onClick={() => api.closePosition()} disabled={!account} style={{ color: 'var(--text2)' }}>✕ 청산</button>
        </div>
      </div>

      <div style={S.col}>
        <div style={S.label}>자동매매</div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, cursor: 'pointer' }}>
          <input type="checkbox" checked={autoEnabled} onChange={(e) => handleAutoToggle(e.target.checked)} />
          <span>활성화</span>
        </label>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12, color: 'var(--text2)' }}>신뢰도 임계</span>
          <input
            type="number" min="0" max="99" step="5"
            value={threshold}
            onChange={(e) => handleThresholdChange(parseFloat(e.target.value))}
            style={{ width: 70 }}
          />
          <span style={{ fontSize: 12, color: 'var(--text2)' }}>%</span>
        </div>
      </div>
    </div>
  )
}

const S: Record<string, React.CSSProperties> = {
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 12 },
  col: { minWidth: 0, background: 'rgba(255,255,255,0.026)', border: '1px solid var(--border-soft)', borderRadius: 8, padding: '12px 13px' },
  label: { fontSize: 11, fontWeight: 700, color: 'var(--text2)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8 },
  bigVal: { fontSize: 22, fontWeight: 850, fontVariantNumeric: 'tabular-nums' },
}
