import React from 'react'
import FloatingPanel from './FloatingPanel'
import RollingNumber from './RollingNumber'
import { channelMeta, formatCurrency, roasBand, STATUS_CLASSES, UNCERTAINTY_BAND } from '../utils/forecast'

const LEVEL_LABEL = { p10: 'worst case', p50: 'expected', p90: 'best case' }

function RoasMeter({ roas }) {
  const band = STATUS_CLASSES[roasBand(roas)]
  const widthPct = Math.max(4, Math.min(100, (roas / 6) * 100))
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-[0.2em] text-white/40">ROAS efficiency</span>
        <span className="text-sm font-medium text-white">
          <RollingNumber value={roas} format={(v) => `${v.toFixed(2)}x`} />
        </span>
      </div>
      <div className={`h-0.5 w-full rounded-full ${band.badgeBg}`}>
        <div
          className={`h-full rounded-full ${band.bg} transition-all duration-700 ease-premium`}
          style={{ width: `${widthPct}%` }}
        />
      </div>
    </div>
  )
}

function RevenueRange({ revenueP10, revenueP50, revenueP90, maxRevenue, hex }) {
  const pct = (v) => Math.max(2, Math.min(100, (v / maxRevenue) * 100))
  return (
    <div>
      <div className="mb-1.5 text-[10px] uppercase tracking-[0.2em] text-white/40">Revenue range</div>
      <div className="relative h-1 overflow-hidden rounded-full bg-white/[0.06]">
        <div
          className="absolute inset-y-0 left-0 rounded-full transition-all duration-700 ease-premium"
          style={{ width: `${pct(revenueP90)}%`, background: hex, opacity: 0.22 }}
        />
        <div
          className="absolute inset-y-0 left-0 rounded-full transition-all duration-700 ease-premium"
          style={{ width: `${pct(revenueP50)}%`, background: hex, opacity: 0.5 }}
        />
        <div
          className="absolute inset-y-0 left-0 rounded-full transition-all duration-700 ease-premium"
          style={{ width: `${pct(revenueP10)}%`, background: hex }}
        />
      </div>
      <div className="mt-1.5 flex justify-between text-[10px] tabular-nums text-white/40">
        <span>P10 {formatCurrency(revenueP10)}</span>
        <span>P50 {formatCurrency(revenueP50)}</span>
        <span>P90 {formatCurrency(revenueP90)}</span>
      </div>
    </div>
  )
}

function ConfidenceBadge({ uncertaintyLevel }) {
  const status = STATUS_CLASSES[UNCERTAINTY_BAND[uncertaintyLevel] ?? 'warning']
  return (
    <span className="inline-flex items-center gap-1.5 text-[9px] font-medium uppercase tracking-[0.18em] text-white/50">
      <span className={`h-1.5 w-1.5 rounded-full ${status.bg}`} />
      {uncertaintyLevel} uncertainty
    </span>
  )
}

export default function ChannelCommandCenter({
  channels,
  level,
  onBudgetChange,
  periodDays,
  selectedChannel,
  onSelectChannel,
}) {
  if (!channels.length) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <p className="text-white/40">No forecast data loaded.</p>
      </div>
    )
  }

  const maxRevenue = Math.max(...channels.map((c) => c.revenueP90), 1)
  const totalRevenue = channels.reduce((sum, c) => sum + c.revenue, 0)
  const totalBudget = channels.reduce((sum, c) => sum + c.budget, 0)
  const totalP10 = channels.reduce((sum, c) => sum + c.revenueP10, 0)
  const totalP90 = channels.reduce((sum, c) => sum + c.revenueP90, 0)
  const blendedRoas = totalBudget > 0 ? totalRevenue / totalBudget : 0

  return (
    <div className="flex min-h-dvh flex-col px-6 pb-32 pt-24 md:px-10">
      {/* Hero — the number the room is built around */}
      <div className="pointer-events-none text-center">
        <div className="eyebrow mb-4">
          Projected revenue · next {periodDays} days · {level.toUpperCase()} {LEVEL_LABEL[level]}
        </div>
        <RollingNumber
          value={totalRevenue}
          format={formatCurrency}
          className="block text-6xl font-extralight leading-none tracking-tight md:text-[86px]"
        />
        <div className="mt-5 flex items-center justify-center gap-8 text-[12px] text-white/45">
          <span className="tabular-nums">P10 {formatCurrency(totalP10)}</span>
          <span className="text-white/75">
            Blended ROAS <RollingNumber value={blendedRoas} format={(v) => `${v.toFixed(2)}x`} />
          </span>
          <span className="tabular-nums">P90 {formatCurrency(totalP90)}</span>
        </div>
      </div>

      {/* Space for the globe to breathe */}
      <div className="min-h-[180px] flex-1" />

      {/* Channel consoles arranged around the table */}
      <div className="mx-auto grid w-full max-w-5xl gap-5 md:grid-cols-3">
        {channels.map((c, i) => {
          const meta = channelMeta(c.channel)
          const isSelected = selectedChannel === c.channel
          const somethingSelected = selectedChannel != null
          return (
            <div
              key={c.channel}
              className={`transition-all duration-700 ease-premium ${
                isSelected
                  ? 'md:-translate-y-2 md:scale-[1.02]'
                  : somethingSelected
                    ? 'opacity-55'
                    : ''
              } ${i === 1 ? 'md:translate-y-2' : ''}`}
            >
              <FloatingPanel
                floatDelay={i * 1.7}
                className={`space-y-5 p-5 ${isSelected ? '!border-white/20' : ''}`}
              >
                <button
                  onClick={() => onSelectChannel?.(isSelected ? null : c.channel)}
                  className="flex w-full items-center justify-between text-left"
                >
                  <span className="flex items-center gap-2.5">
                    <span className="h-2 w-2 rounded-full" style={{ background: meta.hex }} />
                    <span className="text-sm font-medium tracking-wide text-white">{meta.label}</span>
                  </span>
                  <ConfidenceBadge uncertaintyLevel={c.uncertaintyLevel} />
                </button>

                <div>
                  <div className="text-[10px] uppercase tracking-[0.2em] text-white/40">Projected revenue</div>
                  <RollingNumber
                    value={c.revenue}
                    format={formatCurrency}
                    className="mt-1 block text-[26px] font-light leading-none tracking-tight"
                  />
                </div>

                <label className="block">
                  <span className="text-[10px] uppercase tracking-[0.2em] text-white/40">Proposed budget</span>
                  <div className="mt-1 flex items-baseline gap-1.5">
                    <span className="text-sm text-white/35">$</span>
                    <input
                      type="number"
                      className="input-line"
                      value={Math.round(c.budget)}
                      min={0}
                      onChange={(e) => onBudgetChange(c.channel, Number(e.target.value))}
                    />
                  </div>
                </label>

                <RoasMeter roas={c.roas} />
                <RevenueRange
                  revenueP10={c.revenueP10}
                  revenueP50={c.revenueP50}
                  revenueP90={c.revenueP90}
                  maxRevenue={maxRevenue}
                  hex={meta.hex}
                />
              </FloatingPanel>
            </div>
          )
        })}
      </div>
    </div>
  )
}
