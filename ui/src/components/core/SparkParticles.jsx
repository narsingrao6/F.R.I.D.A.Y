import { useMemo, useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { drive } from './drive.js'

/**
 * Bright floating spark nodes — the clearly visible bright dots
 * scattered around the vortex in the reference image. They twinkle
 * and flash independently, creating the "alive with energy" feel.
 */

const COUNT = 800
const R_MIN = 0.45
const R_MAX = 2.6

const sparkVert = /* glsl */ `
  uniform float uTime;
  uniform float uSize;
  uniform float uScale;
  uniform float uBright;
  uniform float uSpin;

  attribute float aRadius;
  attribute float aAngle;
  attribute float aSeed;
  attribute float aSize;
  attribute float aSpeed;
  attribute float aY;

  varying vec3 vColor;
  varying float vAlpha;

  void main() {
    float ang = aAngle + uTime * uSpin * aSpeed;
    float r = aRadius;

    float wobble = 1.0 + 0.06 * sin(uTime * 0.8 + aSeed * 23.0);
    vec3 p = vec3(
      cos(ang) * r * wobble,
      aY + sin(uTime * 1.5 + aSeed * 47.0) * 0.03,
      sin(ang) * r * 0.65
    );

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;

    // Strong twinkle with occasional bright flashes
    float twinkle = pow(0.5 + 0.5 * sin(uTime * (3.0 + aSeed * 10.0) + aSeed * 77.0), 2.5);
    float flash = step(0.94, sin(uTime * (0.4 + aSeed * 2.0) + aSeed * 120.0)) * 3.0;

    const float PT = 0.065;
    gl_PointSize = clamp(
      aSize * uSize * (twinkle + flash) * PT * uScale / max(0.4, -mv.z),
      0.8,
      22.0
    );

    float rNorm = clamp((r - 0.5) / 4.0, 0.0, 1.0);
    vec3 inner = vec3(0.9, 0.98, 1.0);
    vec3 mid = vec3(0.4, 0.78, 1.0);
    vec3 outer = vec3(0.65, 0.38, 1.0);
    vec3 col = mix(inner, mid, smoothstep(0.0, 0.45, rNorm));
    col = mix(col, outer, smoothstep(0.45, 1.0, rNorm));

    vColor = col * uBright * 0.7;
    vAlpha = twinkle + flash * 0.5;
  }
`

const sparkFrag = /* glsl */ `
  varying vec3 vColor;
  varying float vAlpha;

  void main() {
    vec2 d = gl_PointCoord - 0.5;
    float dist = dot(d, d) * 4.0;
    if (dist > 1.0) discard;

    // Very bright core with soft halo = prominent spark node
    float core = exp(-dist * 12.0);
    float halo = pow(1.0 - dist, 1.5);
    float a = (core * 0.8 + halo * 0.2) * vAlpha;

    gl_FragColor = vec4(vColor * (0.8 + 3.0 * core), a * 0.9);
  }
`

export default function SparkParticles() {
  const gl = useThree((s) => s.gl)

  const geometry = useMemo(() => {
    const radius = new Float32Array(COUNT)
    const angle = new Float32Array(COUNT)
    const seed = new Float32Array(COUNT)
    const size = new Float32Array(COUNT)
    const speed = new Float32Array(COUNT)
    const yy = new Float32Array(COUNT)
    const pos = new Float32Array(COUNT * 3)

    for (let i = 0; i < COUNT; i++) {
      radius[i] = R_MIN + Math.pow(Math.random(), 0.65) * (R_MAX - R_MIN)
      angle[i] = Math.random() * Math.PI * 2
      seed[i] = Math.random()
      size[i] = 0.4 + Math.random() * 2.5
      speed[i] = (Math.random() < 0.5 ? -1 : 1) * (0.12 + Math.random() * 0.5)
      yy[i] = (Math.random() - 0.5) * 0.25 * (0.2 + radius[i] * 0.1)
    }

    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    g.setAttribute('aRadius', new THREE.BufferAttribute(radius, 1))
    g.setAttribute('aAngle', new THREE.BufferAttribute(angle, 1))
    g.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1))
    g.setAttribute('aSize', new THREE.BufferAttribute(size, 1))
    g.setAttribute('aSpeed', new THREE.BufferAttribute(speed, 1))
    g.setAttribute('aY', new THREE.BufferAttribute(yy, 1))
    g.boundingSphere = new THREE.Sphere(new THREE.Vector3(), R_MAX * 1.5)
    return g
  }, [])

  const uniforms = useRef({
    uTime: { value: 0 },
    uSize: { value: 1 },
    uScale: { value: 400 },
    uBright: { value: 1 },
    uSpin: { value: 0.2 },
  }).current

  useFrame(() => {
    uniforms.uTime.value = drive.time
    uniforms.uSize.value = drive.size * 2.2
    uniforms.uScale.value = gl.domElement.height * 0.5
    uniforms.uBright.value = drive.bright * 0.35
    uniforms.uSpin.value = drive.spin * 0.5
  })

  return (
    <points geometry={geometry} frustumCulled={false}>
      <shaderMaterial
        vertexShader={sparkVert}
        fragmentShader={sparkFrag}
        uniforms={uniforms}
        transparent
        depthWrite={false}
        depthTest={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  )
}
