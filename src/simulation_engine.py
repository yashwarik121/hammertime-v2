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
    """Run a Monte Carlo race simulation.

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
    # Try ML model first, else use heuristic ~90 seconds + offset
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

    # ── Pre-generate random numbers ───────────────────────────────────────
    rng = np.random.default_rng(seed=None)  # truly random

    # Results accumulators  (n_simulations × n_drivers)
    finish_positions = np.zeros((n_simulations, n_drivers), dtype=np.int32)
    dnf_flags = np.zeros((n_simulations, n_drivers), dtype=bool)

    # Per-lap SC probability converted to per-lap: P(at least one SC in race) = sc_prob
    # => per-lap prob = 1 - (1 - sc_prob)^(1/total_laps)
    sc_per_lap = 1.0 - (1.0 - sc_prob) ** (1.0 / total_laps) if sc_prob > 0 else 0.0
    vsc_per_lap = 1.0 - (1.0 - vsc_prob) ** (1.0 / total_laps) if vsc_prob > 0 else 0.0

    # DNF per-lap probability (derived from per-race rate)
    dnf_per_lap = np.array(
        [
            1.0
            - (1.0 - BASE_DNF_RATE.get(
                DRIVERS_2025[d]["team"], 0.06
            ))
            ** (1.0 / total_laps)
            for d in drivers
        ]
    )

    for sim in range(n_simulations):
        # ── Choose strategy per driver ────────────────────────────────────
        is_wet_race = rng.random() < rain_prob
        strategy_pool = _STRATEGIES_WET if is_wet_race else _STRATEGIES_DRY
        strat_indices = rng.integers(0, len(strategy_pool), size=n_drivers)

        # Cumulative race time per driver
        race_time = np.zeros(n_drivers, dtype=np.float64)
        alive = np.ones(n_drivers, dtype=bool)

        # Build stint schedule: for each driver, list of (start_lap, end_lap, compound)
        stint_schedules: list[list[tuple[int, int, str]]] = []
        for di in range(n_drivers):
            n_stops, stints = strategy_pool[strat_indices[di]]
            schedule: list[tuple[int, int, str]] = []
            cum_lap = 0
            for si, (compound, frac) in enumerate(stints):
                s_start = cum_lap + 1
                if si == len(stints) - 1:
                    s_end = total_laps
                else:
                    s_end = min(total_laps, cum_lap + max(1, int(frac * total_laps + rng.normal(0, 1))))
                schedule.append((s_start, s_end, compound))
                cum_lap = s_end
            stint_schedules.append(schedule)

        # ── Simulate lap by lap (vectorised across drivers) ───────────────
        # Pre-determine SC/VSC events for entire race
        sc_laps = rng.random(total_laps) < sc_per_lap
        vsc_laps = rng.random(total_laps) < vsc_per_lap
        # Avoid SC + VSC on same lap
        vsc_laps = vsc_laps & ~sc_laps

        # SC lasts 3-5 laps, VSC lasts 1-2 laps
        sc_active = np.zeros(total_laps, dtype=bool)
        vsc_active = np.zeros(total_laps, dtype=bool)
        l = 0
        while l < total_laps:
            if sc_laps[l]:
                duration = min(rng.integers(3, 6), total_laps - l)
                sc_active[l : l + duration] = True
                l += duration
            elif vsc_laps[l]:
                duration = min(rng.integers(1, 3), total_laps - l)
                vsc_active[l : l + duration] = True
                l += duration
            else:
                l += 1

        for lap in range(total_laps):
            lap_num = lap + 1  # 1-indexed

            # Fuel effect: ~0.03 s/lap lighter
            fuel_effect = -0.03 * lap

            # Per-driver lap time computation
            for di in range(n_drivers):
                if not alive[di]:
                    continue

                # DNF check
                if rng.random() < dnf_per_lap[di]:
                    alive[di] = False
                    dnf_flags[sim, di] = True
                    race_time[di] = np.inf
                    continue

                # Find current stint
                compound = "MEDIUM"
                tyre_age_in_stint = lap_num
                for s_start, s_end, comp in stint_schedules[di]:
                    if s_start <= lap_num <= s_end:
                        compound = comp
                        tyre_age_in_stint = lap_num - s_start + 1
                        break

                # Base time + compound delta + degradation + fuel + noise
                lap_time = base_times[di]
                lap_time += _COMPOUND_DELTA.get(compound, 0.0)
                lap_time += _COMPOUND_DEG.get(compound, 0.04) * tyre_age_in_stint
                lap_time += fuel_effect
                lap_time += rng.normal(0, 0.3)  # random variation

                # SC / VSC penalties
                if sc_active[lap]:
                    lap_time += SC_LAP_DURATION_PENALTY
                elif vsc_active[lap]:
                    lap_time += VSC_LAP_DURATION_PENALTY

                # Pit stop (on the lap a stint ends and next begins)
                for si in range(len(stint_schedules[di]) - 1):
                    if lap_num == stint_schedules[di][si][1]:
                        pit_time = rng.normal(PIT_STOP_MEAN, PIT_STOP_STD)
                        if rng.random() < PIT_STOP_SLOW_PROBABILITY:
                            pit_time += PIT_STOP_SLOW_PENALTY
                        lap_time += PIT_LANE_TIME + max(1.5, pit_time)
                        break

                race_time[di] += max(lap_time, 50.0)  # sanity floor

        # ── Rank drivers ──────────────────────────────────────────────────
        # DNF'd drivers get position n_drivers (last)
        order = np.argsort(race_time)
        positions = np.empty(n_drivers, dtype=np.int32)
        positions[order] = np.arange(1, n_drivers + 1)
        finish_positions[sim] = positions

    # ═══════════════════════════════════════════════════════════════════════
    # Aggregate results
    # ═══════════════════════════════════════════════════════════════════════

    results: dict[str, Any] = {}
    for di, code in enumerate(drivers):
        pos_array = finish_positions[:, di]
        dnf_array = dnf_flags[:, di]

        # Position distribution (1-20)
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
    n_simulations: int = 5000,
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
