import React, { useEffect, useRef } from 'react'
import { CHANNEL_META } from '../utils/forecast'

// The intelligence engine at the heart of the interface: a draggable
// wireframe globe with the three ad platforms orbiting as nodes, data
// streams flowing toward the core, a circular platform floor beneath,
// and a cinematic camera that reframes per section.
//
// Purely presentational. The only outbound signal is onSelectChannel
// when a node is clicked.

const CHANNEL_KEYS = ['google', 'meta', 'ms']
const TWO_PI = Math.PI * 2
const TILT = -0.42 // camera looks slightly down at the table

// Camera framing per section — lerped every frame for cinematic moves.
const VIEWS = {
  command: { scale: 1, cy: 0.5, dim: 1, nodes: 1, streams: 1, platform: 1 },
  verdict: { scale: 0.62, cy: 0.38, dim: 0.4, nodes: 0.45, streams: 0.3, platform: 0.45 },
  battle: { scale: 0.55, cy: 0.46, dim: 0.14, nodes: 0, streams: 0, platform: 0.18 },
}

function spherePoint(lat, lon) {
  return [Math.cos(lat) * Math.cos(lon), Math.sin(lat), Math.cos(lat) * Math.sin(lon)]
}

function buildWireframe() {
  const lines = []
  const SEG = 60
  for (let m = 0; m < 12; m++) {
    const lon = (m / 12) * TWO_PI
    const pts = []
    for (let s = 0; s <= SEG; s++) pts.push(spherePoint(-Math.PI / 2 + (s / SEG) * Math.PI, lon))
    lines.push(pts)
  }
  for (const deg of [-60, -40, -20, 0, 20, 40, 60]) {
    const lat = (deg * Math.PI) / 180
    const pts = []
    for (let s = 0; s <= SEG; s++) pts.push(spherePoint(lat, (s / SEG) * TWO_PI))
    lines.push(pts)
  }
  return lines
}

export default function GlobeScene({ mode = 'command', activeChannel = null, onSelectChannel }) {
  const canvasRef = useRef(null)
  const propsRef = useRef({ mode, activeChannel, onSelectChannel })
  propsRef.current = { mode, activeChannel, onSelectChannel }

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const wire = buildWireframe()

    // Static starfield (fractions of viewport, so resize keeps composition)
    const stars = Array.from({ length: 110 }, () => ({
      x: Math.random(),
      y: Math.random(),
      r: 0.4 + Math.random() * 0.9,
      phase: Math.random() * TWO_PI,
      speed: 0.3 + Math.random() * 0.7,
    }))

    const state = {
      w: 0,
      h: 0,
      rotY: -0.9,
      vel: 0,
      tiltOffset: 0,
      targetRot: null,
      dragging: false,
      pointerDown: false,
      lastX: 0,
      lastY: 0,
      downX: 0,
      downY: 0,
      view: { ...VIEWS.command },
      particles: [],
      nodeHits: [], // {key, x, y, r}
      t: 0,
    }

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      state.w = window.innerWidth
      state.h = window.innerHeight
      canvas.width = state.w * dpr
      canvas.height = state.h * dpr
      canvas.style.width = `${state.w}px`
      canvas.style.height = `${state.h}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    window.addEventListener('resize', resize)

    // Rotate a globe-frame point into camera space, then project.
    function project(p, cx, cy, R) {
      const [x, y, z] = p
      const ry = state.rotY
      const x1 = x * Math.cos(ry) + z * Math.sin(ry)
      const z1 = -x * Math.sin(ry) + z * Math.cos(ry)
      const tilt = TILT + state.tiltOffset
      const y2 = y * Math.cos(tilt) - z1 * Math.sin(tilt)
      const z2 = y * Math.sin(tilt) + z1 * Math.cos(tilt)
      const s = 3.6 / (3.6 - z2)
      return { x: cx + x1 * R * s, y: cy - y2 * R * s, z: z2, s }
    }

    // Quadratic bezier in globe frame: node -> lifted midpoint -> core surface
    function streamPoint(a, b, t) {
      const mid = [(a[0] + b[0]) * 0.55, (a[1] + b[1]) * 0.5 + 0.85, (a[2] + b[2]) * 0.55]
      const u = 1 - t
      return [
        u * u * a[0] + 2 * u * t * mid[0] + t * t * b[0],
        u * u * a[1] + 2 * u * t * mid[1] + t * t * b[1],
        u * u * a[2] + 2 * u * t * mid[2] + t * t * b[2],
      ]
    }

    function nodePosition(i) {
      const angle = (i / CHANNEL_KEYS.length) * TWO_PI
      return [Math.cos(angle) * 1.62, -0.18, Math.sin(angle) * 1.62]
    }

    function frame() {
      const { mode: m, activeChannel: active } = propsRef.current
      state.t += 1

      // — camera framing lerp —
      const target = VIEWS[m] ?? VIEWS.command
      for (const k of Object.keys(target)) {
        state.view[k] += (target[k] - state.view[k]) * 0.055
      }
      const view = state.view

      // — rotation dynamics —
      if (!state.pointerDown) {
        state.rotY += state.vel
        state.vel *= 0.95
        state.tiltOffset *= 0.92
        if (state.targetRot != null && Math.abs(state.vel) < 0.003) {
          const delta = state.targetRot - state.rotY
          state.rotY += delta * 0.055
          if (Math.abs(delta) < 0.002) state.targetRot = null
        } else if (state.targetRot == null && Math.abs(state.vel) < 0.0015 && !reduced) {
          state.rotY += 0.0011 // idle drift
        }
      }

      const w = state.w
      const h = state.h
      ctx.clearRect(0, 0, w, h)

      const R = Math.min(w, h) * 0.215 * view.scale
      const cx = w / 2
      const cy = h * (view.cy - 0.03)
      const dim = view.dim

      // — starfield —
      for (const st of stars) {
        const tw = reduced ? 0.5 : 0.35 + 0.3 * Math.sin(state.t * 0.01 * st.speed + st.phase)
        ctx.fillStyle = `rgba(255,255,255,${(0.16 * tw).toFixed(3)})`
        ctx.beginPath()
        ctx.arc(st.x * w, st.y * h, st.r, 0, TWO_PI)
        ctx.fill()
      }

      // — volumetric shaft above the globe —
      if (dim > 0.05) {
        const beam = ctx.createLinearGradient(cx, cy - R * 3.2, cx, cy)
        beam.addColorStop(0, 'rgba(255,255,255,0)')
        beam.addColorStop(1, `rgba(255,255,255,${(0.022 * dim).toFixed(3)})`)
        ctx.fillStyle = beam
        ctx.beginPath()
        ctx.moveTo(cx - R * 0.32, cy - R * 3.2)
        ctx.lineTo(cx + R * 0.32, cy - R * 3.2)
        ctx.lineTo(cx + R * 0.85, cy)
        ctx.lineTo(cx - R * 0.85, cy)
        ctx.closePath()
        ctx.fill()
      }

      // — platform floor —
      const platformAlpha = view.platform * dim
      if (platformAlpha > 0.02) {
        const py = cy + R * 1.42
        const glow = ctx.createRadialGradient(cx, py, 0, cx, py, R * 2.1)
        glow.addColorStop(0, `rgba(255,255,255,${(0.05 * platformAlpha).toFixed(3)})`)
        glow.addColorStop(1, 'rgba(255,255,255,0)')
        ctx.fillStyle = glow
        ctx.beginPath()
        ctx.ellipse(cx, py, R * 2.1, R * 0.58, 0, 0, TWO_PI)
        ctx.fill()

        for (const [rr, a] of [
          [1.05, 0.16],
          [1.5, 0.11],
          [1.95, 0.07],
        ]) {
          ctx.strokeStyle = `rgba(255,255,255,${(a * platformAlpha).toFixed(3)})`
          ctx.lineWidth = 1
          ctx.beginPath()
          ctx.ellipse(cx, py, R * rr, R * rr * 0.26, 0, 0, TWO_PI)
          ctx.stroke()
        }
        // rotating survey ticks on the outer ring
        const tickRot = reduced ? 0 : state.t * 0.0008
        ctx.strokeStyle = `rgba(255,255,255,${(0.14 * platformAlpha).toFixed(3)})`
        for (let i = 0; i < 48; i++) {
          const a = (i / 48) * TWO_PI + tickRot
          const r1 = R * 1.95
          const r2 = R * (i % 4 === 0 ? 2.05 : 2.0)
          ctx.beginPath()
          ctx.moveTo(cx + Math.cos(a) * r1, py + Math.sin(a) * r1 * 0.26)
          ctx.lineTo(cx + Math.cos(a) * r2, py + Math.sin(a) * r2 * 0.26)
          ctx.stroke()
        }
      }

      // — wireframe globe, depth-shaded, batched by alpha bucket —
      const buckets = new Map()
      for (const line of wire) {
        let prev = project(line[0], cx, cy, R)
        for (let i = 1; i < line.length; i++) {
          const cur = project(line[i], cx, cy, R)
          const depth = (prev.z + cur.z) / 2 // -1 back … +1 front
          const alpha = (0.035 + 0.16 * (depth + 1) * 0.5) * dim
          const bucket = Math.round(alpha * 40)
          if (bucket > 0) {
            let path = buckets.get(bucket)
            if (!path) {
              path = new Path2D()
              buckets.set(bucket, path)
            }
            path.moveTo(prev.x, prev.y)
            path.lineTo(cur.x, cur.y)
          }
          prev = cur
        }
      }
      ctx.lineWidth = 1
      for (const [bucket, path] of buckets) {
        ctx.strokeStyle = `rgba(255,255,255,${(bucket / 40).toFixed(3)})`
        ctx.stroke(path)
      }

      // core glow at the heart of the globe
      if (dim > 0.05) {
        const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 0.55)
        core.addColorStop(0, `rgba(255,255,255,${(0.10 * dim).toFixed(3)})`)
        core.addColorStop(1, 'rgba(255,255,255,0)')
        ctx.fillStyle = core
        ctx.beginPath()
        ctx.arc(cx, cy, R * 0.55, 0, TWO_PI)
        ctx.fill()
      }

      // — data streams —
      if (view.streams > 0.03 && !reduced) {
        const spawnEvery = 26
        if (state.t % spawnEvery === 0 && state.particles.length < 70) {
          CHANNEL_KEYS.forEach((key, i) => {
            const isActive = active === key
            const rate = isActive ? 3 : active ? 1 : 2
            for (let n = 0; n < rate; n++) {
              state.particles.push({
                i,
                key,
                t: -n * 0.08,
                speed: 0.005 + Math.random() * 0.004,
              })
            }
          })
        }
        for (let pi = state.particles.length - 1; pi >= 0; pi--) {
          const p = state.particles[pi]
          p.t += p.speed
          if (p.t >= 1) {
            state.particles.splice(pi, 1)
            continue
          }
          if (p.t < 0) continue
          const src = nodePosition(p.i)
          const dstDir = 1 / Math.hypot(src[0], src[1], src[2])
          const dst = [src[0] * dstDir, src[1] * dstDir + 0.15, src[2] * dstDir]
          const pos = streamPoint(src, dst, p.t)
          const tail = streamPoint(src, dst, Math.max(0, p.t - 0.055))
          const a = project(pos, cx, cy, R)
          const b = project(tail, cx, cy, R)
          const depthA = (a.z + 1) * 0.5
          const boost = active === p.key ? 1.5 : 1
          const alpha = Math.sin(Math.PI * p.t) * (0.14 + 0.4 * depthA) * view.streams * boost
          const hex = CHANNEL_META[p.key].hex
          ctx.strokeStyle = hex
          ctx.globalAlpha = Math.min(0.8, alpha)
          ctx.lineWidth = 1.2
          ctx.beginPath()
          ctx.moveTo(b.x, b.y)
          ctx.lineTo(a.x, a.y)
          ctx.stroke()
          ctx.globalAlpha = 1
        }
      } else if (state.particles.length) {
        state.particles.length = 0
      }

      // — orbiting platform nodes —
      state.nodeHits = []
      if (view.nodes > 0.03) {
        CHANNEL_KEYS.forEach((key, i) => {
          const meta = CHANNEL_META[key]
          const pr = project(nodePosition(i), cx, cy, R)
          const depth = (pr.z + 1) * 0.5 // 0 back … 1 front
          const isActive = active === key
          const nodeAlpha = (0.35 + 0.65 * depth) * view.nodes * dim
          const size = (isActive ? 5 : 3.6) * pr.s

          // soft halo
          const halo = ctx.createRadialGradient(pr.x, pr.y, 0, pr.x, pr.y, size * 6)
          halo.addColorStop(0, meta.hex)
          halo.addColorStop(1, 'rgba(0,0,0,0)')
          ctx.globalAlpha = 0.14 * nodeAlpha
          ctx.fillStyle = halo
          ctx.beginPath()
          ctx.arc(pr.x, pr.y, size * 6, 0, TWO_PI)
          ctx.fill()

          // core + ring
          ctx.globalAlpha = nodeAlpha
          ctx.fillStyle = meta.hex
          ctx.beginPath()
          ctx.arc(pr.x, pr.y, size, 0, TWO_PI)
          ctx.fill()
          ctx.strokeStyle = meta.hex
          ctx.lineWidth = 1
          ctx.globalAlpha = nodeAlpha * 0.55
          ctx.beginPath()
          ctx.arc(pr.x, pr.y, size * 2.4, 0, TWO_PI)
          ctx.stroke()

          // active: rotating focus arc
          if (isActive) {
            const spin = state.t * 0.02
            ctx.globalAlpha = nodeAlpha * 0.9
            ctx.beginPath()
            ctx.arc(pr.x, pr.y, size * 3.6, spin, spin + Math.PI * 0.66)
            ctx.stroke()
            ctx.beginPath()
            ctx.arc(pr.x, pr.y, size * 3.6, spin + Math.PI, spin + Math.PI * 1.66)
            ctx.stroke()
          }

          // label — ink, never the series color (identity comes from the dot)
          ctx.globalAlpha = (0.3 + 0.55 * depth) * view.nodes * dim
          ctx.fillStyle = '#f4f3f0'
          ctx.font = '500 10px -apple-system, BlinkMacSystemFont, system-ui, sans-serif'
          ctx.textAlign = 'center'
          try {
            ctx.letterSpacing = '2.5px'
          } catch {
            /* older engines */
          }
          ctx.fillText(meta.label.toUpperCase(), pr.x + 1, pr.y + size * 3.6 + 16)
          try {
            ctx.letterSpacing = '0px'
          } catch {
            /* older engines */
          }
          ctx.globalAlpha = 1

          state.nodeHits.push({ key, x: pr.x, y: pr.y, r: Math.max(26, size * 5) })
        })
      }

      rafId = requestAnimationFrame(frame)
    }

    let rafId = requestAnimationFrame(frame)

    // — pointer interaction: drag with inertia, click to focus a platform —
    function onPointerDown(e) {
      state.pointerDown = true
      state.dragging = false
      state.lastX = e.clientX
      state.lastY = e.clientY
      state.downX = e.clientX
      state.downY = e.clientY
      canvas.setPointerCapture?.(e.pointerId)
      canvas.style.cursor = 'grabbing'
    }
    function onPointerMove(e) {
      if (!state.pointerDown) return
      const dx = e.clientX - state.lastX
      const dy = e.clientY - state.lastY
      state.lastX = e.clientX
      state.lastY = e.clientY
      if (Math.abs(e.clientX - state.downX) + Math.abs(e.clientY - state.downY) > 4) {
        state.dragging = true
        state.targetRot = null
      }
      if (state.dragging) {
        state.rotY += dx * 0.0055
        state.vel = dx * 0.0055
        state.tiltOffset = Math.max(-0.14, Math.min(0.14, state.tiltOffset + dy * 0.0016))
      }
    }
    function onPointerUp(e) {
      canvas.style.cursor = 'grab'
      if (state.pointerDown && !state.dragging) {
        // click: hit-test the platform nodes
        const rect = canvas.getBoundingClientRect()
        const x = e.clientX - rect.left
        const y = e.clientY - rect.top
        const hit = state.nodeHits.find((n) => Math.hypot(n.x - x, n.y - y) < n.r)
        if (hit) {
          const { onSelectChannel: select, activeChannel: current } = propsRef.current
          const next = current === hit.key ? null : hit.key
          if (next) {
            // rotate the engine so this node swings to face the camera
            const idx = CHANNEL_KEYS.indexOf(hit.key)
            const nodeAngle = (idx / CHANNEL_KEYS.length) * TWO_PI
            let target = nodeAngle - Math.PI / 2
            while (target - state.rotY > Math.PI) target -= TWO_PI
            while (target - state.rotY < -Math.PI) target += TWO_PI
            state.targetRot = target
          }
          select?.(next)
        }
      }
      state.pointerDown = false
      state.dragging = false
    }

    canvas.addEventListener('pointerdown', onPointerDown)
    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUp)

    // Scene-wide parallax: panels lean opposite the cursor via CSS vars.
    let parRaf = null
    function onParallax(e) {
      if (reduced || parRaf) return
      parRaf = requestAnimationFrame(() => {
        parRaf = null
        const px = (e.clientX / window.innerWidth - 0.5) * 2
        const py = (e.clientY / window.innerHeight - 0.5) * 2
        document.documentElement.style.setProperty('--par-x', px.toFixed(3))
        document.documentElement.style.setProperty('--par-y', py.toFixed(3))
      })
    }
    window.addEventListener('mousemove', onParallax)

    return () => {
      cancelAnimationFrame(rafId)
      if (parRaf) cancelAnimationFrame(parRaf)
      window.removeEventListener('resize', resize)
      canvas.removeEventListener('pointerdown', onPointerDown)
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', onPointerUp)
      window.removeEventListener('mousemove', onParallax)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      role="application"
      aria-label="Interactive revenue globe — drag to rotate, click a platform node to focus it"
      className="fixed inset-0 z-0"
      style={{ cursor: 'grab' }}
    />
  )
}
