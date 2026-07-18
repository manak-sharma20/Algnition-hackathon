import React, { useEffect, useRef } from 'react'

// A small self-rotating wireframe world for Battle View's parallel
// strategy worlds. Non-interactive; tint shifts when its world is winning.
const TWO_PI = Math.PI * 2

export default function MiniGlobe({ size = 150, highlight = false }) {
  const canvasRef = useRef(null)
  const highlightRef = useRef(highlight)
  highlightRef.current = highlight

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    canvas.width = size * dpr
    canvas.height = size * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    let rot = Math.random() * TWO_PI
    let glow = 0
    const R = size * 0.34
    const cx = size / 2
    const cy = size / 2
    const TILT = -0.4

    function project(lat, lon) {
      const x = Math.cos(lat) * Math.cos(lon + rot)
      const y = Math.sin(lat)
      const z = Math.cos(lat) * Math.sin(lon + rot)
      const y2 = y * Math.cos(TILT) - z * Math.sin(TILT)
      const z2 = y * Math.sin(TILT) + z * Math.cos(TILT)
      return { x: cx + x * R, y: cy - y2 * R, z: z2 }
    }

    function frame() {
      rot += reduced ? 0 : 0.004
      glow += ((highlightRef.current ? 1 : 0) - glow) * 0.06
      ctx.clearRect(0, 0, size, size)

      // winning world warms up
      if (glow > 0.02) {
        const halo = ctx.createRadialGradient(cx, cy, 0, cx, cy, size / 2)
        halo.addColorStop(0, `rgba(12,163,12,${(0.10 * glow).toFixed(3)})`)
        halo.addColorStop(1, 'rgba(12,163,12,0)')
        ctx.fillStyle = halo
        ctx.fillRect(0, 0, size, size)
      }

      const SEG = 40
      ctx.lineWidth = 1
      for (let m = 0; m < 8; m++) {
        const lon = (m / 8) * TWO_PI
        let prev = project(-Math.PI / 2, lon)
        for (let s = 1; s <= SEG; s++) {
          const cur = project(-Math.PI / 2 + (s / SEG) * Math.PI, lon)
          const depth = ((prev.z + cur.z) / 2 + 1) * 0.5
          ctx.strokeStyle = `rgba(255,255,255,${(0.09 + 0.3 * depth).toFixed(3)})`
          ctx.beginPath()
          ctx.moveTo(prev.x, prev.y)
          ctx.lineTo(cur.x, cur.y)
          ctx.stroke()
          prev = cur
        }
      }
      for (const deg of [-45, -15, 15, 45]) {
        const lat = (deg * Math.PI) / 180
        let prev = project(lat, 0)
        for (let s = 1; s <= SEG; s++) {
          const cur = project(lat, (s / SEG) * TWO_PI)
          const depth = ((prev.z + cur.z) / 2 + 1) * 0.5
          ctx.strokeStyle = `rgba(255,255,255,${(0.09 + 0.3 * depth).toFixed(3)})`
          ctx.beginPath()
          ctx.moveTo(prev.x, prev.y)
          ctx.lineTo(cur.x, cur.y)
          ctx.stroke()
          prev = cur
        }
      }

      // pedestal ring
      ctx.strokeStyle = `rgba(255,255,255,0.18)`
      ctx.beginPath()
      ctx.ellipse(cx, cy + R * 1.35, R * 1.25, R * 0.3, 0, 0, TWO_PI)
      ctx.stroke()

      rafId = requestAnimationFrame(frame)
    }
    let rafId = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(rafId)
  }, [size])

  return <canvas ref={canvasRef} style={{ width: size, height: size }} aria-hidden="true" />
}
