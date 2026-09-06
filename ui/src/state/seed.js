/** Seed transcript + panel readouts. Replace with live engine data later. */

export const SEED_MESSAGES = []

export const LANGUAGES = [
  { code: 'en', label: 'EN', full: 'ENGLISH' },
  { code: 'te', label: 'తెలుగు', full: 'TELUGU', script: 'indic' },
  { code: 'hi', label: 'हिंदी', full: 'HINDI', script: 'indic' },
]

/** Canned replies so the state machine can be driven from the UI alone. */
export const CANNED = [
  'Start with the basics, Boss — syntax, then small projects daily.',
  'Running that now, Boss.',
  'Understood, Boss. Standing by.',
  'Here is what I found, Boss.',
  'Done, Boss. Anything else?',
]
