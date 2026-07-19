"""LLM narrative layer - turns tribunal forecast JSON into plain-English
explanations and a ranked risk list.

Standalone reference implementation, not imported by generate_features.py,
train.py, predict.py, or run.sh. The offline scored pipeline must run with
no network access; this module is here for local testing / notebook use
and mirrors what frontend/src/utils/llmApi.js does in the browser.

Uses Groq's OpenAI-compatible chat completions API (free tier, no SDK
dependency - plain stdlib HTTP so requirements.txt stays limited to what
the pickled models actually need). Reads the key from the GROQ_API_KEY
environment variable; never hardcode a key here.
"""
import json
import os
import urllib.error
import urllib.request

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


def _call_groq(prompt, json_mode=False, temperature=0.3):
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable is not set")

    body = {
        "model": DEFAULT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    request = urllib.request.Request(
        GROQ_API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "aignition-forecasting-tribunal/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Groq API error {e.code}: {e.read().decode('utf-8')}") from e

    return payload["choices"][0]["message"]["content"]


def get_disagreement_narrative(
    channel_name, horizon_days, prophet_p50, xgb_p50, ridge_p50, blended_p10, blended_p50, blended_p90,
    disagreement_pct, uncertainty_level, current_month, historical_roas,
):
    """Role A: explain in 2-3 sentences why the three models disagree.

    prophet_p50 may be None when Prophet was skipped for a short series -
    the disagreement score itself (see tribunal.py) is computed only from
    whichever models actually ran for that campaign.
    """
    prophet_line = f"${prophet_p50:.2f}" if prophet_p50 is not None else "not available (series too short to fit)"
    prompt = f"""You are an expert digital marketing analyst reviewing a revenue forecast for an e-commerce client.

Three statistical models (Prophet, XGBoost, and Ridge regression) have produced the following P50 (expected case) forecasts for the next {horizon_days} days for {channel_name}:

- Prophet P50: {prophet_line}
- XGBoost P50: ${xgb_p50:.2f}
- Ridge P50: ${ridge_p50:.2f}

The blended ensemble forecast is P10: ${blended_p10:.2f}, P50: ${blended_p50:.2f}, P90: ${blended_p90:.2f}.

Model disagreement score: {disagreement_pct:.1f}% ({uncertainty_level} uncertainty)

The current month is {current_month}. Historical blended ROAS for this channel over the last 30 days was {historical_roas:.2f}.

In 2-3 sentences, explain in plain English WHY these three models are disagreeing. Be specific about what each model is likely seeing that the others are not. Do not use jargon. Do not hedge with "it could be" - state clearly what the most likely cause of disagreement is. End with one sentence about what this means for the agency's confidence in this forecast."""
    return _call_groq(prompt)


def get_causal_summary(channel_name, horizon_days, historical, forecast):
    """Role B: three-paragraph causal summary of past performance, forecast, and risk."""
    prompt = f"""You are an expert digital marketing analyst writing a forecast summary for an agency client report.

Here is the historical and forecast data for {channel_name} over the last 90 days and next {horizon_days} days:

HISTORICAL (last 30 days):
- Total spend: ${historical['spend']:.2f}
- Total revenue: ${historical['revenue']:.2f}
- Blended ROAS: {historical['roas']:.2f}
- Average CVR: {historical['cvr']:.2f}%
- Spend trend: {historical['spend_trend']} (growing/declining/stable)

FORECAST (next {horizon_days} days):
- Projected revenue P50: ${forecast['p50']:.2f}
- Projected revenue range: ${forecast['p10']:.2f} to ${forecast['p90']:.2f}
- Projected blended ROAS: {forecast['roas']:.2f}
- Proposed budget: ${forecast['proposed_budget']:.2f}

Write exactly three paragraphs:

Paragraph 1 - What drove past performance: In 2-3 sentences, identify the 1-2 most important factors that drove revenue performance over the last 30 days on this channel. Be specific about spend levels, conversion rates, and any seasonal effects visible in the data.

Paragraph 2 - What the forecast expects: In 2-3 sentences, explain what the model is projecting and why. Connect the forecast to the specific inputs (spend level, historical ROAS, seasonal period) that are driving it. State the confidence level clearly.

Paragraph 3 - What could break this forecast: In 2 sentences, name the single most likely risk that could cause actual revenue to fall below the P10 estimate, and the single most likely upside scenario that could push revenue above the P90 estimate.

Use plain English. No bullet points. No headers within paragraphs. Write as if explaining to a smart client who is not a data scientist."""
    return _call_groq(prompt)


def get_risk_json(channels_data, horizon_days):
    """Role C: top-3 ranked operational risks across all channels, as JSON."""
    channel_blocks = "\n".join(
        f"""CHANNEL: {c['channel_name']}
- Proposed budget: ${c['budget']:.2f}
- Projected ROAS P50: {c['roas_p50']:.2f}
- Projected ROAS P10 (worst case): {c['roas_p10']:.2f}
- Revenue P50: ${c['revenue_p50']:.2f}
- CVR trend (last 14 days): {c['cvr_trend']} (improving/declining/stable)
- Model uncertainty: {c['uncertainty_level']}
- Spend vs last period: {c['spend_change']:.1f}%"""
        for c in channels_data
    )

    prompt = f"""You are a senior digital marketing strategist reviewing a complete multi-channel forecast for an e-commerce client.

Here is the forecast summary across all channels for the next {horizon_days} days:

{channel_blocks}

Identify and rank the top 3 operational risks across all channels combined. For each risk:
- Name it in 5 words or fewer (e.g. "Meta CVR declining sharply")
- Give it a severity: HIGH / MEDIUM / LOW
- Explain it in exactly 1 sentence
- Give exactly 1 specific, actionable recommendation in 1 sentence

Respond with a JSON object of the form {{"risks": [{{"rank": 1, "name": "...", "severity": "HIGH", "explanation": "...", "recommendation": "..."}}, ...]}} and nothing else."""

    content = _call_groq(prompt, json_mode=True)
    return json.loads(content)["risks"]
