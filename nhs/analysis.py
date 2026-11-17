"""Which trusts will meet the 82% four-hour A&E target by March 2027, and what separates them?

Targets (NHS England):
  * 78% of patients admitted, transferred or discharged within 4 hours by March 2026
    (2025/26 operating plan).
  * every trust to reach at least 82% by March 2027, and 85% nationally by 2028/29
    (Medium term planning framework, October 2025).
"""
import numpy as np
import pandas as pd

TARGET_2026 = 78.0
TARGET_2027 = 82.0
TARGET_2029 = 85.0
OLD_STANDARD = 95.0
MIN_TYPE1_ATTENDANCES = 1000  # a trust counts as running a major A&E above this monthly level
SUM_COLS = ["attendances", "over4", "att_type1", "over4_type1", "att_type3", "dta_12h_plus",
            "adm_via_ae"]


def acute_trusts(p: pd.DataFrame) -> pd.DataFrame:
    """Trusts running a major (type 1) A&E in the latest month."""
    last = p["month"].max()
    latest = p[(p["month"] == last) & (p["att_type1"] >= MIN_TYPE1_ATTENDANCES)]
    return latest[["org_code", "org_name", "region"]].reset_index(drop=True)


def window(p: pd.DataFrame, start, end) -> pd.DataFrame:
    """Pool counts over a date range (inclusive) per trust, then recompute the rates."""
    w = p[(p["month"] >= pd.Timestamp(start)) & (p["month"] <= pd.Timestamp(end))]
    g = w.groupby("org_code")[SUM_COLS].sum()
    g["pct_4h"] = 100 * (1 - g["over4"] / g["attendances"])
    g["pct_4h_type1"] = 100 * (1 - g["over4_type1"] / g["att_type1"])
    g["type3_share"] = 100 * g["att_type3"] / g["attendances"]
    g["trolley_per_100_adm"] = 100 * g["dta_12h_plus"] / g["adm_via_ae"]
    g["admission_rate"] = 100 * g["adm_via_ae"] / g["attendances"]
    return g


def project_march(p: pd.DataFrame, as_of) -> pd.DataFrame:
    """Project each trust's 4-hour performance for the March after `as_of`.

    Projection = last March's performance + the change between the three months to `as_of`
    and the same three months a year earlier. Comparing like-for-like months removes the
    seasonal pattern (A&E performance is always worst in winter and best in spring).
    """
    as_of = pd.Timestamp(as_of)
    base_march = pd.Timestamp(as_of.year if as_of.month >= 3 else as_of.year - 1, 3, 1)
    r_start = as_of - pd.DateOffset(months=2)
    recent = window(p, r_start, as_of)
    prior = window(p, r_start - pd.DateOffset(years=1), as_of - pd.DateOffset(years=1))
    march = p[p["month"] == base_march].set_index("org_code")["pct_4h"]
    out = pd.DataFrame({"base_march_pct": march, "recent_3m_pct": recent["pct_4h"],
                        "same_3m_last_year_pct": prior["pct_4h"]})
    out["yoy_change_pts"] = out["recent_3m_pct"] - out["same_3m_last_year_pct"]
    out["projected_pct"] = out["base_march_pct"] + out["yoy_change_pts"]
    return out


def backtest(p: pd.DataFrame, as_of="2025-10-01", actual_month="2026-03-01") -> dict:
    """Would the projection method have worked a year ago? Project March 2026 from data to
    October 2025, compare with what actually happened, and with a naive 'same as last March'."""
    trusts = acute_trusts(p)["org_code"]
    proj = project_march(p, as_of).reindex(trusts)
    actual = p[p["month"] == actual_month].set_index("org_code")["pct_4h"].reindex(trusts)
    ok = proj["projected_pct"].notna() & actual.notna()
    err = (proj["projected_pct"] - actual)[ok]
    naive = (proj["base_march_pct"] - actual)[ok]
    actual_change = (actual - proj["base_march_pct"])[ok]
    return {"trusts": int(ok.sum()), "trend_mae_pts": err.abs().mean(), "naive_mae_pts": naive.abs().mean(),
            "trend_bias_pts": err.mean(),
            "corr_autumn_trend_vs_march_change": proj["yoy_change_pts"][ok].corr(actual_change),
            "median_trust_change_march_to_march_pts": actual_change.median()}


STATUS_ORDER = ["Already at 82%", "Reachable at last year's pace", "Needs faster improvement",
                 "Not enough data"]


def target_status(p: pd.DataFrame) -> pd.DataFrame:
    """One row per major-A&E trust: how far it is from 82%, and whether last year's pace would get it there.

    The backtest showed that autumn trends are a weak guide to the following March, so this
    does not forecast. It asks a question that needs no forecast: is the improvement each trust
    still needs bigger or smaller than the improvement it actually achieved last year?
    """
    last = p["month"].max()
    year = window(p, last - pd.DateOffset(months=11), last)
    proj = project_march(p, last)
    march25 = p[p["month"] == "2025-03-01"].set_index("org_code")["pct_4h"]

    t = acute_trusts(p).set_index("org_code")
    t["march_2025_pct"] = march25
    t["march_2026_pct"] = proj["base_march_pct"]
    t["improvement_last_year_pts"] = t["march_2026_pct"] - t["march_2025_pct"]
    t["gap_to_82_pts"] = (TARGET_2027 - t["march_2026_pct"]).clip(lower=0)
    t["recent_3m_pct"] = proj["recent_3m_pct"]
    t["same_3m_last_year_pct"] = proj["same_3m_last_year_pct"]
    t["autumn_yoy_change_pts"] = proj["yoy_change_pts"]
    t["if_last_year_repeated_pct"] = t["march_2026_pct"] + t["improvement_last_year_pts"].clip(lower=0)
    t["met_78_in_march_2026"] = t["march_2026_pct"] >= TARGET_2026
    t["status"] = np.select(
        [t["march_2026_pct"] >= TARGET_2027,
         t["if_last_year_repeated_pct"] >= TARGET_2027],
        STATUS_ORDER[:2], STATUS_ORDER[2])
    t.loc[t["march_2026_pct"].isna() | t["march_2025_pct"].isna(), "status"] = STATUS_ORDER[3]
    for col in ["pct_4h", "pct_4h_type1", "type3_share", "trolley_per_100_adm", "admission_rate", "attendances"]:
        t[f"{col}_12m"] = year[col]
    t["rank_all_types"] = t["pct_4h_12m"].rank(ascending=False, method="min")
    t["rank_major_ae"] = t["pct_4h_type1_12m"].rank(ascending=False, method="min")
    return t.reset_index().sort_values("march_2026_pct", ascending=False)


def england_summary(e: pd.DataFrame, national: pd.DataFrame) -> dict:
    last = e["month"].max()
    prev = last - pd.DateOffset(years=1)
    cur, ly = e.set_index("month").loc[last], e.set_index("month").loc[prev]
    mar = e.set_index("month").loc[pd.Timestamp("2026-03-01")]
    return {
        "latest_month": last.strftime("%B %Y"),
        "latest_pct_4h": cur["pct_4h"],
        "same_month_last_year_pct_4h": ly["pct_4h"],
        "march_2026_pct_4h": mar["pct_4h"],
        "latest_type1_pct_4h": cur["pct_4h_type1"],
        "latest_trolley_waits_12h": int(cur["dta_12h_plus"]),
        "trolley_waits_change_pct": 100 * (cur["dta_12h_plus"] / ly["dta_12h_plus"] - 1),
        "attendances_latest": int(cur["attendances"]),
        "attendances_change_pct": 100 * (cur["attendances"] / ly["attendances"] - 1),
        "last_month_95pct_met": national.loc[national["pct_4h"] >= OLD_STANDARD, "month"].max().strftime("%B %Y"),
    }


def drivers(t: pd.DataFrame) -> pd.DataFrame:
    """Correlation of each trust's 12-month 4-hour performance with possible explanations."""
    cols = {
        "trolley_per_100_adm_12m": "12-hour trolley waits per 100 admissions (bed shortage)",
        "type3_share_12m": "Share of attendances at minor units / UTCs (case mix)",
        "admission_rate_12m": "Share of A&E patients admitted (patient acuity)",
        "attendances_12m": "Total attendances (size)",
    }
    return pd.DataFrame([
        {"factor": label,
         "corr_with_4h_all_types": t[c].corr(t["pct_4h_12m"]),
         "corr_with_4h_major_ae_only": t[c].corr(t["pct_4h_type1_12m"])}
        for c, label in cols.items()])


def region_summary(t: pd.DataFrame) -> pd.DataFrame:
    g = t.groupby("region")
    return pd.DataFrame({
        "trusts": g.size(),
        "met_78_march_2026": g["met_78_in_march_2026"].sum(),
        "already_82": g["status"].apply(lambda s: (s == STATUS_ORDER[0]).sum()),
        "reachable_at_last_years_pace": g["status"].apply(lambda s: (s == STATUS_ORDER[1]).sum()),
        "median_march_2026_pct": g["march_2026_pct"].median(),
        "median_trolley_per_100_adm": g["trolley_per_100_adm_12m"].median(),
    }).sort_values("median_march_2026_pct", ascending=False).reset_index()
