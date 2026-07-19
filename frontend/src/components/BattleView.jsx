import React, { useEffect, useMemo, useState } from 'react'
import { compareAllocations } from '../utils/llmApi'
import FloatingPanel from './FloatingPanel'
import MiniGlobe from './MiniGlobe'
import RollingNumber from './RollingNumber'
import { aggregateByChannel, channelBudgetsToCampaignOverrides, channelMeta, formatCurrency } from '../utils/forecast'

function buildAllocation(baselineChannels) {
  const allocation = {}
  for (const c of baselineChannels) allocation[c.channel] = Math.round(c.budget)
  return allocation
}

function summarize(rows, allocation) {
  const campaignOverrides = channelBudgetsToCampaignOverrides(rows, allocation)
  const channels = aggregateByChannel(rows, campaignOverrides, 'p50')
  const totalBudget = channels.reduce((sum, c) => sum + c.budget, 0)
  const totalRevenue = channels.reduce((sum, c) => sum + c.revenue, 0)
  return { channels, totalBudget, totalRevenue, roas: totalBudget > 0 ? totalRevenue / totalBudget : 0 }
}

function StrategyWorld({ label, allocation, onChange, channels, summary, isWinner, floatDelay }) {
  return (
    <FloatingPanel
      floatDelay={floatDelay}
      className="p-6"
      style={isWinner ? { borderColor: 'rgba(12,163,12,0.35)', boxShadow: '0 32px 64px -28px rgba(0,0,0,0.85), 0 0 60px -18px rgba(12,163,12,0.25), inset 0 1px 0 rgba(255,255,255,0.06)' } : undefined}
    >
      <div className="flex items-start justify-between">
        <div>
          <div className="eyebrow">{label}</div>
          <div className="mt-1 text-[10px] uppercase tracking-[0.2em] text-white/30">Strategy world</div>
        </div>
        <span
          className={`inline-flex items-center gap-1.5 rounded-full bg-status-good/15 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-status-good transition-opacity duration-700 ${
            isWinner ? 'opacity-100' : 'opacity-0'
          }`}
        >
          ✓ Winner
        </span>
      </div>

      {/* This world's own globe */}
      <div className="flex justify-center py-2">
        <MiniGlobe size={150} highlight={isWinner} />
      </div>

      <div className="space-y-4">
        {channels.map((c) => {
          const meta = channelMeta(c.channel)
          return (
            <label key={c.channel} className="block">
              <span className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-white/40">
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: meta.hex }} />
                {meta.label}
              </span>
              <div className="mt-1 flex items-baseline gap-1.5">
                <span className="text-sm text-white/35">$</span>
                <input
                  type="number"
                  className="input-line"
                  value={allocation[c.channel] ?? 0}
                  min={0}
                  onChange={(e) => onChange(c.channel, Number(e.target.value))}
                />
              </div>
            </label>
          )
        })}
      </div>

      {/* Energy flowing from the plan into the outcome */}
      <div className="flow-line my-5" />

      <div className="space-y-3">
        <div className="flex items-baseline justify-between">
          <span className="text-[10px] uppercase tracking-[0.2em] text-white/40">Total budget</span>
          <RollingNumber value={summary.totalBudget} format={formatCurrency} className="text-sm tabular-nums text-white/75" />
        </div>
        <div className="flex items-baseline justify-between">
          <span className="text-[10px] uppercase tracking-[0.2em] text-white/40">Projected revenue · P50</span>
          <RollingNumber
            value={summary.totalRevenue}
            format={formatCurrency}
            className="text-[28px] font-extralight leading-none tracking-tight"
          />
        </div>
        <div className="flex items-baseline justify-between">
          <span className="text-[10px] uppercase tracking-[0.2em] text-white/40">Blended ROAS</span>
          <RollingNumber
            value={summary.roas}
            format={(v) => `${v.toFixed(2)}x`}
            className="text-sm font-medium tabular-nums text-white"
          />
        </div>
      </div>
    </FloatingPanel>
  )
}

export default function BattleView({ rows }) {
  const baselineChannels = useMemo(() => aggregateByChannel(rows, {}, 'p50'), [rows])
  const [allocationA, setAllocationA] = useState({})
  const [allocationB, setAllocationB] = useState({})
  const [comparison, setComparison] = useState(null)

  useEffect(() => {
    const base = buildAllocation(baselineChannels)
    setAllocationA(base)
    setAllocationB(base)
    setComparison(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows])

  if (!rows.length) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <p className="text-white/40">No forecast data loaded.</p>
      </div>
    )
  }

  const summaryA = summarize(rows, allocationA)
  const summaryB = summarize(rows, allocationB)
  const winner = summaryA.roas === summaryB.roas ? null : summaryA.roas > summaryB.roas ? 'A' : 'B'

  async function compare() {
    setComparison({ loading: true })
    try {
      const text = await compareAllocations({ allocationA: summaryA, allocationB: summaryB })
      setComparison({ loading: false, text })
    } catch (err) {
      setComparison({ loading: false, error: err.message })
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-6 pb-36 pt-24 md:px-10">
      <div className="text-center">
        <div className="eyebrow mb-3">Battle view</div>
        <h2 className="text-3xl font-extralight tracking-tight md:text-4xl">Two worlds. One budget.</h2>
        <p className="mx-auto mt-3 max-w-lg text-[13px] leading-relaxed text-white/45">
          Compare two budget allocations at the P50 (expected) level. Revenue scales with budget at each channel's
          current blended ROAS — it doesn't model diminishing returns from heavier spend.
        </p>
      </div>

      <div className="mt-10 grid gap-6 md:grid-cols-2">
        <StrategyWorld
          label="Allocation A"
          allocation={allocationA}
          onChange={(channel, value) => setAllocationA((prev) => ({ ...prev, [channel]: value }))}
          channels={baselineChannels}
          summary={summaryA}
          isWinner={winner === 'A'}
          floatDelay={0}
        />
        <StrategyWorld
          label="Allocation B"
          allocation={allocationB}
          onChange={(channel, value) => setAllocationB((prev) => ({ ...prev, [channel]: value }))}
          channels={baselineChannels}
          summary={summaryB}
          isWinner={winner === 'B'}
          floatDelay={2.3}
        />
      </div>

      <div className="mt-8 flex flex-col items-center gap-4">
        <button onClick={compare} className="btn-ghost">
          Ask the tribunal to compare tradeoffs
        </button>
        {comparison && (
          <FloatingPanel className="w-full max-w-2xl px-6 py-4">
            <div className="text-[13px] leading-relaxed text-white/70">
              {comparison.loading && <span className="text-white/40">Comparing allocations…</span>}
              {comparison.error && <span className="text-status-critical">{comparison.error}</span>}
              {comparison.text && comparison.text}
            </div>
          </FloatingPanel>
        )}
      </div>
    </div>
  )
}
