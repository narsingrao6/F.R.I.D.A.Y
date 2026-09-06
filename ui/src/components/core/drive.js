import { damp } from '../../state/pointer.js'

/**
 * Per-state visual profile for the energy vortex. Nothing here snaps:
 * `stepDrive` eases every channel toward the active profile, so a state
 * change reads as the reactor spinning up rather than a cut.
 *
 * Tuned for bright, concentrated energy-vortex look matching the reference.
 */
export const PROFILES = {
  idle: {
    spin: 0.2,
    shear: 0.6,
    bright: 0.9,
    size: 1.1,
    flow: 0.7,
    haze: 0.9,
    cyan: 0.0,
    purple: 0.0,
    contract: 0.0,
    core: 1.15,
  },
  listening: {
    spin: 0.38,
    shear: 1.0,
    bright: 1.15,
    size: 1.3,
    flow: 1.8,
    haze: 1.1,
    cyan: 0.6,
    purple: 0.0,
    contract: 0.05,
    core: 1.3,
  },
  thinking: {
    spin: 0.65,
    shear: 1.8,
    bright: 1.0,
    size: 1.2,
    flow: 2.5,
    haze: 1.15,
    cyan: 0.15,
    purple: 0.55,
    contract: 0.25,
    core: 1.3,
  },
  speaking: {
    spin: 0.3,
    shear: 0.9,
    bright: 1.05,
    size: 1.2,
    flow: 1.2,
    haze: 1.0,
    cyan: 0.28,
    purple: 0.12,
    contract: 0.0,
    core: 1.25,
  },
}

const CHANNELS = Object.keys(PROFILES.idle)

/** Live, smoothed values every core layer reads each frame. */
export const drive = { ...PROFILES.thinking, amp: 0, time: 0 }

export function stepDrive(phase, amp, dt) {
  const target = PROFILES[phase] || PROFILES.idle
  for (const k of CHANNELS) {
    drive[k] = damp(drive[k], target[k], 2.1, dt)
  }
  drive.amp = damp(drive.amp, phase === 'speaking' ? amp : amp * 0.35, 14, dt)
  drive.time += dt * (0.65 + drive.spin * 1.4)
  return drive
}
