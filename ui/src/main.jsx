import React from 'react'
import ReactDOM from 'react-dom/client'

// Bundled locally — no CDN, no network at runtime.
import '@fontsource/orbitron/400.css'
import '@fontsource/orbitron/500.css'
import '@fontsource/orbitron/700.css'
import '@fontsource/orbitron/900.css'
import '@fontsource/rajdhani/400.css'
import '@fontsource/rajdhani/500.css'
import '@fontsource/rajdhani/600.css'
import '@fontsource/rajdhani/700.css'
import '@fontsource/noto-sans-telugu/400.css'
import '@fontsource/noto-sans-telugu/600.css'
import '@fontsource/noto-sans-devanagari/400.css'
import '@fontsource/noto-sans-devanagari/600.css'

import App from './App.jsx'
import './App.css'

ReactDOM.createRoot(document.getElementById('root')).render(<App />)
