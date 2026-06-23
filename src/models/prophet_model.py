# TODO (Day 4 — Manak): Implement ProphetModel
# Per-channel, uncertainty_samples=1000, changepoint_prior_scale=0.05
# Must output p10/p50/p90 dict of numpy arrays


class ProphetModel:
    def __init__(self):
        self.model = None

    def fit(self, series):
        raise NotImplementedError

    def predict(self, series, horizon_days):
        raise NotImplementedError
