import { useState, useEffect } from 'react'
import { api } from '../api'

interface Props { onClose: () => void }

export function CredentialsModal({ onClose }: Props) {
  const [apiKey, setApiKey] = useState('')
  const [secret, setSecret] = useState('')
  const [pass, setPass] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.getCredentials().then((c) => {
      setApiKey(c.api_key || '')
      if (c.has_secret) setSecret('••••••••')
      if (c.has_passphrase) setPass('••••••••')
    })
  }, [])

  const handleSave = async () => {
    setSaving(true)
    await api.saveCredentials(apiKey, secret, pass)
    setSaving(false)
    onClose()
  }

  return (
    <div style={S.overlay} onClick={onClose}>
      <div style={S.modal} onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 16 }}>Bitget API 연동 설정</h3>
        <div style={S.field}>
          <label>API Key</label>
          <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="API Key" style={S.input} />
        </div>
        <div style={S.field}>
          <label>Secret Key</label>
          <input type="password" value={secret} onChange={(e) => setSecret(e.target.value)} placeholder="Secret Key" style={S.input} />
        </div>
        <div style={S.field}>
          <label>Passphrase</label>
          <input type="password" value={pass} onChange={(e) => setPass(e.target.value)} placeholder="Passphrase" style={S.input} />
        </div>
        <p style={{ color: 'var(--yellow)', fontSize: 12, margin: '10px 0' }}>
          ⚠ 실제 주문이 발생합니다. 읽기 전용 키로 먼저 테스트하세요. 자격증명은 로컬 파일에 저장됩니다.
        </p>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button onClick={onClose}>취소</button>
          <button onClick={handleSave} disabled={saving} style={{ borderColor: 'var(--blue)', color: 'var(--blue)' }}>
            {saving ? '저장 중…' : '저장'}
          </button>
        </div>
      </div>
    </div>
  )
}

const S: Record<string, React.CSSProperties> = {
  overlay: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 },
  modal: { background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: 10, padding: 24, width: 400, maxWidth: '90vw' },
  field: { display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 12 },
  input: { width: '100%' },
}
