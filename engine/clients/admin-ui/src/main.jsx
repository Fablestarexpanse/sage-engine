import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { AdminThemeProvider } from './AdminThemeContext.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AdminThemeProvider>
      <App />
    </AdminThemeProvider>
  </StrictMode>,
)
