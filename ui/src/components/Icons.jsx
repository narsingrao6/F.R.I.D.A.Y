/* Hand-drawn HUD glyphs — no icon package, everything inherits currentColor. */

const base = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.7,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
}

const Svg = ({ size = 20, children, box = 24, ...rest }) => (
  <svg viewBox={`0 0 ${box} ${box}`} width={size} height={size} {...base} {...rest}>
    {children}
  </svg>
)

export const ChatIcon = (p) => (
  <Svg {...p}>
    <path d="M3.4 7.2a3 3 0 0 1 3-3h11.2a3 3 0 0 1 3 3v6.1a3 3 0 0 1-3 3H9.6L5 19.8v-3.5h-.6a1 1 0 0 1-1-1z" />
    <circle cx="8.4" cy="10.3" r="1.05" fill="currentColor" stroke="none" />
    <circle cx="12" cy="10.3" r="1.05" fill="currentColor" stroke="none" />
    <circle cx="15.6" cy="10.3" r="1.05" fill="currentColor" stroke="none" />
  </Svg>
)

export const GearIcon = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="3.1" />
    <circle cx="12" cy="12" r="7.4" strokeDasharray="2.4 2.6" opacity="0.75" />
    <path d="M12 1.9v2.6M12 19.5v2.6M1.9 12h2.6M19.5 12h2.6M4.9 4.9l1.9 1.9M17.2 17.2l1.9 1.9M19.1 4.9l-1.9 1.9M6.8 17.2l-1.9 1.9" />
  </Svg>
)

export const ProfileEqIcon = (p) => (
  <Svg {...p} strokeWidth="1.9">
    <path d="M4 14.6V9.4M8 17.4V6.6M12 12.8v-1.6M16 17.4V6.6M20 14.6V9.4" />
  </Svg>
)

export const LangIcon = (p) => (
  <Svg {...p}>
    <rect x="3" y="3" width="18" height="18" rx="4.2" />
    <path d="M6.9 15.6 9.6 8.4l2.7 7.2M7.8 13.4h3.6" />
    <path d="M14.9 8.6h3.9M16.9 8.6v1.4c0 2.6-1 4.3-2.4 5.4M15.4 12.1c.7 1.9 1.9 2.9 3.4 3.4" />
  </Svg>
)

export const WaveIcon = (p) => (
  <Svg {...p} strokeWidth="1.9">
    <path d="M3 12.4v-.8M6.4 16.2V7.8M9.8 18.4V5.6M13.2 14.6V9.4M16.6 17.4V6.6M20 13.2v-2.4" />
  </Svg>
)

export const ChartIcon = (p) => (
  <Svg {...p}>
    <path d="M3.6 3.4v14.2a2.4 2.4 0 0 0 2.4 2.4h14.4" />
    <path d="M7.6 15.4l3.4-4.3 3 2.4 4.6-6" />
    <circle cx="11" cy="11.1" r="1" fill="currentColor" stroke="none" />
    <circle cx="14" cy="13.5" r="1" fill="currentColor" stroke="none" />
  </Svg>
)

export const MicIcon = (p) => (
  <Svg {...p} strokeWidth="1.85">
    <rect x="9" y="2.4" width="6" height="11.2" rx="3" />
    <path d="M5.4 11.2v1.2a6.6 6.6 0 0 0 13.2 0v-1.2M12 19v2.6M8.6 21.6h6.8" />
  </Svg>
)

export const HandIcon = (p) => (
  <Svg {...p} strokeWidth="1.75">
    <path d="M9 11.4V5.2a1.6 1.6 0 0 1 3.2 0v5.4" />
    <path d="M12.2 10.6V4.4a1.6 1.6 0 0 1 3.2 0v6.2" />
    <path d="M15.4 11V6.6a1.55 1.55 0 0 1 3.1 0v7.1a7.4 7.4 0 0 1-7.4 7.4h-.5a6.1 6.1 0 0 1-6.1-6.1v-3.3a1.55 1.55 0 0 1 3.1 0" />
    <path d="M19.9 3.1c1 1 1.6 2.3 1.7 3.7M21.4 1.3c1.4 1.4 2.2 3.2 2.3 5.2" opacity="0.6" />
  </Svg>
)

export const StopIcon = (p) => (
  <Svg {...p}>
    <rect x="6.2" y="6.2" width="11.6" height="11.6" rx="2.6" fill="currentColor" stroke="none" />
  </Svg>
)

export const SendIcon = (p) => (
  <Svg {...p} strokeWidth="1.8">
    <path d="M3.2 11.8 20.6 4.1l-7.7 17.4-2-7.6z" />
    <path d="M10.9 13.9 20.6 4.1" />
  </Svg>
)

export const CheckIcon = (p) => (
  <Svg {...p} strokeWidth="2.4">
    <path d="M4.4 12.7l4.8 4.7L19.6 6.9" />
  </Svg>
)

export const CheckRingIcon = (p) => (
  <Svg {...p} strokeWidth="1.8">
    <circle cx="12" cy="12" r="8.8" />
    <path d="M8.1 12.3l2.8 2.8 5.1-6.1" />
  </Svg>
)

/* Wireframe polyhedron sitting inside the speaker-profile ring. */
export const LatticeIcon = (p) => (
  <Svg {...p} strokeWidth="1.15" box="48">
    <path d="M24 5 41.5 15v20L24 45 6.5 35V15z" />
    <path d="M24 5v40M6.5 15l35 20M41.5 15l-35 20" />
    <path d="M24 12.6l11 6.3v12.2L24 37.4l-11-6.3V18.9z" opacity="0.85" />
    <path d="M13 18.9l22 12.2M35 18.9l-22 12.2M24 12.6v24.8" opacity="0.6" />
    <circle cx="24" cy="25" r="3.4" />
  </Svg>
)
