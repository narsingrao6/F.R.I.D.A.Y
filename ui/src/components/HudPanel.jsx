/**
 * Shared holographic panel frame: gradient hairline, corner brackets,
 * optional titled header. Accent colours are injected as CSS variables so
 * every panel can be re-themed without new stylesheets.
 */
export default function HudPanel({
  accent = 'var(--cyan)',
  accent2,
  glow = 0.55,
  icon,
  title,
  className = '',
  bodyClass = '',
  corners = true,
  children,
  style,
  ...rest
}) {
  return (
    <div
      className={`hud ${className}`}
      style={{
        '--accent': accent,
        '--accent-2': accent2 || accent,
        '--glow': glow,
        ...style,
      }}
      {...rest}
    >
      {corners && (
        <>
          <span className="hud-corner tl" />
          <span className="hud-corner tr" />
          <span className="hud-corner bl" />
          <span className="hud-corner br" />
        </>
      )}
      <div className={`hud-body ${bodyClass}`}>
        {title && (
          <div className="hud-title">
            {icon}
            <span>{title}</span>
          </div>
        )}
        {children}
      </div>
    </div>
  )
}

/** Tiny technical tick marks used as filler detail inside panels. */
export function TickRail({ count = 14 }) {
  return (
    <div className="tick-rail" aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <i key={i} style={{ height: `${i % 4 === 0 ? 8 : i % 2 ? 3 : 5}px` }} />
      ))}
    </div>
  )
}
