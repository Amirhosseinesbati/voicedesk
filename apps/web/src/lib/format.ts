export function formatDateTime(value: string, timezone = 'America/New_York', options: Intl.DateTimeFormatOptions = {}): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  try {
    return new Intl.DateTimeFormat('en-US', { timeZone: timezone, dateStyle: 'medium', timeStyle: 'short', ...options }).format(date)
  } catch {
    return date.toLocaleString('en-US')
  }
}

export function formatTime(value: string, timezone = 'America/New_York'): string {
  return formatDateTime(value, timezone, { dateStyle: undefined, timeStyle: 'short' })
}

export function formatDay(value: string, timezone = 'America/New_York'): string {
  return formatDateTime(value, timezone, { dateStyle: 'medium', timeStyle: undefined })
}

export function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase() ?? '').join('') || '?'
}

export function localDateInput(date: Date): string {
  const year = date.getFullYear()
  return `${year}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

export function asText(value: unknown): string {
  return typeof value === 'string' || typeof value === 'number' ? String(value) : ''
}
