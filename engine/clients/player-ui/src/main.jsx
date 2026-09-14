import './storageMigration.js'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { PlayThemeProvider } from './PlayThemeContext.jsx'
import { WorldProvider } from './WorldContext.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <WorldProvider>
      <PlayThemeProvider>
        <App />
      </PlayThemeProvider>
    </WorldProvider>
  </StrictMode>,
)
