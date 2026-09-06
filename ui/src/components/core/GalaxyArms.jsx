import { useMemo, useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { gauss, rampColor } from './textures.js'
import { vortexVert, vortexFrag } from './shaders.galaxy.js'
import { drive } from './drive.js'

/* Concentrated energy vortex — tight spiral arms, bright core,
   everything within ~3.5 world units. Matches the reference's
   dense, swirling energy look. */

const COUNT = 2600
const CORE_FRAC = 0.5   // Half the particles in the dense bright core
const ARMS = 3           // Tight 3-arm spiral (reference shows 2-3 visible arms)
const R_IN = 0.02
const R_CORE = 0.5       // Dense round core
const R_OUT = 1.7        // Compact — tight around the orb
const WIND = 5.5         // Tighter winding than a galaxy

const ARM_PHASE = [0, 0.12, -0.08]
const ARM_PITCH = [1, 0.96, 1.04]

function buildGeometry() {
  const pos = new Float32Array(COUNT * 3)
  const col = new Float32Array(COUNT * 3)
  const size = new Float32Array(COUNT)
  const seed = new Float32Array(COUNT)
  const radius = new Float32Array(COUNT)
  const rgb = [0, 0, 0]
  const coreCount = Math.floor(COUNT * CORE_FRAC)

  for (let i = 0; i < COUNT; i++) {
    let r, theta, y, bright

    if (i < coreCount) {
      // Dense, very bright core — this blooms to the intense white center
      r = R_IN + Math.pow(Math.random(), 2.2) * R_CORE
      theta = Math.random() * Math.PI * 2
      y = gauss() * 0.04 * (0.2 + r)
      bright = 1.2 + Math.random() * 1.8  // Very bright core particles
    } else {
      // Tight spiral arms — concentrated, well-defined
      const arm = (i - coreCount) % ARMS
      const span = R_OUT - R_CORE
      r = R_CORE + Math.pow(Math.random(), 0.7) * span
      const k = (r - R_CORE) / span
      // Very tight spread — arms stay well defined
      const spread = 0.18 - 0.06 * k
      theta =
        arm * ((Math.PI * 2) / ARMS) +
        ARM_PHASE[arm] +
        (r - R_CORE) * WIND * ARM_PITCH[arm] +
        gauss() * spread
      r += gauss() * (0.08 + 0.12 * k)
      y = gauss() * (0.01 + 0.035 * k)
      const grow = k < 0.3 ? k / 0.3 : 1
      bright = (0.7 + Math.random() * 1.2) * (0.6 + 0.7 * grow)
      // More hot scattered points for energy feel
      if (Math.random() < 0.12) bright *= 3.5
    }

    const rr = Math.max(0.01, r)
    pos[i * 3] = Math.cos(theta) * rr
    pos[i * 3 + 1] = y
    pos[i * 3 + 2] = Math.sin(theta) * rr

    rampColor(rr / R_OUT + gauss() * 0.04, rgb)
    col[i * 3] = rgb[0]
    col[i * 3 + 1] = rgb[1]
    col[i * 3 + 2] = rgb[2]

    size[i] = bright
    seed[i] = Math.random()
    radius[i] = rr
  }

  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  g.setAttribute('aColor', new THREE.BufferAttribute(col, 3))
  g.setAttribute('aSize', new THREE.BufferAttribute(size, 1))
  g.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1))
  g.setAttribute('aRadius', new THREE.BufferAttribute(radius, 1))
  g.boundingSphere = new THREE.Sphere(new THREE.Vector3(), R_OUT * 1.4)
  return g
}

export default function GalaxyArms() {
  const gl = useThree((s) => s.gl)
  const uniforms = useRef({
    uTime: { value: 0 },
    uSpin: { value: 0.2 },
    uShear: { value: 1 },
    uSize: { value: 1 },
    uScale: { value: 400 },
    uAmp: { value: 0 },
    uContract: { value: 0 },
    uCyan: { value: 0 },
    uPurple: { value: 0 },
    uBright: { value: 1 },
  }).current

  const geometry = useMemo(buildGeometry, [])

  useFrame(() => {
    uniforms.uTime.value = drive.time
    uniforms.uSpin.value = drive.spin
    uniforms.uShear.value = drive.shear
    uniforms.uSize.value = drive.size * 1.6  // Smaller particles
    uniforms.uScale.value = gl.domElement.height * 0.5
    uniforms.uAmp.value = drive.amp
    uniforms.uContract.value = drive.contract
    uniforms.uCyan.value = drive.cyan
    uniforms.uPurple.value = drive.purple
    uniforms.uBright.value = drive.bright * 0.4  // subtle — the orb carries the light
  })

  return (
    <points geometry={geometry} frustumCulled={false}>
      <shaderMaterial
        vertexShader={vortexVert}
        fragmentShader={vortexFrag}
        uniforms={uniforms}
        transparent
        depthWrite={false}
        depthTest={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  )
}
