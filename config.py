"""
HAMMERTIME — Configuration & Constants
Auto-detects current season, defines team colors, API endpoints, and all constants.
"""

import os
from datetime import datetime
from pathlib import Path

# ─── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
PROCESSED_DIR = DATA_DIR / "processed"
MODELS_DIR = BASE_DIR / "models"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# Create directories
for d in [CACHE_DIR, PROCESSED_DIR, MODELS_DIR, STATIC_DIR, TEMPLATES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ─── Season Detection ──────────────────────────────────────────────────────────
CURRENT_YEAR = datetime.now().year
# F1 season typically starts in March
# If we're before March, the latest completed season is 2 years ago
# If we're after March, the latest completed season might be last year (or current if season ended)
# Conservative: use last year if current season might still be running
CURRENT_MONTH = datetime.now().month
if CURRENT_MONTH < 3:
    LATEST_COMPLETED_SEASON = CURRENT_YEAR - 2
    CURRENT_SEASON = CURRENT_YEAR - 1
else:
    LATEST_COMPLETED_SEASON = CURRENT_YEAR - 1
    CURRENT_SEASON = CURRENT_YEAR

# Training uses these seasons
TRAINING_SEASONS = [LATEST_COMPLETED_SEASON - 1, LATEST_COMPLETED_SEASON]  # e.g., [2024, 2025]
EVALUATION_SEASON = CURRENT_SEASON  # e.g., 2026

# ─── API Endpoints ─────────────────────────────────────────────────────────────
JOLPICA_BASE_URL = "https://api.jolpi.ca/ergast/f1"
OPENF1_BASE_URL = "https://api.openf1.org/v1"

# ─── Monte Carlo Parameters ───────────────────────────────────────────────────
N_SIMULATIONS = 1000
DEFAULT_RACE_LAPS = 57  # Will be overridden per circuit

# ─── Model Paths ───────────────────────────────────────────────────────────────
MODEL_PATH = MODELS_DIR / "lap_time_model.pkl"
SCALER_PATH = MODELS_DIR / "scaler.pkl"
ENCODER_PATH = MODELS_DIR / "label_encoders.pkl"

# ─── F1 Team Colors (2025 Official) ───────────────────────────────────────────
TEAM_COLORS = {
    "Red Bull Racing":    "#3671C6",
    "Ferrari":            "#E8002D",
    "Mercedes":           "#27F4D2",
    "McLaren":            "#FF8000",
    "Aston Martin":       "#229971",
    "Alpine":             "#FF87BC",
    "Haas F1 Team":       "#B6BABD",
    "RB":                 "#6692FF",
    "Williams":           "#64C4FF",
    "Kick Sauber":        "#52E252",
}

# Alternate team name mappings (FastF1 vs Jolpica naming inconsistencies)
TEAM_NAME_MAP = {
    "Red Bull Racing": ["Red Bull Racing", "Red Bull", "red_bull"],
    "Ferrari": ["Ferrari", "ferrari"],
    "Mercedes": ["Mercedes", "Mercedes-AMG Petronas F1 Team", "mercedes"],
    "McLaren": ["McLaren", "McLaren F1 Team", "mclaren"],
    "Aston Martin": ["Aston Martin", "Aston Martin Aramco F1 Team", "aston_martin"],
    "Alpine": ["Alpine", "Alpine F1 Team", "BWT Alpine F1 Team", "alpine"],
    "Haas F1 Team": ["Haas F1 Team", "Haas", "haas"],
    "RB": ["RB", "Racing Bulls", "RB F1 Team", "AlphaTauri", "rb", "alphatauri"],
    "Williams": ["Williams", "Williams Racing", "williams"],
    "Kick Sauber": ["Kick Sauber", "Sauber", "Stake F1 Team Kick Sauber", "sauber", "kick_sauber"],
}

def normalize_team_name(name: str) -> str:
    """Map any team name variant to the canonical name."""
    for canonical, variants in TEAM_NAME_MAP.items():
        if name in variants or name.lower() in [v.lower() for v in variants]:
            return canonical
    return name

def get_team_color(team_name: str) -> str:
    """Get hex color for a team (with normalization)."""
    canonical = normalize_team_name(team_name)
    return TEAM_COLORS.get(canonical, "#FFFFFF")

# ─── 2025 Driver Data ─────────────────────────────────────────────────────────
DRIVERS_2025 = {
    "VER": {"name": "Max Verstappen", "number": 1, "team": "Red Bull Racing", "nationality": "NL", "country": "Netherlands"},
    "LAW": {"name": "Liam Lawson", "number": 30, "team": "Red Bull Racing", "nationality": "NZ", "country": "New Zealand"},
    "LEC": {"name": "Charles Leclerc", "number": 16, "team": "Ferrari", "nationality": "MC", "country": "Monaco"},
    "HAM": {"name": "Lewis Hamilton", "number": 44, "team": "Ferrari", "nationality": "GB", "country": "United Kingdom"},
    "RUS": {"name": "George Russell", "number": 63, "team": "Mercedes", "nationality": "GB", "country": "United Kingdom"},
    "ANT": {"name": "Kimi Antonelli", "number": 12, "team": "Mercedes", "nationality": "IT", "country": "Italy"},
    "NOR": {"name": "Lando Norris", "number": 4, "team": "McLaren", "nationality": "GB", "country": "United Kingdom"},
    "PIA": {"name": "Oscar Piastri", "number": 81, "team": "McLaren", "nationality": "AU", "country": "Australia"},
    "ALO": {"name": "Fernando Alonso", "number": 14, "team": "Aston Martin", "nationality": "ES", "country": "Spain"},
    "STR": {"name": "Lance Stroll", "number": 18, "team": "Aston Martin", "nationality": "CA", "country": "Canada"},
    "GAS": {"name": "Pierre Gasly", "number": 10, "team": "Alpine", "nationality": "FR", "country": "France"},
    "DOO": {"name": "Jack Doohan", "number": 7, "team": "Alpine", "nationality": "AU", "country": "Australia"},
    "OCO": {"name": "Esteban Ocon", "number": 31, "team": "Haas F1 Team", "nationality": "FR", "country": "France"},
    "BEA": {"name": "Oliver Bearman", "number": 87, "team": "Haas F1 Team", "nationality": "GB", "country": "United Kingdom"},
    "TSU": {"name": "Yuki Tsunoda", "number": 22, "team": "RB", "nationality": "JP", "country": "Japan"},
    "HAD": {"name": "Isack Hadjar", "number": 6, "team": "RB", "nationality": "FR", "country": "France"},
    "ALB": {"name": "Alex Albon", "number": 23, "team": "Williams", "nationality": "TH", "country": "Thailand"},
    "SAI": {"name": "Carlos Sainz", "number": 55, "team": "Williams", "nationality": "ES", "country": "Spain"},
    "HUL": {"name": "Nico Hulkenberg", "number": 27, "team": "Kick Sauber", "nationality": "DE", "country": "Germany"},
    "BOR": {"name": "Gabriel Bortoleto", "number": 5, "team": "Kick Sauber", "nationality": "BR", "country": "Brazil"},
}

# ─── Circuit Data (2025 Calendar with typical race laps) ──────────────────────
CIRCUITS = {
    "bahrain": {"name": "Bahrain Grand Prix", "location": "Sakhir", "country": "Bahrain", "laps": 57, "sc_probability": 0.35, "rain_probability": 0.01},
    "saudi_arabia": {"name": "Saudi Arabian Grand Prix", "location": "Jeddah", "country": "Saudi Arabia", "laps": 50, "sc_probability": 0.55, "rain_probability": 0.02},
    "australia": {"name": "Australian Grand Prix", "location": "Melbourne", "country": "Australia", "laps": 58, "sc_probability": 0.60, "rain_probability": 0.20},
    "japan": {"name": "Japanese Grand Prix", "location": "Suzuka", "country": "Japan", "laps": 53, "sc_probability": 0.30, "rain_probability": 0.25},
    "china": {"name": "Chinese Grand Prix", "location": "Shanghai", "country": "China", "laps": 56, "sc_probability": 0.40, "rain_probability": 0.15},
    "miami": {"name": "Miami Grand Prix", "location": "Miami", "country": "USA", "laps": 57, "sc_probability": 0.45, "rain_probability": 0.30},
    "emilia_romagna": {"name": "Emilia Romagna Grand Prix", "location": "Imola", "country": "Italy", "laps": 63, "sc_probability": 0.35, "rain_probability": 0.20},
    "monaco": {"name": "Monaco Grand Prix", "location": "Monte Carlo", "country": "Monaco", "laps": 78, "sc_probability": 0.65, "rain_probability": 0.10},
    "spain": {"name": "Spanish Grand Prix", "location": "Barcelona", "country": "Spain", "laps": 66, "sc_probability": 0.25, "rain_probability": 0.05},
    "canada": {"name": "Canadian Grand Prix", "location": "Montreal", "country": "Canada", "laps": 70, "sc_probability": 0.55, "rain_probability": 0.30},
    "austria": {"name": "Austrian Grand Prix", "location": "Spielberg", "country": "Austria", "laps": 71, "sc_probability": 0.40, "rain_probability": 0.25},
    "great_britain": {"name": "British Grand Prix", "location": "Silverstone", "country": "United Kingdom", "laps": 52, "sc_probability": 0.35, "rain_probability": 0.35},
    "hungary": {"name": "Hungarian Grand Prix", "location": "Budapest", "country": "Hungary", "laps": 70, "sc_probability": 0.30, "rain_probability": 0.15},
    "belgium": {"name": "Belgian Grand Prix", "location": "Spa-Francorchamps", "country": "Belgium", "laps": 44, "sc_probability": 0.45, "rain_probability": 0.40},
    "netherlands": {"name": "Dutch Grand Prix", "location": "Zandvoort", "country": "Netherlands", "laps": 72, "sc_probability": 0.35, "rain_probability": 0.25},
    "italy": {"name": "Italian Grand Prix", "location": "Monza", "country": "Italy", "laps": 53, "sc_probability": 0.30, "rain_probability": 0.10},
    "azerbaijan": {"name": "Azerbaijan Grand Prix", "location": "Baku", "country": "Azerbaijan", "laps": 51, "sc_probability": 0.60, "rain_probability": 0.05},
    "singapore": {"name": "Singapore Grand Prix", "location": "Marina Bay", "country": "Singapore", "laps": 62, "sc_probability": 0.70, "rain_probability": 0.25},
    "united_states": {"name": "United States Grand Prix", "location": "Austin", "country": "USA", "laps": 56, "sc_probability": 0.35, "rain_probability": 0.10},
    "mexico": {"name": "Mexico City Grand Prix", "location": "Mexico City", "country": "Mexico", "laps": 71, "sc_probability": 0.35, "rain_probability": 0.10},
    "brazil": {"name": "São Paulo Grand Prix", "location": "Interlagos", "country": "Brazil", "laps": 71, "sc_probability": 0.55, "rain_probability": 0.40},
    "las_vegas": {"name": "Las Vegas Grand Prix", "location": "Las Vegas", "country": "USA", "laps": 50, "sc_probability": 0.45, "rain_probability": 0.02},
    "qatar": {"name": "Qatar Grand Prix", "location": "Lusail", "country": "Qatar", "laps": 57, "sc_probability": 0.30, "rain_probability": 0.01},
    "abu_dhabi": {"name": "Abu Dhabi Grand Prix", "location": "Yas Marina", "country": "UAE", "laps": 58, "sc_probability": 0.25, "rain_probability": 0.01},
}

# ─── Nationality Flag Emoji Mapping ───────────────────────────────────────────
COUNTRY_FLAGS = {
    "NL": "🇳🇱", "NZ": "🇳🇿", "MC": "🇲🇨", "GB": "🇬🇧", "IT": "🇮🇹",
    "AU": "🇦🇺", "ES": "🇪🇸", "CA": "🇨🇦", "FR": "🇫🇷", "JP": "🇯🇵",
    "TH": "🇹🇭", "DE": "🇩🇪", "BR": "🇧🇷", "FI": "🇫🇮", "CN": "🇨🇳",
    "DK": "🇩🇰", "MX": "🇲🇽", "US": "🇺🇸",
}

# ─── Tyre Compound Colors ─────────────────────────────────────────────────────
COMPOUND_COLORS = {
    "SOFT": "#FF3333",
    "MEDIUM": "#FFC906",
    "HARD": "#EEEEEE",
    "INTERMEDIATE": "#39B54A",
    "WET": "#00AEEF",
    "UNKNOWN": "#888888",
    "TEST_UNKNOWN": "#888888",
}

# ─── Stochastic Event Defaults ────────────────────────────────────────────────
DEFAULT_SC_PROBABILITY = 0.35       # Per-race safety car probability
DEFAULT_VSC_PROBABILITY = 0.25     # Per-race VSC probability
DEFAULT_RAIN_PROBABILITY = 0.10    # Per-race rain change probability
SC_LAP_DURATION_PENALTY = 25.0     # Seconds added per lap under SC
VSC_LAP_DURATION_PENALTY = 10.0    # Seconds added per lap under VSC
PIT_STOP_MEAN = 2.5                # Average pit stop time (seconds, stationary)
PIT_STOP_STD = 0.3                 # Std dev of pit stop time
PIT_STOP_SLOW_PROBABILITY = 0.03   # Chance of a slow pit stop
PIT_STOP_SLOW_PENALTY = 5.0        # Extra seconds for a slow stop
PIT_LANE_TIME = 20.0               # Time lost entering + exiting pit lane

# DNF base rates per race (approximate from 2024 data)
BASE_DNF_RATE = {
    "Red Bull Racing": 0.05,
    "Ferrari": 0.07,
    "Mercedes": 0.04,
    "McLaren": 0.04,
    "Aston Martin": 0.06,
    "Alpine": 0.08,
    "Haas F1 Team": 0.06,
    "RB": 0.07,
    "Williams": 0.08,
    "Kick Sauber": 0.09,
}

# ─── XGBoost Hyperparameters ──────────────────────────────────────────────────
XGBOOST_PARAMS = {
    "n_estimators": 500,
    "max_depth": 8,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "min_child_weight": 5,
    "objective": "reg:squarederror",
    "eval_metric": "rmse",
    "random_state": 42,
    "n_jobs": -1,
}

# ─── Feature Columns ──────────────────────────────────────────────────────────
FEATURE_COLUMNS = [
    "driver_encoded",
    "circuit_encoded",
    "tyre_compound_encoded",
    "tyre_age",
    "fuel_load_estimate",
    "track_temp",
    "air_temp",
    "lap_number",
    "grid_position",
    "is_wet",
    "stint_number",
    "driver_avg_pace",
    "team_performance_index",
    "lap_fraction",
]

TARGET_COLUMN = "lap_time_seconds"
