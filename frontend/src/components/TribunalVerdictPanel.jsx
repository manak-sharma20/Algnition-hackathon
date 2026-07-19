import React, { useState } from 'react'
import { getDisagreementNarrative } from '../utils/llmApi'
import FloatingPanel from './FloatingPanel'
import RollingNumber from './RollingNumber'
import { channelMeta, formatCurrency, overrideKey } from '../utils/forecast'

function agreementBand(disagreementPct) {
  if (disagreementPct < 5) return { icon: '✓', label: 'Agree', classes: 'bg-status-good/15 text-status-good' }
  if (disagreementPct < 15) return { icon: '⚠', label: 'Diverge', classes: 'bg-status-warning/15 text-status-warning' }
  return { icon: '✕', label: 'Conflict', classes: 'bg-status-critical/15 text-status-critical' }
}

// The three members of the tribunal, each with its own geometric identity.
const MODELS = [
  { key: 'prophet_p50', short: 'P', name: 'Prophet', trait: 'Seasonality', hex: '#9085e9' },
  { key: 'xgb_p50', short: 'X', name: 'XGBoost', trait: 'Nonlinear signals', hex: '#199e70' },
  { key: 'ridge_p50', short: 'R', name: 'Ridge', trait: 'Stability', hex: '#3987e5' },
]

function ProphetGlyph({ hex }) {
  return (
    <svg width="76" height="76" viewBox="0 0 76 76" fill="none" aria-hidden="true">
      <circle
        cx="38" cy="38" r="34"
        stroke={hex} strokeOpacity="0.3" strokeDasharray="3 8"
        className="spin-slow" style={{ transformOrigin: 'center' }}
      />
      <path d="M38 15 L61 56 L15 56 Z" stroke={hex} strokeWidth="1.2" />
      <path
        d="M22 48 q4 -7 8 0 t8 0 t8 0 t8 0"
        stroke={hex} strokeWidth="1.2" strokeDasharray="4 4" className="dash-flow"
      />
    </svg>
  )
}

function XgbGlyph({ hex }) {
  return (
    <svg width="76" height="76" viewBox="0 0 76 76" fill="none" aria-hidden="true">
      <circle
        cx="38" cy="38" r="34"
        stroke={hex} strokeOpacity="0.3" strokeDasharray="3 8"
        className="spin-slower" style={{ transformOrigin: 'center' }}
      />
      <rect x="20" y="20" width="36" height="36" transform="rotate(45 38 38)" stroke={hex} strokeWidth="1.2" />
      <path
        d="M38 24 V38 M38 38 L29 47 M38 38 L47 47 M29 47 L25 53 M29 47 L33 53 M47 47 L43 53 M47 47 L51 53"
        stroke={hex} strokeWidth="1.2" strokeLinecap="round"
      />
    </svg>
  )
}

function RidgeGlyph({ hex }) {
  return (
    <svg width="76" height="76" viewBox="0 0 76 76" fill="none" aria-hidden="true">
      <circle cx="38" cy="38" r="32" stroke={hex} strokeWidth="1.2" strokeOpacity="0.85" />
      <circle
        cx="38" cy="38" r="22"
        stroke={hex} strokeWidth="1.2" strokeDasharray="3 6"
        className="spin-slow" style={{ transformOrigin: 'center' }}
      />
      <circle cx="38" cy="38" r="11" stroke={hex} strokeWidth="1.2" />
    </svg>
  )
}

const GLYPHS = { Prophet: ProphetGlyph, XGBoost: XgbGlyph, Ridge: RidgeGlyph }

// Anchor positions (percent of the triad stage) — entities as observers
// around the center of the table, convergence lines flowing inward.
const ANCHORS = [
  { left: 50, top: 12 },
  { left: 16, top: 74 },
  { left: 84, top: 74 },
]
const CENTER = { left: 50, top: 52 }

function Entity({ model, total, anchor }) {
  const Glyph = GLYPHS[model.name]
  return (
    <div
      className="absolute flex -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-1.5 text-center"
      style={{ left: `${anchor.left}%`, top: `${anchor.top}%` }}
    >
      <Glyph hex={model.hex} />
      <div className="mt-1 text-[10px] font-medium uppercase tracking-[0.3em] text-white">{model.name}</div>
      <div className="text-[9px] uppercase tracking-[0.2em] text-white/35">{model.trait}</div>
      <div className="text-sm font-light tabular-nums text-white/80">
        {total != null ? formatCurrency(total) : '—'}
      </div>
    </div>
  )
}

function ConsensusStage({ rows }) {
  const avgDisagreement = rows.reduce((s, r) => s + (r.disagreement_pct ?? 0), 0) / rows.length
  const consensus = Math.max(0, Math.min(100, 100 - avgDisagreement))

  const totals = MODELS.map((m) => {
    const values = rows.map((r) => r[m.key]).filter((v) => v != null)
    return values.length ? values.reduce((s, v) => s + v, 0) : null
  })

  const RADIUS = 56
  const CIRC = 2 * Math.PI * RADIUS

  return (
    <div className="relative mx-auto h-[380px] w-full max-w-2xl">
      {/* Convergence lines flowing toward the verdict */}
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        {ANCHORS.map((a, i) => (
          <line
            key={i}
            x1={a.left} y1={a.top} x2={CENTER.left} y2={CENTER.top}
            stroke="rgba(255,255,255,0.14)" strokeDasharray="1 5" strokeLinecap="round"
            className="dash-flow" vectorEffect="non-scaling-stroke"
          />
        ))}
      </svg>

      {/* The verdict — a confidence ring at the heart of the table */}
      <div
        className="absolute flex -translate-x-1/2 -translate-y-1/2 flex-col items-center justify-center"
        style={{ left: `${CENTER.left}%`, top: `${CENTER.top}%` }}
      >
        <svg width="150" height="150" viewBox="0 0 150 150" className="absolute">
          <circle cx="75" cy="75" r={RADIUS} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="1.5" />
          <circle
            cx="75" cy="75" r={RADIUS} fill="none"
            stroke="rgba(255,255,255,0.75)" strokeWidth="1.5" strokeLinecap="round"
            strokeDasharray={CIRC}
            strokeDashoffset={CIRC * (1 - consensus / 100)}
            transform="rotate(-90 75 75)"
            style={{ transition: 'stroke-dashoffset 1.1s cubic-bezier(0.22, 1, 0.36, 1)' }}
          />
        </svg>
        <div className="flex h-[150px] w-[150px] flex-col items-center justify-center">
          <RollingNumber
            value={consensus}
            format={(v) => `${v.toFixed(0)}%`}
            className="text-3xl font-extralight tracking-tight"
          />
          <span className="mt-1 text-[9px] uppercase tracking-[0.3em] text-white/40">Consensus</span>
        </div>
      </div>

      {MODELS.map((m, i) => (
        <Entity key={m.name} model={m} total={totals[i]} anchor={ANCHORS[i]} />
      ))}
    </div>
  )
}

export default function TribunalVerdictPanel({ rows, horizonDays }) {
  const [narratives, setNarratives] = useState({})

  async function explainRow(row) {
    const key = overrideKey(row)
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
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <p className="text-white/40">No forecast data loaded.</p>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-6xl px-6 pb-36 pt-24 md:px-10">
      <div className="text-center">
        <div className="eyebrow mb-3">The tribunal</div>
        <h2 className="text-3xl font-extralight tracking-tight md:text-4xl">Three minds. One verdict.</h2>
        <p className="mx-auto mt-3 max-w-md text-[13px] leading-relaxed text-white/45">
          Prophet, XGBoost, and Ridge each forecast every campaign independently. Where they disagree, ask why.
        </p>
      </div>

      <div className="mt-8">
        <ConsensusStage rows={rows} />
      </div>

      {/* Campaign dossiers */}
      <FloatingPanel className="mt-10 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 px-6 pb-4 pt-5">
          <span className="eyebrow">Campaign dossiers</span>
          <span className="flex items-center gap-4 text-[10px] uppercase tracking-[0.15em] text-white/40">
            {MODELS.map((m) => (
              <span key={m.short} className="inline-flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: m.hex }} />
                {m.short} · {m.name}
              </span>
            ))}
          </span>
        </div>

        <div className="overflow-x-auto">
          <div className="min-w-[860px]">
            <div className="grid grid-cols-[150px_1fr_110px_300px_170px] gap-3 border-t px-6 py-2.5 hairline">
              {['Channel', 'Campaign', 'Type', 'Model P50s', 'Agreement'].map((h) => (
                <span key={h} className="text-[9px] font-medium uppercase tracking-[0.24em] text-white/35">
                  {h}
                </span>
              ))}
            </div>

            {rows.map((row) => {
              const band = agreementBand(row.disagreement_pct)
              const meta = channelMeta(row.channel)
              const flagged = row.disagreement_pct >= 5
              const narrative = narratives[overrideKey(row)]

              return (
                <React.Fragment key={overrideKey(row)}>
                  <div className="grid grid-cols-[150px_1fr_110px_300px_170px] items-center gap-3 border-t px-6 py-3 hairline transition-colors duration-300 hover:bg-white/[0.025]">
                    <span className="inline-flex items-center gap-2 text-[13px] text-white/85">
                      <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: meta.hex }} />
                      {meta.label}
                    </span>
                    <span className="truncate text-[13px] text-white/70">{row.campaign_name}</span>
                    <span className="text-[12px] capitalize text-white/40">{row.campaign_type}</span>
                    <span className="flex items-center gap-3.5">
                      {MODELS.map((m) => (
                        <span key={m.short} className="inline-flex items-center gap-1.5" title={m.name}>
                          <span className="h-1.5 w-1.5 rounded-full" style={{ background: m.hex }} />
                          <span className="text-[12px] tabular-nums text-white/70">
                            {row[m.key] != null ? formatCurrency(row[m.key]) : '—'}
                          </span>
                        </span>
                      ))}
                    </span>
                    <span className="flex items-center gap-2.5">
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${band.classes}`}
                      >
                        <span>{band.icon}</span>
                        {row.disagreement_pct.toFixed(1)}%
                      </span>
                      {flagged && (
                        <button
                          onClick={() => explainRow(row)}
                          className="text-[10px] font-medium uppercase tracking-[0.18em] text-white/40 underline decoration-white/20 underline-offset-4 transition-colors hover:text-white"
                        >
                          Explain
                        </button>
                      )}
                    </span>
                  </div>

                  {flagged && narrative && (
                    <div className="border-t px-6 py-4 hairline" style={{ background: 'rgba(255,255,255,0.02)' }}>
                      <div className="border-l pl-4 text-[13px] leading-relaxed text-white/65" style={{ borderColor: 'rgba(255,255,255,0.15)' }}>
                        {narrative.loading && <span className="text-white/40">Asking the tribunal judge…</span>}
                        {narrative.error && <span className="text-status-critical">{narrative.error}</span>}
                        {narrative.text && narrative.text}
                      </div>
                    </div>
                  )}
                </React.Fragment>
              )
            })}
          </div>
        </div>
      </FloatingPanel>
    </div>
  )
}
