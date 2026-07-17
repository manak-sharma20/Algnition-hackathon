import Papa from 'papaparse'
import React, { useEffect, useMemo, useState } from 'react'
import BattleView from './components/BattleView'
import ChannelCommandCenter from './components/ChannelCommandCenter'
import GlobeScene from './components/GlobeScene'
import RiskDial from './components/RiskDial'
import TribunalVerdictPanel from './components/TribunalVerdictPanel'
import { aggregateByChannel, coerceRow, overrideKey } from './utils/forecast'

const TABS = [
  { key: 'command', label: 'Command' },
  { key: 'verdict', label: 'Tribunal' },
  { key: 'battle', label: 'Battle' },
]

const PERIODS = [30, 60, 90]

export default function App() {
  const [rows, setRows] = useState([])
  const [loadError, setLoadError] = useState(null)
  const [level, setLevel] = useState('p50')
  const [periodDays, setPeriodDays] = useState(30)
  const [budgetOverrides, setBudgetOverrides] = useState({})
  const [activeTab, setActiveTab] = useState('command')
  const [selectedChannel, setSelectedChannel] = useState(null)

  useEffect(() => {
    fetch('/predictions.csv')
      .then((res) => {
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
        return res.text()
      })
      .then((text) => {
        const { data } = Papa.parse(text, { header: true, skipEmptyLines: true })
        setRows(data.map(coerceRow))
      })
      .catch((err) => setLoadError(err.message))
  }, [])

  function handleFileUpload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        setRows(results.data.map(coerceRow))
        setBudgetOverrides({})
        setLoadError(null)
      },
    })
  }

  const filteredRows = useMemo(() => rows.filter((r) => r.period_days === periodDays), [rows, periodDays])
  const channels = useMemo(
    () => aggregateByChannel(filteredRows, budgetOverrides, level),
    [filteredRows, budgetOverrides, level]
  )

  function handleChannelBudgetChange(channel, newTotalBudget) {
    const current = channels.find((c) => c.channel === channel)
    if (!current || current.budget <= 0) return
    const scale = newTotalBudget / current.budget

    setBudgetOverrides((prev) => {
      const next = { ...prev }
      for (const campaign of current.campaigns) {
        next[overrideKey(campaign)] = campaign.budget * scale
      }
      return next
    })
  }

  return (
    <div className="relative min-h-dvh text-white">
      {/* The intelligence engine — always present, reframed per section */}
      <GlobeScene mode={activeTab} activeChannel={selectedChannel} onSelectChannel={setSelectedChannel} />

      {/* Top bar */}
      <header className="fixed inset-x-0 top-0 z-30 flex h-16 items-center justify-between px-6 md:px-10">
        <div className="flex items-baseline gap-3">
          <span className="text-[13px] font-semibold tracking-[0.34em] text-white">WAR ROOM</span>
          <span className="hidden text-[10px] tracking-[0.2em] text-white/35 sm:block">AIGNITION 3.0</span>
        </div>

        <nav className="absolute left-1/2 flex -translate-x-1/2 items-center gap-8">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`relative py-2 text-[11px] font-medium uppercase tracking-[0.28em] transition-colors duration-500 ${
                activeTab === tab.key ? 'text-white' : 'text-white/35 hover:text-white/70'
              }`}
            >
              {tab.label}
              <span
                className={`absolute -bottom-0.5 left-1/2 h-px -translate-x-1/2 bg-white transition-all duration-500 ease-premium ${
                  activeTab === tab.key ? 'w-6 opacity-100' : 'w-0 opacity-0'
                }`}
              />
            </button>
          ))}
        </nav>

        <label className="btn-ghost">
          Load CSV
          <input type="file" accept=".csv" className="hidden" onChange={handleFileUpload} />
        </label>
      </header>

      {loadError && (
        <div className="fixed inset-x-0 top-20 z-40 flex justify-center px-6">
          <div className="panel max-w-xl px-5 py-3 text-sm text-status-critical" style={{ borderColor: 'rgba(208,59,59,0.35)' }}>
            Couldn't load default predictions.csv ({loadError}). Run ./run.sh, then use "Load CSV" above.
          </div>
        </div>
      )}

      {/* Content layer — leans gently against the cursor for depth */}
      <main
        className="relative z-10"
        style={{
          transform: 'translate3d(calc(var(--par-x, 0) * -7px), calc(var(--par-y, 0) * -5px), 0)',
          willChange: 'transform',
        }}
      >
        <div key={activeTab} className="scene-enter">
          {activeTab === 'command' && (
            <ChannelCommandCenter
              channels={channels}
              level={level}
              onBudgetChange={handleChannelBudgetChange}
              periodDays={periodDays}
              selectedChannel={selectedChannel}
              onSelectChannel={setSelectedChannel}
            />
          )}
          {activeTab === 'verdict' && <TribunalVerdictPanel rows={filteredRows} horizonDays={periodDays} />}
          {activeTab === 'battle' && <BattleView rows={filteredRows} />}
        </div>
      </main>

      {/* Control dock — risk appetite and planning horizon, present everywhere */}
      <div className="pointer-events-none fixed inset-x-0 bottom-5 z-30 flex justify-center px-4">
        <div className="panel pointer-events-auto flex items-center gap-4 !rounded-full px-4 py-2">
          <RiskDial level={level} onChange={setLevel} />
          <div className="h-5 w-px bg-white/10" />
          <div className="seg">
            {PERIODS.map((p) => (
              <button
                key={p}
                onClick={() => setPeriodDays(p)}
                className={`seg-btn ${periodDays === p ? 'is-active' : ''}`}
              >
                {p}d
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
