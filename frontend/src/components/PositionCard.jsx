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
    <div style={S.grid}>
      <div style={S.box}>
        <div style={S.label}>계정</div>
        <div style={S.big}>{account ? `$${equity.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '연동 안 됨'}</div>
        <div style={S.sub}>가용 {account ? `$${available.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '-'}</div>
      </div>
      <div style={S.box}>
        <div style={S.label}>포지션</div>
        <div style={{ ...S.big, color: btc?.holdSide?.toUpperCase() === 'SHORT' ? 'var(--red)' : 'var(--green)' }}>
          {btc ? `${btc.holdSide?.toUpperCase()} ${btc.total} BTC` : '-'}
        </div>
        <div style={S.sub}>{btc ? `레버리지 ${btc.leverage ?? '-'}x` : 'No BTCUSDT position'}</div>
      </div>
      <div style={S.box}>
        <div style={S.label}>수동 주문</div>
        <div style={S.buttons}>
          <button onClick={() => place('LONG')} disabled={!account} style={{ color: 'var(--green)', borderColor: 'var(--green)' }}>LONG</button>
          <button onClick={() => place('SHORT')} disabled={!account} style={{ color: 'var(--red)', borderColor: 'var(--red)' }}>SHORT</button>
          <button onClick={() => tradingApi.closePosition()} disabled={!account}>청산</button>
        </div>
      </div>
      <div style={S.box}>
        <div style={S.label}>자동매매</div>
        <label style={S.check}>
          <input type="checkbox" checked={Boolean(status?.auto_trade_enabled)} onChange={toggleAuto} />
          <span>{status?.auto_trade_enabled ? 'ON' : 'OFF'}</span>
        </label>
      </div>
    </div>
  )
}

const S = {
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 },
  box: { background: 'rgba(255,255,255,0.026)', border: '1px solid var(--border-soft)', borderRadius: 8, padding: 12 },
  label: { fontSize: 11, fontWeight: 800, color: 'var(--text2)', marginBottom: 8 },
  big: { fontSize: 18, fontWeight: 850 },
  sub: { color: 'var(--text2)', fontSize: 12, marginTop: 5 },
  buttons: { display: 'flex', flexWrap: 'wrap', gap: 6 },
  check: { display: 'flex', gap: 8, alignItems: 'center' },
}
