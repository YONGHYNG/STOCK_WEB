// 역할: 백엔드가 UTC로 내려주는 시간 문자열을 한국 표준시(KST)로 변환.
export function toKst(value) {
  if (!value) return '-'
  const raw = String(value).trim()
  const iso = raw.includes('T') ? raw : raw.replace(' ', 'T')
  // 타임존 표시가 없으면 SQLite CURRENT_TIMESTAMP(UTC)로 간주하고 'Z'를 붙임
  const withZone = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`
  const date = new Date(withZone)
  if (Number.isNaN(date.getTime())) return raw.slice(0, 16)
  // sv-SE 로케일은 "YYYY-MM-DD HH:MM" 형식을 그대로 반환해 별도 조합이 필요 없음
  return new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date).replace('T', ' ')
}
