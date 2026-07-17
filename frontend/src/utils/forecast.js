// Shared helpers for turning predictions.csv rows into what the four War
// Room views need: per-channel/campaign aggregates at a chosen risk level
// (P10/P50/P90) and period (30/60/90), plus a simple budget simulator.

export const NUMERIC_FIELDS = [
  'period_days',
  'revenue_p10',
  'revenue_p50',
  'revenue_p90',
  'roas_p10',
  'roas_p50',
  'roas_p90',
  'disagreement_pct',
  'prophet_p50',
  'xgb_p50',
  'ridge_p50',
]

export function coerceRow(row) {
  const out = { ...row }
  for (const field of NUMERIC_FIELDS) {
    const value = row[field]
    out[field] = value === '' || value === undefined || value === null ? null : Number(value)
  }
  return out
}

// predictions.csv has no explicit spend/budget column - it's implied by
// revenue_p50 / roas_p50 (both already in the file, since roas = revenue / spend
// by definition). This is the "current" budget shown pre-filled in editable
// budget inputs.
export function baselineBudget(row) {
  if (!row.roas_p50) return 0
  return row.revenue_p50 / row.roas_p50
}

// Budget simulation: holds ROAS constant and scales revenue linearly with
// the budget input. This does not model diminishing returns from increased
// spend (a full media-mix model is out of scope per the challenge brief) -
// it answers "at this channel's current efficiency, what would this budget
// produce", which is the same simplification most agency planning
// spreadsheets already make.
export function simulateRevenue(row, budget, level) {
  const roas = row[`roas_${level}`]
  return budget * (roas ?? 0)
}

export const UNCERTAINTY_RANK = { LOW: 0, MODERATE: 1, HIGH: 2 }

export function worstUncertainty(levels) {
  return levels.reduce(
    (worst, level) => (UNCERTAINTY_RANK[level] > UNCERTAINTY_RANK[worst] ? level : worst),
    'LOW'
  )
}

// Thresholds per the brief: green >4x, amber 2-4x, red <2x.
export function roasBand(roas) {
  if (roas > 4) return 'good'
  if (roas >= 2) return 'warning'
  return 'critical'
}

export const UNCERTAINTY_BAND = { LOW: 'good', MODERATE: 'warning', HIGH: 'critical' }

// Fixed categorical assignment, never cycled - same channel is always the
// same color across every view. Trio (blue/magenta/yellow) validated all-pairs
// for CVD separation + contrast on the void surface; hex mirrors the Tailwind
// token for canvas rendering.
export const CHANNEL_META = {
  google: { label: 'Google Ads', dot: 'bg-series-blue', text: 'text-series-blue', hex: '#3987e5' },
  meta: { label: 'Meta Ads', dot: 'bg-series-magenta', text: 'text-series-magenta', hex: '#d55181' },
  ms: { label: 'Microsoft Ads', dot: 'bg-series-yellow', text: 'text-series-yellow', hex: '#c98500' },
}

export function channelMeta(channel) {
  return (
    CHANNEL_META[channel] ?? { label: channel, dot: 'bg-neutral-500', text: 'text-neutral-400', hex: '#898781' }
  )
}

export const STATUS_CLASSES = {
  good: { bg: 'bg-status-good', text: 'text-status-good', badgeBg: 'bg-status-good/15', badgeText: 'text-status-good' },
  warning: {
    bg: 'bg-status-warning',
    text: 'text-status-warning',
    badgeBg: 'bg-status-warning/15',
    badgeText: 'text-status-warning',
  },
  critical: {
    bg: 'bg-status-critical',
    text: 'text-status-critical',
    badgeBg: 'bg-status-critical/15',
    badgeText: 'text-status-critical',
  },
}

// Campaign names repeat across channels (google and bing both export e.g.
// Search_TM_Campaign_02), so overrides must be keyed by (channel, campaign) -
// keying by campaign_name alone let budgets leak between channels (same bug
// the training pipeline fixed by keying the tribunal per channel).
export function overrideKey(row) {
  return `${row.channel}|${row.campaign_name}`
}

// Converts a {channel: totalBudget} map (what Battle View's two allocation
// columns edit) into a {overrideKey: budget} map (what aggregateByChannel's
// budgetOverrides expects) by splitting each channel's total across its
// campaigns in proportion to their baseline budget share.
export function channelBudgetsToCampaignOverrides(rows, channelBudgets) {
  const baselineByChannel = {}
  for (const row of rows) {
    baselineByChannel[row.channel] = (baselineByChannel[row.channel] ?? 0) + baselineBudget(row)
  }

  const overrides = {}
  for (const row of rows) {
    const channelTotal = channelBudgets[row.channel]
    if (channelTotal == null) continue
    const channelBaseline = baselineByChannel[row.channel] ?? 0
    const campaignCount = rows.filter((r) => r.channel === row.channel).length
    const share = channelBaseline > 0 ? baselineBudget(row) / channelBaseline : 1 / campaignCount
    overrides[overrideKey(row)] = channelTotal * share
  }
  return overrides
}

// Groups rows (already filtered to one period_days) by channel, applying
// any per-campaign budget overrides.
export function aggregateByChannel(rows, budgetOverrides, level) {
  const byChannel = {}

  for (const row of rows) {
    const budget = budgetOverrides[overrideKey(row)] ?? baselineBudget(row)
    const revenue = simulateRevenue(row, budget, level)

    if (!byChannel[row.channel]) {
      byChannel[row.channel] = {
        channel: row.channel,
        budget: 0,
        revenue: 0,
        revenueP10: 0,
        revenueP50: 0,
        revenueP90: 0,
        disagreementSum: 0,
        campaignCount: 0,
        uncertaintyLevels: [],
        campaigns: [],
      }
    }

    const agg = byChannel[row.channel]
    agg.budget += budget
    agg.revenue += revenue
    agg.revenueP10 += simulateRevenue(row, budget, 'p10')
    agg.revenueP50 += simulateRevenue(row, budget, 'p50')
    agg.revenueP90 += simulateRevenue(row, budget, 'p90')
    agg.disagreementSum += row.disagreement_pct ?? 0
    agg.campaignCount += 1
    agg.uncertaintyLevels.push(row.uncertainty_level)
    agg.campaigns.push({ ...row, budget, revenue })
  }

  return Object.values(byChannel).map((agg) => ({
    ...agg,
    roas: agg.budget > 0 ? agg.revenue / agg.budget : 0,
    roasP10: agg.budget > 0 ? agg.revenueP10 / agg.budget : 0,
    roasP50: agg.budget > 0 ? agg.revenueP50 / agg.budget : 0,
    roasP90: agg.budget > 0 ? agg.revenueP90 / agg.budget : 0,
    avgDisagreementPct: agg.campaignCount > 0 ? agg.disagreementSum / agg.campaignCount : 0,
    uncertaintyLevel: worstUncertainty(agg.uncertaintyLevels),
  }))
}

export function formatCurrency(value) {
  return `$${Math.round(value).toLocaleString()}`
}
