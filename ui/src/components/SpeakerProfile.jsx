import HudPanel from './HudPanel.jsx'
import { ProfileEqIcon, CheckIcon, LatticeIcon } from './Icons.jsx'

export default function SpeakerProfile({ name = 'UNKNOWN', confidence = 0 }) {
  const isVerified = confidence >= 85;

  return (
    <HudPanel
      className="p-speaker"
      accent={isVerified ? "var(--amber)" : "var(--blue)"}
      accent2={isVerified ? "var(--orange)" : "var(--cyan)"}
      glow={0.6}
      icon={<ProfileEqIcon size={19} />}
      title="Speaker Profile"
    >
      <div className="spk">
        <div className="spk-ring">
          <svg viewBox="0 0 100 100" aria-hidden="true">
            <circle className="spk-track" cx="50" cy="50" r="44" />
            <circle
              className="spk-arc"
              cx="50"
              cy="50"
              r="44"
              strokeDasharray={`${(confidence / 100) * 276} 276`}
            />
            <circle className="spk-inner" cx="50" cy="50" r="34" />
          </svg>
          <LatticeIcon size={44} className="spk-lattice" />
        </div>

        <div className="spk-meta">
          <div className="spk-name">{isVerified ? name : 'AWAITING...'}</div>
          <div className="spk-verified">
            {isVerified ? <CheckIcon size={13} /> : null}
            <span>{isVerified ? 'VERIFIED' : 'STANDBY'}</span>
          </div>
          <div className="spk-conf">Confidence: {confidence}%</div>
          <div className="spk-bar">
            <i style={{ width: `${confidence}%` }} />
            <b>{confidence}%</b>
          </div>
        </div>
      </div>
    </HudPanel>
  )
}
