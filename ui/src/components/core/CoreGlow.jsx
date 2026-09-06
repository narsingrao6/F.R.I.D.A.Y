import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { drive } from './drive.js'

/*
 * Tiny star at the heart of the orb. Solid, spinning micro-crystal so the
 * very centre of the procedural PlasmaOrb keeps a crisp white point.
 */

export default function CoreGlow() {
  const seed = useRef()
  const t = useRef(0)

  useFrame((_, dt) => {
    const d = Math.min(0.05, dt)
    t.current += d
    const k = drive.core * (1 + drive.amp * 0.18)

    if (seed.current) {
      const s = 0.035 * k
      seed.current.scale.setScalar(s)
      seed.current.rotation.y += d * 1.2
      seed.current.rotation.x += d * 0.5
    }
  })

  return (
    <group>
      {/* Tiny star at the heart of the orb */}
      <mesh ref={seed} renderOrder={2}>
        <icosahedronGeometry args={[1, 1]} />
        <meshBasicMaterial
          color="#ffffff"
          transparent
          opacity={0.9}
          depthWrite={false}
          depthTest={false}
          blending={THREE.AdditiveBlending}
        />
      </mesh>
    </group>
  )
}