"""Load NHS England's monthly A&E statistics (MSitAE) into tidy tables.

Source: NHS England, "A&E Attendances and Emergency Admissions"
https://www.england.nhs.uk/statistics/statistical-work-areas/ae-waiting-times-and-activity/
Licensed under the Open Government Licence v3.0.
"""
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
BASE_URL = ("https://www.england.nhs.uk/statistics/statistical-work-areas/ae-waiting-times-and-activity/"
            "ae-attendances-and-emergency-admissions-{year}/")
FINANCIAL_YEARS = ["2024-25", "2025-26", "2026-27"]

COLUMNS = {
    "A&E attendances Type 1": "att_t1",
    "A&E attendances Type 2": "att_t2",
    "A&E attendances Other A&E Department": "att_t3",
    "A&E attendances Booked Appointments Type 1": "att_t1_booked",
    "A&E attendances Booked Appointments Type 2": "att_t2_booked",
    "A&E attendances Booked Appointments Other Department": "att_t3_booked",
    "Attendances over 4hrs Type 1": "over4_t1",
    "Attendances over 4hrs Type 2": "over4_t2",
    "Attendances over 4hrs Other Department": "over4_t3",
    "Attendances over 4hrs Booked Appointments Type 1": "over4_t1_booked",
    "Attendances over 4hrs Booked Appointments Type 2": "over4_t2_booked",
    "Attendances over 4hrs Booked Appointments Other Department": "over4_t3_booked",
    "Patients who have waited 4-12 hs from DTA to admission": "dta_4_12h",
    "Patients who have waited 12+ hrs from DTA to admission": "dta_12h_plus",
    "Emergency admissions via A&E - Type 1": "adm_ae_t1",
    "Emergency admissions via A&E - Type 2": "adm_ae_t2",
    "Emergency admissions via A&E - Other A&E department": "adm_ae_t3",
    "Other emergency admissions": "adm_other",
}
MONTHS = {m: i for i, m in enumerate(
    ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST", "SEPTEMBER",
     "OCTOBER", "NOVEMBER", "DECEMBER"], start=1)}


def download() -> None:
    """Fetch every monthly provider-level CSV and the national time series from NHS England."""
    import urllib.request
    RAW.mkdir(parents=True, exist_ok=True)
    for fy in FINANCIAL_YEARS:
        html = urllib.request.urlopen(BASE_URL.format(year=fy)).read().decode("utf-8", "ignore")
        for url in sorted(set(re.findall(r'href="([^"]+\.csv)"', html))):
            path = RAW / url.rsplit("/", 1)[-1]
            if not path.exists():
                urllib.request.urlretrieve(url, path)


def parse_period(p: str) -> pd.Timestamp:
    """'MSitAE-OCTOBER-2026' -> 2026-10-01."""
    _, month, year = p.strip().split("-")
    return pd.Timestamp(int(year), MONTHS[month.upper()], 1)


def add_measures(df: pd.DataFrame) -> pd.DataFrame:
    """Derived measures, computed from counts so they can be re-aggregated correctly."""
    d = df.copy()
    d["attendances"] = d[[c for c in d if c.startswith("att_")]].sum(axis=1)
    d["over4"] = d[[c for c in d if c.startswith("over4_")]].sum(axis=1)
    d["att_type1"] = d["att_t1"] + d["att_t1_booked"]
    d["over4_type1"] = d["over4_t1"] + d["over4_t1_booked"]
    d["att_type3"] = d["att_t3"] + d["att_t3_booked"]
    d["adm_via_ae"] = d["adm_ae_t1"] + d["adm_ae_t2"] + d["adm_ae_t3"]
    d["pct_4h"] = 100 * (1 - d["over4"] / d["attendances"])
    d["pct_4h_type1"] = 100 * (1 - d["over4_type1"] / d["att_type1"])
    d["type3_share"] = 100 * d["att_type3"] / d["attendances"]
    # "Trolley waits": admitted patients who waited 12+ hours from the decision to admit
    # until they got a bed, per 100 emergency admissions through A&E.
    d["dta_12h_per_100_adm"] = 100 * d["dta_12h_plus"] / d["adm_via_ae"]
    d["admission_rate"] = 100 * d["adm_via_ae"] / d["attendances"]
    return d


def load_months() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (provider-month table, England-total-month table) from all monthly CSVs."""
    frames = []
    for f in sorted(RAW.glob("*.csv")):
        d = pd.read_csv(f)
        d = d[d["Period"].astype(str).str.match(r"^\s*MSitAE-[A-Za-z]+-\d{4}")]  # skip blank/footer rows
        d = d[["Period", "Org Code", "Parent Org", "Org name"] + list(COLUMNS)].rename(
            columns={"Org Code": "org_code", "Parent Org": "region", "Org name": "org_name", **COLUMNS})
        d["month"] = d["Period"].map(parse_period)
        frames.append(d.drop(columns="Period"))
    df = pd.concat(frames, ignore_index=True)
    # A month can be published, then revised: keep one file per month (the revised one if present).
    df = df.drop_duplicates(["month", "org_code"], keep="last")
    df["region"] = df["region"].str.replace("NHS ENGLAND ", "", regex=False).str.title()
    df["org_name"] = (df["org_name"].str.title().str.replace("Nhs", "NHS", regex=False)
                      .str.replace("'S ", "'s ", regex=False).str.replace(" And ", " and ", regex=False)
                      .str.replace(" Of ", " of ", regex=False).str.replace(" The ", " the ", regex=False))
    df["region"] = df["region"].str.replace(" And ", " and ", regex=False).str.replace(" Of ", " of ", regex=False)
    # Some months include an England "TOTAL" row and some don't: drop it and rebuild the total
    # from the providers, so every month is treated the same way.
    is_total = df["org_code"].str.upper().eq("TOTAL") | df["region"].str.upper().eq("TOTAL")
    df = df[~is_total]
    counts = list(COLUMNS.values())
    england = add_measures(df.groupby("month", as_index=False)[counts].sum())
    providers = add_measures(df).sort_values(["org_code", "month"]).reset_index(drop=True)
    return providers, england


def load_national() -> pd.DataFrame:
    """England 4-hour performance by month since November 2010 (NHS England time series)."""
    path = next(RAW.glob("Monthly-AE-Time-Series-*.xls"))
    p = pd.read_excel(path, sheet_name="Performance", header=13, engine="xlrd")
    p = p.rename(columns={"Period": "month", "Percentage in 4 hours or less (all)": "pct_4h",
                          "Percentage in 4 hours or less (type 1)": "pct_4h_type1"})
    p = p[pd.to_datetime(p["month"], errors="coerce").notna()][["month", "pct_4h", "pct_4h_type1"]]
    p["month"] = pd.to_datetime(p["month"])
    p[["pct_4h", "pct_4h_type1"]] = 100 * p[["pct_4h", "pct_4h_type1"]].astype(float)
    return p.reset_index(drop=True)


def build() -> None:
    providers, england = load_months()
    PROCESSED.mkdir(parents=True, exist_ok=True)
    providers.to_csv(PROCESSED / "provider_months.csv", index=False, float_format="%.3f")
    england.to_csv(PROCESSED / "england_months.csv", index=False, float_format="%.3f")
    load_national().to_csv(PROCESSED / "england_since_2010.csv", index=False, float_format="%.3f")


def load(name: str) -> pd.DataFrame:
    return pd.read_csv(PROCESSED / f"{name}.csv", parse_dates=["month"])
