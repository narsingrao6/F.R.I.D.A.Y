/**
 * Global pointer store.
 *
 * A single window listener writes raw normalised coordinates here; every
 * animation loop (Three.js and the 2D background) reads them directly.
 * Nothing is pushed through React state, so moving the mouse never causes
 * a re-render — it only nudges values that rAF loops are already reading.
 */

export const pointer = {
  /** raw target, -1..1, origin at viewport centre */
  tx: 0,
  ty: 0,
  /** smoothed follower — always lags the target */
  x: 0,
  y: 0,
  /** 0..1 ramp that fades in once the pointer has been seen */
  presence: 0,
  /** seconds since the last movement */
  idle: 999,
}

let attached = false

export function attachPointer() {
  if (attached) return () => {}
  attached = true

  const onMove = (e) => {
    pointer.tx = (e.clientX / window.innerWidth) * 2 - 1
    pointer.ty = (e.clientY / window.innerHeight) * 2 - 1
    pointer.idle = 0
  }

  const onLeave = () => {
    pointer.tx = 0
    pointer.ty = 0
  }

  window.addEventListener('pointermove', onMove, { passive: true })
  window.addEventListener('pointerleave', onLeave, { passive: true })

  return () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerleave', onLeave)
    attached = false
  }
}

/**
 * Critically-damped follow: frame-rate independent, never snaps.
 * `lambda` is roughly "how many e-folds per second".
 */
export function damp(current, target, lambda, dt) {
  return current + (target - current) * (1 - Math.exp(-lambda * dt))
}

/** Advance the smoothed pointer. Call once per frame from one place only. */
export function stepPointer(dt) {
  pointer.x = damp(pointer.x, pointer.tx, 2.6, dt)
  pointer.y = damp(pointer.y, pointer.ty, 2.6, dt)
  pointer.presence = damp(pointer.presence, 1, 1.2, dt)
  pointer.idle += dt
}
