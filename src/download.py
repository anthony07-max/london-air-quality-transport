"""Download London Air (LAQN) annual statistics and site metadata, DfT traffic counts for London, and TfL stops."""
import json
import time
from pathlib import Path
import requests

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
LAQN = "https://api.erg.ic.ac.uk/AirQuality"
YEARS = range(2016, 2026)
DFT = "https://storage.googleapis.com/dft-statistics/road-traffic/downloads/aadf/region_id/dft_aadf_region_id_6.csv"  # region 6 = London
TFL = "https://api.tfl.gov.uk/StopPoint/Mode/{mode}"

def get(url, **kw):
    for i in range(4):
        try:
            r = requests.get(url, timeout=180, **kw); r.raise_for_status(); return r
        except Exception as e:
            err = e; time.sleep(3 * (i + 1))
    raise err

def main():
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "laqn_sites.json").write_bytes(get(f"{LAQN}/Information/MonitoringSites/GroupName=London/Json").content)
    for y in YEARS:
        (RAW / f"laqn_annual_{y}.json").write_bytes(get(f"{LAQN}/Annual/MonitoringObjective/GroupName=London/Year={y}/Json").content)
        print("LAQN", y)
    (RAW / "dft_aadf_london.csv").write_bytes(get(DFT).content); print("DfT AADF")
    for mode, keep in [("bus", "NaptanPublicBusCoachTram"), ("tube", "NaptanMetroStation")]:
        stops, page = [], 1
        while True:
            js = get(TFL.format(mode=mode), params={"page": page}).json()
            sp = js.get("stopPoints", []) if isinstance(js, dict) else js
            if not sp: break
            stops += [{"id": s["naptanId"], "name": s.get("commonName"), "lat": s["lat"], "lon": s["lon"]} for s in sp if s.get("stopType") == keep]
            if len(sp) < 1000: break
            page += 1
        (RAW / f"tfl_{mode}_stops.json").write_text(json.dumps(stops)); print("TfL", mode, len(stops))

if __name__ == "__main__":
    main()
