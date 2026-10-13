import { language, t } from '../i18n'

export function formatCents(cents: number): string {
  return (cents / 100).toLocaleString(language(), { style: 'currency', currency: 'EUR' })
}

export function formatTime(iso: string | null): string {
  if (!iso) return t('time.never')
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(language())
}

export function formatBytes(bytes: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = bytes
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i += 1
  }
  return `${i === 0 ? v : v.toFixed(1)} ${units[i]}`
}
