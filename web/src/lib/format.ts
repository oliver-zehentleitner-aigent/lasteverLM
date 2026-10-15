import { language, t } from '../i18n'

export function formatCents(cents: number): string {
  return (cents / 100).toLocaleString(language(), { style: 'currency', currency: 'EUR' })
}

export function formatTime(iso: string | null): string {
  if (!iso) return t('time.never')
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(language())
}

/** A date in a table cell: day, month and time ("15.10., 20:53" in
 *  German), the year only when it is not this one; the full timestamp
 *  belongs in the tooltip (formatTime). */
export function formatShortTime(iso: string | null, now: Date = new Date()): string {
  if (!iso) return t('time.never')
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const year = d.getFullYear() !== now.getFullYear()
  return d.toLocaleString(language(), { day: '2-digit', month: '2-digit', ...(year ? { year: 'numeric' } : {}), hour: '2-digit', minute: '2-digit' })
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
