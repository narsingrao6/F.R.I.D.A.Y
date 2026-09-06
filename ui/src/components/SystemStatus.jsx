import HudPanel from './HudPanel.jsx'
import { GearIcon } from './Icons.jsx'

const ROWS = [
  { label: 'Online Brain', value: 'Active', tone: 'green' },
  { label: 'Offline Brain', value: 'Standby', tone: 'amber' },
]

export default function SystemStatus() {
  return (
    <HudPanel
      className="p-status"
      accent="var(--cyan)"
      accent2="var(--blue)"
      glow={0.5}
      icon={<GearIcon size={19} />}
      title="System Status"
    >
      <div className="p-rows">
        {ROWS.map(({ label, value, tone }) => (
          <div className="row" key={label}>
            <span>{label}</span>
            <span className={`row-val is-${tone}`}>
              <i className={`dot ${tone === 'amber' ? 'amber' : ''}`} />
              {value}
            </span>
          </div>
        ))}
      </div>
    </HudPanel>
  )
}
