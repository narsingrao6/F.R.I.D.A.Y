import { MicIcon, HandIcon, StopIcon } from './Icons.jsx'
import { TickRail } from './HudPanel.jsx'

const BUTTONS = [
  { id: 'mic', label: 'MIC', Icon: MicIcon, accent: 'var(--cyan)' },
  { id: 'interrupt', label: 'INTERRUPT', Icon: HandIcon, accent: 'var(--amber)' },
  { id: 'stop', label: 'STOP', Icon: StopIcon, accent: 'var(--red)' },
]

export default function ControlPanel({ micOn, onMic, onInterrupt, onStop }) {
  const handlers = { mic: onMic, interrupt: onInterrupt, stop: onStop }

  return (
    <div className="ctl-deck">
      <span className="hud-corner tl" />
      <span className="hud-corner tr" />
      <span className="hud-corner bl" />
      <span className="hud-corner br" />

      <div className="ctl-rails" aria-hidden="true">
        <TickRail count={9} />
        <TickRail count={9} />
      </div>

      <div className="ctl-row">
        {BUTTONS.map(({ id, label, Icon, accent }) => (
          <button
            key={id}
            type="button"
            onClick={handlers[id]}
            className={`ctl ctl-${id}${id === 'mic' && micOn ? ' is-on' : ''}${id === 'mic' && !micOn ? ' is-off' : ''}`}
            style={{ '--accent': accent }}
            aria-pressed={id === 'mic' ? micOn : undefined}
          >
            <span className="ctl-orbit" aria-hidden="true" />
            <span className="ctl-ring">
              <span className="ctl-fill" aria-hidden="true" />
              <Icon size={id === 'stop' ? 46 : 44} />
              {id === 'mic' && <span className={`ctl-status-dot${micOn ? ' active' : ''}`} aria-hidden="true" />}
            </span>
            <span className="ctl-label">{label}</span>
            {id === 'mic' && <span className="ctl-state-label">{micOn ? 'ACTIVE' : 'MUTED'}</span>}
          </button>
        ))}
      </div>

      <div className="ctl-foot" aria-hidden="true">
        <i />
      </div>
    </div>
  )
}
