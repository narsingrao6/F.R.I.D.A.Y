import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { nebulaVert, nebulaFrag } from './shaders.nebula.js'
import { drive } from './drive.js'

/** Spiral gas haze lying in the disk plane, under the point cloud. */
export default function Nebula() {
  const uniforms = useRef({
    uTime: { value: 0 },
    uHaze: { value: 1 },
    uBright: { value: 1 },
    uCyan: { value: 0 },
    uPurple: { value: 0 },
    uAmp: { value: 0 },
  }).current

  useFrame(() => {
    uniforms.uTime.value = drive.time
    uniforms.uHaze.value = drive.haze
    uniforms.uBright.value = drive.bright
    uniforms.uCyan.value = drive.cyan
    uniforms.uPurple.value = drive.purple
    uniforms.uAmp.value = drive.amp
  })

  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} renderOrder={0} frustumCulled={false}>
      <planeGeometry args={[5, 5, 1, 1]} />
      <shaderMaterial
        vertexShader={nebulaVert}
        fragmentShader={nebulaFrag}
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
