# TODO (Day 6 — Jain): Implement RidgeModel with residual bootstrap CI
# StandardScaler + Ridge(alpha=1.0, random_state=42)
# Must output p10/p50/p90 dict of numpy arrays


class RidgeModel:
    def __init__(self):
        self.model = None
        self.residuals = None

    def fit(self, X, y):
        raise NotImplementedError

    def predict(self, X):
        raise NotImplementedError
