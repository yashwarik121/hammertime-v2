"""
HAMMERTIME — Data Fetcher
Acquires F1 data from three sources:
  1. FastF1 (session laps, weather, schedule)
  2. Jolpica / Ergast API (standings, results, calendar)
  3. OpenF1 API (driver photos, pit stops, race control)
"""

from __future__ import annotations

import asyncio
import warnings
from typing import Any, Optional

import httpx
import pandas as pd

from config import (
    CACHE_DIR,
    CIRCUITS,
    CURRENT_SEASON,
    DRIVERS_2025,
    JOLPICA_BASE_URL,
    LATEST_COMPLETED_SEASON,
    OPENF1_BASE_URL,
    TRAINING_SEASONS,
)
from src.utils import (
    cache_key,
    load_dataframe_cache,
    load_from_cache,
    save_dataframe_cache,
    save_to_cache,
    setup_logger,
    td_to_seconds,
)

logger = setup_logger("hammertime.data_fetcher")

# Suppress FastF1 FutureWarnings
warnings.filterwarnings("ignore", category=FutureWarning)

# ─── FastF1 Helpers ────────────────────────────────────────────────────────────

_fastf1_cache_enabled = False


def _ensure_fastf1_cache() -> None:
    """Enable the FastF1 disk cache (once)."""
    global _fastf1_cache_enabled
    if not _fastf1_cache_enabled:
        try:
            import fastf1

            fastf1.Cache.enable_cache(str(CACHE_DIR))
            _fastf1_cache_enabled = True
            logger.info("FastF1 cache enabled at %s", CACHE_DIR)
        except Exception as exc:
            logger.warning("Could not enable FastF1 cache: %s", exc)


def _timedelta_cols_to_seconds(df: pd.DataFrame) -> pd.DataFrame:
    """Convert every Timedelta column in *df* to float seconds (in-place copy)."""
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_timedelta64_dtype(df[col]):
            df[col] = df[col].dt.total_seconds()
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# 1.  FastF1 functions
# ═══════════════════════════════════════════════════════════════════════════════


def fetch_event_schedule(year: int) -> Optional[pd.DataFrame]:
    """Return the FastF1 event schedule for *year* as a DataFrame."""
    _ensure_fastf1_cache()
    ck = cache_key("ff1_schedule", year)
    cached = load_dataframe_cache(ck)
    if cached is not None:
        logger.debug("Schedule %d loaded from cache", year)
        return cached

    try:
        import fastf1

        schedule = fastf1.get_event_schedule(year, include_testing=False)
        schedule = _timedelta_cols_to_seconds(schedule)
        save_dataframe_cache(ck, schedule)
        logger.info("Fetched %d event schedule (%d events)", year, len(schedule))
        return schedule
    except Exception as exc:
        logger.error("Failed to fetch event schedule for %d: %s", year, exc)
        return None


def fetch_season_sessions(year: int) -> list[dict[str, Any]]:
    """Return a list of ``{RoundNumber, EventName, ...}`` for every race in *year*."""
    schedule = fetch_event_schedule(year)
    if schedule is None:
        return []
    records: list[dict[str, Any]] = []
    for _, row in schedule.iterrows():
        records.append(
            {
                "round": int(row.get("RoundNumber", 0)),
                "name": row.get("EventName", ""),
                "country": row.get("Country", ""),
                "location": row.get("Location", ""),
                "date": str(row.get("EventDate", "")),
            }
        )
    return records


def fetch_session_laps(
    year: int,
    gp: str | int,
    session_type: str = "R",
) -> Optional[pd.DataFrame]:
    """Load lap-level data for a session.

    Parameters
    ----------
    year : int
    gp : str or int – Grand Prix name or round number
    session_type : str – ``'R'`` (race), ``'Q'``, ``'FP1'`` etc.

    Returns
    -------
    pd.DataFrame or None
    """
    _ensure_fastf1_cache()
    ck = cache_key("ff1_laps", year, gp, session_type)
    cached = load_dataframe_cache(ck)
    if cached is not None:
        logger.debug("Laps %s/%s/%s loaded from cache", year, gp, session_type)
        return cached

    try:
        import fastf1

        session = fastf1.get_session(year, gp, session_type)
        session.load(laps=True, telemetry=False, weather=True, messages=False)
        laps = session.laps
        if laps is None or laps.empty:
            logger.warning("No lap data for %s/%s/%s", year, gp, session_type)
            return None
        laps = _timedelta_cols_to_seconds(laps)
        save_dataframe_cache(ck, laps)
        logger.info(
            "Fetched %d laps for %s/%s/%s",
            len(laps),
            year,
            gp,
            session_type,
        )
        return laps
    except Exception as exc:
        logger.error("Failed to load laps %s/%s/%s: %s", year, gp, session_type, exc)
        return None


def fetch_weather_data(year: int, gp: str | int) -> Optional[pd.DataFrame]:
    """Return weather samples for the race session of *gp* in *year*."""
    _ensure_fastf1_cache()
    ck = cache_key("ff1_weather", year, gp)
    cached = load_dataframe_cache(ck)
    if cached is not None:
        return cached

    try:
        import fastf1

        session = fastf1.get_session(year, gp, "R")
        session.load(laps=False, telemetry=False, weather=True, messages=False)
        weather = session.weather_data
        if weather is None or weather.empty:
            return None
        weather = _timedelta_cols_to_seconds(weather)
        save_dataframe_cache(ck, weather)
        logger.info("Fetched weather for %s/%s", year, gp)
        return weather
    except Exception as exc:
        logger.error("Failed to fetch weather %s/%s: %s", year, gp, exc)
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# 2.  Jolpica / Ergast API  (async)
# ═══════════════════════════════════════════════════════════════════════════════

_JOLPICA_TIMEOUT = 30.0
_JOLPICA_RETRIES = 3


async def _jolpica_get(path: str) -> Optional[dict]:
    """GET ``JOLPICA_BASE_URL + path`` with retries.  Returns parsed JSON or None."""
    url = f"{JOLPICA_BASE_URL}{path}"
    for attempt in range(1, _JOLPICA_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=_JOLPICA_TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Jolpica %s returned %s (attempt %d/%d)",
                path,
                exc.response.status_code,
                attempt,
                _JOLPICA_RETRIES,
            )
        except Exception as exc:
            logger.warning(
                "Jolpica %s error: %s (attempt %d/%d)",
                path,
                exc,
                attempt,
                _JOLPICA_RETRIES,
            )
        if attempt < _JOLPICA_RETRIES:
            await asyncio.sleep(1.0 * attempt)
    return None


async def fetch_driver_standings_async(year: int) -> Optional[list[dict]]:
    """Fetch driver championship standings for *year*."""
    ck = cache_key("jolpica_driver_standings", year)
    cached = load_from_cache(ck)
    if cached is not None:
        return cached

    data = await _jolpica_get(f"/{year}/driverStandings.json")
    if data is None:
        return None
    try:
        standings_lists = data["MRData"]["StandingsTable"]["StandingsLists"]
        if not standings_lists:
            return None
        entries = standings_lists[0]["DriverStandings"]
        result = []
        for entry in entries:
            driver = entry["Driver"]
            constructors = entry.get("Constructors", [{}])
            team = constructors[0].get("name", "") if constructors else ""
            result.append(
                {
                    "position": int(entry["position"]),
                    "points": float(entry["points"]),
                    "wins": int(entry["wins"]),
                    "driver_id": driver.get("driverId", ""),
                    "code": driver.get("code", ""),
                    "given_name": driver.get("givenName", ""),
                    "family_name": driver.get("familyName", ""),
                    "nationality": driver.get("nationality", ""),
                    "team": team,
                }
            )
        save_to_cache(ck, result)
        logger.info("Fetched driver standings %d (%d drivers)", year, len(result))
        return result
    except (KeyError, IndexError, TypeError) as exc:
        logger.error("Parsing driver standings %d failed: %s", year, exc)
        return None


async def fetch_constructor_standings_async(year: int) -> Optional[list[dict]]:
    """Fetch constructor championship standings for *year*."""
    ck = cache_key("jolpica_constructor_standings", year)
    cached = load_from_cache(ck)
    if cached is not None:
        return cached

    data = await _jolpica_get(f"/{year}/constructorStandings.json")
    if data is None:
        return None
    try:
        standings_lists = data["MRData"]["StandingsTable"]["StandingsLists"]
        if not standings_lists:
            return None
        entries = standings_lists[0]["ConstructorStandings"]
        result = []
        for entry in entries:
            constructor = entry["Constructor"]
            result.append(
                {
                    "position": int(entry["position"]),
                    "points": float(entry["points"]),
                    "wins": int(entry["wins"]),
                    "constructor_id": constructor.get("constructorId", ""),
                    "name": constructor.get("name", ""),
                    "nationality": constructor.get("nationality", ""),
                }
            )
        save_to_cache(ck, result)
        logger.info("Fetched constructor standings %d", year)
        return result
    except (KeyError, IndexError, TypeError) as exc:
        logger.error("Parsing constructor standings %d failed: %s", year, exc)
        return None


async def fetch_race_results_async(
    year: int, round_num: Optional[int] = None
) -> Optional[list[dict]]:
    """Fetch race results.  If *round_num* is ``None``, fetch all rounds."""
    ck = cache_key("jolpica_results", year, round_num or "all")
    cached = load_from_cache(ck)
    if cached is not None:
        return cached

    path = f"/{year}/results.json?limit=1000"
    if round_num is not None:
        path = f"/{year}/{round_num}/results.json"

    data = await _jolpica_get(path)
    if data is None:
        return None
    try:
        races = data["MRData"]["RaceTable"]["Races"]
        result: list[dict] = []
        for race in races:
            round_n = int(race["round"])
            race_name = race.get("raceName", "")
            circuit_id = race.get("Circuit", {}).get("circuitId", "")
            for res in race.get("Results", []):
                driver = res.get("Driver", {})
                constructor = res.get("Constructor", {})
                result.append(
                    {
                        "round": round_n,
                        "race_name": race_name,
                        "circuit_id": circuit_id,
                        "position": res.get("position", ""),
                        "position_text": res.get("positionText", ""),
                        "points": float(res.get("points", 0)),
                        "grid": int(res.get("grid", 0)),
                        "status": res.get("status", ""),
                        "driver_id": driver.get("driverId", ""),
                        "code": driver.get("code", ""),
                        "driver_name": f"{driver.get('givenName', '')} {driver.get('familyName', '')}",
                        "team": constructor.get("name", ""),
                    }
                )
        save_to_cache(ck, result)
        logger.info("Fetched race results %d (round=%s, %d entries)", year, round_num, len(result))
        return result
    except (KeyError, IndexError, TypeError) as exc:
        logger.error("Parsing race results %d failed: %s", year, exc)
        return None


async def fetch_race_calendar_async(year: int) -> Optional[list[dict]]:
    """Fetch the race calendar for *year*."""
    ck = cache_key("jolpica_calendar", year)
    cached = load_from_cache(ck)
    if cached is not None:
        return cached

    data = await _jolpica_get(f"/{year}.json")
    if data is None:
        return None
    try:
        races = data["MRData"]["RaceTable"]["Races"]
        result = []
        for race in races:
            circuit = race.get("Circuit", {})
            loc = circuit.get("Location", {})
            result.append(
                {
                    "round": int(race["round"]),
                    "race_name": race.get("raceName", ""),
                    "circuit_id": circuit.get("circuitId", ""),
                    "circuit_name": circuit.get("circuitName", ""),
                    "locality": loc.get("locality", ""),
                    "country": loc.get("country", ""),
                    "date": race.get("date", ""),
                }
            )
        save_to_cache(ck, result)
        logger.info("Fetched race calendar %d (%d races)", year, len(result))
        return result
    except (KeyError, IndexError, TypeError) as exc:
        logger.error("Parsing race calendar %d failed: %s", year, exc)
        return None


# ─── Sync wrappers for Jolpica ─────────────────────────────────────────────────


def _run_async(coro):
    """Run an async coroutine from sync code, handling existing event loops."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're inside an already-running loop (e.g. Jupyter, FastAPI startup)
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


def fetch_driver_standings(year: int) -> Optional[list[dict]]:
    """Sync wrapper for :func:`fetch_driver_standings_async`."""
    return _run_async(fetch_driver_standings_async(year))


def fetch_constructor_standings(year: int) -> Optional[list[dict]]:
    """Sync wrapper for :func:`fetch_constructor_standings_async`."""
    return _run_async(fetch_constructor_standings_async(year))


def fetch_race_results(year: int, round_num: Optional[int] = None) -> Optional[list[dict]]:
    """Sync wrapper for :func:`fetch_race_results_async`."""
    return _run_async(fetch_race_results_async(year, round_num))


def fetch_race_calendar(year: int) -> Optional[list[dict]]:
    """Sync wrapper for :func:`fetch_race_calendar_async`."""
    return _run_async(fetch_race_calendar_async(year))


# ═══════════════════════════════════════════════════════════════════════════════
# 3.  OpenF1 API
# ═══════════════════════════════════════════════════════════════════════════════

_OPENF1_TIMEOUT = 20.0


async def _openf1_get(path: str, params: Optional[dict] = None) -> Optional[list[dict]]:
    """GET ``OPENF1_BASE_URL + path`` — returns list of dicts or None."""
    url = f"{OPENF1_BASE_URL}{path}"
    for attempt in range(1, 3):
        try:
            async with httpx.AsyncClient(timeout=_OPENF1_TIMEOUT) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.warning("OpenF1 %s error: %s (attempt %d)", path, exc, attempt)
            if attempt < 2:
                await asyncio.sleep(1.0)
    return None


async def fetch_driver_photos_async() -> dict[str, dict]:
    """Return ``{driver_number_str: {headshot_url, team_colour, ...}}``."""
    ck = cache_key("openf1_driver_photos")
    cached = load_from_cache(ck)
    if cached is not None:
        return cached

    data = await _openf1_get("/drivers", params={"session_key": "latest"})
    if not data:
        return {}

    result: dict[str, dict] = {}
    for d in data:
        acronym = d.get("name_acronym", "")
        if not acronym:
            continue
        result[acronym] = {
            "headshot_url": d.get("headshot_url", ""),
            "team_colour": d.get("team_colour", ""),
            "full_name": d.get("full_name", ""),
            "driver_number": d.get("driver_number"),
            "country_code": d.get("country_code", ""),
            "team_name": d.get("team_name", ""),
        }
    save_to_cache(ck, result)
    logger.info("Fetched %d driver photos from OpenF1", len(result))
    return result


async def fetch_pit_stops_async(session_key: int) -> Optional[list[dict]]:
    """Fetch pit-stop data for a specific session key."""
    ck = cache_key("openf1_pits", session_key)
    cached = load_from_cache(ck)
    if cached is not None:
        return cached

    data = await _openf1_get("/pit", params={"session_key": session_key})
    if data is None:
        return None
    save_to_cache(ck, data)
    return data


async def fetch_race_control_async(session_key: int) -> Optional[list[dict]]:
    """Fetch race-control messages for a session."""
    ck = cache_key("openf1_rc", session_key)
    cached = load_from_cache(ck)
    if cached is not None:
        return cached

    data = await _openf1_get("/race_control", params={"session_key": session_key})
    if data is None:
        return None
    save_to_cache(ck, data)
    return data


# Sync wrappers for OpenF1

def fetch_driver_photos() -> dict[str, dict]:
    """Sync wrapper."""
    return _run_async(fetch_driver_photos_async())


def fetch_pit_stops(session_key: int) -> Optional[list[dict]]:
    """Sync wrapper."""
    return _run_async(fetch_pit_stops_async(session_key))


def fetch_race_control(session_key: int) -> Optional[list[dict]]:
    """Sync wrapper."""
    return _run_async(fetch_race_control_async(session_key))


# ═══════════════════════════════════════════════════════════════════════════════
# 4.  Season detection & master loader
# ═══════════════════════════════════════════════════════════════════════════════


def detect_latest_season() -> int:
    """Heuristic: return the most recent year for which Jolpica has race results."""
    for year in range(CURRENT_SEASON, CURRENT_SEASON - 3, -1):
        try:
            cal = fetch_race_calendar(year)
            if cal:
                logger.info("Detected latest available season: %d", year)
                return year
        except Exception:
            continue
    return LATEST_COMPLETED_SEASON


def load_all_data(
    years: Optional[list[int]] = None,
    *,
    fetch_laps: bool = True,
) -> dict[str, Any]:
    """Orchestrate data acquisition for one or more seasons.

    Returns a dict::

        {
            "standings": {year: {...}},
            "results": {year: [...]},
            "calendars": {year: [...]},
            "laps": {(year, gp): DataFrame, ...},
            "weather": {(year, gp): DataFrame, ...},
            "driver_photos": {...},
        }
    """
    if years is None:
        years = list(TRAINING_SEASONS)

    out: dict[str, Any] = {
        "standings": {},
        "constructor_standings": {},
        "results": {},
        "calendars": {},
        "laps": {},
        "weather": {},
        "driver_photos": {},
    }

    # Driver photos (OpenF1)
    try:
        out["driver_photos"] = fetch_driver_photos()
    except Exception as exc:
        logger.error("Driver photos fetch failed: %s", exc)

    for year in years:
        logger.info("─── Loading data for %d ───", year)

        # Jolpica: standings + results + calendar
        try:
            out["standings"][year] = fetch_driver_standings(year)
        except Exception as exc:
            logger.error("Driver standings %d: %s", year, exc)

        try:
            out["constructor_standings"][year] = fetch_constructor_standings(year)
        except Exception as exc:
            logger.error("Constructor standings %d: %s", year, exc)

        try:
            out["results"][year] = fetch_race_results(year)
        except Exception as exc:
            logger.error("Race results %d: %s", year, exc)

        try:
            out["calendars"][year] = fetch_race_calendar(year)
        except Exception as exc:
            logger.error("Calendar %d: %s", year, exc)

        # FastF1: laps & weather per GP
        if fetch_laps:
            schedule = fetch_event_schedule(year)
            if schedule is not None:
                for _, row in schedule.iterrows():
                    gp_name = row.get("EventName", "")
                    round_num = int(row.get("RoundNumber", 0))
                    if round_num == 0 or not gp_name:
                        continue
                    try:
                        laps = fetch_session_laps(year, round_num)
                        if laps is not None:
                            out["laps"][(year, gp_name)] = laps
                    except Exception as exc:
                        logger.warning("Laps %d/%s: %s", year, gp_name, exc)

                    try:
                        wx = fetch_weather_data(year, round_num)
                        if wx is not None:
                            out["weather"][(year, gp_name)] = wx
                    except Exception as exc:
                        logger.warning("Weather %d/%s: %s", year, gp_name, exc)

    logger.info("Data loading complete for years %s", years)
    return out
