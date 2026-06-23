# TODO (Day 8 — Manak): Implement ForecastingTribunal class
# Wraps Prophet, XGBoost, Ridge into one picklable object with fit/predict/save/load


class ForecastingTribunal:
    def __init__(self):
        self.prophet_models = {}
        self.xgb_models = {}
        self.ridge_models = {}

    def fit(self, df):
        raise NotImplementedError

    def predict(self, df, horizon_days=30):
        raise NotImplementedError

    @staticmethod
    def save(tribunal, path):
        import pickle, os
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(tribunal, f)

    @staticmethod
    def load(path):
        import pickle
        with open(path, "rb") as f:
            return pickle.load(f)
