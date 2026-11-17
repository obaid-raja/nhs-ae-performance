"""Static charts for the README. The interactive version is the Streamlit app."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np

from . import analysis as A

SURFACE, INK, INK_2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
STATUS_COLOURS = {A.STATUS_ORDER[0]: AQUA, A.STATUS_ORDER[1]: BLUE, A.STATUS_ORDER[2]: ORANGE}

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 10,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": AXIS,
    "axes.labelcolor": INK_2, "axes.titlecolor": INK, "axes.titlesize": 12,
    "axes.titleweight": "bold", "axes.titlelocation": "left",
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False,
    "savefig.dpi": 160, "savefig.bbox": "tight",
})
PCT = mtick.PercentFormatter(decimals=0)


def _yaxis(ax):
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)


def _target(ax, y, label, x):
    ax.axhline(y, color=INK_2, linewidth=1, linestyle=(0, (3, 3)))
    ax.text(x, y + 0.6, label, fontsize=8.5, color=INK_2)


def long_run(n, path):
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(n["month"], n["pct_4h"], color=BLUE, linewidth=2)
    x0 = n["month"].iat[0]
    import pandas as pd
    _target(ax, A.OLD_STANDARD, "95%: original standard, last met July 2015", pd.Timestamp("2016-06-01"))
    _target(ax, A.TARGET_2027, "82%: target for every trust by March 2027", x0)
    _target(ax, A.TARGET_2026, "78%: target for March 2026", x0)
    last = n.iloc[-1]
    ax.annotate(f"{last['pct_4h']:.1f}%\n{last['month']:%b %Y}", (last["month"], last["pct_4h"]),
                xytext=(6, -18), textcoords="offset points", fontsize=8.5, color=INK_2)
    ax.set_ylim(60, 100)
    ax.yaxis.set_major_formatter(PCT)
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _yaxis(ax)
    ax.set_title("England: share of A&E patients seen within 4 hours, 2010 to 2026")
    fig.savefig(path)
    plt.close(fig)


def trust_gaps(t, path):
    d = t.dropna(subset=["march_2026_pct"]).sort_values("march_2026_pct").reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(9, 4.6))
    for status, colour in STATUS_COLOURS.items():
        s = d[d["status"] == status]
        ax.bar(s.index, s["march_2026_pct"], 0.8, color=colour, label=f"{status} ({len(s)})")
    _target(ax, A.TARGET_2027, "82% target, March 2027", 1)
    _target(ax, A.TARGET_2026, "78% target, March 2026", 1)
    ax.set_xticks([])
    ax.set_xlim(-1, len(d))
    ax.set_ylim(40, 100)
    ax.yaxis.set_major_formatter(PCT)
    _yaxis(ax)
    ax.set_xlabel("120 NHS trusts with a major A&E, sorted by March 2026 performance")
    ax.legend(frameon=False, loc="upper left", labelcolor=INK_2, bbox_to_anchor=(0, 0.93))
    ax.set_title("March 2026 four-hour performance, and whether last year's pace reaches 82%")
    fig.savefig(path)
    plt.close(fig)


def trolley_waits(e, path):
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.bar(e["month"], e["dta_12h_plus"] / 1000, width=22, color=BLUE)
    peak = e.loc[e["dta_12h_plus"].idxmax()]
    last = e.iloc[-1]
    for row in (peak, last):
        ax.annotate(f"{row['dta_12h_plus'] / 1000:.1f}k", (row["month"], row["dta_12h_plus"] / 1000),
                    xytext=(0, 4), textcoords="offset points", ha="center", fontsize=8.5, color=INK_2)
    ax.yaxis.set_major_formatter(mtick.StrMethodFormatter("{x:.0f}k"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    _yaxis(ax)
    ax.set_title("Patients waiting 12+ hours for a bed after the decision to admit, England")
    fig.savefig(path)
    plt.close(fig)


def case_mix(t, path):
    d = t.dropna(subset=["type3_share_12m", "pct_4h_12m", "pct_4h_type1_12m"])
    boost = d["pct_4h_12m"] - d["pct_4h_type1_12m"]
    fig, ax = plt.subplots(figsize=(8, 4.4))
    ax.scatter(d["type3_share_12m"], boost, s=36, color=BLUE, edgecolor=SURFACE, linewidth=1.5)
    slope, icpt = np.polyfit(d["type3_share_12m"], boost, 1)
    xs = np.array([0, d["type3_share_12m"].max()])
    ax.plot(xs, icpt + slope * xs, color=INK_2, linewidth=1, linestyle=(0, (3, 3)))
    ax.xaxis.set_major_formatter(PCT)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"+{v:.0f} pts" if v > 0 else f"{v:.0f} pts"))
    _yaxis(ax)
    ax.set_xlabel("Share of a trust's attendances at minor injury units / urgent treatment centres")
    ax.set_ylabel("Headline score minus major-A&E score")
    ax.set_title("Minor-injury activity lifts a trust's headline 4-hour score (last 12 months)")
    fig.savefig(path)
    plt.close(fig)
