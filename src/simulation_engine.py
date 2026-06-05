"""
HAMMERTIME — Simulation Engine
Monte Carlo race simulation with stochastic events, pit strategies, and ML-predicted lap times.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

from config import (
    BASE_DNF_RATE,
    CIRCUITS,
    COMPOUND_COLORS,
    DEFAULT_RACE_LAPS,
    DEFAULT_SC_PROBABILITY,
    DEFAULT_VSC_PROBABILITY,
    DEFAULT_RAIN_PROBABILITY,
    DRIVERS_2025,
    FEATURE_COLUMNS,
    N_SIMULATIONS,
    PIT_LANE_TIME,
    PIT_STOP_MEAN,
    PIT_STOP_SLOW_PENALTY,
    PIT_STOP_SLOW_PROBABILITY,
    PIT_STOP_STD,
    SC_LAP_DURATION_PENALTY,
    VSC_LAP_DURATION_PENALTY,
    get_team_color,
    normalize_team_name,
)
from src.utils import setup_logger

logger = setup_logger("hammertime.simulation")

# ─── Realistic pit strategies ─────────────────────────────────────────────────
# Each strategy is (n_stops, [(compound, stint_frac), ...])
# stint_frac = fraction of race on each compound; pit lap ≈ cumulative frac * total_laps

_STRATEGIES_DRY = [
    # 1-stop
    (1, [("MEDIUM", 0.50), ("HARD", 0.50)]),
    (1, [("SOFT", 0.35), ("HARD", 0.65)]),
    (1, [("SOFT", 0.38), ("MEDIUM", 0.62)]),
    (1, [("MEDIUM", 0.55), ("HARD", 0.45)]),
    (1, [("HARD", 0.55), ("MEDIUM", 0.45)]),
    # 2-stop
    (2, [("SOFT", 0.28), ("MEDIUM", 0.38), ("HARD", 0.34)]),
    (2, [("SOFT", 0.25), ("HARD", 0.40), ("MEDIUM", 0.35)]),
    (2, [("MEDIUM", 0.33), ("HARD", 0.34), ("MEDIUM", 0.33)]),
    (2, [("SOFT", 0.22), ("SOFT", 0.28), ("MEDIUM", 0.50)]),
    # 3-stop (rare)
    (3, [("SOFT", 0.20), ("SOFT", 0.20), ("MEDIUM", 0.30), ("HARD", 0.30)]),
]

_STRATEGIES_WET = [
    (1, [("INTERMEDIATE", 0.50), ("MEDIUM", 0.50)]),
    (2, [("WET", 0.30), ("INTERMEDIATE", 0.35), ("MEDIUM", 0.35)]),
    (1, [("INTERMEDIATE", 0.60), ("HARD", 0.40)]),
]

# ─── Compound speed delta (seconds per lap relative to MEDIUM) ───────────────
_COMPOUND_DELTA = {
    "SOFT": -0.8,
    "MEDIUM": 0.0,
    "HARD": 0.4,
    "INTERMEDIATE": 3.0,
    "WET": 5.0,
    "UNKNOWN": 0.0,
}

# Degradation per lap (seconds) — increases with tyre age
_COMPOUND_DEG = {
    "SOFT": 0.06,
    "MEDIUM": 0.035,
    "HARD": 0.02,
    "INTERMEDIATE": 0.04,
    "WET": 0.05,
    "UNKNOWN": 0.04,
}

# ─── Driver base-pace tiers (seconds offset from a "reference" pace) ─────────
# Top tier ≈ 0, midfield ≈ +0.3..+0.6, backmarkers ≈ +0.8..+1.2
_DRIVER_PACE_OFFSET: dict[str, float] = {
    "VER": 0.00, "NOR": 0.05, "LEC": 0.08, "PIA": 0.10,
    "HAM": 0.12, "RUS": 0.12, "SAI": 0.18, "ALO": 0.22,
    "GAS": 0.30, "ALB": 0.32, "TSU": 0.33, "OCO": 0.35,
    "STR": 0.38, "HUL": 0.40, "BEA": 0.42, "LAW": 0.28,
    "ANT": 0.25, "HAD": 0.45, "DOO": 0.48, "BOR": 0.52,
}


# ═══════════════════════════════════════════════════════════════════════════════
# ML model access
# ═══════════════════════════════════════════════════════════════════════════════

def _try_predict_base_laptime(
    circuit_id: str,
    driver_code: str,
    total_laps: int,
) -> Optional[float]:
    """Ask the ML model for an average base lap time for this driver/circuit.

    Returns None if the model is not available.
    """
    try:
        from src.model_trainer import load_model, predict_lap_time
        from src.feature_engineering import load_encoders

        model = load_model()
        if model is None:
            return None

        encoders = load_encoders()

        # Build a mid-race feature vector
        driver_enc = 0
        circuit_enc = 0
        compound_enc = 0

        if "driver" in encoders:
            enc = encoders["driver"]
            if driver_code in enc.classes_:
                driver_enc = int(enc.transform([driver_code])[0])

        if "circuit" in encoders:
            enc = encoders["circuit"]
            # Try matching circuit_id as string
            for cls in enc.classes_:
                if str(cls).lower() == circuit_id.lower() or circuit_id.lower() in str(cls).lower():
                    circuit_enc = int(enc.transform([cls])[0])
                    break

        if "tyre_compound" in encoders:
            enc = encoders["tyre_compound"]
            if "MEDIUM" in enc.classes_:
                compound_enc = int(enc.transform(["MEDIUM"])[0])

        features = {
            "driver_encoded": driver_enc,
            "circuit_encoded": circuit_enc,
            "tyre_compound_encoded": compound_enc,
            "tyre_age": 10,
            "fuel_load_estimate": 55.0,
            "track_temp": 35.0,
            "air_temp": 25.0,
            "lap_number": total_laps // 2,
            "grid_position": 10,
            "is_wet": 0,
            "stint_number": 1,
            "driver_avg_pace": 0,  # will be overwritten
            "team_performance_index": 0,
            "lap_fraction": 0.5,
        }

        pred = predict_lap_time(features)
        return pred
    except Exception as exc:
        logger.debug("ML prediction unavailable: %s", exc)
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Core simulation (vectorised where possible)
# ═══════════════════════════════════════════════════════════════════════════════


def simulate_race(
    circuit_id: str,
    n_simulations: int = N_SIMULATIONS,
    sc_prob: Optional[float] = None,
    vsc_prob: Optional[float] = None,
    rain_prob: Optional[float] = None,
) -> dict[str, Any]:
    """Run a Monte Carlo race simulation using a vectorized NumPy engine.

    Parameters
    ----------
    circuit_id : str — key from ``config.CIRCUITS``
    n_simulations : int
    sc_prob, vsc_prob, rain_prob : float | None — override per-race probabilities

    Returns
    -------
    dict with per-driver statistics:
        ``{ driver_code: { win_prob, podium_prob, avg_position, position_distribution, dnf_prob } }``
    """
    circuit = CIRCUITS.get(circuit_id)
    if circuit is None:
        logger.error("Unknown circuit '%s'", circuit_id)
        return {"error": f"Unknown circuit: {circuit_id}"}

    total_laps: int = circuit["laps"]
    sc_prob = sc_prob if sc_prob is not None else circuit.get("sc_probability", DEFAULT_SC_PROBABILITY)
    vsc_prob = vsc_prob if vsc_prob is not None else DEFAULT_VSC_PROBABILITY
    rain_prob = rain_prob if rain_prob is not None else circuit.get("rain_probability", DEFAULT_RAIN_PROBABILITY)

    drivers = list(DRIVERS_2025.keys())
    n_drivers = len(drivers)

    # ── Determine base lap time per driver ────────────────────────────────
    reference_lap = 90.0  # fallback
    ml_pred = _try_predict_base_laptime(circuit_id, "VER", total_laps)
    if ml_pred is not None and 60 < ml_pred < 150:
        reference_lap = ml_pred
        logger.info("Using ML-predicted base lap time: %.2f s", reference_lap)
    else:
        logger.info("Using fallback base lap time: %.2f s", reference_lap)

    base_times = np.array(
        [reference_lap + _DRIVER_PACE_OFFSET.get(d, 0.5) for d in drivers],
        dtype=np.float64,
    )

    rng = np.random.default_rng(seed=None)

    # Results accumulators
    finish_positions = np.zeros((n_simulations, n_drivers), dtype=np.int32)
    dnf_flags = np.zeros((n_simulations, n_drivers), dtype=bool)

    # SC/VSC per-lap probability
    sc_per_lap = 1.0 - (1.0 - sc_prob) ** (1.0 / total_laps) if sc_prob > 0 else 0.0
    vsc_per_lap = 1.0 - (1.0 - vsc_prob) ** (1.0 / total_laps) if vsc_prob > 0 else 0.0

    sc_active = np.zeros((n_simulations, total_laps), dtype=bool)
    vsc_active = np.zeros((n_simulations, total_laps), dtype=bool)

    sc_draws = rng.random(size=(n_simulations, total_laps)) < sc_per_lap
    vsc_draws = rng.random(size=(n_simulations, total_laps)) < vsc_per_lap
    vsc_draws = vsc_draws & ~sc_draws

    # Resolve safety car durations
    for s in range(n_simulations):
        l = 0
        while l < total_laps:
            if sc_draws[s, l]:
                duration = min(rng.integers(3, 6), total_laps - l)
                sc_active[s, l : l + duration] = True
                l += duration
            elif vsc_draws[s, l]:
                duration = min(rng.integers(1, 3), total_laps - l)
                vsc_active[s, l : l + duration] = True
                l += duration
            else:
                l += 1

    # Choose strategy pool per simulation (wet vs dry)
    is_wet_race = rng.random(size=n_simulations) < rain_prob
    
    # Pre-generate strategy indices for all simulations and drivers
    strat_indices = np.zeros((n_simulations, n_drivers), dtype=np.int32)
    wet_sims = np.where(is_wet_race)[0]
    dry_sims = np.where(~is_wet_race)[0]

    if len(wet_sims) > 0:
        strat_indices[wet_sims] = rng.integers(0, len(_STRATEGIES_WET), size=(len(wet_sims), n_drivers))
    if len(dry_sims) > 0:
        strat_indices[dry_sims] = rng.integers(0, len(_STRATEGIES_DRY), size=(len(dry_sims), n_drivers))

    # DNF per-lap probability
    dnf_per_lap = np.array(
        [
            1.0 - (1.0 - BASE_DNF_RATE.get(DRIVERS_2025[d]["team"], 0.06)) ** (1.0 / total_laps)
            for d in drivers
        ]
    )

    # Pre-generate noise for all driver laps
    noise = rng.normal(0, 0.3, size=(n_drivers, n_simulations, total_laps))

    # Pre-generate DNF laps
    dnf_laps = np.zeros((n_drivers, n_simulations), dtype=np.int32)
    for di in range(n_drivers):
        dnf_laps[di] = rng.geometric(dnf_per_lap[di], size=n_simulations)

    # Accumulator for total times
    total_race_times = np.zeros((n_simulations, n_drivers), dtype=np.float64)

    # Fuel effect: shape (total_laps,)
    fuel_effect = -0.03 * np.arange(total_laps)

    # Pre-generate pit time draws
    pit_time_draws = rng.normal(PIT_STOP_MEAN, PIT_STOP_STD, size=(n_drivers, n_simulations, 5))
    slow_draws = rng.random(size=(n_drivers, n_simulations, 5)) < PIT_STOP_SLOW_PROBABILITY
    stint_vars = rng.normal(0, 1, size=(n_drivers, n_simulations, 5))

    # Loop over drivers (vectorizing across simulations!)
    for di, code in enumerate(drivers):
        base_time = base_times[di]

        comp_deltas = np.zeros((n_simulations, total_laps), dtype=np.float64)
        comp_degs = np.zeros((n_simulations, total_laps), dtype=np.float64)
        tyre_ages = np.zeros((n_simulations, total_laps), dtype=np.int32)
        pit_time_offsets = np.zeros((n_simulations, total_laps), dtype=np.float64)

        for s in range(n_simulations):
            is_wet = is_wet_race[s]
            strategy_pool = _STRATEGIES_WET if is_wet else _STRATEGIES_DRY
            strat_idx = strat_indices[s, di]
            n_stops, stints = strategy_pool[strat_idx]

            cum_lap = 0
            for si, (compound, frac) in enumerate(stints):
                s_start = cum_lap + 1
                if si == len(stints) - 1:
                    s_end = total_laps
                else:
                    s_end = min(total_laps, cum_lap + max(1, int(frac * total_laps + stint_vars[di, s, si])))

                stint_len = s_end - s_start + 1
                laps_slice = slice(s_start - 1, s_end)
                comp_deltas[s, laps_slice] = _COMPOUND_DELTA.get(compound, 0.0)
                comp_degs[s, laps_slice] = _COMPOUND_DEG.get(compound, 0.04)
                tyre_ages[s, laps_slice] = np.arange(1, stint_len + 1)

                if si < len(stints) - 1 and s_end <= total_laps:
                    pt = pit_time_draws[di, s, si]
                    if slow_draws[di, s, si]:
                        pt += PIT_STOP_SLOW_PENALTY
                    pit_time_offsets[s, s_end - 1] = PIT_LANE_TIME + max(1.5, pt)

                cum_lap = s_end

        # Calculate lap times
        driver_lap_times = base_time + comp_deltas + comp_degs * tyre_ages + fuel_effect + noise[di] + pit_time_offsets

        # Safety Car / VSC active penalties
        driver_lap_times[sc_active] += SC_LAP_DURATION_PENALTY
        driver_lap_times[vsc_active] += VSC_LAP_DURATION_PENALTY

        # Apply sanity floor
        driver_lap_times = np.clip(driver_lap_times, 50.0, None)

        # Total race times per simulation
        sim_times = np.sum(driver_lap_times, axis=1)

        # Apply DNFs
        dl = dnf_laps[di]
        dnf_mask = dl <= total_laps
        sim_times[dnf_mask] = np.inf
        dnf_flags[:, di] = dnf_mask

        total_race_times[:, di] = sim_times

    # Rank drivers per simulation
    orders = np.argsort(total_race_times, axis=1)
    positions = np.zeros((n_simulations, n_drivers), dtype=np.int32)
    rows = np.arange(n_simulations)[:, np.newaxis]
    positions[rows, orders] = np.arange(1, n_drivers + 1)

    # Aggregate results
    results = {}
    for di, code in enumerate(drivers):
        pos_array = positions[:, di]
        dnf_array = dnf_flags[:, di]

        pos_dist = {}
        for p in range(1, n_drivers + 1):
            pos_dist[str(p)] = float(np.mean(pos_array == p))

        info = DRIVERS_2025[code]
        results[code] = {
            "driver_name": info["name"],
            "team": info["team"],
            "team_color": get_team_color(info["team"]),
            "win_prob": float(np.mean(pos_array == 1)),
            "podium_prob": float(np.mean(pos_array <= 3)),
            "top5_prob": float(np.mean(pos_array <= 5)),
            "top10_prob": float(np.mean(pos_array <= 10)),
            "avg_position": float(np.mean(pos_array[~dnf_array])) if np.any(~dnf_array) else 20.0,
            "median_position": float(np.median(pos_array[~dnf_array])) if np.any(~dnf_array) else 20.0,
            "dnf_prob": float(np.mean(dnf_array)),
            "position_distribution": pos_dist,
        }

    # Sort by win probability desc
    results = dict(sorted(results.items(), key=lambda kv: -kv[1]["win_prob"]))

    return {
        "circuit_id": circuit_id,
        "circuit_name": circuit.get("name", circuit_id),
        "total_laps": total_laps,
        "n_simulations": n_simulations,
        "sc_probability": sc_prob,
        "vsc_probability": vsc_prob,
        "rain_probability": rain_prob,
        "drivers": results,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Pre-race prediction card
# ═══════════════════════════════════════════════════════════════════════════════


def get_pre_race_prediction(
    circuit_id: str,
    n_simulations: int = 1000,
) -> dict[str, Any]:
    """Quick prediction card for the frontend.

    Runs a smaller simulation batch and formats the top-10 in a concise structure.
    """
    sim = simulate_race(circuit_id, n_simulations=n_simulations)
    if "error" in sim:
        return sim

    drivers_data = sim["drivers"]
    top10 = list(drivers_data.items())[:10]  # already sorted by win_prob

    return {
        "circuit_id": circuit_id,
        "circuit_name": sim["circuit_name"],
        "total_laps": sim["total_laps"],
        "n_simulations": n_simulations,
        "predictions": [
            {
                "rank": i + 1,
                "code": code,
                "driver_name": data["driver_name"],
                "team": data["team"],
                "team_color": data["team_color"],
                "win_prob": round(data["win_prob"] * 100, 1),
                "podium_prob": round(data["podium_prob"] * 100, 1),
                "avg_position": round(data["avg_position"], 1),
                "dnf_prob": round(data["dnf_prob"] * 100, 1),
            }
            for i, (code, data) in enumerate(top10)
        ],
    }
