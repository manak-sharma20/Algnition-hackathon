import { useEffect, useRef, useState } from 'react'

// Numeric display that rolls smoothly between values instead of snapping.
// Purely presentational: formats whatever value it is handed.
export default function RollingNumber({ value, format = (v) => v, duration = 900, className = '' }) {
  const safe = Number.isFinite(value) ? value : 0
  const [display, setDisplay] = useState(0)
  const fromRef = useRef(0)
  const rafRef = useRef(null)

  useEffect(() => {
    const from = fromRef.current
    const to = safe
    if (from === to) return undefined

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced) {
      fromRef.current = to
      setDisplay(to)
      return undefined
    }

    const start = performance.now()
    function tick(now) {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      const current = from + (to - from) * eased
      setDisplay(current)
      fromRef.current = current
      if (t < 1) rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [safe, duration])

  return <span className={className}>{format(display)}</span>
}
