import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { drive } from './drive.js'

/**
 * Radial energy waves — concentric rings pulsing outward from the core.
 * Compact radius matching the tight vortex.
 */

const WAVE_COUNT = 5
const R_MAX = 2.4
const SEGMENTS = 200

const waveVert = /* glsl */ `
  uniform float uTime;

  attribute float aPhase;
  attribute float aSpeed;

  varying float vAlpha;
  varying float vRadius;

  void main() {
    float life = fract(aPhase + uTime * aSpeed * 0.045);
    float r = life * 2.4;

    float angle = position.x;
    vec3 p = vec3(cos(angle) * r, 0.0, sin(angle) * r);

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;

    vAlpha = smoothstep(0.0, 0.1, life) * (1.0 - smoothstep(0.55, 1.0, life));
    vAlpha *= 0.75 * (1.0 - life * 0.4);
    vRadius = r;
  }
`

const waveFrag = /* glsl */ `
  uniform float uBright;
  uniform float uCyan;
  uniform float uPurple;

  varying float vAlpha;
  varying float vRadius;

  void main() {
    vec3 inner = vec3(0.45, 0.92, 1.0);
    vec3 outer = vec3(0.55, 0.32, 1.0);
    float t = clamp(vRadius / 2.4, 0.0, 1.0);
    vec3 col = mix(inner, outer, t);
    col = mix(col, vec3(0.3, 0.95, 1.0), uCyan * 0.4);
    col = mix(col, vec3(0.5, 0.28, 1.0), uPurple * 0.4);

    gl_FragColor = vec4(col * uBright * 0.55, vAlpha);
  }
`

export default function EnergyWaves() {
  const geometry = useMemo(() => {
    const totalVerts = WAVE_COUNT * (SEGMENTS + 1)
    const positions = new Float32Array(totalVerts * 3)
    const phases = new Float32Array(totalVerts)
    const speeds = new Float32Array(totalVerts)

    for (let w = 0; w < WAVE_COUNT; w++) {
      const basePhase = w / WAVE_COUNT
      const speed = 0.7 + Math.random() * 0.8

      for (let s = 0; s <= SEGMENTS; s++) {
        const idx = w * (SEGMENTS + 1) + s
        const angle = (s / SEGMENTS) * Math.PI * 2

        positions[idx * 3] = angle
        positions[idx * 3 + 1] = 0
        positions[idx * 3 + 2] = 0

        phases[idx] = basePhase
        speeds[idx] = speed
      }
    }

    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    g.setAttribute('aPhase', new THREE.BufferAttribute(phases, 1))
    g.setAttribute('aSpeed', new THREE.BufferAttribute(speeds, 1))
    g.boundingSphere = new THREE.Sphere(new THREE.Vector3(), R_MAX * 1.5)

    const indices = []
    for (let w = 0; w < WAVE_COUNT; w++) {
      const start = w * (SEGMENTS + 1)
      for (let s = 0; s < SEGMENTS; s++) {
        indices.push(start + s, start + s + 1)
      }
    }
    g.setIndex(indices)

    return g
  }, [])

  const uniforms = useRef({
    uTime: { value: 0 },
    uBright: { value: 1 },
    uCyan: { value: 0 },
    uPurple: { value: 0 },
  }).current

  useFrame(() => {
    uniforms.uTime.value = drive.time
    uniforms.uBright.value = drive.bright
    uniforms.uCyan.value = drive.cyan
    uniforms.uPurple.value = drive.purple
  })

  return (
    <lineSegments geometry={geometry} frustumCulled={false}>
      <shaderMaterial
        vertexShader={waveVert}
        fragmentShader={waveFrag}
        uniforms={uniforms}
        transparent
        depthWrite={false}
        depthTest={false}
        blending={THREE.AdditiveBlending}
      />
    </lineSegments>
  )
}
