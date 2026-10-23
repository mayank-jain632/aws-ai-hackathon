import { useState } from 'react'
import './App.css'

type Connection = 'unchecked' | 'checking' | 'connected' | 'failed'

export default function App() {
  const [connection, setConnection] = useState<Connection>('unchecked')

  async function checkBackend() {
    setConnection('checking')
    try {
      const response = await fetch('/api/health', {
        signal: AbortSignal.timeout(5000),
      })
      if (!response.ok) throw new Error('Request failed')
      const data: unknown = await response.json()
      if (
        typeof data !== 'object' || data === null ||
        !('status' in data) || data.status !== 'ok'
      ) throw new Error('Unexpected response')
      setConnection('connected')
    } catch {
      setConnection('failed')
    }
  }

  return (
    <main>
      <p className="team">Team 4</p>
      <h1>AWS hackathon</h1>
      <p>The local workspace is ready for your project.</p>
      <button onClick={checkBackend} disabled={connection === 'checking'}>
        {connection === 'checking' ? 'Checking…' : 'Check backend connection'}
      </button>
      <p role="status" aria-live="polite">
        {connection === 'connected' ? 'Backend connected.' :
          connection === 'failed' ? 'Cannot reach the backend. Start it with npm run dev:backend, then try again.' :
          connection === 'checking' ? 'Connecting to the local API…' :
          'Check the connection when both local servers are running.'}
      </p>
    </main>
  )
}
