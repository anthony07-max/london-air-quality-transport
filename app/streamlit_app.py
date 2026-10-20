from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

P = Path(__file__).resolve().parents[1] / "data" / "processed"
st.set_page_config(page_title="London air quality & transport", layout="wide")
st.title("London air quality and transport")
st.caption("LAQN (London Air) monitoring, DfT traffic counts and TfL stops. By Anthony Adusei-Poku (@anthony07-max)")
aq = pd.read_csv(P / "annual_means.csv"); sites = pd.read_csv(P / "site_features.csv")
sp = st.radio("Pollutant", ["NO2", "PM25", "PM10"], horizontal=True)
yr = st.slider("Year", int(aq.year.min()), int(aq.year.max()), int(aq.year.max()))
d = aq[(aq.species == sp) & (aq.year == yr)].merge(sites[["SiteCode", "traffic_300m", "bus_stops_300m", "ulez_phase"]], on="SiteCode")
st.plotly_chart(px.scatter_map(d, lat="Latitude", lon="Longitude", color="annual_mean", size="annual_mean", hover_name="SiteName",
                               hover_data=["SiteType", "traffic_300m", "bus_stops_300m", "ulez_phase"], color_continuous_scale="YlOrRd",
                               zoom=9, height=600, map_style="open-street-map"), use_container_width=True)
site = st.selectbox("Site history", sorted(aq.SiteName.unique()))
st.plotly_chart(px.line(aq[aq.SiteName == site], x="year", y="annual_mean", color="species", markers=True), use_container_width=True)
