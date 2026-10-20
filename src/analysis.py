"""Trends, ULEZ phase comparison, transport-exposure regression and maps."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
P, CH = ROOT / "data" / "processed", ROOT / "charts"
CH.mkdir(exist_ok=True)

def main():
    aq = pd.read_csv(P / "annual_means.csv")
    st = pd.read_csv(P / "site_features.csv")
    no2 = aq[aq.species == "NO2"]
    out = {}

    # 1. Trend by site type (sites with 8+ of 10 years -> stable panel)
    yrs = no2.groupby("SiteCode").year.nunique()
    panel = no2[no2.SiteCode.isin(yrs[yrs >= 8].index)]
    panel = panel.assign(kind=np.where(panel.SiteType.isin(["Roadside", "Kerbside"]), "Roadside/kerbside", "Background (urban/suburban)"))
    tr = panel.groupby(["year", "kind"]).annual_mean.median().unstack()
    out["panel_sites"] = int(panel.SiteCode.nunique())
    out["no2_median_by_type"] = tr.round(1).to_dict()
    fig, ax = plt.subplots(figsize=(9, 5))
    tr.plot(ax=ax, marker="o"); ax.axhline(40, color="r", ls="--", lw=1); ax.text(2016, 41, "UK legal limit 40 µg/m³", color="r", fontsize=8)
    ax.axhline(10, color="g", ls="--", lw=1); ax.text(2016, 11, "WHO 2021 guideline 10 µg/m³", color="g", fontsize=8)
    for x, lab in [(2019.3, "ULEZ central"), (2021.8, "ULEZ inner"), (2023.6, "ULEZ outer")]:
        ax.axvline(x, color="grey", lw=.8, ls=":"); ax.text(x, ax.get_ylim()[1] * .95, lab, rotation=90, fontsize=7, va="top")
    ax.set_ylabel("Median annual mean NO₂ (µg/m³)"); ax.set_title(f"London NO₂, 2016-2025 ({out['panel_sites']} LAQN sites with 8+ years of data)")
    fig.tight_layout(); fig.savefig(CH / "01_no2_trend.png", dpi=150); plt.close()

    # 2. Compliance
    comp = no2.groupby("year").apply(lambda g: pd.Series({"sites": len(g), "over_40": (g.annual_mean > 40).mean(), "over_who_10": (g.annual_mean > 10).mean()}), include_groups=False)
    pm = aq[aq.species == "PM25"].groupby("year").apply(lambda g: pd.Series({"sites": len(g), "median": g.annual_mean.median(), "over_who_5": (g.annual_mean > 5).mean()}), include_groups=False)
    out["no2_compliance"] = comp.round(3).to_dict("index"); out["pm25"] = pm.round(2).to_dict("index")
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    (comp.over_40 * 100).plot.bar(ax=ax[0], color="#e63946", rot=0); ax[0].set_ylabel("% of sites"); ax[0].set_title("Sites breaking the UK NO₂ limit (40 µg/m³)")
    pm["median"].plot(ax=ax[1], marker="o", color="#6d597a"); ax[1].axhline(5, color="g", ls="--"); ax[1].set_ylim(0)
    ax[1].set_title("Median PM2.5 (WHO guideline 5 µg/m³)"); ax[1].set_ylabel("µg/m³")
    fig.tight_layout(); fig.savefig(CH / "02_compliance.png", dpi=150); plt.close()

    # 3. ULEZ phases: indexed change from 2019 for sites with both years
    b = no2.pivot_table(index="SiteCode", columns="year", values="annual_mean")
    b = b.join(st.set_index("SiteCode")[["ulez_phase", "SiteType"]])
    idx = {}
    for ph, g in b.groupby("ulez_phase"):
        g = g[g[2019].notna()]
        idx[ph] = {y: float((g[y] / g[2019]).median() * 100) for y in range(2016, 2026) if g[y].notna().sum() >= 3}
    ix = pd.DataFrame(idx)
    out["ulez_index_2019_100"] = ix.round(1).to_dict()
    ch = b[[2019, 2024]].dropna().assign(change=lambda d: (d[2024] / d[2019] - 1) * 100).join(b.ulez_phase)
    out["change_2019_2024_by_phase"] = ch.groupby("ulez_phase").change.agg(["median", "size"]).round(1).to_dict("index")
    fig, ax = plt.subplots(figsize=(9, 5)); ix.plot(ax=ax, marker="o"); ax.axhline(100, color="k", lw=.8)
    ax.set_ylabel("NO₂, 2019 = 100 (median across sites)"); ax.set_title("NO₂ change by (approximate) ULEZ phase area")
    fig.tight_layout(); fig.savefig(CH / "03_ulez_phases.png", dpi=150); plt.close()

    # 4. Transport exposure regression (latest data: mean of 2024-2025 per site)
    lat = no2[no2.year >= 2024].groupby("SiteCode").annual_mean.mean().rename("no2").reset_index().merge(st, on="SiteCode")
    lat["roadside"] = lat.SiteType.isin(["Roadside", "Kerbside"]).astype(int)
    lat["log_traffic"] = np.log1p(lat.traffic_300m)
    m = smf.ols("no2 ~ roadside + log_traffic + bus_stops_300m + tube_stations_800m + dist_centre_km", data=lat).fit(cov_type="HC1")
    out["regression"] = {"n": int(m.nobs), "r2": float(m.rsquared),
                         "coefs": pd.DataFrame({"coef": m.params, "lo": m.conf_int()[0], "hi": m.conf_int()[1], "p": m.pvalues}).round(3).to_dict("index")}
    print(m.summary())
    lat.to_csv(P / "latest_site_no2.csv", index=False)
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.8))
    for k, g in lat.groupby("roadside"):
        ax[0].scatter(g.traffic_300m / 1000, g.no2, label="Roadside/kerbside" if k else "Background", alpha=.7)
    ax[0].set_xlabel("Busiest DfT count point within 300 m (thousand vehicles/day)"); ax[0].set_ylabel("NO₂ 2024-25 (µg/m³)"); ax[0].legend()
    ax[0].set_title("Traffic vs NO₂")
    ax[1].scatter(lat.dist_centre_km, lat.no2, c=lat.roadside, cmap="coolwarm", alpha=.7)
    ax[1].set_xlabel("Distance from Charing Cross (km)"); ax[1].set_title("NO₂ falls with distance from the centre")
    fig.tight_layout(); fig.savefig(CH / "04_transport_exposure.png", dpi=150); plt.close()

    # 5. Map
    import json as _j
    tube = pd.DataFrame(_j.loads((ROOT / "data" / "raw" / "tfl_tube_stops.json").read_text()))
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.scatter(tube.lon, tube.lat, s=4, color="#bbbbbb", label="Tube stations (TfL)")
    sc = ax.scatter(lat.Longitude, lat.Latitude, c=lat.no2, cmap="YlOrRd", s=40 + 30 * lat.roadside, edgecolor="k", lw=.4, vmin=10, vmax=45)
    plt.colorbar(sc, ax=ax, label="NO₂ 2024-25 annual mean (µg/m³)")
    for r in lat.nlargest(5, "no2").itertuples(): ax.annotate(r.SiteName.split(" - ")[-1], (r.Longitude, r.Latitude), fontsize=7)
    ax.set_aspect(1 / np.cos(np.radians(51.5))); ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude"); ax.legend(loc="lower left", fontsize=8)
    ax.set_title("LAQN monitoring sites: NO₂ 2024-25 (larger = roadside)")
    fig.tight_layout(); fig.savefig(CH / "05_map.png", dpi=150); plt.close()
    out["top_sites"] = lat.nlargest(5, "no2")[["SiteName", "SiteType", "no2"]].round(1).to_dict("records")
    out["sites_latest"] = int(len(lat))
    (P / "key_findings.json").write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps({k: v for k, v in out.items() if k not in ("regression",)}, indent=1, default=str))

if __name__ == "__main__":
    main()
