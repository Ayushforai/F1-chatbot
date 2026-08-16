import pandas as pd
import os

from utils.venues import csv_race_keyword

DATA_DIR = "./data/historical_csvs"

# Load ALL the CSVs into memory when the app starts
try:
    races_df = pd.read_csv(os.path.join(DATA_DIR, "races.csv"))
    drivers_df = pd.read_csv(os.path.join(DATA_DIR, "drivers.csv"))
    constructors_df = pd.read_csv(os.path.join(DATA_DIR, "constructors.csv"))
    results_df = pd.read_csv(os.path.join(DATA_DIR, "results.csv"))
except FileNotFoundError:
    print("Warning: Historical CSVs not found. Please run setup_historical_data.py first.")


def get_race_results(year: int, country: str, top_n: int = 10, location: str | None = None) -> dict | str:
    """Return the full top-N finishers for a race, with team, gap, and fastest lap data."""
    try:
        races_yr = races_df[races_df['year'] == year]
        if country:
            search_keyword = csv_race_keyword(country, location)
            races_yr = races_yr[races_yr['name'].str.contains(search_keyword, case=False, na=False)]

        if races_yr.empty:
            return f"No races found for {year}" + (f" matching '{country}'." if country else ".")

        race_id = races_yr.iloc[0]['raceId']
        race_name = races_yr.iloc[0]['name']

        res = (
            results_df[results_df['raceId'] == race_id]
            .merge(drivers_df[['driverId', 'forename', 'surname']], on='driverId')
            .merge(constructors_df[['constructorId', 'name']], on='constructorId')
            .sort_values('positionOrder')
            .head(top_n)
        )

        finishers = []
        for _, row in res.iterrows():
            gap = row['time'] if str(row['time']) not in ('\\N', 'nan', '') else 'N/A'
            finishers.append({
                "Position": row['positionText'],
                "Driver": f"{row['forename']} {row['surname']}",
                "Team": row['name'],
                "Gap / Race Time": gap,
                "Fastest Lap": row['fastestLapTime'] if str(row['fastestLapTime']) not in ('\\N', 'nan', '') else 'N/A',
                "Points": row['points'],
            })

        return {"Year": year, "Grand Prix": race_name, "Top Finishers": finishers}
    except Exception as e:
        return f"Historical Database Error: {str(e)}"


def get_historical_driver_info(year: int, driver_ref: str, country: str = None, location: str | None = None):
    """Return race result for a specific driver plus full top-10 context for that race."""
    try:
        # Always fetch the full race results for rich context
        race_data = get_race_results(year, country, location=location)
        if isinstance(race_data, str):
            return race_data  # error string

        if not driver_ref:
            return race_data  # no specific driver — return full results

        # Find the specific driver entry within the results
        driver = drivers_df[drivers_df['surname'].str.contains(driver_ref, case=False, na=False)]
        if driver.empty:
            driver = drivers_df[drivers_df['forename'].str.contains(driver_ref, case=False, na=False)]

        if not driver.empty:
            driver_id = driver.iloc[0]['driverId']
            full_name = f"{driver.iloc[0]['forename']} {driver.iloc[0]['surname']}"

            races_yr = races_df[races_df['year'] == year]
            if country:
                search_keyword = csv_race_keyword(country, location)
                races_yr = races_yr[races_yr['name'].str.contains(search_keyword, case=False, na=False)]

            if not races_yr.empty:
                race_id = races_yr.iloc[0]['raceId']
                res = results_df[(results_df['raceId'] == race_id) & (results_df['driverId'] == driver_id)]
                if not res.empty:
                    constructor_id = res.iloc[0]['constructorId']
                    team_name = constructors_df[constructors_df['constructorId'] == constructor_id].iloc[0]['name']
                    race_data["Queried Driver"] = {
                        "Driver": full_name,
                        "Team": team_name,
                        "Finish Position": res.iloc[0]['positionText'],
                        "Gap / Race Time": res.iloc[0]['time'] if str(res.iloc[0]['time']) not in ('\\N', 'nan', '') else 'N/A',
                        "Fastest Lap": res.iloc[0]['fastestLapTime'] if str(res.iloc[0]['fastestLapTime']) not in ('\\N', 'nan', '') else 'N/A',
                        "Points": res.iloc[0]['points'],
                    }

        return race_data
    except Exception as e:
        return f"Historical Database Error: {str(e)}"