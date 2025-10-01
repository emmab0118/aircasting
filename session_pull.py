import sys
import os
import time
import json
import urllib.parse
from datetime import datetime, timedelta, timezone

import requests
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns


BASE = "https://aircasting.org"
OUTPUT_DIR = "./data"

#helper funcs for converting between datetime and epoch
def utc_now():
    return datetime.now(timezone.utc) #return current time in UTC timezone


def to_epoch_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000) #converts py datetime into epoch ms (unix timestamp * 1000)


def to_epoch_s(dt: datetime) -> int:
    return int(dt.timestamp()) #same as other one but epoch s


def encode_q(obj: dict) -> str:
    return urllib.parse.quote(json.dumps(obj), safe="") #takes py dict convert to json string
#need for aircasting's mapstyle endpoints



def geocode_location(query: str) -> tuple[float, float] | None:
    #return lat lon for city
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": query, "format": "json", "limit": 1}
    r = requests.get(url, params=params, timeout=10, headers={"User-Agent": "aircasting-demo"})
    r.raise_for_status()
    results = r.json()
    if not results:
        return None
    return float(results[0]["lat"]), float(results[0]["lon"])

def make_bounding_box(lat: float, lon: float, km: float = 20) -> dict:
    #return a bounding box around (lat,lon) w radius 20km by default
    dlat = km / 111.0
    dlon = km / (111.0 * math.cos(math.radians(lat)))
    return {"west": lon - dlon, "east": lon + dlon, "south": lat - dlat, "north": lat + dlat}



#session discovery
def pick_fixed_session_near_location(query: str, radius_km: float = 20) -> dict | None:
    coords = geocode_location(query)
    if not coords: #catch if geocode func breaks
        print("Could not geocode location:", query)
        return None
    
    lat, lon = coords
    bbox = make_bounding_box(lat, lon, km=radius_km)

    sensor_names = ["AirBeam3-PM2.5", "AirBeam2-PM2.5", "AirBeam-PM2.5"]
    day_windows = [7, 30, 90]
    kinds = ["active", "dormant"]

    for kind in kinds:
        for days in day_windows:
            for sensor in sensor_names:
                now = utc_now()
                q = {
                    "time_from": to_epoch_s(now - timedelta(days=days)),
                    "time_to": to_epoch_s(now),
                    "tags": "",
                    "usernames": "",
                    **bbox,
                    "sensor_name": sensor,
                    "measurement_type": "Particulate Matter",
                    "unit_symbol": "µg/m³",
                }
                url = f"{BASE}/api/fixed/{kind}/sessions.json?q={encode_q(q)}"
                r = requests.get(url, timeout=30)
                r.raise_for_status()
                sessions = r.json().get("sessions", [])
                if sessions:
                    s0 = sessions[0]
                    sid = s0.get("id") or s0.get("session_id")
                    return {"id": sid, "picked_via": f"mapstyle:{kind}:{days}d:{sensor}", "coords": coords}
    return None

#download???
def download_session_csv(session_id: int, OUTPUT_DIR = "./data"):
    #download measurements for a given session and save as CSV
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    url = f"{BASE}/api/sessions/{session_id}/measurements.json"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()

    rows = []
    for m in data.get("measurements", []):
        rows.append({
            "time": m.get("time"),
            "value": m.get("value"),
            "sensor_name": m.get("sensor_name"),
            "unit": m.get("unit_symbol"),
        })

    if not rows:
        print("No measurements found for this session.")
        return None

    df = pd.DataFrame(rows)
    output_path = os.path.join(OUTPUT_DIR, f"session_{session_id}.csv")
    df.to_csv(output_path, index=False)
    print(f"Saved session data → {output_path} | {len(df)} rows")
    return output_path

#basic ui for testing
#ill change this eventually for displaying on a page w html and php
def prompt():
    query = input("Enter a city or ZIP: ").strip()
    print(f"Looking up {query}...\n")

    session = pick_fixed_session_near_location(query)
    if session:
        coords = session["coords"]
        print(f"Found session near {query} at {coords}, ID={session['id']} via {session['picked_via']}")
        download_session_csv(session["id"], OUTPUT_DIR="downloads")
    else:
        print(f"No sessions found near {query}")

prompt()


#if __name__ == "__main__":
#    prompt()
