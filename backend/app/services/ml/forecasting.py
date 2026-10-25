from typing import List, Tuple, Dict, Any, Optional
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.ensemble import RandomForestRegressor
import xgboost as xgb


class NaiveForecaster(BaseEstimator, RegressorMixin):
    """
    Standard naive time-series baseline (random walk persistence).
    Always predicts the last observed target value from the training history.
    Completely invariant to feature transformations or input scaling.
    """
    def __init__(self):
        self.last_value_: float = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray):
        y_arr = np.asarray(y, dtype=float)
        valid = y_arr[~np.isnan(y_arr)]
        if len(valid) > 0:
            self.last_value_ = float(valid[-1])
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        n_samples = len(X)
        return np.full(n_samples, self.last_value_, dtype=float)


class SeasonalNaiveForecaster(BaseEstimator, RegressorMixin):
    """
    Seasonal naive baseline (default: 7 periods for weekly seasonality).
    Predicts the target value from the corresponding historical seasonal offset.
    Operates strictly in the raw unscaled target space.
    """
    def __init__(self, season_length: int = 7):
        self.season_length = season_length
        self.seasonal_history_: List[float] = []

    def fit(self, X: np.ndarray, y: np.ndarray):
        y_arr = np.asarray(y, dtype=float)
        valid = y_arr[~np.isnan(y_arr)]
        if len(valid) >= self.season_length:
            self.seasonal_history_ = [float(v) for v in valid[-self.season_length:]]
        elif len(valid) > 0:
            # Repeat available values up to season_length
            reps = [float(v) for v in valid]
            while len(reps) < self.season_length:
                reps = reps + reps
            self.seasonal_history_ = reps[:self.season_length]
        else:
            self.seasonal_history_ = [0.0] * self.season_length
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        n_samples = len(X)
        if not self.seasonal_history_:
            return np.zeros(n_samples, dtype=float)
        cycle_len = len(self.seasonal_history_)
        preds = [self.seasonal_history_[i % cycle_len] for i in range(n_samples)]
        return np.asarray(preds, dtype=float)


def engineer_forecasting_features(
    df: pd.DataFrame,
    date_col: str,
    target_col: str,
    entity_cols: Optional[List[str]] = None,
    feature_cols: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, List[str], List[str]]:
    """
    Construct leak-free chronological features for time-series demand forecasting:
    - Grouped lag features (t-1, t-2, t-7, t-14) calculated strictly within each entity group.
    - Rolling window statistics (7d rolling mean) shifted by 1 to prevent target lookahead.
    - Calendar features (day of week, day of month, month, is_weekend, quarter).
    - Initial missing lags filled with 0.0 (no future leakage).
    Returns (featured_df, generated_feature_cols, calendar_feature_cols).
    """
    df = df.copy()

    # Parse datetime
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col])

    # Sort strictly by (entities + date) to ensure chronological order within every entity group
    valid_entity_cols = [e for e in (entity_cols or []) if e in df.columns]
    sort_cols = valid_entity_cols + [date_col]
    df = df.sort_values(by=sort_cols).reset_index(drop=True)

    # 1. Calendar Features (Derived strictly from date, safe from lookahead)
    df["cal_dayofweek"] = df[date_col].dt.dayofweek
    df["cal_dayofmonth"] = df[date_col].dt.day
    df["cal_month"] = df[date_col].dt.month
    df["cal_quarter"] = df[date_col].dt.quarter
    df["cal_is_weekend"] = df["cal_dayofweek"].isin([5, 6]).astype(int)

    calendar_cols = ["cal_dayofweek", "cal_dayofmonth", "cal_month", "cal_quarter", "cal_is_weekend"]

    # 2. Lag and Rolling Features (Group-aware & Shifted)
    lag_cols = []
    lags = [1, 2, 7, 14]

    if valid_entity_cols:
        # Group by entities to isolate each SKU / Store series from contamination
        grouped = df.groupby(valid_entity_cols)[target_col]
        for lag in lags:
            col_name = f"lag_{lag}"
            df[col_name] = grouped.shift(lag)
            lag_cols.append(col_name)

        # 7-period rolling mean shifted by 1 so time t only observes observations up to t-1
        df["rolling_mean_7"] = grouped.transform(
            lambda s: s.shift(1).rolling(window=7, min_periods=1).mean()
        )
        lag_cols.append("rolling_mean_7")

        # Initial lags filled with forward fill within entity, then 0.0 fallback (no future data)
        for col in lag_cols:
            df[col] = df.groupby(valid_entity_cols)[col].transform(lambda s: s.ffill()).fillna(0.0)
    else:
        # Single entity time series
        for lag in lags:
            col_name = f"lag_{lag}"
            df[col_name] = df[target_col].shift(lag)
            lag_cols.append(col_name)

        df["rolling_mean_7"] = df[target_col].shift(1).rolling(window=7, min_periods=1).mean()
        lag_cols.append("rolling_mean_7")

        for col in lag_cols:
            df[col] = df[col].ffill().fillna(0.0)

    # Re-sort dataset globally by chronological date for downstream chronological partitioning
    df = df.sort_values(by=date_col, kind="mergesort").reset_index(drop=True)

    # Combine all feature columns
    all_feature_cols = list(lag_cols) + list(calendar_cols)
    if feature_cols:
        for f in feature_cols:
            if f in df.columns and f not in all_feature_cols and f != target_col and f != date_col:
                all_feature_cols.append(f)

    return df, all_feature_cols, calendar_cols
