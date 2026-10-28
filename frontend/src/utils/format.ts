// Форматирование чисел, объёмов и дат для интерфейса

/** Объём в мегабайтах → «1,5 ГБ», «512 МБ» */
export function formatMb(mb: number | null | undefined): string {
  if (mb === null || mb === undefined) return '—'
  if (mb >= 1024 * 1024) return `${(mb / 1024 / 1024).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ТБ`
  if (mb >= 1024) return `${(mb / 1024).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ГБ`
  return `${mb.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} МБ`
}

/** Размер в байтах → «12,3 КБ» */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return '—'
  const units = ['Б', 'КБ', 'МБ', 'ГБ']
  let value = bytes
  let i = 0
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024
    i += 1
  }
  return `${value.toLocaleString('ru-RU', { maximumFractionDigits: i === 0 ? 0 : 1 })} ${units[i]}`
}

/** ISO-дата → «10.10.2026 14:23» */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** Аптайм в секундах → «3 д 4 ч 12 мин» */
export function formatUptime(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || seconds < 0) return '—'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const parts: string[] = []
  if (days) parts.push(`${days} д`)
  if (days || hours) parts.push(`${hours} ч`)
  parts.push(`${minutes} мин`)
  return parts.join(' ')
}

/** Целое число с разделителями тысяч */
export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return value.toLocaleString('ru-RU')
}

/** Квота: «120 МБ / 1 ГБ» или «120 МБ / без лимита» */
export function formatQuota(usedMb: number, quotaMb: number | null): string {
  return `${formatMb(usedMb)} / ${quotaMb ? formatMb(quotaMb) : 'без лимита'}`
}

/** Процент заполнения квоты (0–100), null — лимита нет */
export function quotaPercent(usedMb: number, quotaMb: number | null): number | null {
  if (!quotaMb || quotaMb <= 0) return null
  return Math.min(100, Math.round((usedMb / quotaMb) * 100))
}

/** Простая проверка адреса e-mail для форм */
export function isEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim())
}

/** Проверка имени домена */
export function isDomainName(value: string): boolean {
  return /^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9-]{2,63}$/i.test(value.trim())
}

/** Локальная часть адреса (до @) */
export function isLocalPart(value: string): boolean {
  return /^[a-z0-9._+-]+$/i.test(value.trim())
}
