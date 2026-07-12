// 역할: 현재 포지션과 진입 정보를 표시하는 컴포넌트.
function num(v) {
  const n = Number(v ?? 0)
  return Number.isFinite(n) ? n : 0
}

function money(value) {
  const n = num(value)
  return n ? `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '-'
}

function pct(value) {
  const n = num(value)
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toFixed(2)}%`
}

function paperPnl(direction, entry, current) {
  const e = num(entry)
  const c = num(current)
  if (!e || !c) return 0
  const gross = direction === 'SHORT' ? ((e - c) / e) * 100 : ((c - e) / e) * 100
  return gross - 0.12
}

export function PositionCard({ account, positions, status, price }) {
  const btc = positions.find((p) => p.symbol === 'BTCUSDT')
  const paper = status?.paper_position
  const paperAccount = status?.paper_account
  const equity = num(account?.accountEquity ?? account?.equity)
  const available = num(account?.available ?? account?.crossMaxAvailable)
  const apiConnected = Boolean(account)
  const usingPaper = status?.trading_mode === 'PAPER_TRADING'
  const displayEquity = usingPaper ? num(paperAccount?.equity) : equity
  const accountLabel = usingPaper ? '모의 자산' : '전체 자산'
  const accountSub = !usingPaper
    ? `가용 $${available.toLocaleString('en-US', { minimumFractionDigits: 2 })}`
    : `확정 $${num(paperAccount?.balance).toFixed(2)} · ${num(paperAccount?.leverage || 20)}배 운용`
  const accountTone = usingPaper && displayEquity
    ? displayEquity >= num(paperAccount?.initial_balance || 100) ? 'tone-long' : 'tone-short'
    : ''
  const hasPaper = !btc && Boolean(paper)
  const currentPrice = hasPaper ? num(price ?? paper?.current_price) : num(price)

  const side = hasPaper ? paper?.direction : btc?.holdSide?.toUpperCase()
  const paperPnlPct = hasPaper && paper?.pnl_pct != null ? num(paper.pnl_pct) : hasPaper ? paperPnl(side, paper?.entry_price, currentPrice || paper?.current_price) : 0
  const pnlTone = paperPnlPct > 0 ? 'tone-long' : paperPnlPct < 0 ? 'tone-short' : 'tone-muted'

  return (
    <div className="account-position">
      <div className="account-position__summary">
        <div className="stat-box account-position__main">
          <div className="eyebrow">계정 연동</div>
          <div className={`account-connection ${apiConnected ? 'tone-long' : 'tone-muted'}`}>{apiConnected ? 'ON' : 'OFF'}</div>
          <div className="value-sub">{apiConnected ? 'Bitget 계정 연결됨' : 'API 계정 미연동'}</div>
        </div>

        <div className="stat-box account-position__main">
          <div className="eyebrow">{accountLabel}</div>
          <div className={`value-xl ${accountTone}`}>
            {displayEquity ? `$${displayEquity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '-'}
          </div>
          <div className="value-sub">{accountSub}</div>
        </div>
      </div>

      {hasPaper && (
        <div className="paper-position">
          <div className="paper-position__row">
            <div>
              <span className="eyebrow">진입가</span>
              <strong>{money(paper?.entry_price)}</strong>
            </div>
            <div>
              <span className="eyebrow">현재가</span>
              <strong>{money(currentPrice || paper?.current_price)}</strong>
            </div>
            <div>
              <span className="eyebrow">수수료 차감 손익률</span>
              <strong className={pnlTone}>{pct(paperPnlPct)}</strong>
              <small>왕복 수수료 {pct(paper?.fee_pct ?? 0.12)}</small>
            </div>
          </div>

          <div className="paper-position__levels">
            <div>
              <span className="eyebrow">손절가</span>
              <strong className="tone-short">{money(paper?.stop_loss)}</strong>
            </div>
            <div>
              <span className="eyebrow">1차 익절</span>
              <strong className="tone-long">{money(paper?.take_profit_1)}</strong>
            </div>
            <div>
              <span className="eyebrow">2차 익절</span>
              <strong className="tone-long">{money(paper?.take_profit_2)}</strong>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
