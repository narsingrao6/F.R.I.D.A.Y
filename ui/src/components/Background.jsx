import { useEffect, useRef } from 'react'
import { pointer, stepPointer, damp } from '../state/pointer.js'

/* Depth layers: tiny stars far back, brighter energy dust up front. */
const LAYERS = [
  { n: 150, depth: 0.14, rMin: 0.35, rMax: 0.95, drift: 2.4, alpha: 0.55 },
  { n: 95, depth: 0.38, rMin: 0.6, rMax: 1.6, drift: 5.5, alpha: 0.7 },
  { n: 46, depth: 0.78, rMin: 1.0, rMax: 2.5, drift: 10, alpha: 0.85 },
]

const TINTS = [
  [127, 233, 255],
  [91, 140, 255],
  [176, 124, 255],
  [255, 122, 217],
  [226, 244, 255],
]

const rand = (a, b) => a + Math.random() * (b - a)

/**
 * Living environment behind the interface.
 *
 * A single 2D canvas carries everything particle-like — stars, drifting
 * energy dust, distant streaks and rare light pulses — while the slow
 * atmospheric washes, holo grid, beams and HUD rings live in CSS layers
 * that this component parallaxes. One rAF loop drives all of it, and it is
 * also the single place the shared pointer follower is advanced.
 */
export default function Background() {
  const canvasRef = useRef(null)
  const parallaxRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d', { alpha: true })
    const holder = parallaxRef.current

    let w = 0
    let h = 0
    let dpr = 1
    let dots = []
    let streaks = []
    let pulses = []
    let nextStreak = 1.2
    let nextPulse = 3.5

    const build = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 1.75)
      w = window.innerWidth
      h = window.innerHeight
      canvas.width = Math.floor(w * dpr)
      canvas.height = Math.floor(h * dpr)
      canvas.style.width = `${w}px`
      canvas.style.height = `${h}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

      dots = []
      for (const L of LAYERS) {
        const n = Math.round(L.n * Math.min(1.35, (w * h) / (1600 * 900)))
        for (let i = 0; i < n; i++) {
          const tint = TINTS[(Math.random() * TINTS.length) | 0]
          dots.push({
            x: Math.random() * w,
            y: Math.random() * h,
            r: rand(L.rMin, L.rMax),
            depth: L.depth,
            vx: rand(-L.drift, L.drift) * 0.4,
            vy: -rand(L.drift * 0.25, L.drift),
            a: rand(0.28, 1) * L.alpha,
            tw: Math.random() * Math.PI * 2,
            tws: rand(0.35, 1.5),
            tint,
          })
        }
      }
    }

    const spawnStreak = () => {
      const edge = Math.random() < 0.5
      const tint = TINTS[(Math.random() * 3) | 0]
      streaks.push({
        x: edge ? rand(-0.1, 0.4) * w : rand(0.6, 1.1) * w,
        y: rand(0.05, 0.95) * h,
        ang: (edge ? rand(-0.34, 0.18) : Math.PI + rand(-0.18, 0.34)),
        len: rand(90, 300),
        sp: rand(70, 210),
        life: 0,
        ttl: rand(2.4, 5),
        tint,
      })
      if (streaks.length > 14) streaks.shift()
    }

    const spawnPulse = () => {
      pulses.push({
        x: rand(0.06, 0.94) * w,
        y: rand(0.08, 0.92) * h,
        r: 4,
        ttl: rand(2.6, 4.2),
        life: 0,
        tint: TINTS[(Math.random() * TINTS.length) | 0],
      })
      if (pulses.length > 4) pulses.shift()
    }

    build()
    window.addEventListener('resize', build)

    let raf
    let last = performance.now()
    let t = 0
    let px = 0
    let py = 0

    const frame = (now) => {
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      t += dt

      // Single owner of the shared pointer follower.
      stepPointer(dt)

      // CSS atmosphere layers parallax further than the canvas dust.
      px = damp(px, pointer.x, 1.8, dt)
      py = damp(py, pointer.y, 1.8, dt)
      if (holder) {
        holder.style.setProperty('--px', px.toFixed(4))
        holder.style.setProperty('--py', py.toFixed(4))
      }

      ctx.clearRect(0, 0, w, h)
      ctx.globalCompositeOperation = 'lighter'

      /* ---- drifting stars & dust ---- */
      for (const d of dots) {
        d.x += d.vx * dt
        d.y += d.vy * dt
        if (d.y < -6) {
          d.y = h + 6
          d.x = Math.random() * w
        }
        if (d.x < -6) d.x = w + 6
        else if (d.x > w + 6) d.x = -6

        const tw = 0.62 + 0.38 * Math.sin(t * d.tws + d.tw)
        const ox = -px * 46 * d.depth
        const oy = -py * 30 * d.depth
        const a = d.a * tw
        const [r, g, b] = d.tint

        ctx.beginPath()
        ctx.fillStyle = `rgba(${r},${g},${b},${a * 0.95})`
        ctx.arc(d.x + ox, d.y + oy, d.r, 0, Math.PI * 2)
        ctx.fill()

        if (d.r > 1.25) {
          const gr = ctx.createRadialGradient(
            d.x + ox,
            d.y + oy,
            0,
            d.x + ox,
            d.y + oy,
            d.r * 7,
          )
          gr.addColorStop(0, `rgba(${r},${g},${b},${a * 0.3})`)
          gr.addColorStop(1, 'rgba(0,0,0,0)')
          ctx.fillStyle = gr
          ctx.beginPath()
          ctx.arc(d.x + ox, d.y + oy, d.r * 7, 0, Math.PI * 2)
          ctx.fill()
        }
      }

      /* ---- distant energy trails ---- */
      nextStreak -= dt
      if (nextStreak <= 0) {
        spawnStreak()
        nextStreak = rand(1.1, 3.4)
      }
      for (let i = streaks.length - 1; i >= 0; i--) {
        const s = streaks[i]
        s.life += dt
        if (s.life > s.ttl) {
          streaks.splice(i, 1)
          continue
        }
        const k = s.life / s.ttl
        const fade = Math.sin(Math.PI * k)
        s.x += Math.cos(s.ang) * s.sp * dt
        s.y += Math.sin(s.ang) * s.sp * dt
        const ex = s.x - Math.cos(s.ang) * s.len
        const ey = s.y - Math.sin(s.ang) * s.len
        const [r, g, b] = s.tint
        const grad = ctx.createLinearGradient(s.x, s.y, ex, ey)
        grad.addColorStop(0, `rgba(${r},${g},${b},${0.5 * fade})`)
        grad.addColorStop(1, 'rgba(0,0,0,0)')
        ctx.strokeStyle = grad
        ctx.lineWidth = 1.15
        ctx.beginPath()
        ctx.moveTo(s.x - px * 22, s.y - py * 16)
        ctx.lineTo(ex - px * 22, ey - py * 16)
        ctx.stroke()
      }

      /* ---- occasional light pulses ---- */
      nextPulse -= dt
      if (nextPulse <= 0) {
        spawnPulse()
        nextPulse = rand(5.5, 11)
      }
      for (let i = pulses.length - 1; i >= 0; i--) {
        const p = pulses[i]
        p.life += dt
        if (p.life > p.ttl) {
          pulses.splice(i, 1)
          continue
        }
        const k = p.life / p.ttl
        const rr = 4 + k * 190
        const a = (1 - k) * (1 - k) * 0.34
        const [r, g, b] = p.tint
        ctx.strokeStyle = `rgba(${r},${g},${b},${a})`
        ctx.lineWidth = 1.1
        ctx.beginPath()
        ctx.arc(p.x - px * 26, p.y - py * 18, rr, 0, Math.PI * 2)
        ctx.stroke()
        ctx.strokeStyle = `rgba(${r},${g},${b},${a * 0.5})`
        ctx.beginPath()
        ctx.arc(p.x - px * 26, p.y - py * 18, rr * 0.62, 0, Math.PI * 2)
        ctx.stroke()
      }

      ctx.globalCompositeOperation = 'source-over'
      raf = requestAnimationFrame(frame)
    }

    raf = requestAnimationFrame(frame)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', build)
    }
  }, [])

  return (
    <div className="bg" ref={parallaxRef} aria-hidden="true">
      <div className="bg-void" />
      <div className="bg-clouds">
        <i className="c1" />
        <i className="c2" />
        <i className="c3" />
        <i className="c4" />
      </div>
      <div className="bg-grid" />
      <div className="bg-beams">
        <i />
        <i />
        <i />
      </div>
      <svg className="bg-rings" viewBox="0 0 1000 1000" preserveAspectRatio="xMidYMid slice">
        <g className="r-slow" transform="translate(500 500)">
          <circle r="330" strokeDasharray="3 13" />
          <circle r="392" strokeDasharray="52 24" opacity="0.5" />
        </g>
        <g className="r-fast" transform="translate(500 500)">
          <circle r="255" strokeDasharray="1.5 9" opacity="0.7" />
          <circle r="452" strokeDasharray="120 60" opacity="0.28" />
        </g>
      </svg>
      <canvas className="bg-canvas" ref={canvasRef} />
      <div className="bg-scan" />
      <div className="bg-vignette" />
    </div>
  )
}
