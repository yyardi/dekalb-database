import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { get } from '../api/client'

const NAV = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/trades', label: 'Trades', end: false },
  { to: '/import', label: 'Import CSV', end: false },
]

interface IBKRStatus {
  enabled: boolean
  connected: boolean
}

export default function Layout() {
  const [ibkrStatus, setIbkrStatus] = useState<IBKRStatus | null>(null)

  useEffect(() => {
    get<IBKRStatus>('/ibkr/status').then(setIbkrStatus).catch(() => null)
  }, [])

  return (
    <div className="flex min-h-screen bg-gray-950 text-gray-100">
      {/* Sidebar */}
      <aside className="w-52 shrink-0 border-r border-gray-800 flex flex-col py-6 px-3">
        <div className="px-3 mb-8">
          <p className="text-xs font-bold tracking-widest text-blue-400 uppercase mb-0.5">DeKalb Capital</p>
          <h1 className="text-base font-semibold text-white">Trade Tracker</h1>
        </div>

        <nav className="flex flex-col gap-0.5">
          {NAV.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `px-3 py-2 rounded-md text-sm transition-colors ${
                  isActive
                    ? 'bg-blue-600/20 text-blue-300 font-medium border border-blue-600/30'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800'
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>

        {/* IBKR connection status — automatic, no user action needed */}
        {ibkrStatus?.enabled && (
          <div className="mt-6 px-3">
            <div className={`flex items-center gap-1.5 text-xs ${ibkrStatus.connected ? 'text-green-400' : 'text-yellow-500'}`}>
              <span className={`w-1.5 h-1.5 rounded-full inline-block ${ibkrStatus.connected ? 'bg-green-400' : 'bg-yellow-500'}`} />
              {ibkrStatus.connected ? 'IBKR Connected' : 'IBKR Connecting...'}
            </div>
          </div>
        )}

        <div className="mt-auto px-3">
          <a
            href="/docs"
            target="_blank"
            rel="noreferrer"
            className="text-xs text-gray-600 hover:text-gray-400 transition-colors"
          >
            API Docs →
          </a>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
