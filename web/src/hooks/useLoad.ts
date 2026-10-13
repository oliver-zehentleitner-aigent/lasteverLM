import { useEffect, useState } from 'react'
import { useAsync } from './useAsync'

/** Load once on mount, expose the same busy/error/run as useAsync. */
export function useLoad<T>(load: () => Promise<T>, initial: T) {
  const [data, setData] = useState<T>(initial)
  const { busy, error, run } = useAsync()
  useEffect(() => {
    void run(async () => setData(await load()))
  }, [load, run])
  return { data, setData, busy, error, run }
}
