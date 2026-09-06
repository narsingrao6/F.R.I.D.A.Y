import { useEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { drive } from './drive.js'

/* The reference shows ~6 clearly visible bright neon orbit curves wrapping
   around the vortex, with bright node-dots at intervals. This rewrite makes
   the trails MUCH more prominent than the original dim hairlines. */

const COLORS = [0x55e8ff, 0x40a0ff, 0x8a5cff, 0x30d4ff, 0x6070ff, 0xb85cff, 0x22ccff]

// Fewer, compact arcs wrapped tightly around the orb
const ARC_COUNT = 12

// Bright node dots along the orbit paths — the "spark" nodes from the reference
const NODE_COUNT = 44

export default function OrbitTrails() {
  const built = useMemo(() => {
    const root = new THREE.Group()
    const arcs = []
    const rings = []
    const nodes = []

    // Orbital arcs — compact, clearly visible curves close to the orb
    for (let i = 0; i < ARC_COUNT; i++) {
      const a = 0.45 + Math.random() * 1.3  // semi-major
      const b = a * (0.45 + Math.random() * 0.5) // semi-minor (more elliptical)
      const sweep = (0.5 + Math.random() * 0.5) * Math.PI * 2
      const start = Math.random() * Math.PI * 2
      const seg = 200
      const pos = new Float32Array((seg + 1) * 3)
      const col = new Float32Array((seg + 1) * 3)
      const c = new THREE.Color(COLORS[i % COLORS.length])

      for (let s = 0; s <= seg; s++) {
        const k = s / seg
        const t = start + k * sweep
        pos[s * 3] = Math.cos(t) * a
        pos[s * 3 + 1] = Math.sin(t * 2.5 + i * 0.7) * 0.04
        pos[s * 3 + 2] = Math.sin(t) * b
        // Brighter taper
        const f = Math.pow(Math.sin(Math.PI * k), 0.6)
        col[s * 3] = c.r * f
        col[s * 3 + 1] = c.g * f
        col[s * 3 + 2] = c.b * f
      }

      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
      geo.setAttribute('color', new THREE.BufferAttribute(col, 3))
      const mat = new THREE.LineBasicMaterial({
        vertexColors: true,
        transparent: true,
        opacity: 0.5,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        depthTest: false,
      })
      const holder = new THREE.Group()
      holder.rotation.x = (Math.random() - 0.5) * 0.55
      holder.rotation.z = (Math.random() - 0.5) * 0.45
      holder.rotation.y = Math.random() * Math.PI * 2
      holder.add(new THREE.Line(geo, mat))
      root.add(holder)
      arcs.push({
        holder,
        mat,
        geo,
        speed: (Math.random() < 0.5 ? -1 : 1) * (0.06 + Math.random() * 0.18),
        base: 0.18 + Math.random() * 0.3,
        ph: Math.random() * 6.283,
      })
    }

    // Bright node dots at orbit intersections — the "spark" nodes from the reference
    const nodeGeo = new THREE.SphereGeometry(0.028, 6, 4)
    for (let i = 0; i < NODE_COUNT; i++) {
      const r = 0.4 + Math.random() * 1.6
      const ang = Math.random() * Math.PI * 2
      const mat = new THREE.MeshBasicMaterial({
        color: COLORS[i % COLORS.length],
        transparent: true,
        opacity: 0.7 + Math.random() * 0.3,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        depthTest: false,
      })
      const mesh = new THREE.Mesh(nodeGeo, mat)
      mesh.position.set(
        Math.cos(ang) * r,
        (Math.random() - 0.5) * 0.15,
        Math.sin(ang) * r * (0.5 + Math.random() * 0.4)
      )
      root.add(mesh)
      nodes.push({
        mesh, mat,
        baseOp: mat.opacity,
        orbitR: r,
        orbitAng: ang,
        speed: (Math.random() < 0.5 ? -1 : 1) * (0.04 + Math.random() * 0.12),
        ph: Math.random() * 6.283,
        twinkleSpeed: 1.5 + Math.random() * 4,
      })
    }

    return { root, arcs, rings, nodes, nodeGeo }
  }, [])

  const t = useRef(0)

  useEffect(
    () => () => {
      for (const a of built.arcs) { a.geo.dispose(); a.mat.dispose() }
      for (const r of built.rings) { r.geo.dispose(); r.mat.dispose() }
      for (const n of built.nodes) { n.mat.dispose() }
      built.nodeGeo.dispose()
    },
    [built],
  )

  useFrame((_, dt) => {
    const d = Math.min(0.05, dt)
    t.current += d
    const rate = 0.4 + drive.spin * 2.5
    const lift = drive.bright * (1 + drive.amp * 0.5)

    for (const a of built.arcs) {
      a.holder.rotation.y += a.speed * rate * d
      a.mat.opacity =
        a.base * lift * (0.6 + 0.4 * Math.sin(t.current * 0.5 + a.ph))
    }
    for (const r of built.rings) {
      r.mesh.rotation.z += r.speed * rate * d * 0.5
      r.mat.opacity =
        r.base * lift * (0.65 + 0.35 * Math.sin(t.current * 0.38 + r.ph))
    }
    // Animate node dots — orbit slowly + twinkle
    for (const n of built.nodes) {
      const ang = n.orbitAng + t.current * n.speed * rate
      n.mesh.position.x = Math.cos(ang) * n.orbitR
      n.mesh.position.z = Math.sin(ang) * n.orbitR * 0.65
      const twinkle = 0.4 + 0.6 * Math.pow(0.5 + 0.5 * Math.sin(t.current * n.twinkleSpeed + n.ph), 2)
      n.mat.opacity = n.baseOp * lift * twinkle
      const s = 0.7 + 0.6 * twinkle
      n.mesh.scale.setScalar(s)
    }
  })

  return <primitive object={built.root} />
}
