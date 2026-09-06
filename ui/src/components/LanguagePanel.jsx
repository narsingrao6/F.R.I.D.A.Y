import HudPanel from './HudPanel.jsx'
import { LangIcon } from './Icons.jsx'
import { LANGUAGES } from '../state/seed.js'

export default function LanguagePanel({ lang, onPick }) {
  const active = LANGUAGES.find((l) => l.code === lang) || LANGUAGES[0]

  return (
    <HudPanel
      className="p-lang"
      accent="var(--violet)"
      accent2="var(--purple)"
      glow={0.55}
      icon={<LangIcon size={19} />}
      title="Language Detected"
    >
      <div className="lang-name">{active.full}</div>
      <div className="lang-sub">Auto-detected from speech</div>

      <div className="lang-pills">
        {LANGUAGES.map((l) => {
          const on = l.code === lang
          return (
            <button
              key={l.code}
              type="button"
              onClick={() => onPick(l.code)}
              className={`pill${on ? ' is-on' : ''}${
                l.script === 'indic' ? ' is-indic' : ''
              }`}
              aria-pressed={on}
            >
              {on ? `${l.label} (active)` : l.label}
            </button>
          )
        })}
      </div>
    </HudPanel>
  )
}
