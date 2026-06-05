import os
import sys
import json
import pandas as pd
from pathlib import Path

sys.path.append(".")
from config import CIRCUITS, DRIVERS_2025, COMPOUND_COLORS, STATIC_DIR
from src.data_fetcher import fetch_event_schedule, fetch_session_laps

def precalculate_season(year: int = 2025):
    output_dir = STATIC_DIR / "precalculated"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Loading event schedule for {year}...")
    schedule = fetch_event_schedule(year)
    if schedule is None:
        print("Error: Could not load event schedule.")
        return
        
    for circuit_id, cdata in CIRCUITS.items():
        print(f"\n==================================================")
        print(f"Processing circuit: {circuit_id} ({cdata['name']})...")
        
        # Find matching GP in schedule
        target_round = None
        for _, row in schedule.iterrows():
            event_name = str(row.get("EventName", "")).lower()
            if circuit_id.lower().replace("_", " ") in event_name or circuit_id.lower() in event_name:
                target_round = int(row.get("RoundNumber", 0))
                break
                
        if target_round is None or target_round == 0:
            print(f"Circuit {circuit_id} not found in schedule, skipping.")
            continue
            
        print(f"Found GP round: {target_round}. Loading session laps...")
        laps_df = fetch_session_laps(year, target_round, "R")
        if laps_df is None or laps_df.empty:
            print(f"No lap data found for round {target_round}, skipping.")
            continue
            
        # ── 1. Extract Lap Times per Driver ──
        drv_col = None
        lap_num_col = None
        lap_time_col = None
        compound_col = None
        stint_col = None
        
        for c in laps_df.columns:
            cl = c.lower()
            if cl == "driver":
                drv_col = c
            elif cl == "lapnumber":
                lap_num_col = c
            elif cl == "laptime":
                lap_time_col = c
            elif cl == "compound":
                compound_col = c
            elif cl == "stint":
                stint_col = c
                
        if not drv_col or not lap_num_col or not lap_time_col or not compound_col:
            print(f"Required columns missing in lap data, skipping.")
            continue
            
        laps_data = {}
        for driver in DRIVERS_2025.keys():
            drv_laps = laps_df[laps_df[drv_col] == driver]
            if drv_laps.empty:
                continue
                
            driver_laps = []
            for _, row in drv_laps.iterrows():
                lap_num = int(row[lap_num_col]) if not pd.isna(row[lap_num_col]) else None
                val = row[lap_time_col]
                
                lap_time = None
                if hasattr(val, "total_seconds"):
                    lap_time = round(val.total_seconds(), 3)
                else:
                    try:
                        lap_time = round(float(val), 3)
                    except (TypeError, ValueError):
                        lap_time = None
                        
                compound = str(row[compound_col]) if not pd.isna(row[compound_col]) else None
                if compound in ("nan", "None", ""):
                    compound = "UNKNOWN"
                    
                if lap_num is not None and lap_time is not None:
                    driver_laps.append({
                        "lap": lap_num,
                        "time": lap_time,
                        "compound": compound,
                        "compound_color": COMPOUND_COLORS.get(compound.upper(), "#888")
                    })
            laps_data[driver] = driver_laps
            
        # ── 2. Extract Tyre Strategies per Driver ──
        strategies = []
        for driver, grp in laps_df.groupby(drv_col):
            stints = []
            if stint_col:
                for stint_num, stint_grp in grp.groupby(stint_col):
                    compounds = stint_grp[compound_col].dropna().unique()
                    comp = str(compounds[0]) if len(compounds) > 0 else "UNKNOWN"
                    if comp in ("nan", "None", ""):
                        comp = "UNKNOWN"
                    stints.append({
                        "stint": int(stint_num) if not pd.isna(stint_num) else 1,
                        "compound": comp.upper(),
                        "compound_color": COMPOUND_COLORS.get(comp.upper(), "#888"),
                        "laps": len(stint_grp)
                    })
            else:
                compounds = grp[compound_col].dropna().unique()
                comp = str(compounds[0]) if len(compounds) > 0 else "UNKNOWN"
                if comp in ("nan", "None", ""):
                    comp = "UNKNOWN"
                stints.append({
                    "stint": 1,
                    "compound": comp.upper(),
                    "compound_color": COMPOUND_COLORS.get(comp.upper(), "#888"),
                    "laps": len(grp)
                })
            strategies.append({
                "driver": str(driver),
                "stints": stints
            })
            
        # Save to JSON file
        result = {
            "circuit_id": circuit_id,
            "circuit_name": cdata["name"],
            "year": year,
            "laps": laps_data,
            "strategies": strategies
        }
        
        output_file = output_dir / f"{circuit_id}.json"
        with open(output_file, "w") as fh:
            json.dump(result, fh, indent=2)
            
        print(f"Successfully saved {output_file} ({len(laps_data)} drivers, {len(strategies)} strategies)")
        
    print("\nPre-calculation complete!")

if __name__ == "__main__":
    precalculate_season(2025)
