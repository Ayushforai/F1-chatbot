import requests

BASE_URL = "https://api.openf1.org/v1"

def format_lap_time(seconds):
    """Converts raw seconds into a standard F1 MM:SS.ms format."""
    if not seconds:
        return "N/A"
    try:
        sec_float = float(seconds)
        if sec_float >= 60:
            minutes = int(sec_float // 60)
            remaining = sec_float % 60
            return f"{minutes}:{remaining:06.3f}"
        return f"{sec_float:.3f}"
    except (ValueError, TypeError):
        return str(seconds)


def get_driver_telemetry(driver_number: int, session_key: str = "latest"):
    """Fetch the latest speed, RPM, and gear telemetry for a specific driver."""
    try:
        if session_key == "latest":
            session_res = requests.get(f"{BASE_URL}/sessions?location=Silverstone&year=2024")
            if session_res.status_code == 200 and session_res.json():
                session_key = session_res.json()[-1]["session_key"]
            else:
                session_key = "9565"

        url = f"{BASE_URL}/car_data?driver_number={driver_number}&session_key={session_key}"
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            if not data:
                return f"No telemetry found for Driver {driver_number} in session {session_key}."

            latest_metrics = data[-1]
            return {
                "driver_number": driver_number,
                "speed": latest_metrics.get("speed"),
                "rpm": latest_metrics.get("rpm"),
                "gear": latest_metrics.get("gear"),
                "drs": latest_metrics.get("drs"),
                "date": latest_metrics.get("date"),
            }

        return f"API Error: Unable to fetch car data (Status Code: {response.status_code})"
    except Exception as e:
        return f"Failed to reach telemetry tower: {str(e)}"


def get_session_info(country: str, year: int = 2024):
    """Fetch scheduling data and session IDs for a specific Grand Prix weekend."""
    try:
        url = f"{BASE_URL}/sessions?country_name={country}&year={year}"
        response = requests.get(url)
        if response.status_code == 200 and response.json():
            session = response.json()[0]
            return {
                "circuit": session.get("circuit_short_name"),
                "date_start": session.get("date_start"),
                "session_name": session.get("session_name"),
            }
        return "No session match found for those parameters."
    except Exception as e:
        return f"Error retrieving session keys: {str(e)}"


def get_fastest_lap_of_race(year: int, country: str, driver_number: int = None):
    """
    Finds the fastest lap of a specific historical race session.
    If a driver_number is provided, finds THAT driver's specific fastest lap.
    """
    try:
        session_url = f"{BASE_URL}/sessions?country_name={country}&year={year}&session_name=Race"
        session_res = requests.get(session_url)

        if session_res.status_code != 200 or not session_res.json():
            return f"Database Error: Could not locate a race session in {country} for {year}."

        session_key = session_res.json()[0]["session_key"]

        laps_url = f"{BASE_URL}/laps?session_key={session_key}"
        laps_res = requests.get(laps_url)
        laps_data = laps_res.json()

        if not laps_data:
            return "No lap data found for this session."

        valid_laps = [lap for lap in laps_data if lap.get("lap_duration") is not None]

        if driver_number is not None:
            valid_laps = [lap for lap in valid_laps if lap.get("driver_number") == driver_number]

        if not valid_laps:
            return f"No valid lap data found for Driver {driver_number} in this session."

        fastest_lap = min(valid_laps, key=lambda x: x["lap_duration"])

        driver_url = f"{BASE_URL}/drivers?session_key={session_key}&driver_number={fastest_lap['driver_number']}"
        driver_res = requests.get(driver_url).json()
        driver_name = driver_res[0]["full_name"] if driver_res else f"Driver {fastest_lap['driver_number']}"

        return {
            "race": f"{country} {year}",
            "driver": driver_name,
            "lap_number": fastest_lap["lap_number"],
            "lap_time_seconds": fastest_lap["lap_duration"],
            "average_speed": fastest_lap.get("st_speed"),
        }

    except Exception as e:
        return f"Historical Archive Error: {str(e)}"


def get_historical_lap(year: int, country: str, driver_number: int, lap_number: int):
    """Fetch data for a specific lap of a specific driver in a historical race."""
    try:
        session_url = f"{BASE_URL}/sessions?country_name={country}&year={year}&session_name=Race"
        session_res = requests.get(session_url)

        if session_res.status_code != 200 or not session_res.json():
            return f"Database Error: Could not locate a race session in {country} for {year}."

        session_key = session_res.json()[0]["session_key"]

        laps_url = f"{BASE_URL}/laps?session_key={session_key}&driver_number={driver_number}&lap_number={lap_number}"
        laps_res = requests.get(laps_url)
        laps_data = laps_res.json()

        if not laps_data:
            return f"No data found for Driver {driver_number}, Lap {lap_number} in {country} {year}."

        lap = laps_data[0]

        driver_url = f"{BASE_URL}/drivers?session_key={session_key}&driver_number={driver_number}"
        driver_res = requests.get(driver_url).json()
        driver_name = driver_res[0]["full_name"] if driver_res else f"Driver {driver_number}"

        return {
            "race": f"{country} {year}",
            "driver": driver_name,
            "lap_number": lap["lap_number"],
            "lap_time_seconds": lap.get("lap_duration"),
            "base_speed": lap.get("st_speed"),
            "is_pit_out_lap": lap.get("is_pit_out_lap"),
        }

    except Exception as e:
        return f"Historical Archive Error: {str(e)}"
