import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { drive } from './drive.js'

/*
 * Procedural plasma orb — matches the reference centrepiece as a true 3D
 * volume (sphere geometry), not a flat billboard.
 *
 *   - white-hot core         (R ≈ 0.05)
 *   - azure/cyan shell ring  (R ≈ 0.32)   <- the bright ring in the reference
 *   - two fainter outer shells (R ≈ 0.56 / 0.77)
 *   - soft halo fading out past R ≈ 1.0
 *
 * R is radial distance on the sphere's local XY (radius 1.7 world units),
 * matching the measured reference ring proportions. Lambert limb shading
 * darkens the silhouette so the orb reads as dimensional, and the plasma
 * noise slowly spins inside the volume so motion sells the 3D.
 */

const EDGE = 1.7

const frag = /* glsl */ `
  uniform float uTime;
  uniform float uBright;
  uniform float uPulse;

  varying vec3 vPos;

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
    for (int i = 0; i < 4; i++) {
      v += a * noise(p);
      p *= 2.1;
      a *= 0.5;
    }
    return v;
  }

  // Soft gaussian band centred on radius c with width w.
  float band(float r, float c, float w) {
    float d = r - c;
    return exp(-d * d / (w * w));
  }

  void main() {
    vec3 n = normalize(vPos);
    vec2 p = vPos.xy / ${EDGE.toFixed(3)};
    p.y *= 0.96; // soft ellipse — the reference orb is a flattened sphere
    float R = length(p);
    float a = atan(p.y, p.x);

    // Rippling noise warps the shell edges; slowly spins for a living 3D ball.
    float rot = uTime * 0.08;
    float ca = cos(rot);
    float sa = sin(rot);
    vec2 pr = vec2(p.x * ca - p.y * sa, p.x * sa + p.y * ca);
    float nR = length(pr);
    float nA = atan(pr.y, pr.x);
    float n = fbm(vec2(nA * 1.5, nR * 2.5) + uTime * 0.12);
    float Rn = R + (n - 0.5) * 0.05 * min(1.0, R * 1.4);

    // Faint spiral-arm texture inside the body, just enough to avoid a flat disc.
    float spiral = 0.5 + 0.5 * sin(nA * 3.0 + (nR + 0.1) * 9.0 - uTime * 0.25);
    float tex = mix(0.42, 1.0, fbm(vec2(nA * 2.0, nR * 4.0) + uTime * 0.1));

    // Dense, bright body — the reference's orb is a solid mass of light
    // from a white-hot core, falling to a dark disc between distinct rings:
    float core    = 1.0 - smoothstep(0.045, 0.16, R);
    float shellA  = band(Rn, 0.30, 0.018);   // bright shell ring
    float shellB  = band(Rn, 0.50, 0.013);
    float shellC  = band(Rn, 0.66, 0.012);
    float shellD  = band(Rn, 0.78, 0.012);
    float bodyFill = 0.16 * exp(-R * 4.0);
    float ring    = shellA * 0.7 + shellB * 0.35 + shellC * 0.3 + shellD * 0.26;

    float body = (core + bodyFill + ring) * tex;
    body *= 0.6 + 0.4 * spiral;

    // Colour: white-hot core -> cyan/azure shell -> violet-blue edge
    vec3 hot = vec3(1.0, 1.0, 1.0);
    vec3 cyan = vec3(0.45, 0.88, 1.0);
    vec3 azure = vec3(0.18, 0.5, 1.0);
    vec3 deep = vec3(0.2, 0.22, 0.78);
    vec3 col = mix(hot, cyan, smoothstep(0.02, 0.3, R));
    col = mix(col, azure, smoothstep(0.28, 0.6, R));
    col = mix(col, deep, smoothstep(0.6, 1.05, R));

    // Lambert shading turns the disc into a sphere: bright toward camera,
    // limb falling off so the silhouette reads dark violet.
    vec3 L = normalize(vec3(0.35, 0.25, 0.9));
    float diff = 0.6 + 0.4 * max(0.0, dot(n, L));

    float spec = pow(max(0.0, dot(normalize(L + vec3(0.0, 0.0, 1.0)), n)), 20.0) * 0.12;

    float valve = 0.85 + 0.15 * sin(uTime * 1.4);
    float aOut = clamp(body * uBright * valve * (0.75 + 0.25 * uPulse), 0.0, 0.6);

    gl_FragColor = vec4(col * (aOut * 1.05 * diff + spec), aOut);
  }
`

const vert = /* glsl */ `
  varying vec3 vPos;
  void main() {
    vPos = position;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`

export default function PlasmaOrb() {
  const mesh = useRef()
  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uBright: { value: 1 },
      uPulse: { value: 1 },
    }),
    [],
  )

  useFrame((state, delta) => {
    const d = Math.min(0.05, delta)
    if (mesh.current) {
      mesh.current.rotation.z += d * 0.06
    }
    uniforms.uTime.value = drive.time
    uniforms.uBright.value = drive.bright * (1 + drive.amp * 0.35)
    uniforms.uPulse.value = drive.core * (1 + 0.1 * Math.sin(drive.time * 1.4))
    void state
  })

  return (
    <mesh ref={mesh} frustumCulled={false}>
      <sphereGeometry args={[EDGE, 96, 72]} />
      <shaderMaterial
        vertexShader={vert}
        fragmentShader={frag}
        uniforms={uniforms}
        transparent
        depthWrite={false}
        depthTest={false}
        blending={THREE.AdditiveBlending}
        side={THREE.DoubleSide}
      />
    </mesh>
  )
}