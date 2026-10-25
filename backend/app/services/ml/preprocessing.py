from typing import List, Tuple, Dict, Any, Optional
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.model_selection import train_test_split


def build_preprocessor(
    numeric_cols: List[str],
    categorical_cols: List[str],
) -> ColumnTransformer:
    """
    Construct a scikit-learn ColumnTransformer fitted exclusively on training data.
    Imputes missing values and scales/encodes without lookahead or test leakage.
    """
    transformers = []

    if numeric_cols:
        num_pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ])
        transformers.append(("num", num_pipeline, numeric_cols))

    if categorical_cols:
        cat_pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
            ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ])
        transformers.append(("cat", cat_pipeline, categorical_cols))

    if not transformers:
        # Fallback if no numeric or categorical features specified
        transformers.append(("num", StandardScaler(), []))

    preprocessor = ColumnTransformer(
        transformers=transformers,
        remainder="drop",
        verbose_feature_names_out=False,
    )
    return preprocessor


def get_preprocessed_feature_names(
    preprocessor: ColumnTransformer,
    numeric_cols: List[str],
    categorical_cols: List[str],
) -> List[str]:
    """Retrieve output feature names from fitted ColumnTransformer."""
    try:
        return list(preprocessor.get_feature_names_out())
    except Exception:
        out_names = list(numeric_cols)
        for cat in categorical_cols:
            out_names.append(f"{cat}_encoded")
        return out_names


class RobustFeaturePreprocessor:
    """
    Adaptive preprocessor that:
    1. Learns column transformations strictly on training data (preventing test leakage).
    2. Automatically cleans currency/formatted numeric strings into float64.
    3. Automatically extracts calendar components from date columns and drops raw text dates.
    4. Automatically drops high-cardinality unique identifiers and constant features.
    5. Bins high-cardinality categorical features into top categories + 'Other'.
    6. Fits a ColumnTransformer with SimpleImputer, StandardScaler, and OneHotEncoder.
    7. Can be serialized via Joblib and applied identically at inference time.
    """
    def __init__(self, top_k_categories: int = 15):
        self.top_k_categories = top_k_categories
        self.currency_cols: List[str] = []
        self.date_cols: List[str] = []
        self.identifier_cols: List[str] = []
        self.constant_cols: List[str] = []
        self.high_cardinality_map: Dict[str, List[str]] = {}
        self.final_numeric_cols: List[str] = []
        self.final_categorical_cols: List[str] = []
        self.column_transformer: Optional[ColumnTransformer] = None
        self.feature_names_out_: List[str] = []
        self.input_features: List[str] = []

    def _clean_dataframe(self, df: pd.DataFrame, is_training: bool = False) -> pd.DataFrame:
        clean = df.copy()

        # 1. Clean currency / formatted numeric columns
        target_currency = self.currency_cols if not is_training else []
        if is_training:
            for col in clean.columns:
                if clean[col].dtype == object:
                    sample = clean[col].dropna().astype(str).str.strip()
                    if len(sample) > 0 and sample.str.contains(r"^[\$\€\£\¥]|\%$|\,", regex=True).mean() >= 0.5:
                        s_clean = sample.str.replace(r"[\$\€\£\¥\,\%\s]", "", regex=True)
                        num = pd.to_numeric(s_clean, errors="coerce")
                        if num.notna().mean() >= 0.8:
                            target_currency.append(col)
            self.currency_cols = target_currency

        for col in self.currency_cols:
            if col in clean.columns:
                s = clean[col].astype(str).str.replace(r"[\$\€\£\¥\,\%\s]", "", regex=True)
                clean[col] = pd.to_numeric(s, errors="coerce")

        # 2. Extract calendar features from date columns
        target_dates = self.date_cols if not is_training else []
        if is_training:
            for col in clean.columns:
                if clean[col].dtype == object or pd.api.types.is_datetime64_any_dtype(clean[col]):
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        dt = pd.to_datetime(clean[col], errors="coerce")
                    if dt.notna().mean() >= 0.8:
                        target_dates.append(col)
            self.date_cols = target_dates

        for col in self.date_cols:
            if col in clean.columns:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    dt = pd.to_datetime(clean[col], errors="coerce")
                clean[f"{col}_month"] = dt.dt.month.fillna(1).astype(int)
                clean[f"{col}_day"] = dt.dt.day.fillna(1).astype(int)
                clean[f"{col}_dow"] = dt.dt.dayofweek.fillna(0).astype(int)
                clean[f"{col}_is_weekend"] = dt.dt.dayofweek.isin([5, 6]).astype(int)
                clean = clean.drop(columns=[col])

        # 3. Detect & drop identifiers and constant columns
        if is_training:
            n_rows = len(clean)
            for col in list(clean.columns):
                # Constant features (0 variance or 1 unique)
                if clean[col].nunique(dropna=False) <= 1:
                    self.constant_cols.append(col)
                    clean = clean.drop(columns=[col])
                    continue
                # Unique identifier string features
                if clean[col].dtype == object and n_rows >= 20:
                    if clean[col].nunique() >= 0.95 * n_rows:
                        self.identifier_cols.append(col)
                        clean = clean.drop(columns=[col])
                        continue
        else:
            for col in self.constant_cols + self.identifier_cols:
                if col in clean.columns:
                    clean = clean.drop(columns=[col])

        # 4. High-cardinality categorical binning
        if is_training:
            for col in clean.columns:
                if clean[col].dtype == object:
                    nunique = clean[col].nunique()
                    if nunique > 20:
                        top_cats = clean[col].value_counts().nlargest(self.top_k_categories).index.tolist()
                        self.high_cardinality_map[col] = top_cats
                        top_set = set(top_cats)
                        clean[col] = clean[col].apply(lambda x: x if x in top_set else "Other")
        else:
            for col, top_cats in self.high_cardinality_map.items():
                if col in clean.columns:
                    top_set = set(top_cats)
                    clean[col] = clean[col].apply(lambda x: x if x in top_set else "Other")

        return clean

    def fit(self, df: pd.DataFrame, feature_cols: List[str]):
        """Fit preprocessor strictly on training split."""
        self.input_features = list(feature_cols)
        X_df = self._clean_dataframe(df[feature_cols], is_training=True)

        self.final_numeric_cols = [c for c in X_df.columns if pd.api.types.is_numeric_dtype(X_df[c])]
        self.final_categorical_cols = [c for c in X_df.columns if not pd.api.types.is_numeric_dtype(X_df[c])]

        transformers = []
        if self.final_numeric_cols:
            num_pipe = Pipeline([
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
            ])
            transformers.append(("num", num_pipe, self.final_numeric_cols))

        if self.final_categorical_cols:
            cat_pipe = Pipeline([
                ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
                ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
            ])
            transformers.append(("cat", cat_pipe, self.final_categorical_cols))

        if not transformers:
            transformers.append(("num", StandardScaler(), []))

        self.column_transformer = ColumnTransformer(
            transformers=transformers,
            remainder="drop",
            verbose_feature_names_out=False,
        )
        self.column_transformer.fit(X_df)
        try:
            self.feature_names_out_ = list(self.column_transformer.get_feature_names_out())
        except Exception:
            self.feature_names_out_ = self.final_numeric_cols + [f"{c}_enc" for c in self.final_categorical_cols]
        return self

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        """Transform validation or inference data using parameters learned during fit."""
        aligned = df.copy()
        for col in self.input_features:
            if col not in aligned.columns:
                aligned[col] = np.nan
        X_df = self._clean_dataframe(aligned[self.input_features], is_training=False)

        for col in self.final_numeric_cols:
            if col not in X_df.columns:
                X_df[col] = 0.0
        for col in self.final_categorical_cols:
            if col not in X_df.columns:
                X_df[col] = "missing"

        return self.column_transformer.transform(X_df)

    def fit_transform(self, df: pd.DataFrame, feature_cols: List[str]) -> np.ndarray:
        self.fit(df, feature_cols)
        return self.transform(df)


def analyze_target_cardinality(y: pd.Series, task_type: str) -> Dict[str, Any]:
    """
    Examine target column cardinality and distribution properties.
    Flags high-cardinality classification targets or zero variance targets.
    """
    n_samples = len(y)
    unique_vals = y.nunique()

    stats: Dict[str, Any] = {
        "n_samples": n_samples,
        "n_unique": unique_vals,
        "is_high_cardinality": False,
        "warning": None,
    }

    if task_type == "classification":
        class_counts = y.value_counts()
        majority_class = str(class_counts.index[0]) if len(class_counts) > 0 else "N/A"
        majority_pct = round((class_counts.iloc[0] / max(n_samples, 1)) * 100, 2) if len(class_counts) > 0 else 0.0

        stats["majority_class"] = majority_class
        stats["majority_percentage"] = majority_pct
        stats["class_distribution"] = {
            str(cls): {"count": int(cnt), "share": round(cnt / max(n_samples, 1), 4)}
            for cls, cnt in class_counts.items()
        }

        if unique_vals > 20:
            stats["is_high_cardinality"] = True
            stats["warning"] = (
                f"Classification target has {unique_vals} distinct values. High-cardinality multi-class "
                f"targets often exhibit low F1 scores. Consider numeric regression or binning."
            )
    elif task_type in ["regression", "forecasting"]:
        num_y = pd.to_numeric(y, errors="coerce").dropna()
        if len(num_y) > 0:
            stats["summary"] = {
                "mean": round(float(num_y.mean()), 4),
                "std": round(float(num_y.std()), 4) if len(num_y) > 1 else 0.0,
                "min": round(float(num_y.min()), 4),
                "q25": round(float(num_y.quantile(0.25)), 4),
                "median": round(float(num_y.median()), 4),
                "q75": round(float(num_y.quantile(0.75)), 4),
                "max": round(float(num_y.max()), 4),
            }
            if stats["summary"]["std"] < 1e-8:
                stats["warning"] = "Target variable has near-zero variance. Models may predict a constant."

    return stats


def split_data(
    df: pd.DataFrame,
    target_col: Optional[str] = None,
    task_type: str = "regression",
    val_size: float = 0.2,
    random_state: int = 42,
    date_col: Optional[str] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, Optional[pd.Series], Optional[pd.Series]]:
    """
    Split dataset into train and validation partitions based on task type.
    - Forecasting: Genuine chronological partitioning by date cutoff or chronological index (no future leakage).
    - Classification: Stratified partitioning when class support permits.
    - Regression & Anomaly: Deterministic randomized partitioning.
    """
    n_total = len(df)
    if n_total < 4:
        raise ValueError(f"Dataset has only {n_total} records, insufficient for train/val partitioning.")

    if task_type == "forecasting":
        # Strictly chronological split
        val_count = max(1, int(n_total * val_size))
        train_count = n_total - val_count

        if date_col and date_col in df.columns:
            try:
                dt_series = pd.to_datetime(df[date_col], errors="coerce")
                unique_dates = dt_series.dropna().drop_duplicates().sort_values()
                if len(unique_dates) >= 4:
                    split_idx = int(len(unique_dates) * (1.0 - val_size))
                    split_idx = max(1, min(len(unique_dates) - 1, split_idx))
                    cutoff_date = unique_dates.iloc[split_idx]
                    train_mask = dt_series < cutoff_date
                    val_mask = dt_series >= cutoff_date
                    if train_mask.sum() > 0 and val_mask.sum() > 0:
                        train_df = df[train_mask].copy()
                        val_df = df[val_mask].copy()
                    else:
                        train_df = df.iloc[:train_count].copy()
                        val_df = df.iloc[train_count:].copy()
                else:
                    train_df = df.iloc[:train_count].copy()
                    val_df = df.iloc[train_count:].copy()
            except Exception:
                train_df = df.iloc[:train_count].copy()
                val_df = df.iloc[train_count:].copy()
        else:
            train_df = df.iloc[:train_count].copy()
            val_df = df.iloc[train_count:].copy()

        y_train = train_df[target_col].copy() if target_col else None
        y_val = val_df[target_col].copy() if target_col else None
        return train_df, val_df, y_train, y_val

    # Non-forecasting tasks
    if target_col and target_col in df.columns:
        X = df.drop(columns=[target_col])
        y = df[target_col]

        stratify = None
        if task_type == "classification":
            # Check if each class has at least 2 occurrences
            class_counts = y.value_counts()
            if (class_counts >= 2).all() and len(class_counts) > 1:
                stratify = y

        X_train, X_val, y_train, y_val = train_test_split(
            X,
            y,
            test_size=val_size,
            random_state=random_state,
            stratify=stratify,
        )
        return X_train, X_val, y_train, y_val

    # Unsupervised anomaly detection
    train_df, val_df = train_test_split(
        df,
        test_size=val_size,
        random_state=random_state,
    )
    return train_df, val_df, None, None
