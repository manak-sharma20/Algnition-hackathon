# TODO (Day 10 — Manak): Implement Claude API wrapper
# Takes forecast JSON, returns Role A / Role B / Role C narrative outputs
# Must NOT be called from run.sh — UI only


def get_disagreement_narrative(channel_name, horizon_days, prophet, xgb, ridge,
                                disagreement_pct, uncertainty_level,
                                current_month, historical_roas):
    raise NotImplementedError("Implement on Day 10")


def get_causal_summary(channel_name, horizon_days, historical, forecast):
    raise NotImplementedError("Implement on Day 10")


def get_risk_json(channels_data, horizon_days):
    raise NotImplementedError("Implement on Day 10")
