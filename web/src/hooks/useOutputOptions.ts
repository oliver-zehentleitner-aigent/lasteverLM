import { useEffect, useState } from 'react'
import { rag } from '../api/rag'
import type { OutputOptionsSpec } from '../api/types'

let cached: Promise<OutputOptionsSpec> | null = null

/** The output options spec, loaded once per page load and shared by every
 *  menu. Null while loading or when rag does not offer it (then documents
 *  are created without options, as before). */
export function useOutputOptions(): OutputOptionsSpec | null {
  const [spec, setSpec] = useState<OutputOptionsSpec | null>(null)
  useEffect(() => {
    let live = true
    cached ??= rag.outputOptions().catch((e: unknown) => {
      cached = null
      throw e
    })
    cached.then(
      (s) => live && setSpec(s),
      () => {
        // no options: the forms hide them
      },
    )
    return () => {
      live = false
    }
  }, [])
  return spec
}
