import React, { useRef } from 'react'

// Floating information module: breathes on a slow cycle, leans a few pixels
// toward the cursor (magnetic), and carries a cursor-proximity light.
// Purely presentational wrapper — children own all behavior.
export default function FloatingPanel({ children, className = '', floatDelay = 0, style }) {
  const ref = useRef(null)

  function handleMove(e) {
    const el = ref.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    el.style.setProperty('--mx', `${x}px`)
    el.style.setProperty('--my', `${y}px`)
    el.style.setProperty('--tx', `${(x / rect.width - 0.5) * 5}px`)
    el.style.setProperty('--ty', `${(y / rect.height - 0.5) * 4}px`)
    el.style.setProperty('--glow', '1')
  }

  function handleLeave() {
    const el = ref.current
    if (!el) return
    el.style.setProperty('--tx', '0px')
    el.style.setProperty('--ty', '0px')
    el.style.setProperty('--glow', '0')
  }

  return (
    <div className="float-wrap" style={{ animationDelay: `${floatDelay}s` }}>
      <div
        ref={ref}
        onMouseMove={handleMove}
        onMouseLeave={handleLeave}
        className={`panel ${className}`}
        style={style}
      >
        {children}
      </div>
    </div>
  )
}
