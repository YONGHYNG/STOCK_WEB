// 역할: 현재 포지션과 진입 정보, Bitget API 연동을 표시하는 컴포넌트.
import { useState } from 'react'
import { tradingApi } from '../api/tradingApi'
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

export function PositionCard({ account, positions, status, price, trades = [] }) {
  const [apiModalOpen, setApiModalOpen] = useState(false)
  const [credentials, setCredentials] = useState({ api_key: '', secret_key: '', passphrase: '' })
  const [credentialState, setCredentialState] = useState({ saving: false, message: '', ok: false })
  const btc = positions.find((p) => p.symbol === 'BTCUSDT')
  const openPaperTrade = trades.find((trade) => trade.trade_type === 'PAPER' && trade.exit_price == null)
  const paper = status?.paper_position ?? (openPaperTrade ? {
    direction: openPaperTrade.direction,
    entry_price: openPaperTrade.entry_price,
    stop_loss: openPaperTrade.stop_loss,
    take_profit_1: openPaperTrade.take_profit_1,
    take_profit_2: openPaperTrade.take_profit_2,
    fee_pct: 0.12,
  } : null)
  const paperAccount = status?.paper_account
  const equity = num(account?.accountEquity ?? account?.equity)
  const available = num(account?.available ?? account?.crossedMaxAvailable ?? account?.crossMaxAvailable)
  const apiConnected = Boolean(account)
  const apiConfigured = Boolean(status?.api_configured)
  const apiConnectionLabel = apiConnected ? 'ON' : apiConfigured ? '연결 중' : 'OFF'
  const displayEquity = apiConnected ? equity : num(paperAccount?.equity)
  const accountLabel = apiConnected ? 'Bitget 실제 자산' : '모의 자산'
  const accountSub = apiConnected
    ? `실제 가용 $${available.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : `확정 $${num(paperAccount?.balance).toFixed(2)} · ${num(paperAccount?.leverage || 20)}배 운용`
  const accountTone = !apiConnected && displayEquity
    ? displayEquity >= num(paperAccount?.initial_balance || 100) ? 'tone-long' : 'tone-short'
    : ''
  const hasPaper = !btc && Boolean(paper)
  const currentPrice = hasPaper ? num(price ?? paper?.current_price) : num(price)

  const side = hasPaper ? paper?.direction : btc?.holdSide?.toUpperCase()
  const paperPnlPct = hasPaper && paper?.pnl_pct != null ? num(paper.pnl_pct) : hasPaper ? paperPnl(side, paper?.entry_price, currentPrice || paper?.current_price) : 0
  const pnlTone = paperPnlPct > 0 ? 'tone-long' : paperPnlPct < 0 ? 'tone-short' : 'tone-muted'

  async function openApiModal() {
    setCredentialState({ saving: false, message: '', ok: false })
    if (apiConnected) {
      setApiModalOpen(true)
      return
    }
    try {
      const saved = await tradingApi.getCredentials()
      setCredentials({ api_key: saved?.api_key ?? '', secret_key: '', passphrase: '' })
    } catch {
      setCredentials({ api_key: '', secret_key: '', passphrase: '' })
    }
    setApiModalOpen(true)
  }

  async function disconnectApi() {
    setCredentialState({ saving: true, message: '실거래 연동을 종료하고 있습니다...', ok: false })
    try {
      const result = await tradingApi.disconnectCredentials()
      if (!result?.ok) throw new Error(result?.error || '연동 종료에 실패했습니다.')
      setCredentialState({ saving: false, message: '', ok: true })
      setApiModalOpen(false)
    } catch (error) {
      setCredentialState({ saving: false, message: error?.message || '연동 종료에 실패했습니다.', ok: false })
    }
  }

  async function connectApi(event) {
    event.preventDefault()
    if (!credentials.api_key.trim() || !credentials.secret_key.trim() || !credentials.passphrase.trim()) {
      setCredentialState({ saving: false, message: '세 항목을 모두 입력해 주세요.', ok: false })
      return
    }
    setCredentialState({ saving: true, message: 'Bitget 계정을 확인하고 있습니다...', ok: false })
    try {
      const result = await tradingApi.saveCredentials({
        api_key: credentials.api_key.trim(),
        secret_key: credentials.secret_key.trim(),
        passphrase: credentials.passphrase.trim(),
      })
      if (!result?.ok || !result?.connected) throw new Error(result?.error || '연결에 실패했습니다.')
      setCredentialState({ saving: false, message: 'Bitget 계정 연동에 성공했습니다.', ok: true })
      setCredentials((current) => ({ ...current, secret_key: '', passphrase: '' }))
      setApiModalOpen(false)
    } catch (error) {
      setCredentialState({ saving: false, message: error?.message || '연결에 실패했습니다.', ok: false })
    }
  }

  return (
    <div className="account-position">
      <div className="account-position__summary">
        <button type="button" className="stat-box account-position__main account-link-card" onClick={openApiModal}>
          <div className="eyebrow">계정 연동</div>
          <div className={`account-connection ${apiConnected ? 'tone-long' : apiConfigured ? 'tone-wait' : 'tone-muted'}`}>{apiConnectionLabel}</div>
          <div className="value-sub">{apiConnected ? 'Bitget 계정 연결됨 · 클릭하여 변경' : apiConfigured ? '저장된 API로 계정 확인 중' : '클릭하여 API 계정 연결'}</div>
        </button>

        <div className="stat-box account-position__main">
          <div className="eyebrow">{accountLabel}</div>
          <div className={`value-xl ${accountTone}`}>
            {apiConnected || displayEquity
              ? `$${displayEquity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
              : '-'}
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

      {apiModalOpen && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => !credentialState.saving && setApiModalOpen(false)}>
          <section className="api-connect-modal" role="dialog" aria-modal="true" aria-labelledby="api-connect-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="api-connect-modal__header">
              <div>
                <h3 id="api-connect-title">{apiConnected ? 'Bitget 계정 연동 종료' : 'Bitget API 계정 연동'}</h3>
                <p>{apiConnected ? '연동을 종료하면 API 정보가 삭제되고 자동매매가 꺼집니다.' : '입력값은 이 PC에만 저장되며, 실제 연결 조회가 성공해야 저장됩니다.'}</p>
              </div>
              <button type="button" className="modal-close" aria-label="닫기" onClick={() => setApiModalOpen(false)} disabled={credentialState.saving}>×</button>
            </div>
            {apiConnected ? (
              <div className="api-connect-form">
                <div className="api-disconnect-confirm">실거래 자동매매 연동을 종료하시겠습니까?</div>
                <div className="api-connect-warning">미체결 실거래 주문은 취소됩니다. 보유 중인 실거래 포지션이 있으면 안전을 위해 연동 종료가 차단됩니다.</div>
                {credentialState.message && <div className="api-connect-result tone-wait">{credentialState.message}</div>}
                <div className="api-connect-actions">
                  <button type="button" onClick={() => setApiModalOpen(false)} disabled={credentialState.saving}>취소</button>
                  <button type="button" className="api-disconnect-submit" onClick={disconnectApi} disabled={credentialState.saving}>{credentialState.saving ? '종료 중...' : '승인하고 종료'}</button>
                </div>
              </div>
            ) : <form className="api-connect-form" onSubmit={connectApi}>
              <label>API Key<input value={credentials.api_key} onChange={(e) => setCredentials({ ...credentials, api_key: e.target.value })} autoComplete="off" /></label>
              <label>Secret Key<input type="password" value={credentials.secret_key} onChange={(e) => setCredentials({ ...credentials, secret_key: e.target.value })} autoComplete="new-password" /></label>
              <label>Passphrase<input type="password" value={credentials.passphrase} onChange={(e) => setCredentials({ ...credentials, passphrase: e.target.value })} autoComplete="new-password" /></label>
              <div className="api-connect-warning">출금·자금이체 권한은 켜지 마세요. 처음에는 읽기 전용 키로 연결을 확인하세요.</div>
              {credentialState.message && <div className={credentialState.ok ? 'api-connect-result tone-long' : 'api-connect-result tone-wait'}>{credentialState.message}</div>}
              <div className="api-connect-actions">
                <button type="button" onClick={() => setApiModalOpen(false)} disabled={credentialState.saving}>취소</button>
                <button type="submit" className="api-connect-submit" disabled={credentialState.saving}>{credentialState.saving ? '연결 확인 중...' : '저장하고 연결'}</button>
              </div>
            </form>}
          </section>
        </div>
      )}
    </div>
  )
}
