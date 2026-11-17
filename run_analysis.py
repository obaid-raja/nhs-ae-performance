"""Build the data, run the analysis and write tables and charts.

    python run_analysis.py              # from data/processed
    python run_analysis.py --download   # fetch the latest months from NHS England first
"""
import sys
from pathlib import Path

import pandas as pd

from nhs import analysis as A
from nhs import data, figures

OUT = Path(__file__).resolve().parent / "outputs"


def main(download: bool):
    if download:
        data.download()
    if download or not (data.PROCESSED / "provider_months.csv").exists():
        data.build()
    p, e, n = data.load("provider_months"), data.load("england_months"), data.load("england_since_2010")

    # Check: England totals rebuilt from the provider files must match NHS England's own series.
    check = e.merge(n, on="month", suffixes=("", "_published"))
    worst = (check["pct_4h"] - check["pct_4h_published"]).abs().max()
    assert worst < 0.05, f"England totals differ from the published series by {worst:.3f} pts"

    t = A.target_status(p)
    summary = A.england_summary(e, n)
    bt = A.backtest(p)
    drivers = A.drivers(t)
    regions = A.region_summary(t)

    (OUT / "tables").mkdir(parents=True, exist_ok=True)
    (OUT / "figures").mkdir(parents=True, exist_ok=True)
    t.to_csv(OUT / "tables" / "trust_target_status.csv", index=False, float_format="%.2f")
    regions.to_csv(OUT / "tables" / "region_summary.csv", index=False, float_format="%.2f")
    drivers.to_csv(OUT / "tables" / "drivers_correlations.csv", index=False, float_format="%.3f")
    pd.Series({**summary, **bt, "validation_max_diff_pts": worst}).to_csv(
        OUT / "tables" / "headline_numbers.csv", header=["value"])

    figures.long_run(n, OUT / "figures" / "1_long_run.png")
    figures.trust_gaps(t, OUT / "figures" / "2_trust_gaps.png")
    figures.trolley_waits(e, OUT / "figures" / "3_trolley_waits.png")
    figures.case_mix(t, OUT / "figures" / "4_case_mix.png")

    print(f"Validated against published England series: max difference {worst:.3f} pts")
    print(summary)
    print({k: round(v, 2) for k, v in bt.items()})
    print(t["status"].value_counts().to_string())
    print(regions.round(1).to_string(index=False))
    print(drivers.round(2).to_string(index=False))


if __name__ == "__main__":
    main("--download" in sys.argv)
