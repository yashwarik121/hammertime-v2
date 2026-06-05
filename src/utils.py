"""
HAMMERTIME — Shared Utilities
Logging, caching helpers, data conversion, and common functions.
"""

import json
import logging
import hashlib
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from config import CACHE_DIR, PROCESSED_DIR

# ─── Logging Setup ─────────────────────────────────────────────────────────────
def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Create a formatted logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s │ %(name)-20s │ %(levelname)-8s │ %(message)s",
            datefmt="%H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger

logger = setup_logger("hammertime")

# ─── Timedelta Helpers ─────────────────────────────────────────────────────────
def td_to_seconds(td) -> Optional[float]:
    """Convert pandas Timedelta or timedelta to float seconds. Returns None for NaT/None."""
    if pd.isna(td):
        return None
    if isinstance(td, timedelta):
        return td.total_seconds()
    if isinstance(td, pd.Timedelta):
        return td.total_seconds()
    try:
        return float(td)
    except (TypeError, ValueError):
        return None

# ─── JSON Cache Helpers ───────────────────────────────────────────────────────
def cache_key(prefix: str, *args) -> str:
    """Generate a cache filename from prefix + args."""
    raw = f"{prefix}_{'_'.join(str(a) for a in args)}"
    return raw.replace(" ", "_").replace("/", "_").lower()

def load_from_cache(key: str) -> Optional[Any]:
    """Load JSON data from cache if exists."""
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    return None

def save_to_cache(key: str, data: Any) -> None:
    """Save data as JSON to cache."""
    path = CACHE_DIR / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, default=str, indent=2)

def load_dataframe_cache(key: str) -> Optional[pd.DataFrame]:
    """Load a cached DataFrame (parquet format)."""
    path = PROCESSED_DIR / f"{key}.parquet"
    if path.exists():
        try:
            return pd.read_parquet(path)
        except Exception:
            return None
    return None

def save_dataframe_cache(key: str, df: pd.DataFrame) -> None:
    """Save DataFrame to cache (parquet format)."""
    path = PROCESSED_DIR / f"{key}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)

# ─── Data Cleaning Helpers ─────────────────────────────────────────────────────
def clean_lap_times(df: pd.DataFrame, time_col: str = "LapTime") -> pd.DataFrame:
    """Remove outlier laps (pit laps, SC laps, very slow laps)."""
    if df.empty:
        return df

    # Convert to seconds if timedelta
    if df[time_col].dtype == "timedelta64[ns]":
        df = df.copy()
        df["_lap_seconds"] = df[time_col].dt.total_seconds()
    else:
        df = df.copy()
        df["_lap_seconds"] = pd.to_numeric(df[time_col], errors="coerce")

    # Remove NaN
    df = df.dropna(subset=["_lap_seconds"])

    # Remove outliers: > 150% of median
    median_time = df["_lap_seconds"].median()
    if median_time > 0:
        df = df[df["_lap_seconds"] <= median_time * 1.5]
        df = df[df["_lap_seconds"] >= median_time * 0.7]

    df = df.drop(columns=["_lap_seconds"])
    return df

def safe_float(value, default: float = 0.0) -> float:
    """Safely convert to float."""
    try:
        v = float(value)
        if pd.isna(v):
            return default
        return v
    except (TypeError, ValueError):
        return default
