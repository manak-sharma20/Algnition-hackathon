import React from 'react'

const POSITIONS = [
  { key: 'p10', label: 'P10', caption: 'Worst case — plan budgets you can survive even here.' },
  { key: 'p50', label: 'P50', caption: "Expected case — the tribunal's single best estimate." },
  { key: 'p90', label: 'P90', caption: 'Best case — what a strong month looks like.' },
]

export default function RiskDial({ level, onChange }) {
  const active = POSITIONS.find((p) => p.key === level) ?? POSITIONS[1]

  return (
    <div className="flex items-center gap-3">
      <div className="seg">
        {POSITIONS.map((p) => (
          <button
            key={p.key}
            onClick={() => onChange(p.key)}
            className={`seg-btn ${level === p.key ? 'is-active' : ''}`}
          >
            {p.label}
          </button>
        ))}
      </div>
      <p className="hidden max-w-[230px] text-[11px] leading-snug text-white/40 lg:block">{active.caption}</p>
    </div>
  )
}
