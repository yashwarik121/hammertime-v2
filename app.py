"""
HAMMERTIME — FastAPI Application
Serves the F1 Race Outcome Simulator dashboard and REST API.

Run with:
    cd f:\\project 101
    python -m uvicorn app:app --reload
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from config import (
    BASE_DNF_RATE,
    CIRCUITS,
    COMPOUND_COLORS,
    COUNTRY_FLAGS,
    CURRENT_SEASON,
    DRIVERS_2025,
    LATEST_COMPLETED_SEASON,
    N_SIMULATIONS,
    STATIC_DIR,
    TEAM_COLORS,
    TEMPLATES_DIR,
    TRAINING_SEASONS,
    get_team_color,
    normalize_team_name,
)
from src.utils import setup_logger

logger = setup_logger("hammertime.app")

# ═══════════════════════════════════════════════════════════════════════════════
# App state
# ═══════════════════════════════════════════════════════════════════════════════

_app_state: dict[str, Any] = {
    "ready": False,
    "model_loaded": False,
    "data_loaded": False,
    "startup_time": None,
    "driver_photos": {},
    "driver_standings": {},
    "constructor_standings": {},
    "error": None,
}


# ═══════════════════════════════════════════════════════════════════════════════
# Lifespan (startup / shutdown)
# ═══════════════════════════════════════════════════════════════════════════════


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup & shutdown handler."""
    logger.info("🏁 HAMMERTIME starting up …")
    t0 = time.time()

    # ── Try to load model ─────────────────────────────────────────────────
    try:
        from src.model_trainer import load_model, should_retrain

        model = load_model()
        if model is not None:
            _app_state["model_loaded"] = True
            logger.info("✅ ML model loaded")
        elif should_retrain():
            logger.info("No model found — will be trained on first request or via data fetch.")
    except Exception as exc:
        logger.warning("Model loading skipped: %s", exc)

    # ── Try to load driver photos ─────────────────────────────────────────
    try:
        from src.data_fetcher import fetch_driver_photos

        photos = fetch_driver_photos()
        if photos:
            _app_state["driver_photos"] = photos
            logger.info("✅ Loaded %d driver photos", len(photos))
    except Exception as exc:
        logger.warning("Driver photos skipped: %s", exc)

    # ── Try to load standings (cache only, no blocking HTTP at startup) ───
    try:
        from src.utils import load_from_cache, cache_key

        ck_d = cache_key("jolpica_driver_standings", CURRENT_SEASON)
        ds = load_from_cache(ck_d)
        if ds:
            _app_state["driver_standings"] = ds
            _app_state["data_loaded"] = True

        ck_c = cache_key("jolpica_constructor_standings", CURRENT_SEASON)
        cs = load_from_cache(ck_c)
        if cs:
            _app_state["constructor_standings"] = cs
    except Exception:
        pass

    _app_state["ready"] = True
    _app_state["startup_time"] = round(time.time() - t0, 2)
    logger.info("🏁 HAMMERTIME ready in %.1f s", _app_state["startup_time"])

    yield  # ← app runs here

    logger.info("🏁 HAMMERTIME shutting down")


# ═══════════════════════════════════════════════════════════════════════════════
# FastAPI app
# ═══════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="HAMMERTIME — F1 Race Outcome Simulator",
    version="1.0.0",
    description="Monte Carlo F1 race simulation powered by XGBoost",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files & templates
STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic models
# ═══════════════════════════════════════════════════════════════════════════════


class SimulationRequest(BaseModel):
    circuit_id: str
    n_simulations: int = Field(default=N_SIMULATIONS, ge=100, le=100_000)
    sc_prob: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    vsc_prob: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    rain_prob: Optional[float] = Field(default=None, ge=0.0, le=1.0)


# ═══════════════════════════════════════════════════════════════════════════════
# Routes — Pages
# ═══════════════════════════════════════════════════════════════════════════════


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main dashboard."""
    # Try to render template; if it doesn't exist, return a minimal HTML page
    try:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "title": "HAMMERTIME",
                "current_season": CURRENT_SEASON,
                "n_simulations": f"{N_SIMULATIONS:,}",
            },
        )
    except Exception as exc:
        logger.error("Template rendering failed: %s", exc, exc_info=True)
        return HTMLResponse(
            content=_fallback_html(),
            status_code=200,
        )


def _fallback_html() -> str:
    """Minimal HTML when template is not yet created."""
    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>HAMMERTIME</title>
<style>
body{font-family:system-ui;background:#1a1a2e;color:#eee;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.card{background:#16213e;padding:3rem;border-radius:1rem;text-align:center;max-width:600px}
h1{color:#ff8000;font-size:2.5rem}
a{color:#27f4d2}
code{background:#0f3460;padding:0.2rem 0.5rem;border-radius:4px}
</style></head><body>
<div class="card">
<h1>🏁 HAMMERTIME</h1>
<p>F1 Race Outcome Simulator — API is running!</p>
<p>Try <a href="/docs">/docs</a> for the interactive API documentation.</p>
<p>Or <a href="/api/status">/api/status</a> to check system status.</p>
<p style="margin-top:2rem;color:#888">Place your <code>index.html</code> in the <code>templates/</code> folder to see the full dashboard.</p>
</div></body></html>"""


# ═══════════════════════════════════════════════════════════════════════════════
# Routes — API
# ═══════════════════════════════════════════════════════════════════════════════

# ─── Status ───────────────────────────────────────────────────────────────────


@app.get("/api/status")
async def api_status():
    """Return application readiness and metadata."""
    from src.model_trainer import get_model_info

    return {
        "status": "ok" if _app_state["ready"] else "starting",
        "model": get_model_info(),
        "data_loaded": _app_state["data_loaded"],
        "startup_time_s": _app_state["startup_time"],
        "current_season": CURRENT_SEASON,
        "training_seasons": TRAINING_SEASONS,
        "circuits_available": len(CIRCUITS),
        "drivers_available": len(DRIVERS_2025),
    }


# ─── Drivers ──────────────────────────────────────────────────────────────────


@app.get("/api/drivers")
async def api_drivers():
    """Return all 2025 drivers with photos and team info."""
    photos = _app_state.get("driver_photos", {})
    result = []
    for code, info in DRIVERS_2025.items():
        photo_data = photos.get(code, {})
        result.append(
            {
                "code": code,
                "name": info["name"],
                "number": info["number"],
                "team": info["team"],
                "team_color": get_team_color(info["team"]),
                "nationality": info["nationality"],
                "country": info["country"],
                "flag": COUNTRY_FLAGS.get(info["nationality"], "🏳️"),
                "headshot_url": photo_data.get("headshot_url", ""),
            }
        )
    return result


@app.get("/api/drivers/{code}")
async def api_driver_detail(code: str):
    """Return detail for a single driver."""
    code = code.upper()
    info = DRIVERS_2025.get(code)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Driver '{code}' not found")

    photos = _app_state.get("driver_photos", {})
    photo_data = photos.get(code, {})

    # Try to get standings info
    standings_entry = None
    standings = _app_state.get("driver_standings")
    if standings:
        for entry in standings:
            if entry.get("code", "").upper() == code:
                standings_entry = entry
                break

    return {
        "code": code,
        "name": info["name"],
        "number": info["number"],
        "team": info["team"],
        "team_color": get_team_color(info["team"]),
        "nationality": info["nationality"],
        "country": info["country"],
        "flag": COUNTRY_FLAGS.get(info["nationality"], "🏳️"),
        "headshot_url": photo_data.get("headshot_url", ""),
        "dnf_rate": BASE_DNF_RATE.get(info["team"], 0.06),
        "standings": standings_entry,
    }


# ─── Standings ────────────────────────────────────────────────────────────────


@app.get("/api/standings/drivers")
async def api_driver_standings(year: int = CURRENT_SEASON):
    """Driver championship standings."""
    # Try cache first
    standings = _app_state.get("driver_standings")
    if standings and year == CURRENT_SEASON:
        return {"year": year, "standings": standings}

    # Fetch live
    try:
        from src.data_fetcher import fetch_driver_standings_async

        data = await fetch_driver_standings_async(year)
        if data:
            if year == CURRENT_SEASON:
                _app_state["driver_standings"] = data
            return {"year": year, "standings": data}
    except Exception as exc:
        logger.error("Standings fetch: %s", exc)

    return {"year": year, "standings": [], "note": "Data not available yet"}


@app.get("/api/standings/constructors")
async def api_constructor_standings(year: int = CURRENT_SEASON):
    """Constructor championship standings."""
    standings = _app_state.get("constructor_standings")
    if standings and year == CURRENT_SEASON:
        return {"year": year, "standings": standings}

    try:
        from src.data_fetcher import fetch_constructor_standings_async

        data = await fetch_constructor_standings_async(year)
        if data:
            if year == CURRENT_SEASON:
                _app_state["constructor_standings"] = data
            return {"year": year, "standings": data}
    except Exception as exc:
        logger.error("Constructor standings fetch: %s", exc)

    return {"year": year, "standings": [], "note": "Data not available yet"}


# ─── Circuits ─────────────────────────────────────────────────────────────────


@app.get("/api/circuits")
async def api_circuits():
    """Available circuits for simulation."""
    return [
        {
            "id": cid,
            "name": cdata["name"],
            "location": cdata["location"],
            "country": cdata["country"],
            "laps": cdata["laps"],
            "sc_probability": cdata["sc_probability"],
            "rain_probability": cdata["rain_probability"],
        }
        for cid, cdata in CIRCUITS.items()
    ]


# ─── Simulation ──────────────────────────────────────────────────────────────


@app.post("/api/simulate")
async def api_simulate(req: SimulationRequest):
    """Run Monte Carlo simulation for a circuit."""
    if req.circuit_id not in CIRCUITS:
        raise HTTPException(status_code=400, detail=f"Unknown circuit: {req.circuit_id}")

    try:
        from src.simulation_engine import simulate_race

        # Run CPU-bound simulation in thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: simulate_race(
                circuit_id=req.circuit_id,
                n_simulations=req.n_simulations,
                sc_prob=req.sc_prob,
                vsc_prob=req.vsc_prob,
                rain_prob=req.rain_prob,
            ),
        )
        return result
    except Exception as exc:
        logger.error("Simulation error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ─── Predictions ──────────────────────────────────────────────────────────────


@app.get("/api/predictions/{circuit_id}")
async def api_prediction(circuit_id: str):
    """Pre-race prediction card for a circuit."""
    if circuit_id not in CIRCUITS:
        raise HTTPException(status_code=404, detail=f"Unknown circuit: {circuit_id}")

    try:
        from src.simulation_engine import get_pre_race_prediction

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: get_pre_race_prediction(circuit_id),
        )
        return result
    except Exception as exc:
        logger.error("Prediction error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ─── Analytics ────────────────────────────────────────────────────────────────


@app.get("/api/analytics/laptimes")
async def api_analytics_laptimes(
    driver: str = Query(..., description="Driver code, e.g. VER"),
    circuit: str = Query(..., description="Circuit ID, e.g. bahrain"),
    year: int = Query(default=LATEST_COMPLETED_SEASON),
):
    """Return lap-time data for a driver at a circuit."""
    driver = driver.upper()
    if driver not in DRIVERS_2025:
        raise HTTPException(status_code=404, detail=f"Unknown driver: {driver}")

    # Try static precalculated cache first
    import json
    precalc_path = STATIC_DIR / "precalculated" / f"{circuit.lower()}.json"
    if precalc_path.exists():
        try:
            with open(precalc_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("year") == year:
                laps = data.get("laps", {}).get(driver, [])
                if laps:
                    logger.info("Loaded laptimes for %s at %s from static precalculated cache", driver, circuit)
                    return {"driver": driver, "circuit": circuit, "year": year, "laps": laps}
        except Exception as exc:
            logger.warning("Could not read precalculated file %s: %s", precalc_path, exc)

    try:
        from src.data_fetcher import fetch_session_laps, fetch_event_schedule

        schedule = fetch_event_schedule(year)
        if schedule is None:
            return {"driver": driver, "circuit": circuit, "year": year, "laps": []}

        # Find matching GP
        target_round = None
        for _, row in schedule.iterrows():
            event_name = str(row.get("EventName", "")).lower()
            if circuit.lower().replace("_", " ") in event_name or circuit.lower() in event_name:
                target_round = int(row.get("RoundNumber", 0))
                break

        if target_round is None or target_round == 0:
            return {"driver": driver, "circuit": circuit, "year": year, "laps": [], "note": "Circuit not found in schedule"}

        laps_df = fetch_session_laps(year, target_round, "R")
        if laps_df is None:
            return {"driver": driver, "circuit": circuit, "year": year, "laps": []}

        # Filter for driver
        drv_col = None
        for c in laps_df.columns:
            if c.lower() == "driver":
                drv_col = c
                break

        if drv_col is None:
            return {"driver": driver, "circuit": circuit, "year": year, "laps": []}

        drv_laps = laps_df[laps_df[drv_col] == driver]

        lap_data = []
        for _, row in drv_laps.iterrows():
            lap_num = None
            lap_time = None
            compound = None
            for c in drv_laps.columns:
                cl = c.lower()
                if cl == "lapnumber":
                    lap_num = int(row[c]) if not pd.isna(row[c]) else None
                elif cl == "laptime":
                    val = row[c]
                    if hasattr(val, "total_seconds"):
                        lap_time = round(val.total_seconds(), 3)
                    else:
                        try:
                            lap_time = round(float(val), 3)
                        except (TypeError, ValueError):
                            lap_time = None
                elif cl == "compound":
                    compound = str(row[c]) if not pd.isna(row[c]) else None

            if lap_num is not None and lap_time is not None:
                lap_data.append(
                    {
                        "lap": lap_num,
                        "time": lap_time,
                        "compound": compound,
                        "compound_color": COMPOUND_COLORS.get(compound or "UNKNOWN", "#888"),
                    }
                )

        return {"driver": driver, "circuit": circuit, "year": year, "laps": lap_data}
    except Exception as exc:
        logger.error("Lap time analytics error: %s", exc)
        return {"driver": driver, "circuit": circuit, "year": year, "laps": [], "error": str(exc)}


@app.get("/api/analytics/tyres")
async def api_analytics_tyres(
    circuit: str = Query(..., description="Circuit ID"),
    year: int = Query(default=LATEST_COMPLETED_SEASON),
):
    """Tyre strategy data for a circuit/year."""
    # Try static precalculated cache first
    import json
    precalc_path = STATIC_DIR / "precalculated" / f"{circuit.lower()}.json"
    if precalc_path.exists():
        try:
            with open(precalc_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("year") == year:
                strategies = data.get("strategies", [])
                if strategies:
                    logger.info("Loaded tyre strategies for %s from static precalculated cache", circuit)
                    return {"circuit": circuit, "year": year, "strategies": strategies}
        except Exception as exc:
            logger.warning("Could not read precalculated file %s: %s", precalc_path, exc)

    try:
        from src.data_fetcher import fetch_session_laps, fetch_event_schedule

        schedule = fetch_event_schedule(year)
        if schedule is None:
            return {"circuit": circuit, "year": year, "strategies": []}

        # Find matching GP
        target_round = None
        for _, row in schedule.iterrows():
            event_name = str(row.get("EventName", "")).lower()
            if circuit.lower().replace("_", " ") in event_name or circuit.lower() in event_name:
                target_round = int(row.get("RoundNumber", 0))
                break

        if target_round is None or target_round == 0:
            return {"circuit": circuit, "year": year, "strategies": []}

        laps_df = fetch_session_laps(year, target_round, "R")
        if laps_df is None:
            return {"circuit": circuit, "year": year, "strategies": []}

        # Build per-driver tyre strategy
        drv_col = compound_col = stint_col = None
        for c in laps_df.columns:
            cl = c.lower()
            if cl == "driver":
                drv_col = c
            elif cl == "compound":
                compound_col = c
            elif cl == "stint":
                stint_col = c

        if not drv_col or not compound_col:
            return {"circuit": circuit, "year": year, "strategies": []}

        strategies = []
        for driver, grp in laps_df.groupby(drv_col):
            stints = []
            if stint_col:
                for stint_num, stint_grp in grp.groupby(stint_col):
                    compounds = stint_grp[compound_col].dropna().unique()
                    comp = str(compounds[0]) if len(compounds) > 0 else "UNKNOWN"
                    stints.append(
                        {
                            "stint": int(stint_num) if not pd.isna(stint_num) else 1,
                            "compound": comp,
                            "compound_color": COMPOUND_COLORS.get(comp, "#888"),
                            "laps": len(stint_grp),
                        }
                    )
            else:
                compounds = grp[compound_col].dropna().unique()
                comp = str(compounds[0]) if len(compounds) > 0 else "UNKNOWN"
                stints.append(
                    {
                        "stint": 1,
                        "compound": comp,
                        "compound_color": COMPOUND_COLORS.get(comp, "#888"),
                        "laps": len(grp),
                    }
                )

            strategies.append({"driver": str(driver), "stints": stints})

        return {"circuit": circuit, "year": year, "strategies": strategies}
    except Exception as exc:
        logger.error("Tyre analytics error: %s", exc)
        return {"circuit": circuit, "year": year, "strategies": [], "error": str(exc)}


@app.get("/api/analytics/reliability")
async def api_analytics_reliability():
    """DNF risk per driver based on team reliability data."""
    result = []
    for code, info in DRIVERS_2025.items():
        team = info["team"]
        rate = BASE_DNF_RATE.get(team, 0.06)
        result.append(
            {
                "code": code,
                "name": info["name"],
                "team": team,
                "team_color": get_team_color(team),
                "dnf_rate_per_race": round(rate, 3),
                "dnf_pct": round(rate * 100, 1),
                "reliability_rating": (
                    "Excellent" if rate <= 0.04 else
                    "Good" if rate <= 0.06 else
                    "Average" if rate <= 0.08 else
                    "Poor"
                ),
            }
        )
    result.sort(key=lambda d: d["dnf_rate_per_race"])
    return result

# ─── Calendar & Schedule ─────────────────────────────────────────────────────


@app.get("/api/calendar")
async def api_calendar(year: int = CURRENT_SEASON):
    """Full season calendar with next-race detection."""
    from datetime import datetime, timezone

    try:
        from src.data_fetcher import fetch_race_calendar_async

        cal = await fetch_race_calendar_async(year)
    except Exception as exc:
        logger.error("Calendar fetch: %s", exc)
        cal = None

    # Fallback to CIRCUITS config if API unavailable
    if not cal:
        cal = [
            {
                "round": i + 1,
                "race_name": cdata["name"],
                "circuit_id": cid,
                "circuit_name": cdata["name"],
                "locality": cdata["location"],
                "country": cdata["country"],
                "date": "",
            }
            for i, (cid, cdata) in enumerate(CIRCUITS.items())
        ]

    now = datetime.now(timezone.utc)
    next_race = None
    enriched = []

    for race in cal:
        race_date_str = race.get("date", "")
        status = "upcoming"
        race_dt = None

        if race_date_str:
            try:
                race_dt = datetime.strptime(race_date_str, "%Y-%m-%d").replace(
                    hour=14, tzinfo=timezone.utc
                )
                if race_dt.date() < now.date():
                    status = "completed"
                elif race_dt.date() == now.date():
                    status = "live"
                else:
                    status = "upcoming"
            except ValueError:
                pass

        entry = {
            "round": race.get("round", 0),
            "race_name": race.get("race_name", ""),
            "circuit_id": race.get("circuit_id", ""),
            "circuit_name": race.get("circuit_name", ""),
            "locality": race.get("locality", ""),
            "country": race.get("country", ""),
            "date": race_date_str,
            "status": status,
        }
        enriched.append(entry)

        # Pick first upcoming as next race
        if next_race is None and status in ("upcoming", "live") and race_dt:
            countdown_ms = max(0, int((race_dt - now).total_seconds() * 1000))
            next_race = {**entry, "status": "next", "countdown_ms": countdown_ms}
            entry["status"] = "next"

    return {"year": year, "calendar": enriched, "next_race": next_race}


@app.get("/api/recent-results")
async def api_recent_results(year: int = CURRENT_SEASON, limit: int = 5):
    """Recent race winners (most recent first)."""
    try:
        from src.data_fetcher import fetch_race_results_async

        results = await fetch_race_results_async(year)
    except Exception as exc:
        logger.error("Recent results fetch: %s", exc)
        results = None

    if not results:
        return {"year": year, "results": [], "note": "No results available yet"}

    # Group by round, find P1 and podium
    from collections import defaultdict

    rounds: dict[int, list] = defaultdict(list)
    for r in results:
        rnd = r.get("round", 0)
        if rnd > 0:
            rounds[rnd].append(r)

    race_results = []
    for rnd in sorted(rounds.keys(), reverse=True):
        entries = sorted(rounds[rnd], key=lambda x: int(x.get("position", 99) or 99))
        if not entries:
            continue

        winner = entries[0]
        podium = []
        for e in entries[:3]:
            code = e.get("code", "")
            driver_info = DRIVERS_2025.get(code, {})
            team = e.get("team", driver_info.get("team", ""))
            podium.append({
                "position": int(e.get("position", 0) or 0),
                "code": code,
                "name": e.get("driver_name", driver_info.get("name", code)),
                "team": team,
                "team_color": get_team_color(team),
            })

        w_code = winner.get("code", "")
        w_info = DRIVERS_2025.get(w_code, {})
        w_team = winner.get("team", w_info.get("team", ""))

        race_results.append({
            "round": rnd,
            "race_name": winner.get("race_name", f"Round {rnd}"),
            "circuit_id": winner.get("circuit_id", ""),
            "country": "",
            "date": "",
            "winner": {
                "code": w_code,
                "name": winner.get("driver_name", w_info.get("name", w_code)),
                "team": w_team,
                "team_color": get_team_color(w_team),
            },
            "podium": podium,
        })

        if len(race_results) >= limit:
            break

    return {"year": year, "results": race_results}


# ═══════════════════════════════════════════════════════════════════════════════
# Import guard for pd (used in analytics endpoint)
# ═══════════════════════════════════════════════════════════════════════════════
import pandas as pd
