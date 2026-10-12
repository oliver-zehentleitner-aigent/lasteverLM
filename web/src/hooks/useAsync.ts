import { useCallback, useState } from 'react'

/** Tracks one in-flight action and its last error, so every pane shows the
 *  same busy and error states without each one re-implementing them. */
export function useAsync() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true)
    setError(null)
    try {
      return await fn()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      return undefined
    } finally {
      setBusy(false)
    }
  }, [])

  return { busy, error, run, clearError: () => setError(null) }
}
