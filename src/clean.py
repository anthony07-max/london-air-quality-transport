"""Tidy LAQN annual means and join site-level transport exposure (DfT traffic, TfL bus stops and tube stations)."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, OUT = ROOT / "data" / "raw", ROOT / "data" / "processed"
CHARING_CROSS = (51.5073, -0.1276)

def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371000 * 2 * np.arcsin(np.sqrt(a))

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sites = pd.DataFrame(json.loads((RAW / "laqn_sites.json").read_text())["Sites"]["Site"])
    sites.columns = [c.lstrip("@") for c in sites.columns]
    sites = sites[["SiteCode", "SiteName", "SiteType", "LocalAuthorityName", "Latitude", "Longitude", "DateOpened", "DateClosed"]]
    sites = sites[(sites.Latitude != "") & (sites.Longitude != "")]
    sites[["Latitude", "Longitude"]] = sites[["Latitude", "Longitude"]].astype(float)

    rows = []
    for f in sorted(RAW.glob("laqn_annual_*.json")):
        js = json.loads(f.read_text())["SiteObjectives"]["Site"]
        for s in js:
            objs = s.get("Objective", [])
            objs = objs if isinstance(objs, list) else [objs]
            d = {}
            for o in objs:
                d[(o["@SpeciesCode"], o["@ObjectiveName"])] = o["@Value"]
            for sp, mean_name in [("NO2", "40 ug/m3 as an annual mean"), ("PM25", "Annual mean > 20 ug/m3"), ("PM10", "40 ug/m3 as an annual mean")]:
                cands = [k for k in d if k[0] == sp and ("annual mean" in k[1].lower())]
                if not cands: continue
                val = pd.to_numeric(d[cands[0]], errors="coerce")
                cap = pd.to_numeric(d.get((sp, "Capture Rate (%)")), errors="coerce")
                rows.append({"SiteCode": s["@SiteCode"], "year": int(f.stem[-4:]), "species": sp, "annual_mean": val, "capture": cap})
    aq = pd.DataFrame(rows).dropna(subset=["annual_mean"])
    aq = aq[(aq.capture >= 75) & (aq.annual_mean > 0)]
    aq = aq.merge(sites[["SiteCode", "SiteName", "SiteType", "LocalAuthorityName", "Latitude", "Longitude"]], on="SiteCode")
    aq.to_csv(OUT / "annual_means.csv", index=False)

    # Transport exposure around each site
    aadf = pd.read_csv(RAW / "dft_aadf_london.csv", low_memory=False)
    latest = aadf.year.max()
    a = aadf[aadf.year == latest]
    bus = pd.DataFrame(json.loads((RAW / "tfl_bus_stops.json").read_text()))
    tube = pd.DataFrame(json.loads((RAW / "tfl_tube_stops.json").read_text()))
    st = sites[sites.SiteCode.isin(aq.SiteCode)].copy()
    feats = []
    for r in st.itertuples():
        da = haversine(r.Latitude, r.Longitude, a.latitude.values, a.longitude.values)
        db = haversine(r.Latitude, r.Longitude, bus.lat.values, bus.lon.values)
        dt = haversine(r.Latitude, r.Longitude, tube.lat.values, tube.lon.values)
        near = a[da <= 300]
        feats.append({"SiteCode": r.SiteCode,
                      "traffic_300m": near.all_motor_vehicles.max() if len(near) else 0,
                      "hgv_300m": near.all_hgvs.max() if len(near) else 0,
                      "nearest_count_point_m": da.min(),
                      "bus_stops_300m": int((db <= 300).sum()), "tube_stations_800m": int((dt <= 800).sum()),
                      "dist_centre_km": haversine(r.Latitude, r.Longitude, *CHARING_CROSS) / 1000})
    st = st.merge(pd.DataFrame(feats), on="SiteCode")
    # ULEZ phase by distance from Charing Cross: an APPROXIMATION of the real boundaries (see README)
    st["ulez_phase"] = pd.cut(st.dist_centre_km, [0, 3, 9, 100], labels=["Central (Apr 2019)", "Inner (Oct 2021, approx.)", "Outer (Aug 2023, approx.)"])
    st.to_csv(OUT / "site_features.csv", index=False)
    print(len(aq), "site-year-pollutant rows;", st.shape[0], "sites; AADF year", latest)
    print(aq.groupby(["species", "year"]).size().unstack(0))

if __name__ == "__main__":
    main()
