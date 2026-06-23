# TODO (Day 5 — Jain): Implement XGBModel with 100-run bootstrap CI
# random_state varies 0–99 across bootstrap runs
# Must output p10/p50/p90 dict of numpy arrays


class XGBModel:
    def __init__(self):
        self.models = []

    def fit(self, X, y):
        raise NotImplementedError

    def predict(self, X):
        raise NotImplementedError
