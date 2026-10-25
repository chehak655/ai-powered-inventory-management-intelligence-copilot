import io
import math
import hashlib
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np
from fastapi import HTTPException, status


def compute_sha256(content: bytes) -> str:
    """Calculate SHA-256 hash of byte content."""
    hasher = hashlib.sha256()
    hasher.update(content)
    return hasher.hexdigest()


def parse_dataset_bytes(content: bytes, filename: str) -> pd.DataFrame:
    """
    Parse uploaded CSV or Excel file bytes into a clean Pandas DataFrame.
    Validates file integrity, handles encodings, and deduplicates column names.
    """
    if not content or len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty.",
        )

    ext = filename.lower().split(".")[-1] if "." in filename else ""
    if ext not in ["csv", "xlsx"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '.{ext}'. Supported formats are CSV (.csv) and Excel (.xlsx).",
        )

    df: Optional[pd.DataFrame] = None

    if ext == "csv":
        # Attempt multiple standard encodings
        encodings = ["utf-8", "utf-8-sig", "latin1", "cp1252"]
        parsed = False
        last_error = ""

        for enc in encodings:
            try:
                # First check first line for delimiters
                sample = content[:4096].decode(enc, errors="ignore")
                sep = ","
                if sample.count(";") > sample.count(",") and sample.count(";") > sample.count("\t"):
                    sep = ";"
                elif sample.count("\t") > sample.count(","):
                    sep = "\t"

                df = pd.read_csv(
                    io.BytesIO(content),
                    encoding=enc,
                    sep=sep,
                    on_bad_lines="error",
                    low_memory=False,
                )
                parsed = True
                break
            except Exception as e:
                last_error = str(e)
                continue

        if not parsed or df is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to parse CSV file. Ensure valid delimiters and encoding: {last_error}",
            )

    elif ext == "xlsx":
        try:
            df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to parse Excel workbook: {str(e)}",
            )

    # Basic validations
    if df is None or df.empty:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dataset contains no readable rows.",
        )

    if len(df.columns) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dataset contains no columns.",
        )

    # Clean column headers
    import re
    clean_cols = []
    seen = {}
    for i, col in enumerate(df.columns):
        raw_name = str(col).strip()
        if not raw_name or raw_name.lower().startswith("unnamed:"):
            raw_name = f"column_{i+1}"
        
        # Strip pandas-generated '.1', '.2' duplicate suffixes so we can normalize cleanly
        base_name = re.sub(r"\.\d+$", "", raw_name)
        
        # Deduplicate headers cleanly with underscores
        if base_name in seen:
            seen[base_name] += 1
            unique_name = f"{base_name}_{seen[base_name]}"
        else:
            seen[base_name] = 0
            unique_name = base_name

        clean_cols.append(unique_name)

    df.columns = clean_cols
    return df


def clean_val_for_json(val: Any) -> Any:
    """Ensure value is serializable into standard JSON."""
    if val is None or pd.isna(val):
        return None
    if isinstance(val, (np.integer, int)):
        return int(val)
    if isinstance(val, (np.floating, float)):
        if math.isnan(val) or math.isinf(val):
            return None
        return round(float(val), 4)
    if isinstance(val, (pd.Timestamp, np.datetime64)):
        return str(val)
    return str(val)


def profile_dataset(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Generate deep data-quality profiling report on dataset.
    Detects missing values, types, duplicates, constant columns, and leakage risks.
    """
    row_count = int(len(df))
    col_count = int(len(df.columns))
    dup_rows = int(df.duplicated().sum())
    dup_row_pct = round((dup_rows / max(row_count, 1)) * 100, 2)

    column_profiles = []
    issues = []
    candidate_dates = []
    candidate_targets = []
    candidate_entities = []

    for col in df.columns:
        series = df[col]
        missing_count = int(series.isna().sum())
        missing_pct = round((missing_count / max(row_count, 1)) * 100, 2)
        unique_count = int(series.nunique(dropna=True))

        # Infer type
        inferred_type = "categorical"
        is_numeric = False
        is_datetime = False

        # Attempt datetime check
        lower_name = col.lower()
        if any(d in lower_name for d in ["date", "timestamp", "time", "day", "month", "year"]) or "datetime" in str(series.dtype).lower():
            try:
                # Try parsing sample non-null values
                non_nulls = series.dropna().head(20)
                if len(non_nulls) > 0:
                    pd.to_datetime(non_nulls, errors="raise")
                    inferred_type = "datetime"
                    is_datetime = True
                    candidate_dates.append(col)
            except Exception:
                pass

        if not is_datetime:
            if pd.api.types.is_numeric_dtype(series):
                inferred_type = "numeric"
                is_numeric = True
            elif pd.api.types.is_bool_dtype(series):
                inferred_type = "boolean"
            else:
                # Check if object column can be safely converted to numeric
                try:
                    non_nulls = series.dropna().head(50)
                    if len(non_nulls) > 0:
                        converted = pd.to_numeric(non_nulls, errors="raise")
                        inferred_type = "numeric"
                        is_numeric = True
                except Exception:
                    # Check cardinality
                    if unique_count > (row_count * 0.9) and unique_count > 50:
                        inferred_type = "text"
                    else:
                        inferred_type = "categorical"

        is_constant = (unique_count <= 1 and row_count > 1)
        is_identifier = (
            unique_count == row_count and row_count > 20
        ) or any(id_kw in lower_name for id_kw in ["_id", "id_", "uuid", "guid", "pk", "key"])

        col_prof: Dict[str, Any] = {
            "name": col,
            "inferred_type": inferred_type,
            "missing_count": missing_count,
            "missing_percentage": missing_pct,
            "unique_count": unique_count,
            "is_constant": is_constant,
            "is_identifier": is_identifier,
            "sample_values": [clean_val_for_json(v) for v in series.dropna().head(5).tolist()],
        }

        # Numeric stats
        if is_numeric:
            numeric_series = pd.to_numeric(series, errors="coerce").dropna()
            if len(numeric_series) > 0:
                col_prof["numeric_stats"] = {
                    "min": clean_val_for_json(numeric_series.min()),
                    "max": clean_val_for_json(numeric_series.max()),
                    "mean": clean_val_for_json(numeric_series.mean()),
                    "median": clean_val_for_json(numeric_series.median()),
                    "std": clean_val_for_json(numeric_series.std() if len(numeric_series) > 1 else 0),
                    "q25": clean_val_for_json(numeric_series.quantile(0.25)),
                    "q75": clean_val_for_json(numeric_series.quantile(0.75)),
                }

        # Categorical top values
        if inferred_type in ["categorical", "boolean"]:
            val_counts = series.value_counts(dropna=True).head(5)
            col_prof["top_categories"] = [
                {
                    "value": clean_val_for_json(cat),
                    "count": int(cnt),
                    "percentage": round((cnt / max(row_count, 1)) * 100, 2),
                }
                for cat, cnt in val_counts.items()
            ]

        # Datetime stats
        if inferred_type == "datetime":
            try:
                dt_series = pd.to_datetime(series, errors="coerce").dropna()
                if len(dt_series) > 0:
                    col_prof["datetime_stats"] = {
                        "min_date": str(dt_series.min()),
                        "max_date": str(dt_series.max()),
                    }
            except Exception:
                pass

        column_profiles.append(col_prof)

        # Detect candidate entities
        if any(e in lower_name for e in ["product", "item", "sku", "store", "shop", "warehouse", "location", "category"]):
            candidate_entities.append(col)

        # Detect candidate target
        if any(t in lower_name for t in ["demand", "sales", "quantity", "units", "orders", "revenue", "target", "stock_needed", "forecast"]):
            candidate_targets.append(col)

        # Quality issues detection
        if missing_pct > 50:
            issues.append({
                "type": "warning",
                "category": "excessive_missing",
                "column": col,
                "message": f"Column '{col}' has {missing_pct}% missing values (exceeds 50%).",
            })
        if is_constant:
            issues.append({
                "type": "warning",
                "category": "constant_column",
                "column": col,
                "message": f"Column '{col}' has only {unique_count} distinct value(s) across all rows and provides no predictive signal.",
            })

    if dup_row_pct > 10:
        issues.append({
            "type": "warning",
            "category": "duplicate_rows",
            "column": None,
            "message": f"Dataset contains {dup_rows} duplicate rows ({dup_row_pct}% of dataset).",
        })

    if row_count < 20:
        issues.append({
            "type": "warning",
            "category": "small_sample",
            "column": None,
            "message": f"Dataset has only {row_count} rows, which may be insufficient for robust machine learning models.",
        })

    # Overall Health Score (0 - 100)
    score = 100
    if dup_row_pct > 0:
        score -= min(15, int(dup_row_pct))
    for col_p in column_profiles:
        if col_p["missing_percentage"] > 20:
            score -= 5
        if col_p["is_constant"]:
            score -= 5
    if row_count < 30:
        score -= 20
    health_score = max(10, min(100, score))

    return {
        "summary": {
            "row_count": row_count,
            "column_count": col_count,
            "duplicate_rows": dup_rows,
            "duplicate_row_percentage": dup_row_pct,
            "health_score": health_score,
        },
        "columns": column_profiles,
        "issues": issues,
        "candidates": {
            "dates": candidate_dates,
            "targets": candidate_targets,
            "entities": candidate_entities,
        },
    }


def suggest_default_configuration(profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recommend machine learning task and dynamic column mappings using transparent heuristics.
    Never hardcodes fixed column names; adapts dynamically to any dataset schema.
    """
    columns = profile["columns"]
    candidates = profile["candidates"]
    col_names = [c["name"] for c in columns]

    # Date column
    date_col = candidates["dates"][0] if candidates["dates"] else None

    # Target column
    target_col = None
    if candidates["targets"]:
        target_col = candidates["targets"][0]
    else:
        # Fallback: pick the first numeric column that is not constant and not identifier
        for c in columns:
            if c["inferred_type"] == "numeric" and not c["is_constant"] and not c["is_identifier"]:
                target_col = c["name"]
                break

    # Determine recommended task
    recommended_task = "regression"
    if date_col and target_col:
        recommended_task = "forecasting"
    elif target_col:
        # Check target type
        target_prof = next((c for c in columns if c["name"] == target_col), None)
        if target_prof and target_prof["inferred_type"] in ["categorical", "boolean"]:
            recommended_task = "classification"
        else:
            recommended_task = "regression"
    else:
        recommended_task = "anomaly"

    # Feature columns: all columns except target, date_col, constant, and pure identifiers
    feature_cols = [
        c["name"]
        for c in columns
        if c["name"] != target_col
        and c["name"] != date_col
        and not c["is_constant"]
        and not c["is_identifier"]
    ]

    entity_cols = [
        e for e in candidates["entities"]
        if e != target_col and e != date_col
    ]

    return {
        "recommended_task": recommended_task,
        "target_column": target_col,
        "feature_columns": feature_cols,
        "date_column": date_col,
        "entity_columns": entity_cols,
        "excluded_columns": [c["name"] for c in columns if c["is_constant"] or c["is_identifier"]],
    }


def validate_dataset_configuration(
    profile: Optional[Dict[str, Any]],
    task_type: str,
    target_column: Optional[str],
    feature_columns: List[str],
    date_column: Optional[str] = None,
    entity_columns: Optional[List[str]] = None,
    df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Validate dataset configuration against task type, column types, and target distribution.
    - Validates target compatibility with task.
    - Warns when a classification target has excessive cardinality, particularly when continuous/numeric.
    - Recommends regression for numeric quantities.
    - Computes class counts, imbalance ratio, and estimated validation support.
    - Never mutates or overrides the user's selected task or target.
    """
    warnings: List[str] = []
    recommendation: Optional[str] = None
    target_diagnostics: Dict[str, Any] = {}
    is_valid = True

    columns_meta = profile.get("columns", []) if profile else []
    col_map = {c["name"]: c for c in columns_meta}
    row_count = profile.get("summary", {}).get("row_count", 0) if profile else (len(df) if df is not None else 0)

    # Supervised target check
    if task_type in ["regression", "forecasting", "classification"]:
        if not target_column:
            return {
                "is_valid": False,
                "warnings": [f"Task '{task_type}' requires a target column."],
                "recommendation": None,
                "target_diagnostics": {},
            }

        target_prof = col_map.get(target_column)
        target_series = df[target_column].dropna() if (df is not None and target_column in df.columns) else None

        inferred_type = target_prof.get("inferred_type") if target_prof else None
        unique_count = (
            int(target_series.nunique())
            if target_series is not None
            else (target_prof.get("unique_count", 0) if target_prof else 0)
        )

        # 1. Regression & Forecasting target validation
        if task_type in ["regression", "forecasting"]:
            if inferred_type in ["categorical", "text"]:
                warnings.append(
                    f"Selected target '{target_column}' is inferred as categorical text. "
                    f"Regression requires a continuous numeric target variable."
                )
            if unique_count <= 1 and row_count > 1:
                warnings.append(
                    f"Selected target '{target_column}' has zero variance (constant across rows). "
                    f"Models will not be able to learn predictive relationships."
                )

        # 2. Classification target validation
        elif task_type == "classification":
            is_numeric = (
                pd.api.types.is_numeric_dtype(target_series)
                if target_series is not None
                else (inferred_type == "numeric")
            )

            # Check excessive cardinality
            if is_numeric and unique_count > 10:
                warnings.append(
                    f"Classification target '{target_column}' is numeric with {unique_count} distinct values "
                    f"(continuous or high cardinality). Running classification will create {unique_count} discrete classes "
                    f"with extreme data sparsity and severely degraded Macro-F1."
                )
                recommendation = "Recommend switching task to 'regression' for continuous numeric targets unless discrete classification is explicitly intended."
            elif unique_count > 20:
                warnings.append(
                    f"Classification target '{target_column}' has high cardinality ({unique_count} distinct classes). "
                    f"Multi-class classification with many sparse categories often yields low Macro-F1."
                )
                recommendation = "Consider grouping low-frequency categories or formulating as numeric regression if values are ordinal/numeric."

            # Calculate class distribution & validation-set support
            val_holdout_rows = max(1, int(row_count * 0.2))
            est_support_per_class = round(val_holdout_rows / max(unique_count, 1), 2)

            class_dist = {}
            imbalance_ratio = 1.0
            majority_pct = 0.0

            if target_series is not None:
                counts = target_series.value_counts()
                maj_cnt = int(counts.iloc[0]) if len(counts) > 0 else 0
                min_cnt = int(counts.iloc[-1]) if len(counts) > 0 else 0
                imbalance_ratio = round(maj_cnt / max(min_cnt, 1), 2)
                majority_pct = round((maj_cnt / max(len(target_series), 1)) * 100, 2)
                class_dist = {str(k): int(v) for k, v in counts.head(10).items()}
            elif target_prof and target_prof.get("top_categories"):
                top_cats = target_prof["top_categories"]
                if len(top_cats) > 0:
                    majority_pct = top_cats[0].get("percentage", 0.0)
                class_dist = {str(tc["value"]): int(tc["count"]) for tc in top_cats}

            target_diagnostics = {
                "unique_classes": unique_count,
                "majority_percentage": majority_pct,
                "imbalance_ratio": imbalance_ratio,
                "estimated_val_support_per_class": est_support_per_class,
                "class_counts_sample": class_dist,
                "is_high_cardinality": unique_count > 20 or (is_numeric and unique_count > 10),
            }

            if imbalance_ratio > 10.0:
                warnings.append(
                    f"Severe class imbalance detected: majority class represents {majority_pct}% of the dataset "
                    f"(imbalance ratio {imbalance_ratio}:1). Minority classes may have very few training examples."
                )

    # Feature column and entity column mutual exclusivity checks
    if target_column and target_column in feature_columns:
        warnings.append(f"Target column '{target_column}' cannot also be included as a regular feature column.")
        is_valid = False

    if entity_columns:
        if target_column and target_column in entity_columns:
            warnings.append(f"Target column '{target_column}' cannot also be included as an entity/grouping column.")
            is_valid = False

    # 3. Date column check for forecasting
    if task_type == "forecasting":
        if not date_column:
            warnings.append("Time-series forecasting requires a valid chronological date/time column.")
            is_valid = False
        else:
            if date_column in feature_columns:
                warnings.append(f"Date column '{date_column}' cannot also be listed as a regular feature column.")
                is_valid = False
            if target_column and date_column == target_column:
                warnings.append(f"Date column '{date_column}' cannot be identical to the target column.")
                is_valid = False
            if entity_columns and date_column in entity_columns:
                warnings.append(f"Date column '{date_column}' cannot also be included as an entity/grouping column.")
                is_valid = False

            # Semantic advisory for expiration dates vs transaction/observation dates
            lower_date = date_column.lower()
            if any(exp in lower_date for exp in ["expir", "shelf_life", "best_before", "use_by"]):
                alt_dates = [
                    c["name"] for c in columns_meta
                    if (c.get("inferred_type") == "datetime" or any(dk in c["name"].lower() for dk in ["date", "time", "order", "received", "sale"]))
                    and c["name"] != date_column and c["name"] != target_column
                ]
                alt_msg = f" Consider using an observation or transaction date such as {', '.join(repr(d) for d in alt_dates)}." if alt_dates else ""
                warnings.append(
                    f"Selected date column '{date_column}' appears to represent product shelf-life expiration rather than demand/stock observation timeline.{alt_msg} "
                    f"Time-series forecasting models learn chronological patterns best when aligned with demand or inventory events."
                )

    return {
        "is_valid": is_valid,
        "warnings": warnings,
        "recommendation": recommendation,
        "target_diagnostics": target_diagnostics,
    }


def get_paginated_preview(
    df: pd.DataFrame,
    page: int = 1,
    page_size: int = 20
) -> Dict[str, Any]:
    """Return paginated preview records formatted safely for JSON response."""
    safe_page = max(1, page)
    safe_page_size = max(1, min(100, page_size))
    total_rows = len(df)
    total_pages = max(1, math.ceil(total_rows / safe_page_size))

    offset = (safe_page - 1) * safe_page_size
    slice_df = df.iloc[offset : offset + safe_page_size]

    records = []
    for _, row in slice_df.iterrows():
        record_dict = {col: clean_val_for_json(val) for col, val in row.items()}
        records.append(record_dict)

    return {
        "total_rows": total_rows,
        "page": safe_page,
        "page_size": safe_page_size,
        "total_pages": total_pages,
        "columns": list(df.columns),
        "records": records,
    }
