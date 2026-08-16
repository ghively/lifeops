import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import { registerSW } from 'virtual:pwa-register'
import ErrorBoundary from './components/ErrorBoundary'
import { logger } from './lib/logger'

// Global error handlers — catch bugs outside React (promises, event handlers, libraries)
window.addEventListener('error', (event) => {
  logger.error('GlobalError', event.message, {
    filename: event.filename,
    lineno: event.lineno,
    colno: event.colno,
    stack: event.error?.stack,
  })
})

window.addEventListener('unhandledrejection', (event) => {
  logger.error('UnhandledRejection', event.reason?.message || String(event.reason), {
    stack: event.reason?.stack,
    promise: true,
  })
})

registerSW({
  immediate: true,
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
)
