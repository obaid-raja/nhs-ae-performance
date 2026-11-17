"""NHS A&E Four-Hour Target Tracker: every trust with a major A&E against the 78% and 82% targets.

    streamlit run app.py
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from nhs import analysis as A
from nhs import data

BLUE, ORANGE, AQUA, GREY = "#2a78d6", "#eb6834", "#1baf7a", "#898781"
STATUS_COLOURS = {A.STATUS_ORDER[0]: AQUA, A.STATUS_ORDER[1]: BLUE, A.STATUS_ORDER[2]: ORANGE,
                  A.STATUS_ORDER[3]: GREY}

st.set_page_config(page_title="NHS A&E Four-Hour Target Tracker", page_icon="🏥", layout="wide")


@st.cache_data
def load():
    p, e = data.load("provider_months"), data.load("england_months")
    return p, e, A.target_status(p)


p, e, t = load()
last = p["month"].max()

st.title("NHS A&E Four-Hour Target Tracker")
st.caption(f"Monthly NHS England A&E statistics, April 2024 to {last:%B %Y}. "
           "Target: 78% of patients admitted, transferred or discharged within 4 hours by March 2026; "
           "at least 82% at every trust by March 2027. Source: NHS England (OGL v3.0).")

cur = e.iloc[-1]
ly = e[e["month"] == last - pd.DateOffset(years=1)].iloc[0]
c = st.columns(4)
c[0].metric(f"England, {last:%b %Y}", f"{cur['pct_4h']:.1f}%",
            f"{cur['pct_4h'] - ly['pct_4h']:+.1f} pts on a year ago")
c[1].metric("Major A&E only (type 1)", f"{cur['pct_4h_type1']:.1f}%",
            f"{cur['pct_4h_type1'] - ly['pct_4h_type1']:+.1f} pts")
c[2].metric("12-hour waits for a bed", f"{int(cur['dta_12h_plus']):,}",
            f"{100 * (cur['dta_12h_plus'] / ly['dta_12h_plus'] - 1):+.1f}%", delta_color="inverse")
c[3].metric("Trusts already at 82% (March 2026)", f"{(t['status'] == A.STATUS_ORDER[0]).sum()} of {len(t)}")

tab_trust, tab_league, tab_about = st.tabs(["Look up a trust", "All trusts", "Method"])

with tab_trust:
    names = t.sort_values("org_name")
    code = st.selectbox("Trust", names["org_code"], format_func=dict(zip(names["org_code"], names["org_name"])).get)
    row = t.set_index("org_code").loc[code]
    m = p[p["org_code"] == code].sort_values("month")
    k = st.columns(4)
    k[0].metric("March 2026", f"{row['march_2026_pct']:.1f}%",
                f"{row['improvement_last_year_pts']:+.1f} pts on March 2025")
    k[1].metric("Still needed for 82%", f"{row['gap_to_82_pts']:.1f} pts")
    k[2].metric("Last 3 months vs a year earlier", f"{row['recent_3m_pct']:.1f}%",
                f"{row['autumn_yoy_change_pts']:+.1f} pts")
    k[3].metric("Status", row["status"])

    fig = go.Figure()
    fig.add_scatter(x=m["month"], y=m["pct_4h"], name="All types (headline)", mode="lines+markers",
                    line=dict(color=BLUE, width=2))
    fig.add_scatter(x=m["month"], y=m["pct_4h_type1"], name="Major A&E only", mode="lines+markers",
                    line=dict(color=ORANGE, width=2))
    for y, label in ((A.TARGET_2027, "82% (Mar 2027)"), (A.TARGET_2026, "78% (Mar 2026)")):
        fig.add_hline(y=y, line_dash="dot", line_color=GREY, annotation_text=label,
                      annotation_position="top left")
    fig.update_layout(title="Share of patients seen within 4 hours", yaxis_ticksuffix="%", height=400,
                      hovermode="x unified", margin=dict(l=10, r=10, t=50, b=10),
                      legend=dict(orientation="h", y=-0.15))
    st.plotly_chart(fig, width="stretch")

    fig = go.Figure(go.Bar(x=m["month"], y=m["dta_12h_plus"], marker_color=BLUE))
    fig.update_layout(title="Patients waiting 12+ hours for a bed after the decision to admit", height=300,
                      margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, width="stretch")

with tab_league:
    region = st.selectbox("Region", ["All"] + sorted(t["region"].unique()))
    d = t if region == "All" else t[t["region"] == region]
    d = d.sort_values("march_2026_pct")
    fig = go.Figure(go.Bar(
        x=d["march_2026_pct"], y=d["org_name"], orientation="h",
        marker_color=[STATUS_COLOURS[s] for s in d["status"]],
        customdata=d[["status", "gap_to_82_pts", "improvement_last_year_pts"]].values,
        hovertemplate="%{y}<br>March 2026: %{x:.1f}%<br>%{customdata[0]}<br>Needs +%{customdata[1]:.1f} pts"
                      "<br>Last year: %{customdata[2]:+.1f} pts<extra></extra>"))
    fig.add_vline(x=A.TARGET_2027, line_dash="dot", line_color=GREY)
    fig.add_vline(x=A.TARGET_2026, line_dash="dot", line_color=GREY)
    fig.update_layout(height=max(400, 18 * len(d)), xaxis_ticksuffix="%", margin=dict(l=10, r=10, t=30, b=10),
                      title="March 2026 four-hour performance (colour = status)")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(d.sort_values("march_2026_pct", ascending=False)[
        ["org_name", "region", "march_2026_pct", "improvement_last_year_pts", "gap_to_82_pts", "status",
         "pct_4h_type1_12m", "trolley_per_100_adm_12m", "type3_share_12m"]].rename(columns={
            "org_name": "Trust", "region": "Region", "march_2026_pct": "March 2026 %",
            "improvement_last_year_pts": "Change on March 2025 (pts)", "gap_to_82_pts": "Needed for 82% (pts)",
            "status": "Status", "pct_4h_type1_12m": "Major A&E % (12m)",
            "trolley_per_100_adm_12m": "12h waits per 100 admissions (12m)",
            "type3_share_12m": "Minor-unit share of attendances % (12m)"}),
        hide_index=True, width="stretch")

with tab_about:
    st.markdown(f"""
- **Four-hour performance** = share of all A&E attendances (booked and unbooked, all department types)
  admitted, transferred or discharged within 4 hours of arrival, the measure the targets use.
- **Major A&E only** counts type 1 departments: consultant-led, 24-hour emergency departments.
  Trusts that also run minor injury units or urgent treatment centres score higher on the headline measure.
- **Status** compares the improvement each trust still needs to reach 82% with the improvement it actually
  made between March 2025 and March 2026. It is not a forecast: a backtest showed that autumn trends predict
  the following March poorly (see the README).
- **12-hour waits** count admitted patients who waited more than 12 hours from the decision to admit until
  they left A&E (often called trolley waits).
- Trusts shown: the {len(t)} NHS trusts with more than {A.MIN_TYPE1_ATTENDANCES:,} major A&E attendances in {last:%B %Y}.
""")
