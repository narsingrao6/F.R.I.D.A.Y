/**
 * CSS-driven bar meter. Heights come from a deterministic pseudo-random
 * profile so it looks like real audio rather than a sine wave, and each bar
 * animates on its own offset.
 */
export default function Waveform({
  count = 5,
  className = '',
  live = true,
  peak = 1,
  shape = 'flat',
}) {
  return (
    <div
      className={`wave ${live ? 'is-live' : ''} ${className}`}
      style={{ '--peak': peak }}
      aria-hidden="true"
    >
      {Array.from({ length: count }, (_, i) => {
        const n = Math.abs(Math.sin(i * 12.9898) * 43758.5453) % 1
        const bell =
          shape === 'bell' ? Math.sin((Math.PI * (i + 0.5)) / count) ** 0.7 : 1
        const h = (0.26 + n * 0.74) * bell
        return (
          <i
            key={i}
            style={{
              '--h': h.toFixed(3),
              animationDelay: `${(-i * 0.11 - n * 0.4).toFixed(2)}s`,
            }}
          />
        )
      })}
    </div>
  )
}
