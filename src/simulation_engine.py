"""
HAMMERTIME — Simulation Engine
Monte Carlo race simulation with stochastic events, pit strategies, dirty air,
overtaking, and ML-predicted lap times.

Performance target: < 3 seconds for 2000 simulations of a full race.
Vectorised across simulations using NumPy; loops only over drivers (20) and laps.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

import numpy as np

from config import (
    BASE_DNF_RATE,
    CIRCUITS,
    COMPOUND_COLORS,
    DEFAULT_RACE_LAPS,
    DEFAULT_SC_PROBABILITY,
    DEFAULT_VSC_PROBABILITY,
    DEFAULT_RAIN_PROBABILITY,
    DIRTY_AIR_PENALTY,
    DRIVERS_2025,
    N_SIMULATIONS,
    OVERTAKE_INDEX,
    PIT_LANE_TIME,
    PIT_STOP_MEAN,
    PIT_STOP_SLOW_PENALTY,
    PIT_STOP_SLOW_PROBABILITY,
    PIT_STOP_STD,
    SC_LAP_DURATION_PENALTY,
    STATIC_DIR,
    VSC_LAP_DURATION_PENALTY,
    get_team_color,
    normalize_team_name,
)
from src.utils import setup_logger

logger = setup_logger("hammertime.simulation")

# ─── Realistic pit strategies ─────────────────────────────────────────────────
_STRATEGIES_DRY = [
    (1, [("MEDIUM", 0.50), ("HARD", 0.50)]),
    (1, [("SOFT", 0.35), ("HARD", 0.65)]),
    (1, [("SOFT", 0.38), ("MEDIUM", 0.62)]),
    (1, [("MEDIUM", 0.55), ("HARD", 0.45)]),
    (1, [("HARD", 0.55), ("MEDIUM", 0.45)]),
    (2, [("SOFT", 0.28), ("MEDIUM", 0.38), ("HARD", 0.34)]),
    (2, [("SOFT", 0.25), ("HARD", 0.40), ("MEDIUM", 0.35)]),
    (2, [("MEDIUM", 0.33), ("HARD", 0.34), ("MEDIUM", 0.33)]),
    (2, [("SOFT", 0.22), ("SOFT", 0.28), ("MEDIUM", 0.50)]),
    (3, [("SOFT", 0.20), ("SOFT", 0.20), ("MEDIUM", 0.30), ("HARD", 0.30)]),
]

_STRATEGIES_WET = [
    (1, [("INTERMEDIATE", 0.50), ("MEDIUM", 0.50)]),
    (2, [("WET", 0.30), ("INTERMEDIATE", 0.35), ("MEDIUM", 0.35)]),
    (1, [("INTERMEDIATE", 0.60), ("HARD", 0.40)]),
]

# ─── Compound speed delta (seconds per lap relative to MEDIUM) ───────────────
_COMPOUND_DELTA = {
    "SOFT": -0.8, "MEDIUM": 0.0, "HARD": 0.4,
    "INTERMEDIATE": 3.0, "WET": 5.0, "UNKNOWN": 0.0,
}

_COMPOUND_DEG = {
    "SOFT": 0.06, "MEDIUM": 0.035, "HARD": 0.02,
    "INTERMEDIATE": 0.04, "WET": 0.05, "UNKNOWN": 0.04,
}

# ─── Driver base-pace tiers ─────────────────────────────────────────────────
_DRIVER_PACE_OFFSET: dict[str, float] = {
    "VER": 0.00, "NOR": 0.05, "LEC": 0.08, "PIA": 0.10,
    "HAM": 0.12, "RUS": 0.12, "SAI": 0.18, "ALO": 0.22,
    "GAS": 0.30, "ALB": 0.32, "TSU": 0.33, "OCO": 0.35,
    "STR": 0.38, "HUL": 0.40, "BEA": 0.42, "LAW": 0.28,
    "ANT": 0.25, "HAD": 0.45, "DOO": 0.48, "BOR": 0.52,
}

# Named strategies for advanced simulation comparison
_NAMED_STRATEGIES = [
    {"name": "Soft-Hard (1-stop)", "stints": [{"compound": "SOFT", "laps": 20}, {"compound": "HARD", "laps": 37}]},
    {"name": "Medium-Hard (1-stop)", "stints": [{"compound": "MEDIUM", "laps": 28}, {"compound": "HARD", "laps": 29}]},
    {"name": "Soft-Medium-Hard (2-stop)", "stints": [{"compound": "SOFT", "laps": 15}, {"compound": "MEDIUM", "laps": 20}, {"compound": "HARD", "laps": 22}]},
    {"name": "Medium-Medium-Soft (2-stop)", "stints": [{"compound": "MEDIUM", "laps": 20}, {"compound": "MEDIUM", "laps": 20}, {"compound": "SOFT", "laps": 17}]},
    {"name": "Soft-Medium (1-stop)", "stints": [{"compound": "SOFT", "laps": 22}, {"compound": "MEDIUM", "laps": 35}]},
]


# ═══════════════════════════════════════════════════════════════════════════════
# ML model access
# ═══════════════════════════════════════════════════════════════════════════════

def _try_predict_base_laptime(circuit_id: str, driver_code: str, total_laps: int) -> Optional[float]:
    """Ask the ML model for an average base lap time. Returns None if unavailable."""
    try:
        from src.model_trainer import load_model, predict_lap_time
        from src.feature_engineering import load_encoders

        model = load_model()
        if model is None:
            return None

        encoders = load_encoders()
        driver_enc = circuit_enc = compound_enc = 0

        if "driver" in encoders:
            enc = encoders["driver"]
            if driver_code in enc.classes_:
                driver_enc = int(enc.transform([driver_code])[0])

        if "circuit" in encoders:
            enc = encoders["circuit"]
            for cls in enc.classes_:
                if str(cls).lower() == circuit_id.lower() or circuit_id.lower() in str(cls).lower():
                    circuit_enc = int(enc.transform([cls])[0])
                    break

        if "tyre_compound" in encoders:
            enc = encoders["tyre_compound"]
            if "MEDIUM" in enc.classes_:
                compound_enc = int(enc.transform(["MEDIUM"])[0])

        features = {
            "driver_encoded": driver_enc, "circuit_encoded": circuit_enc,
            "tyre_compound_encoded": compound_enc, "tyre_age": 10,
            "fuel_load_estimate": 55.0, "track_temp": 35.0, "air_temp": 25.0,
            "lap_number": total_laps // 2, "grid_position": 10, "is_wet": 0,
            "stint_number": 1, "driver_avg_pace": 0, "team_performance_index": 0,
            "lap_fraction": 0.5,
        }
        pred = predict_lap_time(features)
        return pred
    except Exception as exc:
        logger.debug("ML prediction unavailable: %s", exc)
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: build tyre schedule for vectorised sim
# ═══════════════════════════════════════════════════════════════════════════════

def _build_stint_schedule(
    stints_spec: list[tuple[str, float]],
    total_laps: int,
    rng: np.random.Generator,
    n_simulations: int,
):
    """Return (compound_delta, compound_deg, tyre_age, pit_mask) arrays shaped (n_simulations, total_laps)."""
    comp_deltas = np.zeros((n_simulations, total_laps), dtype=np.float64)
    comp_degs = np.zeros((n_simulations, total_laps), dtype=np.float64)
    tyre_ages = np.zeros((n_simulations, total_laps), dtype=np.float64)
    pit_laps = np.zeros((n_simulations, total_laps), dtype=bool)

    # slight variance for stint boundaries
    stint_vars = rng.normal(0, 1, size=(n_simulations, len(stints_spec)))

    cum_laps = np.zeros(n_simulations, dtype=np.int32)
    for si, (compound, frac) in enumerate(stints_spec):
        delta = _COMPOUND_DELTA.get(compound, 0.0)
        deg = _COMPOUND_DEG.get(compound, 0.04)

        if si == len(stints_spec) - 1:
            s_end = np.full(n_simulations, total_laps, dtype=np.int32)
        else:
            raw = cum_laps + np.maximum(1, (frac * total_laps + stint_vars[:, si]).astype(np.int32))
            s_end = np.minimum(raw, total_laps)

        for lap in range(total_laps):
            mask = (lap >= cum_laps) & (lap < s_end)
            comp_deltas[mask, lap] = delta
            comp_degs[mask, lap] = deg
            tyre_ages[mask, lap] = lap - cum_laps[mask] + 1

        # Mark pit stop at end of non-final stint
        if si < len(stints_spec) - 1:
            for s in range(n_simulations):
                if s_end[s] > 0 and s_end[s] < total_laps:
                    pit_laps[s, s_end[s] - 1] = True

        cum_laps = s_end

    return comp_deltas, comp_degs, tyre_ages, pit_laps


# ═══════════════════════════════════════════════════════════════════════════════
# Core simulation
# ═══════════════════════════════════════════════════════════════════════════════

def simulate_race(
    circuit_id: str,
    n_simulations: int = N_SIMULATIONS,
    sc_prob: Optional[float] = None,
    vsc_prob: Optional[float] = None,
    rain_prob: Optional[float] = None,
    grid_override: Optional[dict[str, int]] = None,
    force_weather_lap: Optional[int] = None,
    disable_sc: bool = False,
) -> dict[str, Any]:
    """Run a Monte Carlo race simulation using vectorized NumPy.

    Parameters
    ----------
    circuit_id : str — key from ``config.CIRCUITS``
    n_simulations : int
    sc_prob, vsc_prob, rain_prob : float | None — override per-race probabilities
    grid_override : dict | None — {driver_code: grid_position} for what-if
    force_weather_lap : int | None — lap number when rain starts (what-if)
    disable_sc : bool — disable all safety cars (what-if)

    Returns
    -------
    dict with per-driver statistics including position_distribution for all 20 positions,
    confidence intervals, and race metadata.
    """
    t_start = time.perf_counter()

    circuit = CIRCUITS.get(circuit_id)
    if circuit is None:
        logger.error("Unknown circuit '%s'", circuit_id)
        return {"error": f"Unknown circuit: {circuit_id}"}

    total_laps: int = circuit["laps"]
    sc_prob = 0.0 if disable_sc else (sc_prob if sc_prob is not None else circuit.get("sc_probability", DEFAULT_SC_PROBABILITY))
    vsc_prob = 0.0 if disable_sc else (vsc_prob if vsc_prob is not None else DEFAULT_VSC_PROBABILITY)
    rain_prob = rain_prob if rain_prob is not None else circuit.get("rain_probability", DEFAULT_RAIN_PROBABILITY)
    overtake_idx = OVERTAKE_INDEX.get(circuit_id, 0.40)

    drivers = list(DRIVERS_2025.keys())
    n_drivers = len(drivers)
    driver_idx = {code: i for i, code in enumerate(drivers)}

    # ── Base lap time ────────────────────────────────────────────────────
    reference_lap = 90.0
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

    # ── Grid positions (affects first lap time) ──────────────────────────
    grid = np.arange(1, n_drivers + 1, dtype=np.int32)
    if grid_override:
        for code, pos in grid_override.items():
            if code in driver_idx:
                grid[driver_idx[code]] = max(1, min(n_drivers, pos))
        # Re-sort: if two drivers occupy same slot, break ties
        used = set()
        for i in range(n_drivers):
            while grid[i] in used:
                grid[i] += 1
            used.add(grid[i])

    # ── Safety Car / VSC events ──────────────────────────────────────────
    sc_per_lap = 1.0 - (1.0 - sc_prob) ** (1.0 / total_laps) if sc_prob > 0 else 0.0
    vsc_per_lap = 1.0 - (1.0 - vsc_prob) ** (1.0 / total_laps) if vsc_prob > 0 else 0.0

    sc_active = np.zeros((n_simulations, total_laps), dtype=bool)
    vsc_active = np.zeros((n_simulations, total_laps), dtype=bool)

    if not disable_sc:
        sc_draws = rng.random(size=(n_simulations, total_laps)) < sc_per_lap
        vsc_draws = rng.random(size=(n_simulations, total_laps)) < vsc_per_lap
        vsc_draws = vsc_draws & ~sc_draws

        sc_durations = rng.integers(3, 6, size=(n_simulations, total_laps))
        vsc_durations = rng.integers(1, 3, size=(n_simulations, total_laps))

        for s in range(n_simulations):
            l = 0
            while l < total_laps:
                if sc_draws[s, l]:
                    dur = min(int(sc_durations[s, l]), total_laps - l)
                    sc_active[s, l:l + dur] = True
                    l += dur
                elif vsc_draws[s, l]:
                    dur = min(int(vsc_durations[s, l]), total_laps - l)
                    vsc_active[s, l:l + dur] = True
                    l += dur
                else:
                    l += 1

    # ── Rain events ──────────────────────────────────────────────────────
    if force_weather_lap is not None:
        rain_start_lap = np.full(n_simulations, force_weather_lap, dtype=np.int32)
        is_wet_race = np.ones(n_simulations, dtype=bool)
    else:
        is_wet_race = rng.random(size=n_simulations) < rain_prob
        rain_start_lap = rng.integers(total_laps // 4, 3 * total_laps // 4 + 1, size=n_simulations)
        rain_start_lap[~is_wet_race] = total_laps + 1  # effectively no rain

    # ── Strategy selection ───────────────────────────────────────────────
    strat_indices = np.zeros((n_simulations, n_drivers), dtype=np.int32)
    wet_sims = np.where(is_wet_race)[0]
    dry_sims = np.where(~is_wet_race)[0]
    if len(wet_sims) > 0:
        strat_indices[wet_sims] = rng.integers(0, len(_STRATEGIES_WET), size=(len(wet_sims), n_drivers))
    if len(dry_sims) > 0:
        strat_indices[dry_sims] = rng.integers(0, len(_STRATEGIES_DRY), size=(len(dry_sims), n_drivers))

    # ── DNF per-lap probability ──────────────────────────────────────────
    dnf_per_lap = np.array([
        1.0 - (1.0 - BASE_DNF_RATE.get(DRIVERS_2025[d]["team"], 0.06)) ** (1.0 / total_laps)
        for d in drivers
    ])

    # ── Pre-generate random draws ────────────────────────────────────────
    noise = rng.normal(0, 0.3, size=(n_drivers, n_simulations, total_laps))
    dnf_draw = rng.random(size=(n_drivers, n_simulations))
    dnf_thresholds = np.array([BASE_DNF_RATE.get(DRIVERS_2025[d]["team"], 0.06) for d in drivers])
    dnf_flags = np.zeros((n_simulations, n_drivers), dtype=bool)
    for di in range(n_drivers):
        dnf_flags[:, di] = dnf_draw[di] < dnf_thresholds[di]

    pit_time_draws = rng.normal(PIT_STOP_MEAN, PIT_STOP_STD, size=(n_drivers, n_simulations, 5))
    slow_draws = rng.random(size=(n_drivers, n_simulations, 5)) < PIT_STOP_SLOW_PROBABILITY
    stint_vars = rng.normal(0, 1, size=(n_drivers, n_simulations, 5))
    dirty_air_draws = rng.uniform(DIRTY_AIR_PENALTY[0], DIRTY_AIR_PENALTY[1], size=(n_simulations, total_laps))
    overtake_draws = rng.random(size=(n_simulations, total_laps, n_drivers))

    # Fuel effect: lighter car = faster
    fuel_effect = -0.03 * np.arange(total_laps)

    # ── Build per-driver lap times ───────────────────────────────────────
    # all_lap_times[di] shape = (n_simulations, total_laps)
    all_lap_times = np.zeros((n_drivers, n_simulations, total_laps), dtype=np.float64)

    for di, code in enumerate(drivers):
        base_time = base_times[di]

        comp_deltas = np.zeros((n_simulations, total_laps), dtype=np.float64)
        comp_degs = np.zeros((n_simulations, total_laps), dtype=np.float64)
        tyre_ages = np.zeros((n_simulations, total_laps), dtype=np.int32)
        pit_time_offsets = np.zeros((n_simulations, total_laps), dtype=np.float64)
        is_on_dry_compound = np.ones((n_simulations, total_laps), dtype=bool)

        for s in range(n_simulations):
            is_wet = is_wet_race[s]
            strategy_pool = _STRATEGIES_WET if is_wet else _STRATEGIES_DRY
            strat_idx = strat_indices[s, di]
            n_stops, stints = strategy_pool[strat_idx]

            cum_lap = 0
            for si, (compound, frac) in enumerate(stints):
                if si == len(stints) - 1:
                    s_end = total_laps
                else:
                    s_end = min(total_laps, cum_lap + max(1, int(frac * total_laps + stint_vars[di, s, si])))

                laps_slice = slice(cum_lap, s_end)
                stint_len = s_end - cum_lap
                comp_deltas[s, laps_slice] = _COMPOUND_DELTA.get(compound, 0.0)
                comp_degs[s, laps_slice] = _COMPOUND_DEG.get(compound, 0.04)
                tyre_ages[s, laps_slice] = np.arange(1, stint_len + 1)

                if compound in ("INTERMEDIATE", "WET"):
                    is_on_dry_compound[s, laps_slice] = False

                if si < len(stints) - 1 and s_end < total_laps:
                    pt = pit_time_draws[di, s, si]
                    if slow_draws[di, s, si]:
                        pt += PIT_STOP_SLOW_PENALTY
                    pit_time_offsets[s, s_end - 1] = PIT_LANE_TIME + max(1.5, pt)

                cum_lap = s_end

        # Build raw lap times: vectorized across all simulations for this driver
        driver_lap_times = base_time + comp_deltas + comp_degs * tyre_ages + fuel_effect + noise[di] + pit_time_offsets

        # Grid position penalty for lap 1 (congestion)
        grid_pos = grid[di]
        driver_lap_times[:, 0] += grid_pos * 0.15

        # SC / VSC penalties
        driver_lap_times[sc_active] += SC_LAP_DURATION_PENALTY
        driver_lap_times[vsc_active] += VSC_LAP_DURATION_PENALTY

        # Rain penalty for drivers on dry compounds after rain starts
        for s in range(n_simulations):
            if is_wet_race[s]:
                r_lap = rain_start_lap[s]
                if r_lap < total_laps:
                    rain_mask = np.arange(total_laps) >= r_lap
                    dry_in_rain = rain_mask & is_on_dry_compound[s]
                    driver_lap_times[s, dry_in_rain] += 8.0  # huge penalty on slicks in rain

        # Floor sanity
        driver_lap_times = np.clip(driver_lap_times, 50.0, None)

        all_lap_times[di] = driver_lap_times

    # ── Position tracking with dirty air & overtaking (lap-by-lap) ──────
    # cumulative_times[sim, driver]
    cumulative_times = np.zeros((n_simulations, n_drivers), dtype=np.float64)
    # current positions[sim, driver] = position (1..n_drivers)
    # Initialize from grid
    current_positions = np.tile(grid, (n_simulations, 1)).astype(np.int32)

    for lap in range(total_laps):
        # Add this lap's times to cumulative
        lap_times_this_lap = np.zeros((n_simulations, n_drivers), dtype=np.float64)
        for di in range(n_drivers):
            lap_times_this_lap[:, di] = all_lap_times[di, :, lap]

        # Apply dirty air: for each driver, check if there's a car within 1.5s ahead
        if lap > 0:
            for di in range(n_drivers):
                my_pos = current_positions[:, di]
                # Find who is in position (my_pos - 1) i.e. car ahead
                for dj in range(n_drivers):
                    if di == dj:
                        continue
                    # dj is ahead of di where dj's position = di's position - 1
                    ahead_mask = (current_positions[:, dj] == my_pos - 1)
                    if not np.any(ahead_mask):
                        continue
                    # Check gap
                    gap = cumulative_times[ahead_mask, di] - cumulative_times[ahead_mask, dj]
                    close_mask_local = gap < 1.5
                    # Apply dirty air to those simulations
                    full_mask = np.zeros(n_simulations, dtype=bool)
                    indices = np.where(ahead_mask)[0]
                    full_mask[indices[close_mask_local]] = True
                    lap_times_this_lap[full_mask, di] += dirty_air_draws[full_mask, lap]

        cumulative_times += lap_times_this_lap

        # Rerank positions based on cumulative times
        # DNF'd drivers get infinite time
        effective_times = cumulative_times.copy()
        for di in range(n_drivers):
            effective_times[dnf_flags[:, di], di] = np.inf

        orders = np.argsort(effective_times, axis=1)
        new_positions = np.zeros((n_simulations, n_drivers), dtype=np.int32)
        rows = np.arange(n_simulations)[:, np.newaxis]
        new_positions[rows, orders] = np.arange(1, n_drivers + 1)

        # Overtaking logic: if a faster car is behind, chance to swap
        if lap > 2 and not np.all(sc_active[:, lap]):
            for di in range(n_drivers):
                for dj in range(n_drivers):
                    if di == dj:
                        continue
                    # di is behind dj, and di is faster
                    behind_mask = (new_positions[:, di] == new_positions[:, dj] + 1)
                    if not np.any(behind_mask):
                        continue
                    # Check pace advantage
                    pace_di = all_lap_times[di, :, lap]
                    pace_dj = all_lap_times[dj, :, lap]
                    faster_mask = behind_mask & (pace_di < pace_dj - 0.3)
                    if not np.any(faster_mask):
                        continue
                    # Overtake probability based on circuit
                    overtake_chance = overtake_idx * 0.4  # scale down to per-lap probability
                    # Don't overtake under SC
                    not_sc = ~sc_active[:, lap]
                    overtake_mask = faster_mask & not_sc & (overtake_draws[:, lap, di] < overtake_chance)
                    if np.any(overtake_mask):
                        # Swap positions
                        pos_di = new_positions[overtake_mask, di].copy()
                        pos_dj = new_positions[overtake_mask, dj].copy()
                        new_positions[overtake_mask, di] = pos_dj
                        new_positions[overtake_mask, dj] = pos_di

        current_positions = new_positions

    # ── Final positions ──────────────────────────────────────────────────
    positions = current_positions.copy()

    # ── Aggregate results ────────────────────────────────────────────────
    # Get valid (non-DNF) race times for confidence intervals
    finished_times = cumulative_times.copy()
    for di in range(n_drivers):
        finished_times[dnf_flags[:, di], di] = np.nan

    results = {}
    for di, code in enumerate(drivers):
        pos_array = positions[:, di]
        dnf_array = dnf_flags[:, di]

        pos_dist = {}
        for p in range(1, n_drivers + 1):
            pos_dist[str(p)] = float(np.mean(pos_array == p))

        valid_times = finished_times[:, di]
        valid_times_clean = valid_times[~np.isnan(valid_times)]

        if len(valid_times_clean) > 0:
            ci_lower = float(np.percentile(valid_times_clean, 2.5))
            ci_upper = float(np.percentile(valid_times_clean, 97.5))
            avg_time = float(np.mean(valid_times_clean))
        else:
            ci_lower = ci_upper = avg_time = 0.0

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
            "confidence_interval_95": {"lower": round(ci_lower, 2), "upper": round(ci_upper, 2)},
            "avg_race_time": round(avg_time, 2),
        }

    results = dict(sorted(results.items(), key=lambda kv: -kv[1]["win_prob"]))

    elapsed = time.perf_counter() - t_start
    logger.info("Simulation completed in %.2f s (%d sims, %s)", elapsed, n_simulations, circuit_id)

    return {
        "circuit_id": circuit_id,
        "circuit_name": circuit.get("name", circuit_id),
        "total_laps": total_laps,
        "n_simulations": n_simulations,
        "sc_probability": sc_prob,
        "vsc_probability": vsc_prob,
        "rain_probability": rain_prob,
        "simulation_time_s": round(elapsed, 2),
        "drivers": results,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Advanced strategy simulation (single driver focus)
# ═══════════════════════════════════════════════════════════════════════════════


def simulate_advanced_strategy(
    circuit_id: str,
    driver_code: str,
    starting_position: int,
    weather: str,
    tyre_strategy: list[dict],
    n_simulations: int = 2000,
) -> dict[str, Any]:
    """Run a focused simulation for ONE driver with custom parameters.

    Parameters
    ----------
    circuit_id : str
    driver_code : str — e.g. "VER"
    starting_position : int — grid position (1-20)
    weather : str — 'dry', 'wet', or 'mixed'
    tyre_strategy : list[dict] — e.g. [{"compound": "SOFT", "laps": 20}, {"compound": "HARD", "laps": 37}]
    n_simulations : int

    Returns
    -------
    dict with win_prob, podium_prob, top10_prob, expected_position, avg_race_time,
    position_distribution, recommended_strategy
    """
    circuit = CIRCUITS.get(circuit_id)
    if circuit is None:
        return {"error": f"Unknown circuit: {circuit_id}"}

    if driver_code not in DRIVERS_2025:
        return {"error": f"Unknown driver: {driver_code}"}

    total_laps = circuit["laps"]
    drivers = list(DRIVERS_2025.keys())
    n_drivers = len(drivers)
    target_di = drivers.index(driver_code)

    reference_lap = 90.0
    ml_pred = _try_predict_base_laptime(circuit_id, "VER", total_laps)
    if ml_pred is not None and 60 < ml_pred < 150:
        reference_lap = ml_pred

    base_times = np.array(
        [reference_lap + _DRIVER_PACE_OFFSET.get(d, 0.5) for d in drivers],
        dtype=np.float64,
    )

    rng = np.random.default_rng(seed=None)

    # Set weather probabilities
    if weather == "wet":
        rain_prob = 0.95
    elif weather == "mixed":
        rain_prob = 0.50
    else:
        rain_prob = 0.02

    # Run the full simulation with grid override for the target driver
    grid_override = {driver_code: starting_position}

    result = simulate_race(
        circuit_id=circuit_id,
        n_simulations=n_simulations,
        rain_prob=rain_prob,
        grid_override=grid_override,
    )

    if "error" in result:
        return result

    driver_result = result["drivers"].get(driver_code, {})

    # Compare 5 common strategies to recommend the best
    best_strategy = None
    best_avg_pos = 99.0
    strategy_comparisons = []

    for named_strat in _NAMED_STRATEGIES:
        # Scale stint laps to match total race laps
        total_strat_laps = sum(s["laps"] for s in named_strat["stints"])
        scale = total_laps / total_strat_laps if total_strat_laps > 0 else 1.0
        scaled_stints = [
            {"compound": s["compound"], "laps": max(1, int(s["laps"] * scale))}
            for s in named_strat["stints"]
        ]
        # Fix rounding: assign remainder to last stint
        used = sum(s["laps"] for s in scaled_stints[:-1])
        scaled_stints[-1]["laps"] = total_laps - used

        # Estimate position from compound deltas and degradation
        avg_delta = 0.0
        cum_laps = 0
        for stint in scaled_stints:
            compound = stint["compound"]
            laps = stint["laps"]
            delta = _COMPOUND_DELTA.get(compound, 0.0)
            deg = _COMPOUND_DEG.get(compound, 0.04)
            avg_age = (laps + 1) / 2
            avg_delta += (delta + deg * avg_age) * laps
            cum_laps += laps

        avg_delta /= total_laps if total_laps > 0 else 1
        # Pit time cost
        n_pits = len(scaled_stints) - 1
        pit_cost = n_pits * (PIT_LANE_TIME + PIT_STOP_MEAN) / total_laps

        effective_pace = avg_delta + pit_cost
        strategy_comparisons.append({
            "name": named_strat["name"],
            "stints": scaled_stints,
            "estimated_pace_delta": round(effective_pace, 3),
        })

        if effective_pace < best_avg_pos:
            best_avg_pos = effective_pace
            best_strategy = {
                "name": named_strat["name"],
                "stints": scaled_stints,
                "estimated_pace_delta": round(effective_pace, 3),
            }

    return {
        "circuit_id": circuit_id,
        "circuit_name": circuit.get("name", circuit_id),
        "driver_code": driver_code,
        "driver_name": DRIVERS_2025[driver_code]["name"],
        "team": DRIVERS_2025[driver_code]["team"],
        "starting_position": starting_position,
        "weather": weather,
        "tyre_strategy": tyre_strategy,
        "n_simulations": n_simulations,
        "win_prob": driver_result.get("win_prob", 0.0),
        "podium_prob": driver_result.get("podium_prob", 0.0),
        "top5_prob": driver_result.get("top5_prob", 0.0),
        "top10_prob": driver_result.get("top10_prob", 0.0),
        "expected_position": driver_result.get("avg_position", 20.0),
        "avg_race_time": driver_result.get("avg_race_time", 0.0),
        "position_distribution": driver_result.get("position_distribution", {}),
        "confidence_interval_95": driver_result.get("confidence_interval_95", {}),
        "recommended_strategy": best_strategy,
        "strategy_comparisons": strategy_comparisons,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Debrief report generator
# ═══════════════════════════════════════════════════════════════════════════════


def generate_debrief_report(circuit_id: str) -> dict[str, Any]:
    """Generate an AI-style strategic debrief for a completed race.

    Uses precalculated data from static/precalculated/{circuit_id}.json.
    Analyzes tyre strategies, pit stops, stint lengths, and generates
    natural language report sections.
    """
    precalc_path = STATIC_DIR / "precalculated" / f"{circuit_id}.json"
    if not precalc_path.exists():
        return {"error": f"No precalculated data for circuit: {circuit_id}"}

    try:
        with open(precalc_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        return {"error": f"Failed to load precalculated data: {exc}"}

    circuit = CIRCUITS.get(circuit_id, {})
    circuit_name = data.get("circuit_name", circuit.get("name", circuit_id))
    year = 2026

    laps_data = data.get("laps", {})
    strategies_data = data.get("strategies", [])

    # ── Analyse lap times ────────────────────────────────────────────────
    driver_stats = {}
    for driver_code, laps in laps_data.items():
        valid_times = [l["time"] for l in laps if l.get("time") is not None and not (isinstance(l["time"], float) and np.isnan(l["time"])) and l["time"] < 200]
        if not valid_times:
            continue
        driver_stats[driver_code] = {
            "total_laps": len(laps),
            "avg_lap": round(np.mean(valid_times), 3),
            "best_lap": round(min(valid_times), 3),
            "worst_lap": round(max(valid_times), 3),
            "std_lap": round(float(np.std(valid_times)), 3),
            "consistency_score": round(max(0, 100 - float(np.std(valid_times)) * 20), 1),
        }

    # Sort by avg lap time (fastest first)
    sorted_drivers = sorted(driver_stats.items(), key=lambda x: x[1]["avg_lap"])

    # ── Pit performance ──────────────────────────────────────────────────
    pit_performance = []
    for strat in strategies_data:
        driver = strat.get("driver", "")
        stints = strat.get("stints", [])
        n_stops = max(0, len(stints) - 1)

        compounds_used = [s.get("compound", "UNKNOWN") for s in stints]
        stint_lengths = [s.get("laps", 0) for s in stints]
        strategy_desc = " → ".join(compounds_used)

        pit_performance.append({
            "driver": driver,
            "driver_name": DRIVERS_2025.get(driver, {}).get("name", driver),
            "team": DRIVERS_2025.get(driver, {}).get("team", ""),
            "n_stops": n_stops,
            "strategy": strategy_desc,
            "compounds": compounds_used,
            "stint_lengths": stint_lengths,
        })

    # ── Strategy analysis ────────────────────────────────────────────────
    strategy_counts = {}
    for pp in pit_performance:
        key = pp["strategy"]
        strategy_counts[key] = strategy_counts.get(key, 0) + 1

    most_popular = max(strategy_counts, key=strategy_counts.get) if strategy_counts else "Unknown"
    avg_stops = np.mean([pp["n_stops"] for pp in pit_performance]) if pit_performance else 0

    strategy_analysis = {
        "most_popular_strategy": most_popular,
        "avg_pit_stops": round(float(avg_stops), 1),
        "strategy_distribution": strategy_counts,
        "unique_strategies": len(strategy_counts),
    }

    # ── Team execution scores ────────────────────────────────────────────
    team_scores = {}
    for driver_code, stats in driver_stats.items():
        team = DRIVERS_2025.get(driver_code, {}).get("team", "Unknown")
        if team not in team_scores:
            team_scores[team] = {"consistency_scores": [], "avg_laps": []}
        team_scores[team]["consistency_scores"].append(stats["consistency_score"])
        team_scores[team]["avg_laps"].append(stats["avg_lap"])

    team_execution = []
    for team, scores in team_scores.items():
        avg_consistency = round(np.mean(scores["consistency_scores"]), 1)
        avg_pace = round(np.mean(scores["avg_laps"]), 3)
        team_execution.append({
            "team": team,
            "team_color": get_team_color(team),
            "consistency_score": avg_consistency,
            "avg_pace": avg_pace,
            "execution_rating": (
                "Excellent" if avg_consistency >= 85 else
                "Good" if avg_consistency >= 70 else
                "Average" if avg_consistency >= 55 else
                "Below Average"
            ),
        })
    team_execution.sort(key=lambda x: -x["consistency_score"])

    # ── Generate narrative ───────────────────────────────────────────────
    winner = sorted_drivers[0] if sorted_drivers else None
    runner_up = sorted_drivers[1] if len(sorted_drivers) > 1 else None

    if winner:
        w_code, w_stats = winner
        w_name = DRIVERS_2025.get(w_code, {}).get("name", w_code)
        w_team = DRIVERS_2025.get(w_code, {}).get("team", "")

        # Find winner's strategy
        w_strat = "Unknown"
        for pp in pit_performance:
            if pp["driver"] == w_code:
                w_strat = pp["strategy"]
                break

        narrative = (
            f"{w_name} dominated the {circuit_name} with an average lap time of "
            f"{w_stats['avg_lap']}s. Running a {w_strat} strategy, "
            f"{w_name.split()[0]} maintained exceptional consistency "
            f"(σ = {w_stats['std_lap']}s) throughout the race. "
        )
        if runner_up:
            r_code, r_stats = runner_up
            r_name = DRIVERS_2025.get(r_code, {}).get("name", r_code)
            pace_gap = round(r_stats["avg_lap"] - w_stats["avg_lap"], 3)
            narrative += (
                f"{r_name} finished as the closest challenger, "
                f"{pace_gap}s per lap slower on average. "
            )
        narrative += (
            f"The most popular strategy was {most_popular}, "
            f"with an average of {round(float(avg_stops), 1)} pit stops per driver."
        )
    else:
        narrative = f"Race debrief data for {circuit_name} is being processed."

    # ── Safety car impact ────────────────────────────────────────────────
    # Check laps data for anomalies that suggest SC (very slow laps for everyone)
    sc_suspected_laps = []
    if sorted_drivers:
        all_driver_laps = {}
        for driver_code, laps in laps_data.items():
            for l in laps:
                lap_num = l.get("lap", 0)
                t = l.get("time")
                if t is not None and not (isinstance(t, float) and np.isnan(t)):
                    if lap_num not in all_driver_laps:
                        all_driver_laps[lap_num] = []
                    all_driver_laps[lap_num].append(t)

        for lap_num, times in sorted(all_driver_laps.items()):
            if len(times) >= 10:
                median_t = np.median(times)
                if median_t > 110:  # Well above normal race pace
                    sc_suspected_laps.append({
                        "lap": lap_num,
                        "avg_time": round(float(np.mean(times)), 2),
                        "likely_event": "Safety Car" if median_t > 120 else "VSC",
                    })

    safety_car_impact = {
        "suspected_sc_periods": len(sc_suspected_laps),
        "affected_laps": sc_suspected_laps[:5],  # Top 5
        "impact_summary": (
            f"{len(sc_suspected_laps)} suspected neutralization period(s) detected "
            f"based on lap time anomalies."
            if sc_suspected_laps
            else "No safety car periods detected in this race."
        ),
    }

    # ── Overtakes summary (estimated from position changes) ──────────────
    overtakes_summary = {
        "estimated_total": len(sorted_drivers) * 2,  # rough estimate
        "circuit_overtake_index": OVERTAKE_INDEX.get(circuit_id, 0.40),
        "difficulty": (
            "Very Difficult" if OVERTAKE_INDEX.get(circuit_id, 0.40) < 0.20 else
            "Difficult" if OVERTAKE_INDEX.get(circuit_id, 0.40) < 0.40 else
            "Moderate" if OVERTAKE_INDEX.get(circuit_id, 0.40) < 0.55 else
            "Easy"
        ),
    }

    return {
        "circuit_id": circuit_id,
        "circuit_name": circuit_name,
        "year": year,
        "narrative": narrative,
        "pit_performance": pit_performance,
        "strategy_analysis": strategy_analysis,
        "safety_car_impact": safety_car_impact,
        "overtakes_summary": overtakes_summary,
        "team_execution_scores": team_execution,
        "driver_stats": {code: stats for code, stats in sorted_drivers},
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
    top10 = list(drivers_data.items())[:10]

    return {
        "circuit_id": circuit_id,
        "circuit_name": sim["circuit_name"],
        "total_laps": sim["total_laps"],
        "n_simulations": n_simulations,
        "simulation_time_s": sim.get("simulation_time_s", 0),
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
