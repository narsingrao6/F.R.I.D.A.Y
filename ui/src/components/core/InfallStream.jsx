import { useMemo, useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { gauss } from './textures.js'
import { drive } from './drive.js'

/* Particles spiralling inward — tighter, brighter, more prominent to
   show the energy flowing into the core. */

const COUNT = 2200
const R_OUT = 1.9

const vert = /* glsl */ `
  uniform float uTime, uFlow, uSpin, uSize, uScale, uBright, uCyan, uPurple, uAmp;
  attribute float aR0, aAngle, aSeed, aSpeed, aY, aSize;
  varying vec3 vColor;
  varying float vA;

  void main() {
    float life = fract(aSeed + uTime * 0.065 * uFlow * aSpeed);
    float fall = pow(life, 1.2);
    float r = mix(aR0, 0.06, fall);
    // More rotation during fall — visible spiraling
    float ang = aAngle + fall * 7.5 + uTime * uSpin * 1.1;
    vec3 p = vec3(cos(ang) * r, aY * (1.0 - fall * 0.85), sin(ang) * r);
    p.xz *= 1.0 + uAmp * 0.15;

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    const float PT = 0.042;
    gl_PointSize = clamp(
      aSize * uSize * PT * uScale / max(0.35, -mv.z),
      1.0,
      20.0
    );

    vA = smoothstep(0.0, 0.06, life) * (1.0 - smoothstep(0.65, 1.0, life));

    vec3 hot = vec3(0.85, 0.98, 1.0);
    vec3 cold = vec3(0.42, 0.36, 1.0);
    vColor = mix(cold, hot, pow(clamp(1.0 - r / 3.5, 0.0, 1.0), 1.4));
    vColor = mix(vColor, vec3(0.22, 0.96, 1.0), uCyan * 0.55);
    vColor = mix(vColor, vec3(0.52, 0.28, 1.0), uPurple * 0.55);
    vColor *= uBright * 1.3;
  }
`

const frag = /* glsl */ `
  varying vec3 vColor;
  varying float vA;
  void main() {
    vec2 d = gl_PointCoord - 0.5;
    float dist = dot(d, d) * 4.0;
    if (dist > 1.0) discard;
    float a = pow(1.0 - dist, 1.8) * vA;
    float core = exp(-dist * 8.0) * 0.5;
    gl_FragColor = vec4(vColor * (0.7 + 2.2 * a + core), a * 0.95);
  }
`

export default function InfallStream() {
  const gl = useThree((s) => s.gl)

  const geometry = useMemo(() => {
    const pos = new Float32Array(COUNT * 3)
    const r0 = new Float32Array(COUNT)
    const angle = new Float32Array(COUNT)
    const seed = new Float32Array(COUNT)
    const speed = new Float32Array(COUNT)
    const yy = new Float32Array(COUNT)
    const size = new Float32Array(COUNT)

    for (let i = 0; i < COUNT; i++) {
      r0[i] = 1.0 + Math.random() * (R_OUT - 1.0)
      angle[i] = Math.random() * Math.PI * 2
      seed[i] = Math.random()
      speed[i] = 0.6 + Math.random() * 1.2
      yy[i] = gauss() * 0.08
      size[i] = 0.6 + Math.random() * 1.8
    }

    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    g.setAttribute('aR0', new THREE.BufferAttribute(r0, 1))
    g.setAttribute('aAngle', new THREE.BufferAttribute(angle, 1))
    g.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1))
    g.setAttribute('aSpeed', new THREE.BufferAttribute(speed, 1))
    g.setAttribute('aY', new THREE.BufferAttribute(yy, 1))
    g.setAttribute('aSize', new THREE.BufferAttribute(size, 1))
    g.boundingSphere = new THREE.Sphere(new THREE.Vector3(), R_OUT * 1.4)
    return g
  }, [])

  const uniforms = useRef({
    uTime: { value: 0 },
    uFlow: { value: 1 },
    uSpin: { value: 0.2 },
    uSize: { value: 2 },
    uScale: { value: 400 },
    uBright: { value: 1 },
    uCyan: { value: 0 },
    uPurple: { value: 0 },
    uAmp: { value: 0 },
  }).current

  useFrame(() => {
    uniforms.uTime.value = drive.time
    uniforms.uFlow.value = drive.flow
    uniforms.uSpin.value = drive.spin
    uniforms.uSize.value = drive.size * 1.6
    uniforms.uScale.value = gl.domElement.height * 0.5
    uniforms.uBright.value = drive.bright * 0.4
    uniforms.uCyan.value = drive.cyan
    uniforms.uPurple.value = drive.purple
    uniforms.uAmp.value = drive.amp
  })

  return (
    <points geometry={geometry} frustumCulled={false}>
      <shaderMaterial
        vertexShader={vert}
        fragmentShader={frag}
        uniforms={uniforms}
        transparent
        depthWrite={false}
        depthTest={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  )
}
