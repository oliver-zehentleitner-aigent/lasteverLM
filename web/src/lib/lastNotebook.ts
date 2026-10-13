const KEY = 'lasteverlm.notebook'

/** The notebook the workspace opens with: the last one used in this
 *  browser. Storage may be blocked; then the first notebook opens. */
export function readLastNotebook(): string | null {
  try {
    return window.localStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function writeLastNotebook(id: string): void {
  try {
    window.localStorage.setItem(KEY, id)
  } catch {
    // not remembered; the first notebook is selected on the next load
  }
}
