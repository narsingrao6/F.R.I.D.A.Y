import HudPanel from './HudPanel.jsx'
import { ChartIcon } from './Icons.jsx'

const R = 42
const C = 2 * Math.PI * R

export default function SessionMetrics({ metrics }) {
  const { processing, messages, uptime, score } = metrics

  return (
    <HudPanel
      className="p-metrics"
      accent="var(--blue)"
      accent2="var(--cyan)"
      glow={0.5}
      icon={<ChartIcon size={19} />}
      title="Session Metrics"
    >
      <div className="met">
        <div className="met-rows">
          <div className="row">
            <span>Processing:</span>
            <span className="row-val">{processing}</span>
          </div>
          <div className="row">
            <span>Messages:</span>
            <span className="row-val">{messages}</span>
          </div>
          <div className="row">
            <span>Uptime:</span>
            <span className="row-val">{uptime}</span>
          </div>
        </div>

        <div className="met-ring">
          <svg viewBox="0 0 100 100" aria-hidden="true">
            <defs>
              <linearGradient id="metGrad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="var(--cyan)" />
                <stop offset="52%" stopColor="var(--violet)" />
                <stop offset="100%" stopColor="var(--magenta)" />
              </linearGradient>
            </defs>
            <circle className="met-track" cx="50" cy="50" r={R} />
            <circle
              className="met-arc"
              cx="50"
              cy="50"
              r={R}
              strokeDasharray={`${(score / 100) * C} ${C}`}
            />
          </svg>
          <div className="met-num">
            {score}
            <sup>%</sup>
          </div>
        </div>
      </div>
    </HudPanel>
  )
}
