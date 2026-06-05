"""
HAMMERTIME — Feature Engineering
Transforms raw FastF1 lap data into ML-ready features for the XGBoost model.
"""

from __future__ import annotations

import pickle
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder

from config import (
    CIRCUITS,
    ENCODER_PATH,
    FEATURE_COLUMNS,
    PROCESSED_DIR,
    TARGET_COLUMN,
    TRAINING_SEASONS,
    normalize_team_name,
)
from src.utils import (
    clean_lap_times,
    load_dataframe_cache,
    safe_float,
    save_dataframe_cache,
    setup_logger,
    td_to_seconds,
)
from src.data_fetcher import fetch_event_schedule, fetch_session_laps, fetch_weather_data

logger = setup_logger("hammertime.features")

# ─── Label Encoders ────────────────────────────────────────────────────────────

_encoders: dict[str, LabelEncoder] = {}


def _get_or_create_encoder(name: str) -> LabelEncoder:
    """Return the existing encoder for *name*, or create a new one."""
    if name not in _encoders:
        _encoders[name] = LabelEncoder()
    return _encoders[name]


def save_encoders() -> None:
    """Persist label encoders to disk."""
    ENCODER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ENCODER_PATH, "wb") as fh:
        pickle.dump(_encoders, fh)
    logger.info("Saved %d encoders to %s", len(_encoders), ENCODER_PATH)


def load_encoders() -> dict[str, LabelEncoder]:
    """Load previously saved encoders (returns empty dict on failure)."""
    global _encoders
    if ENCODER_PATH.exists():
        try:
            with open(ENCODER_PATH, "rb") as fh:
                _encoders = pickle.load(fh)
            logger.info("Loaded %d encoders from %s", len(_encoders), ENCODER_PATH)
            return _encoders
        except Exception as exc:
            logger.warning("Could not load encoders: %s", exc)
    return _encoders


# ─── Weather helpers ───────────────────────────────────────────────────────────


def _summarize_weather(weather_df: Optional[pd.DataFrame]) -> dict[str, float]:
    """Compute per-session average weather values."""
    defaults = {"track_temp": 35.0, "air_temp": 25.0, "is_wet": 0.0}
    if weather_df is None or weather_df.empty:
        return defaults

    track_col = None
    air_col = None
    rain_col = None

    for col in weather_df.columns:
        cl = col.lower()
        if "tracktemp" in cl or "track_temp" in cl:
            track_col = col
        elif "airtemp" in cl or "air_temp" in cl:
            air_col = col
        elif "rainfall" in cl or "rain" in cl:
            rain_col = col

    result = {}
    result["track_temp"] = (
        safe_float(weather_df[track_col].mean(), defaults["track_temp"])
        if track_col
        else defaults["track_temp"]
    )
    result["air_temp"] = (
        safe_float(weather_df[air_col].mean(), defaults["air_temp"])
        if air_col
        else defaults["air_temp"]
    )
    if rain_col:
        # Rainfall column is bool or 0/1
        try:
            result["is_wet"] = float(weather_df[rain_col].any())
        except Exception:
            result["is_wet"] = 0.0
    else:
        result["is_wet"] = 0.0

    return result


# ─── Per-session feature builder ───────────────────────────────────────────────


def build_features_for_session(
    year: int,
    gp: str | int,
    laps_df: Optional[pd.DataFrame] = None,
    weather_df: Optional[pd.DataFrame] = None,
) -> Optional[pd.DataFrame]:
    """Build feature rows for every usable lap in a session.

    Parameters
    ----------
    year : int
    gp : str or int — Grand-Prix name or round number
    laps_df : DataFrame — pre-loaded laps (if None, will fetch)
    weather_df : DataFrame — pre-loaded weather (if None, will fetch)

    Returns
    -------
    pd.DataFrame with FEATURE_COLUMNS + TARGET_COLUMN, or None
    """
    # Load laps
    if laps_df is None:
        laps_df = fetch_session_laps(year, gp, "R")
    if laps_df is None or laps_df.empty:
        logger.warning("No laps for %s/%s — skipping", year, gp)
        return None

    # Load weather
    if weather_df is None:
        weather_df = fetch_weather_data(year, gp)
    wx = _summarize_weather(weather_df)

    # ── Resolve column names (FastF1 may vary across versions) ─────────────
    df = laps_df.copy()

    # Normalise column access
    col_map: dict[str, str] = {}
    for col in df.columns:
        cl = col.lower()
        if cl == "laptime":
            col_map["LapTime"] = col
        elif cl == "lapnumber":
            col_map["LapNumber"] = col
        elif cl == "driver":
            col_map["Driver"] = col
        elif cl == "team":
            col_map["Team"] = col
        elif cl == "compound":
            col_map["Compound"] = col
        elif cl == "tyrelife" or cl == "tyre_life":
            col_map["TyreLife"] = col
        elif cl == "stint":
            col_map["Stint"] = col
        elif cl == "gridposition" or cl == "position":
            col_map["GridPosition"] = col
        elif cl == "trackstatus":
            col_map["TrackStatus"] = col
        elif cl == "ispersonalbest":
            col_map["IsPersonalBest"] = col

    # Ensure essential columns exist
    needed = ["LapTime", "LapNumber", "Driver"]
    for n in needed:
        if n not in col_map:
            logger.warning("Missing column %s in laps for %s/%s", n, year, gp)
            return None

    # ── Lap time in seconds ───────────────────────────────────────────────
    lt_col = col_map["LapTime"]
    if pd.api.types.is_timedelta64_dtype(df[lt_col]):
        df["lap_time_seconds"] = df[lt_col].dt.total_seconds()
    else:
        df["lap_time_seconds"] = pd.to_numeric(df[lt_col], errors="coerce")

    df = df.dropna(subset=["lap_time_seconds"])

    # ── Clean outlier laps ────────────────────────────────────────────────
    df = clean_lap_times(df, time_col=lt_col)
    if df.empty:
        return None

    # ── Remove pit in/out and SC laps ─────────────────────────────────────
    if "TrackStatus" in col_map:
        ts_col = col_map["TrackStatus"]
        # TrackStatus: '1' = green, '2' = yellow, '4' = SC, '6' = VSC, etc.
        # Keep only green-flag laps
        mask_green = df[ts_col].astype(str).isin(["1", "1.0", "nan", ""])
        # If that filters out everything, keep all
        if mask_green.sum() > len(df) * 0.2:
            df = df[mask_green]

    # Remove pit in/out laps if identifiable
    for pit_col_name in ("PitInTime", "PitOutTime"):
        for c in df.columns:
            if c.lower() == pit_col_name.lower():
                df = df[df[c].isna() | (df[c] == 0) | (df[c] == "")]
                break

    if df.empty:
        return None

    # ── Determine total laps ──────────────────────────────────────────────
    ln_col = col_map["LapNumber"]
    df[ln_col] = pd.to_numeric(df[ln_col], errors="coerce")
    total_laps = int(df[ln_col].max()) if not df[ln_col].isna().all() else 57

    # ── Build feature columns ─────────────────────────────────────────────
    driver_col = col_map["Driver"]
    team_col = col_map.get("Team")
    compound_col = col_map.get("Compound")
    tyre_life_col = col_map.get("TyreLife")
    stint_col = col_map.get("Stint")
    grid_col = col_map.get("GridPosition")

    # Circuit name
    circuit_name = str(gp)

    rows: list[dict[str, Any]] = []

    # Pre-compute driver rolling averages
    driver_groups = df.groupby(driver_col)
    driver_rolling: dict[str, pd.Series] = {}
    for drv, grp in driver_groups:
        sorted_grp = grp.sort_values(ln_col)
        driver_rolling[drv] = sorted_grp["lap_time_seconds"].rolling(5, min_periods=1).mean()

    # Pre-compute team average pace relative to field
    field_median = df["lap_time_seconds"].median()
    team_perf: dict[str, float] = {}
    if team_col:
        for team, grp in df.groupby(col_map["Team"]):
            team_median = grp["lap_time_seconds"].median()
            # Negative = faster than field, positive = slower
            team_perf[team] = (team_median - field_median) / field_median if field_median else 0.0

    # Grid position per driver (first lap)
    driver_grid: dict[str, int] = {}
    if grid_col:
        first_laps = df[df[ln_col] == df[ln_col].min()]
        for _, row in first_laps.iterrows():
            drv = row[driver_col]
            gp_val = row.get(col_map["GridPosition"], 0)
            driver_grid[drv] = int(safe_float(gp_val, 10))

    for idx, row in df.iterrows():
        drv = row[driver_col]
        lap_num = int(safe_float(row[ln_col], 1))

        compound = str(row.get(compound_col, "UNKNOWN") if compound_col else "UNKNOWN")
        if compound in ("nan", "None", ""):
            compound = "UNKNOWN"

        tyre_age = int(safe_float(row.get(tyre_life_col, 1) if tyre_life_col else 1, 1))
        stint_num = int(safe_float(row.get(stint_col, 1) if stint_col else 1, 1))

        fuel_load = max(1.0, 110.0 * (1.0 - (lap_num - 1) / max(total_laps - 1, 1)))

        # Driver rolling avg (use index match)
        if drv in driver_rolling and idx in driver_rolling[drv].index:
            avg_pace = driver_rolling[drv].loc[idx]
        else:
            avg_pace = row["lap_time_seconds"]

        team_name = str(row.get(col_map["Team"], "Unknown") if team_col else "Unknown")
        tpi = team_perf.get(team_name, 0.0)

        grid_pos = driver_grid.get(drv, 10)

        rows.append(
            {
                "driver": drv,
                "circuit": circuit_name,
                "tyre_compound": compound,
                "tyre_age": tyre_age,
                "fuel_load_estimate": round(fuel_load, 2),
                "track_temp": wx["track_temp"],
                "air_temp": wx["air_temp"],
                "lap_number": lap_num,
                "grid_position": grid_pos,
                "is_wet": wx["is_wet"],
                "stint_number": stint_num,
                "driver_avg_pace": round(float(avg_pace), 4),
                "team_performance_index": round(tpi, 6),
                "lap_fraction": round(lap_num / total_laps, 4),
                "lap_time_seconds": row["lap_time_seconds"],
            }
        )

    if not rows:
        return None

    feat_df = pd.DataFrame(rows)
    logger.info(
        "Built %d feature rows for %s/%s",
        len(feat_df),
        year,
        gp,
    )
    return feat_df


# ─── Encode categorical columns ───────────────────────────────────────────────


def _encode_categoricals(df: pd.DataFrame, fit: bool = True) -> pd.DataFrame:
    """Label-encode driver, circuit, tyre_compound into *_encoded columns.

    When *fit* is True the encoders are (re-)fitted; otherwise they transform only.
    """
    df = df.copy()
    mapping = {
        "driver": "driver_encoded",
        "circuit": "circuit_encoded",
        "tyre_compound": "tyre_compound_encoded",
    }
    for raw_col, enc_col in mapping.items():
        if raw_col not in df.columns:
            df[enc_col] = 0
            continue
        enc = _get_or_create_encoder(raw_col)
        vals = df[raw_col].astype(str)
        if fit:
            # Fit on all unique vals seen so far
            all_classes = set(enc.classes_) if hasattr(enc, "classes_") and enc.classes_ is not None else set()
            all_classes.update(vals.unique())
            enc.fit(sorted(all_classes))
        # Transform — unseen labels get -1
        known = set(enc.classes_)
        df[enc_col] = vals.apply(lambda v: int(enc.transform([v])[0]) if v in known else -1)

    return df


# ─── Full training dataset ────────────────────────────────────────────────────


def build_training_dataset(
    years: Optional[list[int]] = None,
    *,
    force_rebuild: bool = False,
) -> Optional[pd.DataFrame]:
    """Build (or load cached) training dataset across multiple seasons.

    Parameters
    ----------
    years : list[int] — defaults to ``config.TRAINING_SEASONS``
    force_rebuild : bool — ignore cache

    Returns
    -------
    pd.DataFrame ready for model training (with encoded features + target)
    """
    if years is None:
        years = list(TRAINING_SEASONS)

    ck = f"training_dataset_{'_'.join(str(y) for y in sorted(years))}"

    if not force_rebuild:
        cached = load_dataframe_cache(ck)
        if cached is not None and not cached.empty:
            logger.info("Loaded cached training dataset (%d rows)", len(cached))
            # Re-load encoders
            load_encoders()
            return cached

    all_frames: list[pd.DataFrame] = []

    for year in years:
        logger.info("Building features for season %d …", year)
        schedule = fetch_event_schedule(year)
        if schedule is None:
            logger.warning("No schedule for %d — skipping", year)
            continue

        for _, event in schedule.iterrows():
            gp_name = event.get("EventName", "")
            round_num = int(event.get("RoundNumber", 0))
            if round_num == 0 or not gp_name:
                continue
            try:
                feat = build_features_for_session(year, round_num)
                if feat is not None and not feat.empty:
                    feat["year"] = year
                    all_frames.append(feat)
            except Exception as exc:
                logger.warning("Feature build %d/%s failed: %s", year, gp_name, exc)
                continue

    if not all_frames:
        logger.error("No training data produced for years %s", years)
        return None

    combined = pd.concat(all_frames, ignore_index=True)
    logger.info("Combined raw features: %d rows", len(combined))

    # Encode categoricals (fit mode)
    combined = _encode_categoricals(combined, fit=True)
    save_encoders()

    # Ensure all feature columns present
    for col in FEATURE_COLUMNS:
        if col not in combined.columns:
            combined[col] = 0

    # Ensure target present
    if TARGET_COLUMN not in combined.columns:
        logger.error("Target column '%s' not in dataset!", TARGET_COLUMN)
        return None

    # Drop non-numeric helper columns and keep only needed
    keep_cols = FEATURE_COLUMNS + [TARGET_COLUMN, "driver", "circuit", "tyre_compound", "year"]
    existing_keep = [c for c in keep_cols if c in combined.columns]
    combined = combined[existing_keep]

    # Drop rows with NaN in feature or target
    combined = combined.dropna(subset=FEATURE_COLUMNS + [TARGET_COLUMN])

    save_dataframe_cache(ck, combined)
    logger.info("Training dataset saved: %d rows, %d columns", *combined.shape)
    return combined
