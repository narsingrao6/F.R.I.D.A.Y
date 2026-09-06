import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { drive } from './drive.js'

/**
 * Radial god-rays from the core — subtle volumetric light beams
 * visible in the reference as faint radial streaks through the vortex.
 */

const rayVert = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`

const rayFrag = /* glsl */ `
  uniform float uTime;
  uniform float uBright;
  uniform float uCyan;
  uniform float uPurple;

  varying vec2 vUv;

  float hash(float n) {
    return fract(sin(n) * 43758.5453);
  }

  void main() {
    vec2 uv = (vUv - 0.5) * 2.0;
    float r = length(uv);
    if (r > 1.0) discard;

    float ang = atan(uv.y, uv.x);

    // 6 primary rays
    float rays = 0.0;
    for (int i = 0; i < 6; i++) {
      float fi = float(i);
      float rayAng = fi * 1.0472 + uTime * 0.025 * (1.0 + fi * 0.08);
      float diff = abs(mod(ang - rayAng + 3.14159, 6.28318) - 3.14159);
      float width = 0.06 + 0.03 * sin(uTime * 0.35 + fi * 2.5);
      float ray = exp(-diff * diff / (width * width));
      ray *= 0.3 + 0.7 * hash(fi * 11.0 + floor(uTime * 0.4));
      rays += ray;
    }

    // Strong centre falloff
    float fade = exp(-r * 2.8) * smoothstep(1.0, 0.08, r);
    rays *= fade;

    // Radial streaks
    float streaks = 0.0;
    for (int i = 0; i < 12; i++) {
      float fi = float(i);
      float sAng = fi * 0.5236 + uTime * 0.018;
      float diff = abs(mod(ang - sAng + 3.14159, 6.28318) - 3.14159);
      streaks += exp(-diff * diff / 0.004) * 0.2 * exp(-r * 3.5);
    }

    float total = rays + streaks;

    vec3 inner = vec3(0.8, 0.96, 1.0);
    vec3 outer = vec3(0.42, 0.32, 1.0);
    vec3 col = mix(inner, outer, smoothstep(0.0, 0.6, r));
    col = mix(col, vec3(0.3, 0.94, 1.0), uCyan * 0.4);
    col = mix(col, vec3(0.5, 0.28, 1.0), uPurple * 0.4);

    float a = total * uBright * 0.13;
    gl_FragColor = vec4(col * (0.7 + total * 0.9), a);
  }
`

export default function VolumetricRays() {
  const uniforms = useRef({
    uTime: { value: 0 },
    uBright: { value: 1 },
    uCyan: { value: 0 },
    uPurple: { value: 0 },
  }).current

  useFrame(() => {
    uniforms.uTime.value = drive.time
    uniforms.uBright.value = drive.bright * (1 + drive.amp * 0.35)
    uniforms.uCyan.value = drive.cyan
    uniforms.uPurple.value = drive.purple
  })

  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} renderOrder={-1} frustumCulled={false}>
      <planeGeometry args={[5, 5, 1, 1]} />
      <shaderMaterial
        vertexShader={rayVert}
        fragmentShader={rayFrag}
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
