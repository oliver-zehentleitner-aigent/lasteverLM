export function formatCents(cents: number): string {
  return (cents / 100).toLocaleString(undefined, { style: 'currency', currency: 'EUR' })
}

export function formatTime(iso: string | null): string {
  if (!iso) return 'never'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}
