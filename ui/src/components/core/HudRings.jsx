import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { drive } from './drive.js'

/**
 * Concentric holographic HUD rings in the 3D scene — dashed circles,
 * rotating at different speeds. Adds the tactical-display feel from the
 * reference image with segmented ring patterns.
 */

const HUD_RINGS = [
  { r: 2.0, segments: 64, dash: 0.6, gap: 0.4, color: [0.35, 0.88, 1.0], opacity: 0.35, speed: 0.12 },
  { r: 2.8, segments: 96, dash: 0.35, gap: 0.65, color: [0.42, 0.58, 1.0], opacity: 0.28, speed: -0.08 },
  { r: 3.5, segments: 128, dash: 0.5, gap: 0.5, color: [0.60, 0.38, 1.0], opacity: 0.22, speed: 0.15 },
  { r: 4.2, segments: 80, dash: 0.7, gap: 0.3, color: [0.30, 0.82, 1.0], opacity: 0.18, speed: -0.1 },
  { r: 5.0, segments: 48, dash: 0.4, gap: 0.6, color: [0.55, 0.32, 1.0], opacity: 0.15, speed: 0.06 },
  { r: 1.4, segments: 48, dash: 0.3, gap: 0.7, color: [0.55, 0.92, 1.0], opacity: 0.32, speed: -0.18 },
]

const hudVert = /* glsl */ `
  uniform float uTime;
  uniform float uSpeed;
  uniform float uRadius;

  attribute float aAngle;
  attribute float aOn;

  varying float vOn;

  void main() {
    float ang = aAngle + uTime * uSpeed;
    vec3 p = vec3(cos(ang) * uRadius, 0.0, sin(ang) * uRadius);

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    gl_PointSize = 2.0;

    vOn = aOn;
  }
`

const hudFrag = /* glsl */ `
  uniform vec3 uColor;
  uniform float uOpacity;
  uniform float uBright;

  varying float vOn;

  void main() {
    if (vOn < 0.5) discard;

    vec2 d = gl_PointCoord - 0.5;
    float dist = dot(d, d) * 4.0;
    if (dist > 1.0) discard;

    float a = (1.0 - dist) * uOpacity;
    gl_FragColor = vec4(uColor * uBright, a);
  }
`

function HudRing({ config }) {
  const { r, segments, dash, gap, color, opacity, speed } = config
  const totalPoints = segments * 2 // oversample for smooth circle

  const geometry = useMemo(() => {
    const angles = new Float32Array(totalPoints)
    const on = new Float32Array(totalPoints)

    for (let i = 0; i < totalPoints; i++) {
      angles[i] = (i / totalPoints) * Math.PI * 2
      // dash pattern
      const segFrac = (i / totalPoints) * segments
      const inSeg = segFrac % 1
      on[i] = inSeg < dash / (dash + gap) ? 1.0 : 0.0
    }

    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(totalPoints * 3), 3))
    g.setAttribute('aAngle', new THREE.BufferAttribute(angles, 1))
    g.setAttribute('aOn', new THREE.BufferAttribute(on, 1))
    g.boundingSphere = new THREE.Sphere(new THREE.Vector3(), r * 1.5)
    return g
  }, [totalPoints, segments, dash, gap, r])

  const uniforms = useRef({
    uTime: { value: 0 },
    uSpeed: { value: speed },
    uRadius: { value: r },
    uColor: { value: new THREE.Vector3(...color) },
    uOpacity: { value: opacity },
    uBright: { value: 1 },
  }).current

  useFrame(() => {
    uniforms.uTime.value = drive.time
    uniforms.uBright.value = drive.bright * 0.85
  })

  return (
    <points geometry={geometry} frustumCulled={false}>
      <shaderMaterial
        vertexShader={hudVert}
        fragmentShader={hudFrag}
        uniforms={uniforms}
        transparent
        depthWrite={false}
        depthTest={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  )
}

export default function HudRings() {
  return (
    <group>
      {HUD_RINGS.map((cfg, i) => (
        <HudRing key={i} config={cfg} />
      ))}
    </group>
  )
}
