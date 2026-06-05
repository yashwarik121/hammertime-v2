"""
HAMMERTIME — Model Trainer
XGBoost regression pipeline for lap-time prediction.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from config import (
    FEATURE_COLUMNS,
    MODEL_PATH,
    PROCESSED_DIR,
    SCALER_PATH,
    TARGET_COLUMN,
    TRAINING_SEASONS,
    XGBOOST_PARAMS,
)
from src.utils import setup_logger

logger = setup_logger("hammertime.model")

# ─── Module-level singletons ──────────────────────────────────────────────────
_model = None
_scaler: Optional[StandardScaler] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Training
# ═══════════════════════════════════════════════════════════════════════════════


def train_model(
    force_retrain: bool = False,
    years: Optional[list[int]] = None,
) -> Any:
    """Train (or re-train) the XGBoost lap-time model.

    Parameters
    ----------
    force_retrain : bool
        If False and a saved model exists, return the saved model.
    years : list[int] | None
        Seasons to train on (defaults to ``TRAINING_SEASONS``).

    Returns
    -------
    xgboost.XGBRegressor — the fitted model (also cached as module singleton).
    """
    global _model, _scaler

    if not force_retrain and MODEL_PATH.exists() and SCALER_PATH.exists():
        logger.info("Saved model found — loading instead of retraining.")
        return load_model()

    # ── Build / load training data ────────────────────────────────────────
    from src.feature_engineering import build_training_dataset

    df = build_training_dataset(years=years, force_rebuild=force_retrain)
    if df is None or df.empty:
        logger.error("No training data available — cannot train model.")
        return None

    # ── Prepare X, y ──────────────────────────────────────────────────────
    missing_cols = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if missing_cols:
        logger.error("Missing feature columns: %s", missing_cols)
        return None

    X = df[FEATURE_COLUMNS].copy()
    y = df[TARGET_COLUMN].copy()

    # Convert to numeric (safety net)
    X = X.apply(pd.to_numeric, errors="coerce").fillna(0)
    y = pd.to_numeric(y, errors="coerce").dropna()
    X = X.loc[y.index]

    logger.info("Training data: X=%s  y=%s", X.shape, y.shape)

    # ── Scale features ────────────────────────────────────────────────────
    _scaler = StandardScaler()
    X_scaled = _scaler.fit_transform(X)

    # ── Train / validation split ──────────────────────────────────────────
    X_train, X_val, y_train, y_val = train_test_split(
        X_scaled, y, test_size=0.15, random_state=42
    )

    # ── Train XGBoost ─────────────────────────────────────────────────────
    try:
        from xgboost import XGBRegressor
    except ImportError:
        logger.error("xgboost is not installed — cannot train model.")
        return None

    params = dict(XGBOOST_PARAMS)
    # Remove eval_metric from constructor (passed to fit via eval_set instead)
    eval_metric = params.pop("eval_metric", "rmse")

    model = XGBRegressor(**params)
    model.fit(
        X_train,
        y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )

    # ── Evaluate ──────────────────────────────────────────────────────────
    y_pred_val = model.predict(X_val)
    rmse = float(np.sqrt(mean_squared_error(y_val, y_pred_val)))
    mae = float(mean_absolute_error(y_val, y_pred_val))
    logger.info("Validation  RMSE=%.4f s   MAE=%.4f s", rmse, mae)

    y_pred_train = model.predict(X_train)
    train_rmse = float(np.sqrt(mean_squared_error(y_train, y_pred_train)))
    logger.info("Training    RMSE=%.4f s", train_rmse)

    # ── Save ──────────────────────────────────────────────────────────────
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(MODEL_PATH, "wb") as fh:
        pickle.dump(model, fh)
    with open(SCALER_PATH, "wb") as fh:
        pickle.dump(_scaler, fh)

    logger.info("Model saved to %s", MODEL_PATH)
    _model = model
    return model


# ═══════════════════════════════════════════════════════════════════════════════
# Loading & Prediction
# ═══════════════════════════════════════════════════════════════════════════════


def load_model() -> Any:
    """Load the saved XGBoost model + scaler. Returns the model or None."""
    global _model, _scaler

    if _model is not None:
        return _model

    if not MODEL_PATH.exists():
        logger.warning("No saved model at %s", MODEL_PATH)
        return None

    try:
        with open(MODEL_PATH, "rb") as fh:
            _model = pickle.load(fh)
        if SCALER_PATH.exists():
            with open(SCALER_PATH, "rb") as fh:
                _scaler = pickle.load(fh)
        logger.info("Model loaded from %s", MODEL_PATH)
        return _model
    except Exception as exc:
        logger.error("Failed to load model: %s", exc)
        return None


def predict_lap_time(features: dict[str, float] | pd.DataFrame) -> Optional[float]:
    """Predict a single lap time (seconds) given feature values.

    Parameters
    ----------
    features : dict or single-row DataFrame with keys matching FEATURE_COLUMNS.

    Returns
    -------
    float — predicted lap time in seconds, or None on failure.
    """
    model = load_model()
    if model is None:
        return None

    if isinstance(features, dict):
        row = pd.DataFrame([features])
    else:
        row = features.copy()

    # Ensure column order
    for col in FEATURE_COLUMNS:
        if col not in row.columns:
            row[col] = 0

    row = row[FEATURE_COLUMNS].apply(pd.to_numeric, errors="coerce").fillna(0)

    if _scaler is not None:
        row_scaled = _scaler.transform(row)
    else:
        row_scaled = row.values

    try:
        pred = model.predict(row_scaled)
        return float(pred[0])
    except Exception as exc:
        logger.error("Prediction failed: %s", exc)
        return None


def predict_lap_times_batch(features_df: pd.DataFrame) -> np.ndarray:
    """Predict lap times for many rows at once (returns ndarray of seconds).

    Falls back to NaN array if model is unavailable.
    """
    model = load_model()
    if model is None:
        return np.full(len(features_df), np.nan)

    df = features_df[FEATURE_COLUMNS].copy()
    df = df.apply(pd.to_numeric, errors="coerce").fillna(0)

    if _scaler is not None:
        X = _scaler.transform(df)
    else:
        X = df.values

    try:
        return model.predict(X)
    except Exception as exc:
        logger.error("Batch prediction failed: %s", exc)
        return np.full(len(features_df), np.nan)


# ═══════════════════════════════════════════════════════════════════════════════
# Retraining heuristic
# ═══════════════════════════════════════════════════════════════════════════════


def should_retrain() -> bool:
    """Return True if the model is missing or the training data has grown."""
    if not MODEL_PATH.exists():
        return True

    # Check if new processed data is newer than the model
    try:
        model_mtime = MODEL_PATH.stat().st_mtime
        for parquet in PROCESSED_DIR.glob("training_dataset_*.parquet"):
            if parquet.stat().st_mtime > model_mtime:
                logger.info("Training data newer than model — retraining recommended.")
                return True
    except Exception:
        pass

    return False


def get_model_info() -> dict[str, Any]:
    """Return metadata about the current model (for /api/status)."""
    info: dict[str, Any] = {
        "model_exists": MODEL_PATH.exists(),
        "scaler_exists": SCALER_PATH.exists(),
        "model_path": str(MODEL_PATH),
    }
    if MODEL_PATH.exists():
        info["model_size_bytes"] = MODEL_PATH.stat().st_size
        info["model_modified"] = MODEL_PATH.stat().st_mtime
    return info
