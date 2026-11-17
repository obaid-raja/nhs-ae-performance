import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from nhs import analysis as A
from nhs import data


def test_parse_period():
    assert data.parse_period("MSitAE-OCTOBER-2026") == pd.Timestamp("2026-10-01")
    assert data.parse_period(" MSitAE-march-2025 ") == pd.Timestamp("2025-03-01")


def _counts(**kw):
    base = {c: 0 for c in data.COLUMNS.values()}
    base.update(kw)
    return base


def test_four_hour_measure_includes_booked_and_all_types():
    d = data.add_measures(pd.DataFrame([_counts(att_t1=800, att_t1_booked=100, att_t3=100,
                                                over4_t1=180, over4_t1_booked=20)]))
    assert d["attendances"].iat[0] == 1000
    assert d["pct_4h"].iat[0] == pytest.approx(80.0)
    assert d["pct_4h_type1"].iat[0] == pytest.approx(100 * (1 - 200 / 900))


def _months(code, values, start="2025-03-01"):
    rows = []
    for i, (att, over) in enumerate(values):
        rows.append({"org_code": code, "org_name": code, "region": "R",
                     "month": pd.Timestamp(start) + pd.DateOffset(months=i),
                     **_counts(att_t1=att, over4_t1=over)})
    return data.add_measures(pd.DataFrame(rows))


def test_window_pools_counts_not_percentages():
    p = _months("X", [(1000, 100), (3000, 900)])
    w = A.window(p, "2025-03-01", "2025-04-01")
    assert w.loc["X", "pct_4h"] == pytest.approx(100 * (1 - 1000 / 4000))  # 75%, not the 80% mean


def test_status_rules():
    # 20 months from March 2025 to October 2026.
    def series(mar25, mar26):
        v = [(2000, 2000 * (1 - mar25 / 100))] + [(2000, 600)] * 11
        v += [(2000, 2000 * (1 - mar26 / 100))] + [(2000, 600)] * 7
        return v
    p = pd.concat([_months("A", series(80, 85)),   # already above 82
                   _months("B", series(74, 78)),   # +4 last year, needs +4 -> reachable
                   _months("C", series(75, 76))],  # +1 last year, needs +6 -> needs faster
                  ignore_index=True)
    t = A.target_status(p).set_index("org_code")
    assert t.loc["A", "status"] == "Already at 82%"
    assert t.loc["B", "status"] == "Reachable at last year's pace"
    assert t.loc["C", "status"] == "Needs faster improvement"
    assert t.loc["C", "gap_to_82_pts"] == pytest.approx(6)


def test_england_totals_match_published_series():
    if not (data.PROCESSED / "england_months.csv").exists():
        pytest.skip("processed data not built")
    e, n = data.load("england_months"), data.load("england_since_2010")
    m = e.merge(n, on="month", suffixes=("", "_pub"))
    assert len(m) == len(e)
    assert (m["pct_4h"] - m["pct_4h_pub"]).abs().max() < 0.05


def test_app_runs():
    at = AppTest.from_file("../app.py", default_timeout=60).run()
    assert not at.exception
    assert len(at.tabs) == 3
