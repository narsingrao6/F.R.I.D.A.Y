import * as THREE from 'three'

/** Soft radial falloff sprite, generated once — no image assets. */
export function makeGlowTexture(stops) {
  const size = 256
  const c = document.createElement('canvas')
  c.width = c.height = size
  const ctx = c.getContext('2d')
  const g = ctx.createRadialGradient(
    size / 2,
    size / 2,
    0,
    size / 2,
    size / 2,
    size / 2,
  )
  for (const [at, color] of stops) g.addColorStop(at, color)
  ctx.fillStyle = g
  ctx.fillRect(0, 0, size, size)
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.needsUpdate = true
  return tex
}

export const GLOW_TIGHT = () =>
  makeGlowTexture([
    [0, 'rgba(255,255,255,1)'],
    [0.14, 'rgba(215,246,255,0.92)'],
    [0.34, 'rgba(96,206,255,0.42)'],
    [0.62, 'rgba(48,110,255,0.13)'],
    [1, 'rgba(0,0,0,0)'],
  ])

export const GLOW_WIDE = () =>
  makeGlowTexture([
    [0, 'rgba(180,230,255,0.55)'],
    [0.26, 'rgba(70,150,255,0.28)'],
    [0.58, 'rgba(130,70,240,0.12)'],
    [1, 'rgba(0,0,0,0)'],
  ])

/** Box-Muller — clustered scatter looks organic, uniform noise does not. */
export function gauss() {
  let u = 0
  let v = 0
  while (u === 0) u = Math.random()
  while (v === 0) v = Math.random()
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v)
}

/** Radius → colour ramp: white-hot core → cyan → blue → purple rim. */
const RAMP = [
  [0.0,  [1.0, 1.0, 1.0]],
  [0.06, [0.92, 0.98, 1.0]],
  [0.15, [0.65, 0.94, 1.0]],
  [0.28, [0.35, 0.82, 1.0]],
  [0.45, [0.2,  0.52, 1.0]],
  [0.65, [0.45, 0.35, 1.0]],
  [0.82, [0.65, 0.3,  0.98]],
  [1.0,  [0.85, 0.35, 0.88]],
]

export function rampColor(t, out) {
  const k = Math.min(0.9999, Math.max(0, t))
  let i = 0
  while (i < RAMP.length - 2 && k > RAMP[i + 1][0]) i++
  const [a, ca] = RAMP[i]
  const [b, cb] = RAMP[i + 1]
  const f = (k - a) / (b - a)
  out[0] = ca[0] + (cb[0] - ca[0]) * f
  out[1] = ca[1] + (cb[1] - ca[1]) * f
  out[2] = ca[2] + (cb[2] - ca[2]) * f
  return out
}
