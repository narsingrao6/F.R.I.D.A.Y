import { useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { EffectComposer, Bloom } from '@react-three/postprocessing'
import * as THREE from 'three'
import { pointer, damp } from '../state/pointer.js'
import { stepDrive, drive } from './core/drive.js'
import Nebula from './core/Nebula.jsx'
import GalaxyArms from './core/GalaxyArms.jsx'
import InfallStream from './core/InfallStream.jsx'
import OrbitTrails from './core/OrbitTrails.jsx'
import CoreGlow from './core/CoreGlow.jsx'
import PlasmaOrb from './core/PlasmaOrb.jsx'
import SparkParticles from './core/SparkParticles.jsx'
import EnergyWaves from './core/EnergyWaves.jsx'
import VolumetricRays from './core/VolumetricRays.jsx'
import Universe from './core/Universe.jsx'

const BASE_TILT = -0.42
const CAM_Z = 10.5

function DepthRig({ phase, amplitude, children }) {
  const group = useRef()
  const camera = useThree((state) => state.camera)
  const smooth = useRef({ x: 0, y: 0 })
  useFrame((_, delta) => {
    const dt = Math.min(0.05, delta)
    stepDrive(phase, amplitude.current, dt)
    smooth.current.x = damp(smooth.current.x, pointer.x * 0.85, 2, dt)
    smooth.current.y = damp(smooth.current.y, -pointer.y * 0.6, 2, dt)
    camera.position.set(smooth.current.x, smooth.current.y, CAM_Z - drive.amp * 0.5)
    camera.lookAt(0, 0, 0)
    if (group.current) {
      group.current.rotation.z = smooth.current.x * -0.035
      group.current.rotation.x = BASE_TILT + smooth.current.y * 0.035
      group.current.rotation.y = smooth.current.x * 0.045
    }
  })
  return <group ref={group} rotation={[BASE_TILT, 0, 0]}>{children}</group>
}

function DeepOrbit({ radius, tilt, color, speed, opacity = 0.75, dash = false }) {
  const ref = useRef()
  useFrame((_, delta) => {
    if (ref.current) ref.current.rotation.z += delta * speed * (0.55 + drive.spin * 0.35)
  })
  return (
    <mesh ref={ref} rotation={[tilt, 0, 0]} position={[0, 0, -0.22]}>
      <torusGeometry args={[radius, dash ? 0.012 : 0.018, 8, 160]} />
      <meshBasicMaterial color={color} transparent opacity={opacity} blending={THREE.AdditiveBlending} depthWrite={false} />
    </mesh>
  )
}

function CoreDepth() {
  const ref = useRef()
  useFrame((_, delta) => {
    if (ref.current) {
      ref.current.rotation.y += delta * 0.38
      ref.current.rotation.x = Math.sin(drive.time * 0.35) * 0.08
      ref.current.scale.setScalar(1 + drive.amp * 0.08 + Math.sin(drive.time * 1.5) * 0.015)
    }
  })
  return (
    <group ref={ref}>
      <mesh position={[0, 0, 0.06]}>
        <icosahedronGeometry args={[0.06, 2]} />
        <meshBasicMaterial color="#d9fbff" transparent opacity={0.4} blending={THREE.AdditiveBlending} />
      </mesh>
      <mesh scale={2.1}>
        <icosahedronGeometry args={[0.13, 2]} />
        <meshBasicMaterial color="#39dfff" wireframe transparent opacity={0.12} blending={THREE.AdditiveBlending} />
      </mesh>
    </group>
  )
}

function Scene({ phase, amplitude }) {
  return (
    <Canvas dpr={[1, 2]} camera={{ position: [0, 0, CAM_Z], fov: 32, near: 0.1, far: 80 }} gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }} onCreated={({ gl }) => { gl.toneMapping = THREE.ACESFilmicToneMapping; gl.toneMappingExposure = 1.05; gl.setClearColor(0x000000, 0) }}>
      <ambientLight intensity={0.08} />
      <Universe />
      <DepthRig phase={phase} amplitude={amplitude}>
        <Nebula />
        <VolumetricRays />
        <DeepOrbit radius={0.53} tilt={0.1} color="#7fe4ff" speed={0.9} opacity={0.3} />
        <DeepOrbit radius={0.96} tilt={-0.5} color="#5b7bff" speed={-0.55} opacity={0.2} />
        <DeepOrbit radius={1.31} tilt={0.55} color="#a86aff" speed={0.34} opacity={0.15} dash />
        <DeepOrbit radius={1.62} tilt={-0.18} color="#31bfff" speed={-0.28} opacity={0.12} dash />
        <EnergyWaves />
        <OrbitTrails />
        <GalaxyArms />
        <InfallStream />
        <SparkParticles />
        <PlasmaOrb />
        <CoreGlow />
        <CoreDepth />
      </DepthRig>
      <EffectComposer disableNormalPass multisampling={0} autoClear={false}>
        <Bloom intensity={0.14} luminanceThreshold={0.45} luminanceSmoothing={0.3} radius={0.25} mipmapBlur />
      </EffectComposer>
    </Canvas>
  )
}

export default function EnergyCore({ phase, amplitude }) {
  return <div className="energy-core-canvas"><Scene phase={phase} amplitude={amplitude} /></div>
}
