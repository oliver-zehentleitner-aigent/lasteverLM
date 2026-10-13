import { useEffect, useState } from 'react'
import { WALKER_TRACK, walkerAt } from '../../lib/walker'

const reduced = () => typeof window !== 'undefined' && (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false)

/** A small ASCII figure walking on the spot next to "Generating…", every
 *  250 ms; decorative (aria-hidden) and still when motion is reduced. Its
 *  track has a fixed width, so the text beside it never moves. */
export function Walker() {
  const [tick, setTick] = useState(0)
  useEffect(() => {
    if (reduced()) return
    const timer = setInterval(() => setTick((x) => x + 1), 250)
    return () => clearInterval(timer)
  }, [])
  return (
    <span className="walker" aria-hidden="true" style={{ width: `${WALKER_TRACK + 3}ch` }}>
      {walkerAt(tick)}
    </span>
  )
}
