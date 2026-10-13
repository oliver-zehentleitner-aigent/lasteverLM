import { Component, type ReactNode } from 'react'

interface Props {
  /** what failed, for the sentence shown instead */
  what: string
  children: ReactNode
}

/** Keeps a failing part (a lazily loaded chart library, say) from blanking
 *  the whole app: it shows one sentence in its place, the rest stays. */
export class ErrorBoundary extends Component<Props, { error: string | null }> {
  state = { error: null as string | null }

  static getDerivedStateFromError(e: unknown) {
    return { error: e instanceof Error ? e.message : String(e) }
  }

  render() {
    if (this.state.error) {
      return (
        <p className="error">
          {this.props.what} could not be shown: {this.state.error}
        </p>
      )
    }
    return this.props.children
  }
}
