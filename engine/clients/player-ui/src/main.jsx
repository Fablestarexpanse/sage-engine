import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { PlayThemeProvider } from './PlayThemeContext.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <PlayThemeProvider>
      <App />
    </PlayThemeProvider>
  </StrictMode>,
)
