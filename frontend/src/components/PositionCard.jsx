// 역할: 현재 포지션과 진입 정보를 표시하는 컴포넌트.
import { tradingApi } from '../api/tradingApi'

function num(v) {
  const n = Number(v ?? 0)
  return Number.isFinite(n) ? n : 0
}

export function PositionCard({ account, positions, status, onStatusPatch }) {
  const btc = positions.find((p) => p.symbol === 'BTCUSDT')
  const orderSize = status?.order_size_btc ?? 0.001
  const equity = num(account?.accountEquity ?? account?.equity)
  const available = num(account?.available ?? account?.crossMaxAvailable)

  async function place(side) {
    await tradingApi.placeOrder(side, orderSize)
  }

  async function toggleAuto(e) {
    const enabled = e.target.checked
    await tradingApi.setAutoTrade(enabled, status?.confidence_threshold)
    onStatusPatch({ auto_trade_enabled: enabled })
  }

  const side = btc?.holdSide?.toUpperCase()
  const sideTone = side === 'SHORT' ? 'tone-short' : side === 'LONG' ? 'tone-long' : 'tone-muted'

  return (
    <div className="account-position">
      <div className="account-position__summary">
        <div className="stat-box account-position__main">
          <div className="eyebrow">계정 평가금</div>
          <div className="value-xl">{account ? `$${equity.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '연동 안 됨'}</div>
          <div className="value-sub">가용 {account ? `$${available.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '-'}</div>
        </div>

        <div className="stat-box account-position__main">
          <div className="eyebrow">BTCUSDT 포지션</div>
          <div className={`value-xl ${sideTone}`}>
            {btc ? `${side} ${btc.total} BTC` : '-'}
          </div>
          <div className="value-sub">{btc ? `레버리지 ${btc.leverage ?? '-'}x` : '보유 포지션 없음'}</div>
        </div>
      </div>

      <div className="stat-box account-position__controls">
        <div>
          <div className="eyebrow">수동 주문</div>
          <div className="btn-row">
            <button className="btn-long" onClick={() => place('LONG')} disabled={!account}>LONG</button>
            <button className="btn-short" onClick={() => place('SHORT')} disabled={!account}>SHORT</button>
            <button onClick={() => tradingApi.closePosition()} disabled={!account}>청산</button>
          </div>
        </div>

        <div>
          <div className="eyebrow">자동매매</div>
          <label className="switch-inline" style={{ marginTop: 6 }}>
            <input type="checkbox" checked={Boolean(status?.auto_trade_enabled)} onChange={toggleAuto} />
            <span>{status?.auto_trade_enabled ? 'ON' : 'OFF'}</span>
          </label>
        </div>
      </div>
    </div>
  )
}
