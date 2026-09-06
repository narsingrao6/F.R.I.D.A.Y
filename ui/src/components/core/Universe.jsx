import { useMemo, useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { drive } from './drive.js'

/*
 * Distant galaxy backdrop — spiral arms radiate from the middle of the screen
 * out across the whole background, so the "universe" reads through the glass
 * sections. The dense energy orb in the centre stays exactly as the reference.
 *
 * Layers sit on large planes far behind the core (z ~ -24), outside the tilt
 * rig, so they stay stable while the orb breathes and tilts.
 */

const STAR_COUNT = 4200
const NEB_W = 46
const NEB_H = 26
const NEB_Z = -23
const STAR_Z = -24

const starVert = /* glsl */ `
  uniform float uTime;
  uniform float uScale;
  attribute float aSize;
  attribute float aSeed;
  attribute float aBright;

  varying float vSeed;
  varying float vBright;

  void main() {
    float tw = 0.92 + 0.08 * sin(uTime * (0.5 + aSeed * 1.7) + aSeed * 41.0);
    vec3 p = position;
    p.z = ${STAR_Z.toFixed(1)};
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    const float PT = 0.085;
    gl_PointSize = clamp(aSize * uScale * PT / max(0.2, -mv.z), 0.6, 4.5);
    vSeed = aSeed;
    vBright = aBright * tw;
  }
`

const starFrag = /* glsl */ `
  varying float vSeed;
  varying float vBright;

  void main() {
    vec2 d = gl_PointCoord - 0.5;
    float dist = dot(d, d) * 4.0;
    if (dist > 1.0) discard;
    float core = exp(-dist * 16.0);
    float halo = pow(1.0 - dist, 2.0);
    float a = (core * 0.75 + halo * 0.25) * vBright;

    vec3 tint = mix(vec3(1.0, 1.0, 1.0), vec3(0.78, 0.88, 1.0), vSeed);
    if (fract(vSeed * 47.7) < 0.06) tint = vec3(1.0, 0.9, 0.78);
    if (fract(vSeed * 19.3) < 0.05) tint = vec3(0.8, 1.0, 0.95);

    gl_FragColor = vec4(tint * a * 0.9, a);
  }
`

const nebulaVert = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`

const nebulaFrag = /* glsl */ `
  uniform float uTime;
  uniform float uHaze;
  varying vec2 vUv;

  float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
  }

  float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(
      mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
      mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x),
      u.y
    );
  }

  float fbm(vec2 p) {
    float v = 0.0;
    float a = 0.5;
    for (int i = 0; i < 5; i++) {
      v += a * noise(p);
      p *= 2.2;
      a *= 0.5;
    }
    return v;
  }

void main() {
    vec2 uv = (vUv - 0.5) * 2.0;
    float drift = uTime * 0.006;
    float r = length(uv);
    float ang = atan(uv.y, uv.x);

    // Two spiral arms radiating outward from the centre of the screen —
    // the galaxy "spread from the middle to the whole background".
    float arm = cos(ang * 2.0 + 3.6 * log(max(r, 0.02)) + uTime * 0.02);
    float armW = 0.42 + 0.52 * arm;
    float armTaper = 1.0 - smoothstep(0.0, 1.7, r);
    float swirl = armW * armTaper;

    // Patchy gas clouds ride the arms
    float c1 = fbm(uv * 1.6 + vec2(drift, -drift * 0.6));
    float c2 = fbm(uv * 3.1 - vec2(drift * 1.3, drift * 0.8) + 7.7);
    float dens = (c1 * 0.5 + c2 * 0.5) * swirl;

    // Milky band across the diagonal
    float band = exp(-pow(length((uv + vec2(0.25, 0.12)) * vec2(1.0, 2.6)), 1.6) * 1.1);
    dens += band * 0.3;

    // Galaxy palette: cyan core -> teal/magenta arms -> deep violet haze.
    // Arm bands push toward magenta/cyan so the spiral structure reads clearly.
    vec3 cyan = vec3(0.42, 0.9, 1.0);
    vec3 teal = vec3(0.26, 0.62, 0.85);
    vec3 magenta = vec3(0.92, 0.4, 0.84);
    vec3 violet = vec3(0.5, 0.32, 0.8);
    vec3 col = mix(teal, cyan, 0.12);
    col = mix(col, magenta, clamp(c2 * 0.8 + arm * 0.35, 0.0, 1.0));
    col = mix(col, violet, (1.0 - swirl) * 0.45);

    // Galaxy covers right to the plane corners — only a gentle outermost fade.
    float edge = 1.0 - smoothstep(0.98, 1.35, r);
    // Quiet pocket right behind the orb so the reference centrepiece stays crisp.
    float centerDip = 0.1 + 0.9 * smoothstep(0.1, 0.6, r);
    float alpha = clamp(dens * uHaze * 0.42, 0.0, 0.38) * edge * centerDip;

    gl_FragColor = vec4(col * 1.0, alpha);
  }
`

function buildStars() {
  const pos = new Float32Array(STAR_COUNT * 3)
  const size = new Float32Array(STAR_COUNT)
  const seed = new Float32Array(STAR_COUNT)
  const bright = new Float32Array(STAR_COUNT)
  for (let i = 0; i < STAR_COUNT; i++) {
    pos[i * 3] = (Math.random() - 0.5) * NEB_W
    pos[i * 3 + 1] = (Math.random() - 0.5) * NEB_H
    pos[i * 3 + 2] = STAR_Z
    size[i] = 0.8 + Math.pow(Math.random(), 2.2) * 3.4
    seed[i] = Math.random()
    const r = Math.random()
    bright[i] = r < 0.05 ? 1.4 : r < 0.25 ? 0.9 : 0.35 + Math.random() * 0.55
  }
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  g.setAttribute('aSize', new THREE.BufferAttribute(size, 1))
  g.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1))
  g.setAttribute('aBright', new THREE.BufferAttribute(bright, 1))
  return g
}

export default function Universe() {
  const gl = useThree((s) => s.gl)
  const stars = useMemo(buildStars, [])
  const uniforms = useRef({
    uTime: { value: 0 },
    uScale: { value: 400 },
  }).current
  const neb = useRef({ uTime: { value: 0 }, uHaze: { value: 1 } }).current

  useFrame(() => {
    uniforms.uTime.value = drive.time
    uniforms.uScale.value = gl.domElement.height * 0.5
    neb.uTime.value = drive.time
    neb.uHaze.value = Math.max(0.4, drive.haze * 0.75)
  })

  return (
    <group>
      {/* Galaxy gas-dust clouds filling the whole background */}
      <mesh position={[0, 0, NEB_Z]} renderOrder={-3} frustumCulled={false}>
        <planeGeometry args={[NEB_W, NEB_H, 1, 1]} />
        <shaderMaterial
          vertexShader={nebulaVert}
          fragmentShader={nebulaFrag}
          uniforms={neb}
          transparent
          depthWrite={false}
          depthTest={false}
          blending={THREE.AdditiveBlending}
          side={THREE.DoubleSide}
        />
      </mesh>

      {/* Distant starfield */}
      <points geometry={stars} renderOrder={-2} frustumCulled={false}>
        <shaderMaterial
          vertexShader={starVert}
          fragmentShader={starFrag}
          uniforms={uniforms}
          transparent
          depthWrite={false}
          depthTest={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
    </group>
  )
}