import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { SEED_MESSAGES, CANNED } from './seed.js'

const STATUS = {
  idle: 'STANDBY',
  listening: 'LISTENING',
  thinking: 'PROCESSING',
  speaking: 'SPEAKING',
}

const CAPTION = {
  idle: 'Standing by',
  listening: 'Listening...',
  thinking: 'Thinking...',
  speaking: 'Speaking...',
}

const clockNow = () => {
  const d = new Date()
  return {
    time: d
      .toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
      .toUpperCase(),
    day: d.toLocaleDateString('en-US', { weekday: 'long' }).toUpperCase(),
    date: d
      .toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
      .toUpperCase(),
  }
}

const stamp = () =>
  new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })

export function useFriday() {
  const [phase, setPhase] = useState('idle')
  const [messages, setMessages] = useState(SEED_MESSAGES)
  const [lang, setLang] = useState('en')
  const [clock, setClock] = useState(clockNow)
  const [uptime, setUptime] = useState(0)
  const [micOn, setMicOn] = useState(false)

  /** Live voice amplitude, 0..1. Read by the 3D loop every frame. */
  const amplitude = useRef(0)
  const phaseRef = useRef(phase)
  phaseRef.current = phase
  const timers = useRef([])

  const later = useCallback((fn, ms) => {
    const id = setTimeout(fn, ms)
    timers.current.push(id)
    return id
  }, [])

  useEffect(
    () => () => {
      timers.current.forEach(clearTimeout)
      timers.current = []
    },
    [],
  )

  /* one-second heartbeat: wall clock + uptime */
  useEffect(() => {
    const id = setInterval(() => {
      setClock(clockNow())
      setUptime((u) => u + 1)
    }, 1000)
    return () => clearInterval(id)
  }, [])

  /* synthesised speech envelope — layered sines gated by a syllable pulse */
  useEffect(() => {
    let raf
    let t = 0
    let last = performance.now()
    const tick = (now) => {
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      t += dt
      let target = 0
      if (phaseRef.current === 'speaking') {
        const syl = Math.max(0, Math.sin(t * 9.1) * 0.6 + Math.sin(t * 3.7) * 0.4)
        const grain = 0.72 + 0.28 * Math.sin(t * 27.3 + Math.cos(t * 11.7) * 2)
        target = Math.min(1, syl * grain * 1.25)
      } else if (phaseRef.current === 'listening') {
        target = 0.22 + 0.18 * Math.sin(t * 2.3) + 0.08 * Math.sin(t * 7.9)
      }
      amplitude.current += (target - amplitude.current) * Math.min(1, dt * 12)
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [])

  const push = useCallback((msg) => {
    setMessages((prev) => {
      // Don't add duplicate messages unnecessarily
      return [
        ...prev.map((m) => ({ ...m, stacked: false })),
        { id: Date.now() + Math.random(), at: stamp(), ...msg },
      ]
    })
  }, [])

  useEffect(() => {
    let active = true
    const poll = async () => {
      if (!active) return
      if (window.pywebview && window.pywebview.api) {
        try {
          const updates = await window.pywebview.api.get_updates()
          if (updates && active) {
            setPhase((oldPhase) => (oldPhase !== updates.phase ? updates.phase : oldPhase))
            if (updates.micOn !== undefined) {
              setMicOn(updates.micOn)
            }
            if (updates.messages && updates.messages.length > 0) {
              updates.messages.forEach(msg => {
                push({ kind: msg.kind, text: msg.text })
              })
            }
          }
        } catch (e) {
          console.error("Polling error", e)
        }
      }
      setTimeout(poll, 100)
    }
    setTimeout(poll, 500)
    
    return () => { active = false }
  }, [push])

  const send = useCallback(
    (text) => {
      const body = text.trim()
      if (!body) return

      push({ kind: 'user', text: body, stacked: true })

      if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.send_command(body)
      }
    },
    [push],
  )

  const toggleMic = useCallback(() => {
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.toggle_mic()
    } else {
        setMicOn((on) => {
        const next = !on
        setPhase(next ? 'listening' : 'idle')
        return next
        })
    }
  }, [])

  const interrupt = useCallback(() => {
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.interrupt()
    } else {
        timers.current.forEach(clearTimeout)
        timers.current = []
        setPhase('listening')
        setMicOn(true)
    }
  }, [])

  const halt = useCallback(() => {
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.halt()
    } else {
        timers.current.forEach(clearTimeout)
        timers.current = []
        setMicOn(false)
        setPhase('idle')
    }
  }, [])

  const metrics = useMemo(
    () => ({
      processing: phase === 'thinking' ? '—' : '1.2s',
      messages: messages.length,
      uptime: `${Math.floor(uptime / 60)} min`,
      score: 98,
    }),
    [phase, messages.length, uptime],
  )

  return {
    phase,
    setPhase,
    status: STATUS[phase],
    caption: CAPTION[phase],
    messages,
    send,
    lang,
    setLang,
    clock,
    micOn,
    toggleMic,
    interrupt,
    halt,
    metrics,
    amplitude,
  }
}
