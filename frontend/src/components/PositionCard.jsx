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

  return (
    <div className="grid-auto" style={{ '--min-col': '150px' }}>
      <div className="stat-box">
        <div className="eyebrow">계정</div>
        <div className="value-lg">{account ? `$${equity.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '연동 안 됨'}</div>
        <div className="value-sub">가용 {account ? `$${available.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '-'}</div>
      </div>
      <div className="stat-box">
        <div className="eyebrow">포지션</div>
        <div className={`value-lg ${btc?.holdSide?.toUpperCase() === 'SHORT' ? 'tone-short' : 'tone-long'}`}>
          {btc ? `${btc.holdSide?.toUpperCase()} ${btc.total} BTC` : '-'}
        </div>
        <div className="value-sub">{btc ? `레버리지 ${btc.leverage ?? '-'}x` : '-'}</div>
      </div>
      <div className="stat-box">
        <div className="eyebrow">수동 주문</div>
        <div className="btn-row">
          <button className="btn-long" onClick={() => place('LONG')} disabled={!account}>LONG</button>
          <button className="btn-short" onClick={() => place('SHORT')} disabled={!account}>SHORT</button>
          <button onClick={() => tradingApi.closePosition()} disabled={!account}>청산</button>
        </div>
      </div>
      <div className="stat-box">
        <div className="eyebrow">자동매매</div>
        <label className="switch-inline">
          <input type="checkbox" checked={Boolean(status?.auto_trade_enabled)} onChange={toggleAuto} />
          <span>{status?.auto_trade_enabled ? 'ON' : 'OFF'}</span>
        </label>
      </div>
    </div>
  )
}
