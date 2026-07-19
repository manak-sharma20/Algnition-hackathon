// Browser-side LLM caller for the War Room UI - the only network call in
// the whole project. The offline pipeline (run.sh) never touches this.
//
// Uses Groq's free OpenAI-compatible API directly from the browser (no SDK).
// The challenge brief allows any LLM provider (OpenAI/Gemini/Anthropic/
// similar); Groq was chosen for its free tier. Mirrors src/llm_narrator.py.

const GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'
const API_KEY = import.meta.env.VITE_GROQ_API_KEY
const MODEL = import.meta.env.VITE_GROQ_MODEL || 'llama-3.3-70b-versatile'

async function callGroq(prompt, { jsonMode = false, temperature = 0.3 } = {}) {
  if (!API_KEY) {
    throw new Error('VITE_GROQ_API_KEY is not set - copy frontend/.env.example to frontend/.env and add your key')
  }

  const body = {
    model: MODEL,
    messages: [{ role: 'user', content: prompt }],
    temperature,
  }
  if (jsonMode) {
    body.response_format = { type: 'json_object' }
  }

  const response = await fetch(GROQ_API_URL, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Groq API error ${response.status}: ${text}`)
  }

  const payload = await response.json()
  return payload.choices[0].message.content
}

// Role A: explain in 2-3 sentences why the three models disagree.
// prophetP50 may be null when Prophet was skipped for a short series.
export async function getDisagreementNarrative({
  channelName, horizonDays, prophetP50, xgbP50, ridgeP50, blendedP10, blendedP50, blendedP90,
  disagreementPct, uncertaintyLevel, currentMonth, historicalRoas,
}) {
  const prophetLine = prophetP50 != null ? `$${prophetP50.toFixed(2)}` : 'not available (series too short to fit)'
  const prompt = `You are an expert digital marketing analyst reviewing a revenue forecast for an e-commerce client.

Three statistical models (Prophet, XGBoost, and Ridge regression) have produced the following P50 (expected case) forecasts for the next ${horizonDays} days for ${channelName}:

- Prophet P50: ${prophetLine}
- XGBoost P50: $${xgbP50.toFixed(2)}
- Ridge P50: $${ridgeP50.toFixed(2)}

The blended ensemble forecast is P10: $${blendedP10.toFixed(2)}, P50: $${blendedP50.toFixed(2)}, P90: $${blendedP90.toFixed(2)}.

Model disagreement score: ${disagreementPct.toFixed(1)}% (${uncertaintyLevel} uncertainty)

The current month is ${currentMonth}. Historical blended ROAS for this channel over the last 30 days was ${historicalRoas.toFixed(2)}.

In 2-3 sentences, explain in plain English WHY these three models are disagreeing. Be specific about what each model is likely seeing that the others are not. Do not use jargon. Do not hedge with "it could be" - state clearly what the most likely cause of disagreement is. End with one sentence about what this means for the agency's confidence in this forecast.`

  return callGroq(prompt)
}

// Role B: three-paragraph causal summary of past performance, forecast, and risk.
export async function getCausalSummary({ channelName, horizonDays, historical, forecast }) {
  const prompt = `You are an expert digital marketing analyst writing a forecast summary for an agency client report.

Here is the historical and forecast data for ${channelName} over the last 90 days and next ${horizonDays} days:

HISTORICAL (last 30 days):
- Total spend: $${historical.spend.toFixed(2)}
- Total revenue: $${historical.revenue.toFixed(2)}
- Blended ROAS: ${historical.roas.toFixed(2)}
- Average CVR: ${historical.cvr.toFixed(2)}%
- Spend trend: ${historical.spendTrend} (growing/declining/stable)

FORECAST (next ${horizonDays} days):
- Projected revenue P50: $${forecast.p50.toFixed(2)}
- Projected revenue range: $${forecast.p10.toFixed(2)} to $${forecast.p90.toFixed(2)}
- Projected blended ROAS: ${forecast.roas.toFixed(2)}
- Proposed budget: $${forecast.proposedBudget.toFixed(2)}

Write exactly three paragraphs:

Paragraph 1 - What drove past performance: In 2-3 sentences, identify the 1-2 most important factors that drove revenue performance over the last 30 days on this channel. Be specific about spend levels, conversion rates, and any seasonal effects visible in the data.

Paragraph 2 - What the forecast expects: In 2-3 sentences, explain what the model is projecting and why. Connect the forecast to the specific inputs (spend level, historical ROAS, seasonal period) that are driving it. State the confidence level clearly.

Paragraph 3 - What could break this forecast: In 2 sentences, name the single most likely risk that could cause actual revenue to fall below the P10 estimate, and the single most likely upside scenario that could push revenue above the P90 estimate.

Use plain English. No bullet points. No headers within paragraphs. Write as if explaining to a smart client who is not a data scientist.`

  return callGroq(prompt)
}

// Battle View: one-sentence tradeoff comparison between two budget
// allocations (not one of the three forecast-report roles above).
export async function compareAllocations({ allocationA, allocationB }) {
  const prompt = `You are a media planner comparing two budget allocations for an e-commerce client.

Allocation A: $${allocationA.totalBudget.toFixed(2)} total budget, projected revenue $${allocationA.totalRevenue.toFixed(2)}, blended ROAS ${allocationA.roas.toFixed(2)}x.
Allocation B: $${allocationB.totalBudget.toFixed(2)} total budget, projected revenue $${allocationB.totalRevenue.toFixed(2)}, blended ROAS ${allocationB.roas.toFixed(2)}x.

In exactly one sentence, state which allocation is the better tradeoff and why. Plain English, no jargon.`

  return callGroq(prompt)
}

// Role C: top-3 ranked operational risks across all channels, as JSON.
export async function getRiskJson({ channelsData, horizonDays }) {
  const channelBlocks = channelsData
    .map(
      (c) => `CHANNEL: ${c.channelName}
- Proposed budget: $${c.budget.toFixed(2)}
- Projected ROAS P50: ${c.roasP50.toFixed(2)}
- Projected ROAS P10 (worst case): ${c.roasP10.toFixed(2)}
- Revenue P50: $${c.revenueP50.toFixed(2)}
- CVR trend (last 14 days): ${c.cvrTrend} (improving/declining/stable)
- Model uncertainty: ${c.uncertaintyLevel}
- Spend vs last period: ${c.spendChange.toFixed(1)}%`
    )
    .join('\n')

  const prompt = `You are a senior digital marketing strategist reviewing a complete multi-channel forecast for an e-commerce client.

Here is the forecast summary across all channels for the next ${horizonDays} days:

${channelBlocks}

Identify and rank the top 3 operational risks across all channels combined. For each risk:
- Name it in 5 words or fewer (e.g. "Meta CVR declining sharply")
- Give it a severity: HIGH / MEDIUM / LOW
- Explain it in exactly 1 sentence
- Give exactly 1 specific, actionable recommendation in 1 sentence

Respond with a JSON object of the form {"risks": [{"rank": 1, "name": "...", "severity": "HIGH", "explanation": "...", "recommendation": "..."}, ...]} and nothing else.`

  const content = await callGroq(prompt, { jsonMode: true })
  return JSON.parse(content).risks
}
