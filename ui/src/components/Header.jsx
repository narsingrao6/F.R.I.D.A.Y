import Waveform from './Waveform.jsx'

/** Row of fading energy pips flanking the status capsule. */
function Pips({ dir = 'left', n = 7 }) {
  return (
    <div className={`pips ${dir}`} aria-hidden="true">
      {Array.from({ length: n }, (_, i) => (
        <i key={i} style={{ '--i': i, '--n': n }} />
      ))}
    </div>
  )
}

export default function Header({ status, clock }) {
  return (
    <header className="hdr">
      {/* ---- brand ---- */}
      <div className="hdr-brand">
        <div className="brand-frame">
          <span className="hud-corner tl" />
          <span className="hud-corner tr" />
          <span className="hud-corner bl" />
          <span className="hud-corner br" />
          <h1 className="brand-name">F.R.I.D.A.Y.</h1>
          <p className="brand-tag">
            <span>INTELLIGENT</span>
            <b>•</b>
            <span>RELIABLE</span>
            <b>•</b>
            <span>ADAPTIVE</span>
          </p>
        </div>
      </div>

      {/* ---- processing status + clock ---- */}
      <div className="hdr-center">
        <div className="hdr-rail" aria-hidden="true">
          <span className="rail-line l" />
          <span className="rail-line r" />
        </div>

        <div className="status-row">
          <Pips dir="left" />
          <span className="chev l" aria-hidden="true" />
          <div className="status-capsule" role="status">
            <span className="status-orb" />
            <span className="status-text">{status}</span>
          </div>
          <span className="chev r" aria-hidden="true" />
          <Pips dir="right" />
        </div>

        <div className="clock">
          <span className="clock-time">{clock.time}</span>
          <b>•</b>
          <span>{clock.day}</span>
          <b>•</b>
          <span>{clock.date}</span>
        </div>
      </div>

      {/* ---- AI active ---- */}
      <div className="hdr-status">
        <div className="ai-badge">
          <Waveform count={5} className="ai-wave" shape="bell" />
          <span className="ai-text">AI ACTIVE</span>
          <span className="dot" />
        </div>
      </div>
    </header>
  )
}
