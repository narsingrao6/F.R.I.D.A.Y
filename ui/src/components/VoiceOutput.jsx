import HudPanel from './HudPanel.jsx'
import { WaveIcon } from './Icons.jsx'
import Waveform from './Waveform.jsx'

export default function VoiceOutput({
  voice = 'Aria Neural',
  rate = '+5%',
  volume = '100%',
  speaking = false,
}) {
  return (
    <HudPanel
      className="p-voice"
      accent="var(--magenta)"
      accent2="var(--pink-hot)"
      glow={0.55}
      icon={<WaveIcon size={19} />}
      title="Voice Output"
    >
      <div className="voice">
        <div className="voice-meta">
          <div className="row">
            <span>Voice:</span>
            <span className="row-val">{voice}</span>
          </div>
          <div className="row">
            <span>Rate:</span>
            <span className="row-val">
              {rate}
              <b className="sep">•</b>
              <span className="muted">Volume:</span>
              {volume}
            </span>
          </div>
        </div>
        <Waveform
          count={13}
          className="voice-wave"
          shape="bell"
          peak={speaking ? 1.25 : 0.85}
        />
      </div>
    </HudPanel>
  )
}
