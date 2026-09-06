import { useEffect, useRef } from 'react'
import { attachPointer, pointer, damp } from './state/pointer.js'
import { useFriday } from './state/useFriday.js'

import Background from './components/Background.jsx'
import Header from './components/Header.jsx'
import Conversation from './components/Conversation.jsx'
import EnergyCore from './components/EnergyCore.jsx'
import ControlPanel from './components/ControlPanel.jsx'
import SystemStatus from './components/SystemStatus.jsx'
import SpeakerProfile from './components/SpeakerProfile.jsx'
import LanguagePanel from './components/LanguagePanel.jsx'
import VoiceOutput from './components/VoiceOutput.jsx'
import SessionMetrics from './components/SessionMetrics.jsx'

function CaptionPips({ side }) {
  return (
    <span className={`cap-pips ${side}`} aria-hidden="true">
      {Array.from({ length: 6 }, (_, i) => (
        <i key={i} style={{ '--i': i }} />
      ))}
    </span>
  )
}

export default function App() {
  const f = useFriday()
  const shellRef = useRef(null)

  useEffect(() => attachPointer(), [])

  /* Propagate pointer position to shell CSS variables for panel parallax */
  useEffect(() => {
    let raf
    let sx = 0
    let sy = 0
    const tick = () => {
      const dt = 0.016
      sx = damp(sx, pointer.x, 2.2, dt)
      sy = damp(sy, pointer.y, 2.2, dt)
      if (shellRef.current) {
        shellRef.current.style.setProperty('--px', sx.toFixed(4))
        shellRef.current.style.setProperty('--py', sy.toFixed(4))
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [])

  return (
    <>
      {/* Layer 0: 2D particle/star field */}
      <Background />

      {/* Layer 1: Full-screen 3D galaxy background */}
      <EnergyCore phase={f.phase} amplitude={f.amplitude} />

      {/* Layer 2: All UI panels floating over the galaxy */}
      <div className="shell" ref={shellRef}>
        <Header status={f.status} clock={f.clock} />

        <div className="stage-row">
          <div className="col col-left">
            <Conversation messages={f.messages} onSend={f.send} />
          </div>

          <div className="col col-center">
            <div className="stage">
              <div className="stage-frame" aria-hidden="true">
                <span className="stage-ring ring-a" />
                <span className="stage-ring ring-b" />
                <span className="stage-ring ring-c" />
                <span className="stage-ring ring-d" />
                <span className="stage-ring ring-e" />
                <span className="stage-ring ring-f" />
                <span className="stage-ring ring-g" />
                <span className="stage-scanline" />
                <span className="stage-bracket bracket-l" />
                <span className="stage-bracket bracket-r" />
              </div>
              <div className={`stage-caption is-${f.phase}`}>
                <CaptionPips side="l" />
                <span className="cap-text">{f.caption}</span>
                <CaptionPips side="r" />
              </div>
            </div>

            <ControlPanel
              micOn={f.micOn}
              onMic={f.toggleMic}
              onInterrupt={f.interrupt}
              onStop={f.halt}
            />
          </div>

          <div className="col col-right">
            <SystemStatus />
            <SpeakerProfile />
            <LanguagePanel lang={f.lang} onPick={f.setLang} />
            <VoiceOutput speaking={f.phase === 'speaking'} />
            <SessionMetrics metrics={f.metrics} />
          </div>
        </div>
      </div>
    </>
  )
}
