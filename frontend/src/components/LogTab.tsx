import { useEffect, useRef } from 'react'

interface Props { logs: string[] }

export function LogTab({ logs }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  return (
    <div style={S.container}>
      {logs.length === 0 && <div style={{ ...S.line, color: 'var(--text2)' }}>로그 수신 대기 중</div>}
      {logs.map((line, i) => (
        <div key={i} style={{
          ...S.line,
          color: line.includes('[ERROR]') || line.includes('[FAIL]') ? 'var(--red)'
            : line.includes('[자동매매]') || line.includes('[모의매매]') ? 'var(--blue)'
            : line.includes('익절') ? 'var(--green)'
            : line.includes('손절') ? 'var(--red)'
            : line.includes('[WARN]') ? 'var(--yellow)'
            : 'var(--text2)',
        }}>{line}</div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}

const S: Record<string, React.CSSProperties> = {
  container: { height: 300, overflowY: 'auto', padding: '12px 14px', background: 'rgba(0,0,0,0.26)', border: '1px solid var(--border-soft)', borderRadius: 8, fontFamily: 'Consolas, ui-monospace, monospace', fontSize: 12 },
  line: { lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-all' },
}
