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

const OUTPUT_KEY = 'lasteverlm.openOutput'

/** A document to select when the notebook opens next, set by the
 *  library's "open"; read once. */
export function writeOpenOutput(id: string): void {
  try {
    window.sessionStorage.setItem(OUTPUT_KEY, id)
  } catch {
    // the notebook opens on its first document instead
  }
}

export function takeOpenOutput(): string | null {
  try {
    const id = window.sessionStorage.getItem(OUTPUT_KEY)
    window.sessionStorage.removeItem(OUTPUT_KEY)
    return id
  } catch {
    return null
  }
}
