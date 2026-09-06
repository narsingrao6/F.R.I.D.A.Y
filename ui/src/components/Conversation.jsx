import { useEffect, useRef, useState } from 'react'
import HudPanel from './HudPanel.jsx'
import { ChatIcon, SendIcon, CheckIcon, CheckRingIcon } from './Icons.jsx'

function Bubble({ msg }) {
  const indic = msg.script === 'indic' ? ' is-indic' : ''
  const inline = msg.kind === 'user' && !msg.stacked

  return (
    <li className={`msg is-${msg.kind}${msg.stacked ? ' is-stacked' : ''}`}>
      <div className={`bub${indic}`}>
        {msg.lead && <CheckRingIcon size={17} className="bub-lead" />}
        <span className="bub-text">{msg.text}</span>
        {inline && <time className="bub-at inside">{msg.at}</time>}
        {msg.done && <CheckIcon size={15} className="bub-done" />}
        {msg.stacked && <time className="bub-at under">{msg.at}</time>}
      </div>
      {msg.kind !== 'user' && <time className="bub-at outside">{msg.at}</time>}
    </li>
  )
}

export default function Conversation({ messages, onSend }) {
  const [draft, setDraft] = useState('')
  const listRef = useRef(null)
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length])

  const submit = (e) => {
    e.preventDefault()
    onSend(draft)
    setDraft('')
  }

  return (
    <HudPanel
      className="conv"
      bodyClass="conv-body"
      accent="var(--cyan)"
      accent2="var(--violet)"
      glow={0.7}
      icon={<ChatIcon size={22} />}
      title="Conversation"
    >
      <ul className="conv-list scroller" ref={listRef}>
        {messages.map((m) => (
          <Bubble key={m.id} msg={m} />
        ))}
        <li ref={endRef} className="conv-end" aria-hidden="true" />
      </ul>

      <div className="conv-pips" aria-hidden="true">
        <i />
        <i />
        <i />
        <i />
      </div>

      <form className="conv-input" onSubmit={submit}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Type a message..."
          aria-label="Message F.R.I.D.A.Y."
          spellCheck="false"
        />
        <button type="submit" className="conv-send" aria-label="Send message">
          <SendIcon size={21} />
        </button>
      </form>
    </HudPanel>
  )
}
