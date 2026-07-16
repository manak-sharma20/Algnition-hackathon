import React, { useState } from 'react'
import { getDisagreementNarrative } from '../utils/claudeApi'
import { channelMeta, formatCurrency } from '../utils/forecast'

function agreementBand(disagreementPct) {
  if (disagreementPct < 5) return { icon: '✓', label: 'Agree', classes: 'bg-status-good/15 text-status-good' }
  if (disagreementPct < 15) return { icon: '⚠', label: 'Diverge', classes: 'bg-status-warning/15 text-status-warning' }
  return { icon: '✕', label: 'Conflict', classes: 'bg-status-critical/15 text-status-critical' }
}

function ModelBadge({ label, value, colorClass }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium ${colorClass}`}>
      {label}
      <span className="tabular-nums">{value != null ? formatCurrency(value) : '—'}</span>
    </span>
  )
}

export default function TribunalVerdictPanel({ rows, horizonDays }) {
  const [narratives, setNarratives] = useState({})

  async function explainRow(row) {
    const key = row.campaign_name
    setNarratives((prev) => ({ ...prev, [key]: { loading: true } }))
    try {
      const text = await getDisagreementNarrative({
        channelName: `${row.campaign_name} (${row.channel})`,
        horizonDays,
        prophetP50: row.prophet_p50,
        xgbP50: row.xgb_p50,
        ridgeP50: row.ridge_p50,
        blendedP10: row.revenue_p10,
        blendedP50: row.revenue_p50,
        blendedP90: row.revenue_p90,
        disagreementPct: row.disagreement_pct,
        uncertaintyLevel: row.uncertainty_level,
        currentMonth: new Date().toLocaleString('default', { month: 'long' }),
        historicalRoas: row.roas_p50,
      })
      setNarratives((prev) => ({ ...prev, [key]: { loading: false, text } }))
    } catch (err) {
      setNarratives((prev) => ({ ...prev, [key]: { loading: false, error: err.message } }))
    }
  }

  if (!rows.length) {
    return <div className="text-neutral-400">No forecast data loaded.</div>
  }

  return (
    <div className="rounded-xl border border-neutral-800 overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-neutral-900 text-neutral-400 text-xs uppercase">
          <tr>
            <th className="text-left px-4 py-2">Channel</th>
            <th className="text-left px-4 py-2">Campaign</th>
            <th className="text-left px-4 py-2">Type</th>
            <th className="text-left px-4 py-2">Model P50s</th>
            <th className="text-left px-4 py-2">Agreement</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const band = agreementBand(row.disagreement_pct)
            const meta = channelMeta(row.channel)
            const flagged = row.disagreement_pct >= 5
            const narrative = narratives[row.campaign_name]

            return (
              <React.Fragment key={row.campaign_name}>
                <tr className="border-t border-neutral-800">
                  <td className="px-4 py-2">
                    <span className={`inline-flex items-center gap-1.5 ${meta.text}`}>
                      <span className={`h-2 w-2 rounded-full ${meta.dot}`} />
                      {meta.label}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-neutral-200">{row.campaign_name}</td>
                  <td className="px-4 py-2 text-neutral-400 capitalize">{row.campaign_type}</td>
                  <td className="px-4 py-2 space-x-1">
                    <ModelBadge label="Prophet" value={row.prophet_p50} colorClass="bg-series-violet/20 text-series-violet" />
                    <ModelBadge label="XGB" value={row.xgb_p50} colorClass="bg-series-aqua/20 text-series-aqua" />
                    <ModelBadge label="Ridge" value={row.ridge_p50} colorClass="bg-series-blue/20 text-series-blue" />
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-2">
                      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${band.classes}`}>
                        <span>{band.icon}</span>
                        {row.disagreement_pct.toFixed(1)}%
                      </span>
                      {flagged && (
                        <button
                          onClick={() => explainRow(row)}
                          className="text-xs text-neutral-400 underline hover:text-neutral-200"
                        >
                          Explain
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
                {flagged && narrative && (
                  <tr className="bg-neutral-900/60">
                    <td colSpan={5} className="px-4 py-3 text-sm text-neutral-300">
                      {narrative.loading && 'Asking the tribunal judge…'}
                      {narrative.error && <span className="text-status-critical">{narrative.error}</span>}
                      {narrative.text && narrative.text}
                    </td>
                  </tr>
                )}
              </React.Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
