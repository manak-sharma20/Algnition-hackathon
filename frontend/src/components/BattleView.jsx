import React, { useEffect, useMemo, useState } from 'react'
import { compareAllocations } from '../utils/claudeApi'
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

function AllocationColumn({ label, allocation, onChange, channels, summary, isWinner }) {
  return (
    <div className={`rounded-xl border p-4 space-y-4 ${isWinner ? 'border-status-good bg-status-good/5' : 'border-neutral-800 bg-neutral-900'}`}>
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">{label}</h3>
        {isWinner && (
          <span className="rounded-full bg-status-good/15 px-2 py-0.5 text-xs font-semibold text-status-good">
            WINNER
          </span>
        )}
      </div>

      <div className="space-y-3">
        {channels.map((c) => {
          const meta = channelMeta(c.channel)
          return (
            <label key={c.channel} className="block">
              <span className={`text-xs ${meta.text}`}>{meta.label}</span>
              <div className="mt-1 flex items-center rounded-lg border border-neutral-700 bg-neutral-950 px-2">
                <span className="text-neutral-500 text-sm">$</span>
                <input
                  type="number"
                  className="w-full bg-transparent px-2 py-1.5 text-sm tabular-nums focus:outline-none"
                  value={allocation[c.channel] ?? 0}
                  min={0}
                  onChange={(e) => onChange(c.channel, Number(e.target.value))}
                />
              </div>
            </label>
          )
        })}
      </div>

      <div className="border-t border-neutral-800 pt-3 space-y-1 text-sm">
        <div className="flex justify-between">
          <span className="text-neutral-400">Total budget</span>
          <span className="tabular-nums">{formatCurrency(summary.totalBudget)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-neutral-400">Projected revenue (P50)</span>
          <span className="tabular-nums font-medium">{formatCurrency(summary.totalRevenue)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-neutral-400">Blended ROAS</span>
          <span className="tabular-nums font-semibold">{summary.roas.toFixed(2)}x</span>
        </div>
      </div>
    </div>
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
    return <div className="text-neutral-400">No forecast data loaded.</div>
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
    <div>
      <p className="text-sm text-neutral-400 mb-4">
        Compare two budget allocations at the P50 (expected) level. Revenue scales with budget at each channel's
        current blended ROAS - it doesn't model diminishing returns from heavier spend.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <AllocationColumn
          label="Allocation A"
          allocation={allocationA}
          onChange={(channel, value) => setAllocationA((prev) => ({ ...prev, [channel]: value }))}
          channels={baselineChannels}
          summary={summaryA}
          isWinner={winner === 'A'}
        />
        <AllocationColumn
          label="Allocation B"
          allocation={allocationB}
          onChange={(channel, value) => setAllocationB((prev) => ({ ...prev, [channel]: value }))}
          channels={baselineChannels}
          summary={summaryB}
          isWinner={winner === 'B'}
        />
      </div>

      <div className="mt-4">
        <button
          onClick={compare}
          className="text-sm rounded-lg border border-neutral-700 px-3 py-1.5 hover:bg-neutral-900"
        >
          Ask the tribunal to compare tradeoffs
        </button>
        {comparison && (
          <div className="mt-3 rounded-lg border border-neutral-800 bg-neutral-900 p-3 text-sm text-neutral-300">
            {comparison.loading && 'Comparing allocations…'}
            {comparison.error && <span className="text-status-critical">{comparison.error}</span>}
            {comparison.text && comparison.text}
          </div>
        )}
      </div>
    </div>
  )
}
