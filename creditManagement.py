from __future__ import annotations
import os
import re
import sys
import base64
import calendar
import datetime
import io
import json
import shutil
import tempfile
import traceback
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, html, dcc, Input, Output, State, ALL, ctx, no_update

def _project_root() -> Path:
    """Find the project root (folder with 3_env/0_tradingVE) upward — so every
    relative path works regardless of where the file lives on the drive."""
    here = Path(__file__).resolve()
    for base in [here.parent, *here.parents]:
        if (base / "3_env" / "designs.py").exists() or (base / "0_tradingVE").is_dir():
            return base
    return Path(r"S:\benjaminSuermann")


ROOT = _project_root()
sys.path.insert(0, str(ROOT / "3_env"))
import designs as ds

COL = {
    "bonds": {"id": "id", "nom": "nominal", "mv": ("market value", "value"),
              "dur": ("duration", "mod duration"),
              "dv01": "dv01", "dts": "duration times spread", "spread": "i spread",
              "oas": "oas", "spd": "spread per duration", "sector": " sector",
              "issuer": ("ultimate parent", "parent"), "rating": "rating", "ccy": "currency",
              "mat": "maturity", "seg": "segment", "rank": "rank", "conv": "convexity",
              "country": ("operation", "domicile"), "industry": " industry",
              "px5d": "5d px change", "px1m": "1m px change",
              "sp30": "30d i spread", "sp120": "120d i spread", "basis": " cds basis",
              "d2e": "debt to ebitda", "fcf": "fcf to total debt", "coupon": "coupon ",
              "quick": "quick ratio", "fcov": "fixed charge cov ratio"},
    "cds":   {"id": "id", "nom": "nominal", "mv": "market value", "dur": "duration",
              "cs01": "dv01", "spread": " cds par spread", "sector": " sector",
              "issuer": "ultimate parent", "rating": "rating", "ccy": "currency",
              "mat": "maturity", "px5d": "5d px change", "px1m": "1m px change",
              "spd": "spread per duration", "sp30": "30d i spread", "sp120": "120d i spread"},
    "swaps": {"id": "id", "ccy": "ccy", "mat": "maturity", "pay": ("Pay Rate (%)", "pay"),
              "rec": ("Rec Rate (%)", "rec"), "nom": ("Notional", "nominal"), "bpv": "bpv",
              "npv": "npv", "npv_t1": "npv t-1"},
    "futures": {"id": "id", "n": "contracts", "ccy": "ccy",
                "dv01": ("Zins-DV01 (€)", "dv01"), "dur": ("Eq. Duration", "dur")},
    "fx":    {"id": "id", "name": "name", "ccy": "ccy", "settle": ("Settlement", "maturity"),
              "px": ("Preis / Rate", "preis"), "typ": "Typ"},
}
NUM = {"nom", "mv", "dur", "dv01", "dts", "spread", "oas", "spd", "mat", "conv",
       "px5d", "px1m", "sp30", "sp120", "basis", "d2e", "fcf", "coupon",
       "cs01", "bpv", "pay", "rec", "n", "px", "quick", "fcov", "npv", "npv_t1"}
DATE_AS_TEXT = {("swaps", "mat"), ("fx", "settle")}

MAT_BUCKETS = [(0, 2, "0-2y"), (2, 4, "2-4y"), (4, 6, "4-6y"), (6, 8, "6-8y"),
               (8, 10, "8-10y"), (10, 15, "10-15y"), (15, 25, "15-25y"), (25, 99, "25y+")]
BUCKET_LABELS = [b[2] for b in MAT_BUCKETS]
RATING_ORDER = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-",
                "BB+", "BB", "BB-", "NR"]


def _bucket(y: float) -> str:
    for lo, hi, lbl in MAT_BUCKETS:
        if lo <= y < hi:
            return lbl
    return BUCKET_LABELS[-1]


# The Bloomberg export renames sheets (swaps→irs, futures→future …). Candidates per role,
# so the app finds the sheet tolerantly instead of failing on a fixed name.
SHEET_ALIASES = {"bonds": ("bonds",), "cds": ("cds",), "swaps": ("swaps", "irs"),
                 "futures": ("futures", "future"), "fx": ("fx",)}


def _pick_sheet(raw: dict, key: str) -> pd.DataFrame:
    lut = {str(k).strip().lower(): k for k in raw}
    for cand in SHEET_ALIASES.get(key, (key,)):
        hit = lut.get(cand.lower())
        if hit is not None and not raw[hit].empty:
            return raw[hit]
    return pd.DataFrame()


def load(path: str) -> dict[str, pd.DataFrame]:
    """Read all sheets, map to the internal schema, harden types, derive buckets."""
    raw = pd.read_excel(path, sheet_name=None)
    d: dict[str, pd.DataFrame] = {}
    for sheet, mapping in COL.items():
        src = _pick_sheet(raw, sheet)
        lut = {str(c).strip().lower(): c for c in src.columns}   # case-/whitespace-tolerant
        def pick(v, lut=lut, src=src):
            for n in (v,) if isinstance(v, str) else v:
                col = lut.get(str(n).strip().lower())
                if col is not None:
                    return src[col]
            return np.nan
        out = pd.DataFrame({k: pick(v) for k, v in mapping.items()})
        for c in out.columns.intersection(NUM):
            if (sheet, c) not in DATE_AS_TEXT:
                out[c] = pd.to_numeric(out[c], errors="coerce")
        d[sheet] = out

    b = d["bonds"].dropna(subset=["mv"]).copy()
    b["dv01"] = b["dv01"].fillna(b["dur"] * b["mv"] / 1e4)
    b["cs01"] = b["dv01"]                       # Proxy: Spread-Dur ≈ Dur (Fixkupon)
    b["bucket"] = b["mat"].apply(_bucket)
    b["dsp30"] = b["sp30"]        # Spalten sind bereits Δ-Spreads (bp)
    b["dsp120"] = b["sp120"]

    c = d["cds"].dropna(subset=["nom"]).copy()
    c["bucket"] = c["mat"].fillna(0).apply(_bucket)
    c["dsp30"] = c["sp30"]
    c["dsp120"] = c["sp120"]

    s = d["swaps"].dropna(subset=["bpv"]).copy()
    s["mat_y"] = (pd.to_datetime(s["mat"], format="%d.%m.%Y", errors="coerce")
                  - pd.Timestamp.today()).dt.days / 365.25
    s["bucket"] = s["mat_y"].fillna(0).apply(_bucket)

    f = d["futures"].dropna(subset=["dv01"]).copy()
    f["bucket"] = f["dur"].fillna(0).apply(_bucket)

    d.update(bonds=b, cds=c, swaps=s, futures=f)
    return d


def metrics(d: dict[str, pd.DataFrame]) -> dict:
    """Portfolio KPIs for the header."""
    b, c, s, f = d["bonds"], d["cds"], d["swaps"], d["futures"]
    mv = b["mv"].sum()
    w = b["mv"] / mv
    ir_long = b["dv01"].sum() + f.loc[f["dv01"] > 0, "dv01"].sum()
    ir_hedge = s["bpv"].sum() + f.loc[f["dv01"] < 0, "dv01"].sum()
    return dict(
        mv=mv, n_bonds=len(b), n_cds=len(c), n_swaps=len(s),
        ir_long=ir_long, ir_hedge=ir_hedge, ir_net=ir_long + ir_hedge,
        hedge_ratio=-ir_hedge / ir_long if ir_long else 0.0,
        cs01=b["cs01"].sum() + c["cs01"].sum(),
        cs01_bonds=b["cs01"].sum(), cs01_cds=c["cs01"].sum(),
        dur_gross=float((b["dur"] * w).sum()),
        dur_net=float((ir_long + ir_hedge) / mv * 1e4),
        spread_avg=float((b["spread"] * w).sum()),
        oas_avg=float((b["oas"] * w).sum()),
        dts=float((b["dts"] * w).sum()),
        wam=float((b["mat"] * w).sum()),
        conv=float((b["conv"] * w).sum()),
        coupon=float((b["coupon"] * w).sum()) * 100,
        spd=float((b["spd"] * w).sum()),
        spread_mv=float((b["spread"] * b["mv"]).sum()),      # Σ iSpread·MV (bp·€) → /NAV = bond spread carry
        cds_prem=float((c["spread"] * c["nom"]).sum()),      # Σ cdsSpread·notional (signed) → net CDS premium
        fx_mv=float(b.loc[b["ccy"] != "EUR", "mv"].sum()),
        fv=float(b["nom"].sum()),
        cds_notional=float(c["nom"].sum()),
        credit_heat=float(mv + c["nom"].sum()),
    )


def fund_facts(path: str) -> dict:
    """Fund-level data from the KVG fact-sheet tab (ui / Übersicht / Vermögensübersicht):
    NAV, cash, gross fund assets, accrued interest, VaR. Tab name is searched tolerantly,
    values are label-based — if the tab or a label is missing, that value is simply omitted."""
    try:
        allsheets = pd.read_excel(path, sheet_name=None, header=None)
    except Exception:
        return {}
    lut = {str(k).strip().lower(): k for k in allsheets}
    key = next((lut[c] for c in ("ui", "übersicht", "uebersicht", "overview",
                                 "vermögensübersicht", "vermoegensuebersicht") if c in lut), None)
    if key is None:
        return {}
    rows = allsheets[key].values.tolist()

    def _num(x):
        v = pd.to_numeric(x, errors="coerce")
        return None if pd.isna(v) else float(v)

    def find(label, exact=False):
        lab = label.strip().lower()
        for r in rows:
            for j, c in enumerate(r):
                cl = ("" if pd.isna(c) else str(c)).strip().lower()
                if (cl == lab) if exact else (lab in cl):
                    for k in range(j + 1, len(r)):
                        v = _num(r[k])
                        if v is not None:
                            return v
        return None

    asof = None
    for r in rows:
        for c in r:
            s = "" if pd.isna(c) else str(c)
            if "ewertungsdatum" in s.lower():
                mo = re.search(r"\d{2}\.\d{2}\.\d{4}", s)
                if mo:
                    asof = mo.group(0)
    out = {"nav": find("fondsvermögen", exact=True), "cash": find("bankguthaben"),
           "gross": find("summe aktiva"), "accrued": find("zins- und dividenden"),
           "renten": find("renten"), "var_fonds": find("fonds", exact=True),
           "var_util": find("var-auslastung"), "var_limit": find("marktrisikolimit"),
           "asof": asof}
    return {k: v for k, v in out.items() if v is not None}


def ladder(d: dict[str, pd.DataFrame], kind: str) -> pd.DataFrame:
    """DV01 / CS01 profile per maturity bucket across all instruments."""
    g = lambda df, col: df.groupby("bucket")[col].sum().reindex(BUCKET_LABELS).fillna(0)
    if kind == "ir":
        out = pd.DataFrame({"Bonds": g(d["bonds"], "dv01"),
                            "Swaps": g(d["swaps"], "bpv"),
                            "Futures": g(d["futures"], "dv01")})
    else:
        out = pd.DataFrame({"Bonds": g(d["bonds"], "cs01"),
                            "CDS": g(d["cds"], "cs01")})
    out["Netto"] = out.sum(axis=1)
    return out


# Explorer config (dropdown chart): metric × dimension
EXPLORER_METRICS = {
    "Market Value (€M)":   ("mv",     "sum",  1e-6),
    "Rate DV01 (€/bp)":    ("dv01",   "sum",  1.0),
    "CS01 (€/bp)":         ("cs01",   "sum",  1.0),
    "Avg I-Spread MVw (bp)": ("spread", "wavg", 1.0),
    "Avg Duration MVw (y)":  ("dur",    "wavg", 1.0),
    "Avg Carry Eff. (bp/y)": ("spd",    "wavg", 1.0),
}
EXPLORER_DIMS = {"Sector": "sector", "Rating": "rating", "Maturity": "bucket",
                 "Currency": "ccy", "Rank": "rank", "Segment": "seg"}


def explore(b: pd.DataFrame, metric: str, dim: str) -> pd.Series:
    """Explorer aggregation: sum or MV-weighted average."""
    col, how, scale = EXPLORER_METRICS[metric]
    dcol = EXPLORER_DIMS[dim]
    if how == "sum":
        out = b.groupby(dcol)[col].sum() * scale
    else:
        out = b.groupby(dcol).apply(
            lambda g: np.average(g[col], weights=g["mv"]), include_groups=False) * scale
    if dcol == "bucket":
        out = out.reindex(BUCKET_LABELS).dropna()
    elif dcol == "rating":
        out = out.reindex([r for r in RATING_ORDER if r in out.index])
    else:
        out = out.sort_values(ascending=False)
    return out


POS_TYPES = ["Bond", "CDS", "IRS", "Future", "FX"]


def positions(d: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """All instruments in one shared position table (filterable by type)."""
    b, c, s, f, fx = d["bonds"], d["cds"], d["swaps"], d["futures"], d["fx"]
    frames = [
        pd.DataFrame({"Type": "Bond", "id": b["id"], "Name": b["issuer"], "Sector": b["sector"],
                      "Rtg": b["rating"], "Ccy": b["ccy"], "Mat": b["mat"], "Nominal": b["nom"],
                      "MV": b["mv"], "Dur": b["dur"], "DV01/BPV": b["dv01"], "Spread": b["spread"]}),
        pd.DataFrame({"Type": "CDS", "id": c["id"], "Name": c["issuer"], "Sector": c["sector"],
                      "Rtg": c["rating"], "Ccy": c["ccy"], "Mat": c["mat"], "Nominal": c["nom"],
                      "MV": c["mv"], "Dur": c["dur"], "DV01/BPV": c["cs01"], "Spread": c["spread"]}),
        pd.DataFrame({"Type": "IRS", "id": s["id"], "Name": s["ccy"].astype(str) + " Payer",
                      "Ccy": s["ccy"], "Mat": s["mat_y"], "Nominal": s["nom"], "DV01/BPV": s["bpv"]}),
    ]
    if len(f):
        frames.append(pd.DataFrame({"Type": "Future", "id": f["id"], "Ccy": f["ccy"],
                                    "Dur": f["dur"], "DV01/BPV": f["dv01"]}))
    if len(fx):
        frames.append(pd.DataFrame({"Type": "FX", "id": fx["id"], "Name": fx["name"],
                                    "Ccy": fx["ccy"]}))
    return pd.concat(frames, ignore_index=True)


def pnl_projection(d: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Simplified 1-day market-value projection per instrument type (T-1 · T0 · T+1).
    Bonds/CDS: daily return ≈ 5-day price change / 5. Swaps: market value (NPV),
    daily change = NPV − NPV(T-1). Futures: MtM-neutral. No market scenario."""
    rows = []
    def price_leg(name, df):
        r = (df["px5d"] / 5 / 100).fillna(0)
        mv0 = df["mv"].fillna(0)
        m1, p1 = mv0 / (1 + r), mv0 * (1 + r)
        rows.append(dict(Instrument=name, mv_m1=m1.sum(), mv0=mv0.sum(), mv_p1=p1.sum(),
                         pnl_real=(mv0 - m1).sum(), pnl_proj=(p1 - mv0).sum()))
    price_leg("Bonds", d["bonds"])
    price_leg("CDS", d["cds"])
    s = d["swaps"]                                    # Swaps über Marktwert (NPV), nicht Nominal
    npv0 = s["npv"].fillna(0) if "npv" in s.columns else pd.Series(0.0, index=s.index)
    npv1 = s["npv_t1"].fillna(npv0) if "npv_t1" in s.columns else npv0
    rows.append(dict(Instrument="Swaps", mv_m1=float(npv1.sum()), mv0=float(npv0.sum()),
                     mv_p1=float(npv0.sum()), pnl_real=float((npv0 - npv1).sum()), pnl_proj=0.0))
    if len(d["futures"]):
        rows.append(dict(Instrument="Futures", mv_m1=0.0, mv0=0.0, mv_p1=0.0,
                         pnl_real=0.0, pnl_proj=0.0))
    out = pd.DataFrame(rows)
    tot = out.drop(columns="Instrument").sum()
    tot["Instrument"] = "Total"
    return pd.concat([out, tot.to_frame().T[out.columns]], ignore_index=True)


# ── Credit source: cash bonds, CDS or both (for all credit charts) ──────────
CREDIT_SRC = ["Bonds", "CDS", "Both"]


def credit_view(d: dict[str, pd.DataFrame], source: str) -> pd.DataFrame:
    if source == "Bonds":
        return d["bonds"]
    if source == "CDS":
        return d["cds"]
    return pd.concat([d["bonds"], d["cds"]], ignore_index=True)


# ── Allocation: guidelines, ESG exclusions, fundamental screen ─────────────
IG_PREFIX = ("AAA", "AA", "A", "BBB")


def _is_ig(r) -> bool:
    return str(r).strip().upper().startswith(IG_PREFIX)


def guideline_check(d: dict[str, pd.DataFrame], m: dict) -> pd.DataFrame:
    """Guideline compliance of the defensive Art. 8+ retail fund (cash book)."""
    b = d["bonds"]
    mv = b["mv"].sum()
    sub_ig = b.loc[~b["rating"].apply(_is_ig), "mv"].sum() / mv
    bbb = b.loc[b["rating"].astype(str).str.upper().str.startswith("BBB"), "mv"].sum() / mv
    cds_lev = d["cds"]["nom"].sum() / mv
    fx, dur = m["fx_mv"] / m["mv"], m["dur_net"]
    rows = [
        ("Sub-IG quota (< BBB-)", f"{sub_ig:.1%}", "< 10%", sub_ig < 0.10),
        ("Triple-B quota (BBB)", f"{bbb:.1%}", "≤ 40%", bbb <= 0.40),
        ("Net duration", f"{dur:.2f} y", "−1 to 3 y", -1 <= dur <= 3),
        ("CDS leverage (notional/MV)", f"{cds_lev:.1%}", "≤ 50%", cds_lev <= 0.50),
        ("FX ≠ EUR", f"{fx:.1%}", "< 5%", fx < 0.05),
    ]
    return pd.DataFrame([dict(Guideline=n, Actual=v, Limit=l,
                              Status="OK" if ok else "Breach") for n, v, l, ok in rows])


ESG_EXCLUSIONS = [
    ("Controversial weapons", "any involvement"),
    ("Conventional weapons", "> 10% revenue"),
    ("Thermal coal", "> 30% revenue"),
    ("Tobacco", "> 5% revenue"),
    ("UN Global Compact", "violation (Fail)"),
    ("Sovereigns (Freedom House)", "“Not Free”"),
    ("Controversies", "case flag “Red”"),
    ("ESG rating (MSCI)", "CCC or B"),
]

FUND_RULES = [("d2e", ">", 5.0), ("fcf", "<", 0.0), ("quick", "<", 0.5), ("fcov", "<", 2.0)]


def fundamental_screen(d: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Balance-sheet quality per bond; counts breached thresholds (where data exists)."""
    b = d["bonds"]
    flags = pd.Series(0, index=b.index)
    for col, op, thr in FUND_RULES:
        hit = (b[col] > thr) if op == ">" else (b[col] < thr)
        flags = flags + hit.fillna(False).astype(int)
    return pd.DataFrame({
        "Issuer": b["issuer"], "Sector": b["sector"], "Rtg": b["rating"],
        "MV(M)": b["mv"] / 1e6, "ND/EBITDA": b["d2e"], "FCF/Debt": b["fcf"],
        "Quick": b["quick"], "FCC": b["fcov"], "Flags": flags,
    }).sort_values(["Flags", "MV(M)"], ascending=[False, False])


# ── Reporting: allocations net, in % of fund volume (fact-sheet style) ───────
# Static reference data (not in the risk export) — maintained here centrally.
FUND_META = {"name": "nordIX Anleihen Defensiv I", "isin": "DE000A2DKRH6",
             "company": "nordIX AG", "benchmark": "—", "inception": "08.03.2017", "ter": "0.67%"}
COUNTRY_NAMES = {"DE": "Germany", "FR": "France", "NL": "Netherlands", "US": "USA",
    "GB": "United Kingdom", "LU": "Luxembourg", "SE": "Sweden", "AU": "Australia", "IE": "Ireland",
    "AT": "Austria", "CH": "Switzerland", "DK": "Denmark", "FI": "Finland", "NO": "Norway",
    "CA": "Canada", "JP": "Japan", "CZ": "Czechia", "IS": "Iceland", "AE": "UAE", "MX": "Mexico",
    "CL": "Chile", "ES": "Spain", "IT": "Italy", "BE": "Belgium", "IL": "Israel", "PL": "Poland"}


def _gov_mask(df: pd.DataFrame) -> pd.Series:
    return df["seg"].astype(str).str.strip().str.lower().eq("govt")


def avg_rating(b: pd.DataFrame) -> str:
    """MV-weighted average rating as a notch, mapped back onto the rating scale."""
    m = {r: i for i, r in enumerate(RATING_ORDER)}
    notch = b["rating"].astype(str).str.strip().str.upper().map(m)
    ok = notch.notna() & b["mv"].notna()
    if not ok.any():
        return "NR"
    avg = float((notch[ok] * b["mv"][ok]).sum() / b["mv"][ok].sum())
    return RATING_ORDER[min(len(RATING_ORDER) - 1, max(0, round(avg)))]


def _with_total(out: pd.DataFrame, name: str) -> pd.DataFrame:
    tot = {name: "Σ Total", "Sovereign": round(out["Sovereign"].sum(), 2),
           "Credit": round(out["Credit"].sum(), 2), "Total": round(out["Total"].sum(), 2)}
    return pd.concat([out, pd.DataFrame([tot])], ignore_index=True)


def alloc_split(df: pd.DataFrame, by: str, nav: float, name: str, order=None,
                top: int | None = None, mapper: dict | None = None) -> pd.DataFrame:
    """Allocation per group (by), split sovereign vs. credit, net in % of NAV."""
    d = df.dropna(subset=[by, "mv"]).copy()
    key = d[by].astype(str).str.strip()
    d["_k"] = key.map(lambda x: mapper.get(x, x)) if mapper else key
    g = d[_gov_mask(d)].groupby("_k")["mv"].sum() / nav * 100
    c = d[~_gov_mask(d)].groupby("_k")["mv"].sum() / nav * 100
    out = pd.DataFrame({"Sovereign": g, "Credit": c}).fillna(0.0)
    out["Total"] = out["Sovereign"] + out["Credit"]
    idx = order or list(out.sort_values("Total", ascending=False).index)
    out = out.reindex([x for x in idx if x in out.index])
    out = out[out["Total"] > 0.005].round(2)
    if top:
        out = out.head(top)
    return _with_total(out.reset_index().rename(columns={"_k": name}), name)


def alloc_assetclass(d: dict[str, pd.DataFrame], nav: float, cash: float | None) -> pd.DataFrame:
    """Coarse asset-class split sovereign/credit/cash/other in % of NAV."""
    b = d["bonds"]
    gov = float(b[_gov_mask(b)]["mv"].sum() / nav * 100)
    cred = float(b[~_gov_mask(b)]["mv"].sum() / nav * 100)
    csh = float((cash or 0) / nav * 100)
    rest = max(0.0, 100.0 - gov - cred - csh)
    rows = [("Sovereign bonds", round(gov, 2)), ("Corporate bonds (credit)", round(cred, 2)),
            ("Cash / bank balance", round(csh, 2)), ("Other (swaps, receiv./payab.)", round(rest, 2)),
            ("Σ Total", round(gov + cred + csh + rest, 2))]
    return pd.DataFrame(rows, columns=["Asset class", "Share"])


# Marktkurven-Spalten → (interner Key, Label, Theme-Farbe, Dash). Ein Blatt reicht;
# _curve_key() matcht echte Bloomberg-Überschriften (EUR midswap/ESTR/SOFR) tolerant.
CURVE_SPECS = [("swap", "EUR-Swapkurve", "primary", None), ("estr", "EUR ESTR OIS", "secondary", "dash"),
               ("sofr", "USD SOFR OIS", "highlight", "dot"), ("bund", "Bund-Kurve", "secondary", "dash"),
               ("govie", "Govie-Kurve", "secondary", "dash")]


def _curve_key(col: str):
    cl = str(col).strip().lower()
    if cl == "tenor" or cl.startswith("tenor") or "laufzeit" in cl or cl in ("years", "jahre"):
        return "tenor"
    if "sofr" in cl:
        return "sofr"
    if "estr" in cl or "ester" in cl or "€str" in cl:
        return "estr"
    if "bund" in cl:
        return "bund"
    if "govie" in cl or "govt" in cl:
        return "govie"
    if "midswap" in cl or "swap" in cl:
        return "swap"
    return None


def load_curves(path: str):
    """Market curves from sheet 'curves' or 'market' (tenor + swap/ESTR/SOFR/bund).
    Tolerant of title rows and real Bloomberg headers; if all is missing,
    the chart falls back to the fund-book rates."""
    try:
        raw = pd.read_excel(path, sheet_name=None, header=None)
    except Exception:
        return None
    lut = {str(k).strip().lower(): k for k in raw}
    key = next((lut[c] for c in ("curves", "market", "kurven", "swap-kurven") if c in lut), None)
    if key is None:
        return None
    df = raw[key]
    hdr = next((i for i in range(min(len(df), 10))
                if any(_curve_key(v) == "tenor" for v in df.iloc[i].tolist())), None)
    if hdr is None:
        return None
    ren = {j: _curve_key(v) for j, v in enumerate(df.iloc[hdr].tolist()) if _curve_key(v)}
    body = df.iloc[hdr + 1:, list(ren)].copy()
    body.columns = list(ren.values())
    if "tenor" not in body.columns:
        return None
    for c in body.columns:
        body[c] = pd.to_numeric(body[c], errors="coerce")
    return body.dropna(subset=["tenor"]).sort_values("tenor").reset_index(drop=True)


# ── Time-series store: one daily headline snapshot, upserted by date ─────────
SNAPSHOT_STORE = ROOT / "_creditManagementData.csv"
SNAPSHOT_FIELDS = ["nav", "cash", "gross", "accrued", "mv", "credit_heat", "cds_notional", "fv",
                   "fx_mv", "ir_long", "ir_hedge", "ir_net", "cs01", "cs01_bonds", "cs01_cds",
                   "dur_net", "dur_gross", "wam", "conv", "spread_avg", "oas_avg", "dts", "spd",
                   "coupon", "hedge_ratio", "var_util", "pnl_real", "n_bonds", "n_cds", "n_swaps"]


def _asof_iso(facts: dict) -> str:
    """Normalise the KVG as-of date (DD.MM.YYYY) to ISO; fall back to today."""
    raw = facts.get("asof")
    d = pd.to_datetime(raw, format="%d.%m.%Y", errors="coerce") if raw else None
    return (d if d is not None and not pd.isna(d) else pd.Timestamp.today()).strftime("%Y-%m-%d")


def snapshot_row(m: dict, facts: dict, nav: float, pnl: pd.DataFrame) -> dict:
    """Flat daily record of headline fund metrics for the time series."""
    real = pnl.loc[pnl["Instrument"] == "Total", "pnl_real"]
    row = {"date": _asof_iso(facts), "nav": nav, "cash": facts.get("cash"),
           "gross": facts.get("gross"), "accrued": facts.get("accrued"), "var_util": facts.get("var_util"),
           "pnl_real": float(real.iloc[0]) if len(real) else None}
    for k in SNAPSHOT_FIELDS:
        row.setdefault(k, m.get(k))
    return row


def save_snapshot(row: dict) -> None:
    """Upsert today's snapshot into the CSV store (keyed by date); never raises."""
    try:
        old = pd.read_csv(SNAPSHOT_STORE) if SNAPSHOT_STORE.exists() else pd.DataFrame()
        if "date" in old.columns:
            old = old[old["date"].astype(str) != row["date"]]
        out = pd.concat([old, pd.DataFrame([row])], ignore_index=True).sort_values("date")
        out.to_csv(SNAPSHOT_STORE, index=False)
    except Exception as ex:
        print(f"[store] snapshot save failed: {ex}")


def load_history() -> pd.DataFrame:
    """Full snapshot history (empty frame if the store is missing/unreadable)."""
    try:
        if SNAPSHOT_STORE.exists():
            return pd.read_csv(SNAPSHOT_STORE, parse_dates=["date"]).sort_values("date")
    except Exception:
        pass
    return pd.DataFrame()
# ══ End of data layer ═════════════════════════════════════════════════════════

PORTFOLIO_DIR = ROOT / "0_tradingVE" / "0_portfolios"


def _resolve_xlsx(name: str) -> str:
    """Respect a full path; look up a bare file name in the portfolio folder."""
    p = Path(name)
    return str(p if p.is_file() else PORTFOLIO_DIR / p.name)


XLSX = _resolve_xlsx(sys.argv[1] if len(sys.argv) > 1 else "nad.xlsx")
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8050


def _empty_book() -> dict[str, pd.DataFrame]:
    """Schema-complete empty book so all aggregations run without a crash on a
    missing/broken file (the values are not shown in that case anyway)."""
    schema = {
        "bonds": ["id", "mv", "dv01", "dur", "cs01", "dts", "spread", "oas", "conv", "mat",
                  "coupon", "spd", "ccy", "nom", "sector", "issuer", "rating", "seg", "rank",
                  "bucket", "dsp30", "dsp120", "px5d", "px1m", "sp30", "sp120", "basis",
                  "d2e", "fcf", "quick", "fcov", "country", "industry"],
        "cds": ["id", "nom", "mv", "cs01", "dur", "sector", "issuer", "rating", "ccy", "mat",
                "bucket", "dsp30", "dsp120", "spread", "spd", "sp30", "sp120", "px5d", "px1m"],
        "swaps": ["id", "bpv", "nom", "mat", "mat_y", "bucket", "pay", "rec", "ccy"],
        "futures": ["id", "dv01", "dur", "bucket", "ccy"],
        "fx": ["id", "name", "ccy"],
    }
    return {k: pd.DataFrame({c: pd.Series(dtype="float64") for c in cols})
            for k, cols in schema.items()}


# Portfolio load is guarded: a missing/broken nad.xlsx must not kill the app.
# Markets/Admin keep working; the Portfolio tabs then show a clear message.
try:
    D = load(XLSX)
    PORTFOLIO_OK, PORTFOLIO_ERR = True, ""
except Exception as _pf_ex:
    import traceback as _tb
    _tb.print_exc()
    D, PORTFOLIO_OK, PORTFOLIO_ERR = _empty_book(), False, str(_pf_ex)

M = metrics(D)
B = D["bonds"]

FACTS = fund_facts(XLSX)                 # Fonds-Ebene aus Blatt 'ui'/'Übersicht'
NAV = FACTS.get("nav") or M["mv"] or 1.0  # Bezugsbasis; Fallback Bond-MV, dann 1.0
if pd.isna(NAV) or NAV == 0:
    NAV = 1.0
CASH = FACTS.get("cash")

CURVES = load_curves(XLSX)
_CV_NOTE = (("Left axis: EUR swap curve from the Excel sheet (real market curve). "
             if (CURVES is not None and "swap" in CURVES.columns) else
             "Left axis: swap fixed rates from the fund book (approx.). Add a 'curves'/'market' sheet "
             "with columns tenor + swap (via Bloomberg =BDH) to plot the real EUR curve. ")
            + "Right axis: portfolio I-spread, MV-weighted per maturity bucket.")

POS = positions(D)
POS_VIEW = POS.assign(**{"Nom(M)": POS["Nominal"] / 1e6, "MV(M)": POS["MV"] / 1e6}).round(
    {"Mat": 1, "Nom(M)": 2, "MV(M)": 2, "Dur": 2, "DV01/BPV": 0, "Spread": 0})
POS_COLS = ["Type", "id", "Name", "Sector", "Rtg", "Ccy", "Mat", "Nom(M)", "MV(M)",
            "Dur", "DV01/BPV", "Spread"]

def eur(v: float, sign: bool = False) -> str:
    """Institutionelle Kurzform: 32.4 MM EUR / 400 TEUR / 950 EUR."""
    a = abs(float(v))
    pre = ("+" if v > 0 else "-" if v < 0 else "") if sign else ("-" if v < 0 else "")
    if a >= 1e6:
        return f"{pre}{a/1e6:.1f} MM EUR"
    if a >= 1e3:
        return f"{pre}{a/1e3:,.0f} TEUR".replace(",", " ")
    return f"{pre}{a:,.0f} EUR".replace(",", " ")


PNL = pnl_projection(D)
# Display in institutional short form (MM EUR / TEUR); plus hidden raw-€
# columns (…_n) purely for numeric traffic-light colouring of the PnL columns.
PNL_DISP = PNL.assign(
    mv_m1=PNL["mv_m1"].apply(eur), mv0=PNL["mv0"].apply(eur), mv_p1=PNL["mv_p1"].apply(eur),
    pnl_real=PNL["pnl_real"].apply(lambda v: eur(v, sign=True)),
    pnl_proj=PNL["pnl_proj"].apply(lambda v: eur(v, sign=True)),
    pnl_real_n=pd.to_numeric(PNL["pnl_real"], errors="coerce").round(0),
    pnl_proj_n=pd.to_numeric(PNL["pnl_proj"], errors="coerce").round(0))
PNL_COLS = [("Instrument", "Instrument"), ("mv_m1", "MV T-1"), ("mv0", "MV T0"),
            ("mv_p1", "MV T+1"), ("pnl_real", "PnL T-1→T0"), ("pnl_proj", "PnL T0→T+1")]
PNL_COND = ([{"if": {"filter_query": f"{{{n}}} < 0", "column_id": c},
              "color": ds.COLORS["negative"]} for c, n in
             (("pnl_real", "pnl_real_n"), ("pnl_proj", "pnl_proj_n"))]
            + [{"if": {"filter_query": f"{{{n}}} > 0", "column_id": c},
                "color": ds.COLORS["primary"]} for c, n in
               (("pnl_real", "pnl_real_n"), ("pnl_proj", "pnl_proj_n"))]
            + [{"if": {"filter_query": '{Instrument} = Total'}, "fontWeight": 700}])

GUIDE = guideline_check(D, M)
GUIDE_COND = [{"if": {"filter_query": '{Status} = Breach', "column_id": "Status"},
               "color": ds.COLORS["negative"], "fontWeight": 700},
              {"if": {"filter_query": '{Status} = OK', "column_id": "Status"},
               "color": ds.COLORS["primary"], "fontWeight": 700}]

FUND = fundamental_screen(D).round(
    {"MV(M)": 2, "ND/EBITDA": 2, "FCF/Debt": 3, "Quick": 2, "FCC": 2})
FUND_COLS = ["Issuer", "Sector", "Rtg", "MV(M)", "ND/EBITDA", "FCF/Debt", "Quick", "FCC", "Flags"]
FUND_COND = [{"if": {"filter_query": q, "column_id": c}, "color": ds.COLORS["negative"]}
             for q, c in [("{ND/EBITDA} > 5", "ND/EBITDA"), ("{FCF/Debt} < 0", "FCF/Debt"),
                          ("{Quick} < 0.5", "Quick"), ("{FCC} < 2", "FCC")]
             ] + [{"if": {"filter_query": "{Flags} > 0", "column_id": "Flags"},
                   "color": ds.COLORS["negative"], "fontWeight": 700}]

SECTORS = sorted(set(B["sector"].dropna()) | set(D["cds"]["sector"].dropna()))
SECTOR_COLOR = {s: ds.CHART_PALETTE[i % len(ds.CHART_PALETTE)] for i, s in enumerate(SECTORS)}
DIVERGING = [[0, ds.HEX["negative"]], [0.5, ds.HEX["surface"]], [1, ds.HEX["positive"]]]
SEQUENTIAL = [[0, ds.HEX["surface"]], [1, ds.HEX["primary"]]]

if PORTFOLIO_OK:                        # record today's snapshot for the time series
    save_snapshot(snapshot_row(M, FACTS, NAV, PNL))
HISTORY = load_history()


# ── UI building blocks (build on the theme, do not change it) ───────────────
def stat(label: str, value: str, sub: str = "", accent: str | None = None):
    ac = accent or ds.COLORS["primary"]
    return html.Div([
        html.Div(label, style=ds.LABEL_STYLE),
        html.Div(value, style={"fontFamily": ds.FONT.get("numeric", ds.FONT["family"]),
                               "fontWeight": 500, "fontSize": "26px", "color": ds.COLORS["text"],
                               "marginTop": "7px", "lineHeight": 1.05, "letterSpacing": "-0.02em",
                               "fontVariantNumeric": "tabular-nums"}),
        html.Div(sub, style={**ds.LABEL_STYLE, "textTransform": "none",
                             "letterSpacing": 0, "marginTop": "6px", "opacity": 0.9}),
    ], className="stat-card", style={**ds.CARD_STYLE, "flex": "1", "minWidth": "158px",
              "padding": "15px 17px", "position": "relative",
              "borderLeft": f"3px solid {ac}",
              "boxShadow": "0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.05)",
              "transition": "box-shadow .18s ease, transform .18s ease"})


def chart(fig, cid: str):
    return dcc.Graph(id=cid, figure=fig, config={"displaylogo": False})


def legend_right(fig):
    """Titel top-left, Legende top-right — vermeidet Überlappung im Theme-Layout."""
    return fig.update_layout(legend=dict(orientation="h", y=1.14, x=1, xanchor="right"))


TAB_STYLE = {"fontFamily": ds.FONT["family"], "fontSize": "13px", "padding": "9px 18px",
             "background": ds.COLORS["surface"], "border": f"1px solid {ds.COLORS['border']}",
             "color": ds.COLORS["text"]}
TAB_SELECTED = {**TAB_STYLE, "background": ds.COLORS["primary"], "color": "#FFF",
                "borderColor": ds.COLORS["primary"], "fontWeight": 600}

TOPTAB_STYLE = {"fontFamily": ds.FONT["family"], "fontSize": "15px", "fontWeight": 600,
                "padding": "12px 28px", "background": ds.COLORS["background"], "border": "none",
                "borderBottom": f"2px solid {ds.COLORS['border']}", "color": ds.COLORS["secondary"]}
TOPTAB_SELECTED = {**TOPTAB_STYLE, "color": ds.COLORS["primary"],
                   "borderBottom": f"3px solid {ds.COLORS['primary']}"}


def fmt(v: float, dec: int = 0) -> str:
    return f"{v:,.{dec}f}".replace(",", "\u2009")


# ── Standard-Charts ─────────────────────────────────────────────────────────
def fig_ladder_ir():
    L = ladder(D, "ir")
    fig = go.Figure()
    for col, color in [("Bonds", ds.HEX["primary"]), ("Swaps", ds.HEX["negative"]),
                       ("Futures", ds.HEX["highlight"])]:
        fig.add_bar(name=col, x=L.index, y=L[col], marker_color=color)
    fig.add_scatter(name="Net", x=L.index, y=L["Netto"], mode="lines+markers",
                    line=dict(color=ds.HEX["text"], width=2.5), marker=dict(size=8))
    fig.update_layout(barmode="relative")
    return legend_right(ds.style_figure(fig, height=400, legend=True))


def fig_ladder_cs():
    L = ladder(D, "cs")
    fig = go.Figure()
    fig.add_bar(name="Bonds", x=L.index, y=L["Bonds"], marker_color=ds.HEX["secondary"])
    fig.add_bar(name="CDS", x=L.index, y=L["CDS"], marker_color=ds.HEX["highlight"])
    fig.add_scatter(name="Net", x=L.index, y=L["Netto"], mode="lines+markers",
                    line=dict(color=ds.HEX["text"], width=2.5))
    fig.update_layout(barmode="relative")
    return legend_right(ds.style_figure(fig, height=360, legend=True))


def _sec_colors(sectors):
    return [SECTOR_COLOR.get(s, ds.HEX["border"]) for s in sectors]


def fig_scatter(cdf):
    fig = go.Figure(go.Scatter(
        x=cdf["dur"], y=cdf["spread"], mode="markers",
        marker=dict(size=np.sqrt(cdf["mv"].clip(lower=0)) / 26, sizemin=4,
                    color=_sec_colors(cdf["sector"]),
                    line=dict(width=1, color="#FFF"), opacity=0.9),
        text=cdf["issuer"],
        customdata=np.stack([cdf["mv"] / 1e6, cdf["rating"], cdf["sector"]], axis=-1),
        hovertemplate="<b>%{text}</b><br>Dur %{x:.1f}y · %{y:.0f}bp · "
                      "%{customdata[0]:.1f}M · %{customdata[1]}<extra></extra>"))
    fig = ds.style_figure(fig, height=430)
    return fig.update_layout(hovermode="closest",
                             xaxis_title="Duration (y)", yaxis_title="I-Spread (bp)")


def fig_heatmap(cdf):
    p = cdf.pivot_table(values="cs01", index="sector", columns="bucket",
                        aggfunc="sum").reindex(columns=BUCKET_LABELS)
    fig = go.Figure(go.Heatmap(
        z=p.values, x=p.columns, y=p.index, colorscale=SEQUENTIAL, showscale=False,
        text=np.where(np.isnan(p.values), "",
                      np.vectorize(lambda v: fmt(v))(np.nan_to_num(p.values))),
        texttemplate="%{text}", textfont=dict(size=10),
        hovertemplate="%{y} · %{x}: %{z:,.0f} €/bp<extra></extra>"))
    fig = ds.style_figure(fig, height=380)
    return fig.update_layout(hovermode="closest")


def fig_issuers(cdf):
    g = cdf.groupby("issuer").agg(mv=("mv", "sum"), cs01=("cs01", "sum")).nlargest(15, "mv")
    g = g.sort_values("mv")
    fig = go.Figure(go.Bar(y=g.index, x=g["mv"] / 1e6, orientation="h",
                           marker_color=ds.HEX["primary"],
                           customdata=g["cs01"],
                           hovertemplate="%{y}: %{x:.1f}M · CS01 %{customdata:,.0f} €/bp<extra></extra>"))
    fig = ds.style_figure(fig, height=460)
    return fig.update_layout(hovermode="closest")


def fig_swapbook():
    s = D["swaps"].sort_values("mat_y")
    fig = go.Figure(go.Bar(
        x=s["mat_y"], y=s["bpv"], width=0.35, marker_color=ds.HEX["negative"],
        customdata=np.stack([s["nom"] / 1e6, s["pay"], s["rec"]], axis=-1),
        hovertemplate="%{x:.1f}y · BPV %{y:,.0f} €/bp · %{customdata[0]:.0f}M<br>"
                      "Pay %{customdata[1]:.2f}% / Rec %{customdata[2]:.2f}%<extra></extra>"))
    fig = ds.style_figure(fig, height=340)
    return fig.update_layout(hovermode="closest", xaxis_title="Time to maturity (y)")


def fig_movers(cdf):
    d = cdf.dropna(subset=["dsp30"])
    top = pd.concat([d.nlargest(9, "dsp30"), d.nsmallest(9, "dsp30")]).sort_values("dsp30")
    fig = go.Figure(go.Bar(
        y=top["issuer"], x=top["dsp30"], orientation="h",
        marker_color=[ds.HEX["negative"] if v > 0 else ds.HEX["positive"]
                      for v in top["dsp30"]]))
    fig = ds.style_figure(fig, height=460)
    return fig.update_layout(hovermode="closest")


# ── Die 5 Advanced-Visualisierungen ─────────────────────────────────────────
def fig_3d_cs01_surface():
    """2) CS01 surface: sector × maturity as a 3D surface — risk hotspots made vivid."""
    p = (B.pivot_table(values="cs01", index="sector", columns="bucket", aggfunc="sum")
         .reindex(columns=BUCKET_LABELS).fillna(0))
    fig = go.Figure(go.Surface(
        z=p.values, x=list(range(len(p.columns))), y=list(range(len(p.index))),
        colorscale=SEQUENTIAL, showscale=False, opacity=0.96,
        contours=dict(z=dict(show=True, usecolormap=True, project_z=True)),
        hovertemplate="CS01 %{z:,.0f} €/bp<extra></extra>"))
    fig.update_layout(
        **{k: v for k, v in ds.PLOTLY_LAYOUT.items() if k not in ("xaxis", "yaxis")},
        height=560, margin=dict(l=0, r=0, t=10, b=0),
        scene=dict(
            xaxis=dict(title="", ticktext=list(p.columns), tickvals=list(range(len(p.columns))),
                       backgroundcolor=ds.HEX["background"], gridcolor=ds.HEX["border"]),
            yaxis=dict(title="", ticktext=list(p.index), tickvals=list(range(len(p.index))),
                       backgroundcolor=ds.HEX["background"], gridcolor=ds.HEX["border"]),
            zaxis=dict(title="CS01 €/bp", backgroundcolor=ds.HEX["background"],
                       gridcolor=ds.HEX["border"]),
            camera=dict(eye=dict(x=1.7, y=-1.7, z=0.9)),
            aspectratio=dict(x=1.4, y=1.1, z=0.6)))
    return fig


def fig_momentum_quadrant(cdf):
    """3) Spread momentum quadrant: Δ30d vs. Δ120d — early-warning system.
    Top-right = persistent deterioration, top-left = fresh stress."""
    b = cdf.dropna(subset=["dsp30", "dsp120"])
    fig = go.Figure(go.Scatter(
        x=b["dsp120"], y=b["dsp30"], mode="markers",
        marker=dict(size=np.sqrt(b["mv"].clip(lower=0)) / 26, sizemin=4,
                    color=_sec_colors(b["sector"]),
                    line=dict(width=1, color="#FFF"), opacity=0.9),
        text=b["issuer"],
        hovertemplate="<b>%{text}</b><br>Δ120d %{x:+.0f}bp · Δ30d %{y:+.0f}bp<extra></extra>"))
    fig.add_hline(y=0, line=dict(color=ds.HEX["border"], width=1))
    fig.add_vline(x=0, line=dict(color=ds.HEX["border"], width=1))
    ann = dict(font=dict(size=11, color=ds.HEX["secondary"], family=ds.FONT["family"]),
               showarrow=False, xref="x domain", yref="y domain")
    for x, y, t in [(0.98, 0.98, "PERSISTENT WEAKNESS"), (0.02, 0.98, "FRESH STRESS"),
                    (0.02, 0.02, "RECOVERY INTACT"), (0.98, 0.02, "LATE RECOVERY")]:
        fig.add_annotation(x=x, y=y, text=t, xanchor="right" if x > 0.5 else "left", **ann)
    fig = ds.style_figure(fig, height=470)
    return fig.update_layout(hovermode="closest",
                             xaxis_title="Δ I-Spread 120d (bp)",
                             yaxis_title="Δ I-Spread 30d (bp)")


def fig_carry_treemap():
    """4) Carry treemap: sector → issuer, area = MV, colour = carry efficiency.
    Pink areas = much capital for little spread per duration → rotation candidates."""
    b = B.dropna(subset=["spd"]).assign(w=lambda x: x["spd"] * x["mv"])
    g = (b.groupby(["sector", "issuer"], as_index=False)
           .agg(mv=("mv", "sum"), w=("w", "sum")))
    g["spd"] = g["w"] / g["mv"]
    sec = g.groupby("sector", as_index=False).agg(mv=("mv", "sum"), w=("w", "sum"))
    sec["spd"] = sec["w"] / sec["mv"]
    mid = float(b["w"].sum() / b["mv"].sum())
    labels = list(sec["sector"]) + list(g["issuer"])
    parents = [""] * len(sec) + list(g["sector"])
    values = list(sec["mv"]) + list(g["mv"])
    colors = list(sec["spd"]) + list(g["spd"])
    fig = go.Figure(go.Treemap(
        labels=labels, parents=parents, values=values, branchvalues="total",
        marker=dict(colors=colors, colorscale=DIVERGING, cmid=mid,
                    colorbar=dict(title="bp/y", thickness=12, len=0.6),
                    line=dict(width=1.5, color=ds.HEX["background"])),
        textfont=dict(family=ds.FONT["family"], size=11),
        hovertemplate="<b>%{label}</b><br>MV %{value:,.0f} € · "
                      "Carry-Eff. %{color:.1f} bp/y<extra></extra>"))
    fig.update_layout(
        **{k: v for k, v in ds.PLOTLY_LAYOUT.items() if k not in ("xaxis", "yaxis")},
        height=520, margin=dict(l=0, r=0, t=10, b=0))
    return fig


def fig_curve_waterfall():
    """5) Curve-risk waterfall: cumulative net DV01 along the curve —
    shows where duration risk builds up despite hedging (steepener/flattener bias)."""
    net = ladder(D, "ir")["Netto"]
    fig = go.Figure(go.Waterfall(
        x=net.index, y=net.values,
        totals=dict(marker=dict(color=ds.HEX["primary"])),
        increasing=dict(marker=dict(color=ds.HEX["positive"])),
        decreasing=dict(marker=dict(color=ds.HEX["negative"])),
        connector=dict(line=dict(color=ds.HEX["border"], width=1)),
        measure=["relative"] * len(net),
        text=[f"{v:+,.0f}".replace(",", "\u2009") for v in net.values],
        textposition="outside", textfont=dict(size=10)))
    fig.add_annotation(x=len(net) - 1, y=float(net.cumsum().iloc[-1]),
                       text=f"Σ Net {net.sum():+,.0f} €/bp".replace(",", "\u2009"),
                       showarrow=True, arrowhead=0, ax=0, ay=-38,
                       font=dict(family=ds.FONT["family"], size=12))
    fig = ds.style_figure(fig, height=400)
    return fig.update_layout(hovermode="closest")


# ── Credit-spread curves ────────────────────────────────────────────────────
SPREAD_METRICS = {"I-Spread": "spread", "OAS": "oas"}
_BUCKET_MID = {lbl: (lo + hi) / 2 if hi < 90 else lo + 3 for lo, hi, lbl in MAT_BUCKETS}


def _spread_term(df: pd.DataFrame, col: str) -> pd.Series:
    """MV-weighted spread (col) per maturity bucket, in bucket order."""
    d = df.dropna(subset=[col, "mv"])
    return (d.groupby("bucket").apply(lambda x: np.average(x[col], weights=x["mv"]),
            include_groups=False).reindex(BUCKET_LABELS).dropna())


def fig_spread_curve(col: str):
    """Credit-spread term structure of the cash book (OAS or I-spread) per bucket."""
    g = _spread_term(B, col)
    fig = go.Figure(go.Scatter(
        x=list(g.index), y=g.values, mode="lines+markers",
        line=dict(color=ds.HEX["primary"], width=2.5), marker=dict(size=8),
        fill="tozeroy", fillcolor="rgba(92,114,133,0.10)",
        hovertemplate="%{x}: %{y:.0f} bp<extra></extra>"))
    fig = ds.style_figure(fig, height=380)
    return fig.update_layout(hovermode="x unified", xaxis_title="Maturity bucket",
                             yaxis_title="Spread (bp)")


def fig_rate_vs_spread():
    """Just two lines: the EUR swap curve (%) and the portfolio credit spread (bp) across
    maturity. Uses the 'curves'/'market' sheet (real EUR curve), else the fund-book rates."""
    fig = go.Figure()
    if CURVES is not None and "swap" in CURVES.columns:
        fig.add_scatter(name="EUR swap curve", x=CURVES["tenor"],
                        y=pd.to_numeric(CURVES["swap"], errors="coerce"), mode="lines+markers",
                        line=dict(color=ds.HEX["primary"], width=2.5), marker=dict(size=6),
                        hovertemplate="%{x:.0f}y · %{y:.2f}%<extra></extra>")
    else:
        s = D["swaps"].dropna(subset=["mat_y", "pay"])
        sw = s.groupby(s["mat_y"].round(1))["pay"].mean().sort_index()
        fig.add_scatter(name="Swap fixed rate (book)", x=list(sw.index), y=sw.values,
                        mode="lines+markers", line=dict(color=ds.HEX["primary"], width=2.5),
                        marker=dict(size=7), hovertemplate="%{x:.1f}y · %{y:.2f}%<extra></extra>")
    sp = _spread_term(B, "spread")
    fig.add_scatter(name="Portfolio spread", x=[_BUCKET_MID[l] for l in sp.index], y=sp.values,
                    mode="lines+markers", yaxis="y2",
                    line=dict(color=ds.HEX["highlight"], width=2.5, dash="dot"),
                    marker=dict(size=7), hovertemplate="%{x:.1f}y · %{y:.0f} bp<extra></extra>")
    fig = ds.style_figure(fig, height=400, legend=True)
    fig.update_layout(hovermode="x unified", xaxis_title="Maturity (y)",
                      yaxis=dict(title="Rate (%)", gridcolor=ds.HEX["border"], zeroline=False),
                      yaxis2=dict(title="Spread (bp)", overlaying="y", side="right", showgrid=False))
    return legend_right(fig)


# ── Explorer (Dropdown-Chart) ───────────────────────────────────────────────
def dropdown(cid, options, value, width="260px"):
    return dcc.Dropdown(id=cid, options=[{"label": o, "value": o} for o in options],
                        value=value, clearable=False,
                        style={"width": width, "fontFamily": ds.FONT["family"],
                               "fontSize": "13px"})


# ── Portfolio-Assistent (Claude) ────────────────────────────────────────────
def _portfolio_digest() -> str:
    """Compact text snapshot of the portfolio as context for the language model."""
    L_ir, L_cs = ladder(D, "ir").round(0), ladder(D, "cs").round(0)
    sec = (B.groupby("sector")
             .agg(mv_Mio=("mv", lambda x: x.sum() / 1e6), dv01=("dv01", "sum"),
                  cs01=("cs01", "sum"), spread=("spread", "mean"))
             .round(1).sort_values("cs01", ascending=False))
    cols = ["issuer", "sector", "rating", "ccy", "mat", "mv", "dur", "dv01",
            "cs01", "spread", "spd", "dsp30", "dsp120", "conv", "basis"]
    pos = B[cols].copy()
    pos["mv"] = (pos["mv"] / 1e6).round(2)
    pos = pos.round({"mat": 1, "dur": 2, "dv01": 0, "cs01": 0, "spread": 0,
                     "spd": 1, "dsp30": 0, "dsp120": 0, "conv": 2, "basis": 0})
    return "\n".join([
        f"As of: {pd.Timestamp.today():%Y-%m-%d}",
        "",
        "== KEY FIGURES (DV01/CS01 in €/bp) ==",
        f"Bond market value: EUR {M['mv']/1e6:.1f}m ({M['n_bonds']} positions, {M['n_swaps']} payer swaps, {M['n_cds']} CDS)",
        f"Gross rate DV01 {M['ir_long']:.0f} | Hedge DV01 {M['ir_hedge']:.0f} | Net {M['ir_net']:.0f} | Net duration {M['dur_net']:.2f}y | Hedge ratio {M['hedge_ratio']:.1%}",
        f"CS01 total {M['cs01']:.0f} (bonds {M['cs01_bonds']:.0f}, CDS {M['cs01_cds']:.0f}) | Spread duration {M['dur_gross']:.2f}y | DTS {M['dts']:.1f}",
        f"Avg I-spread MVw {M['spread_avg']:.0f} bp | Avg OAS {M['oas_avg']:.0f} bp | Carry eff. {M['spd']:.1f} bp/y | Avg coupon {M['coupon']:.2f}%",
        f"WAM {M['wam']:.1f}y | Convexity {M['conv']:.2f} | FX≠EUR EUR {M['fx_mv']/1e6:.1f}m ({M['fx_mv']/M['mv']:.1%})",
        "",
        "== RATE DV01 PER MATURITY BUCKET (€/bp) ==", L_ir.to_string(),
        "",
        "== SPREAD DV01 / CS01 PER MATURITY BUCKET (€/bp) ==", L_cs.to_string(),
        "",
        "== SECTOR EXPOSURE (mv in m, dv01/cs01 in €/bp, spread in bp) ==", sec.to_string(),
        "",
        "== ALL BOND POSITIONS (mv in m; dsp30/dsp120 = Δ I-spread 30/120 days in bp) ==",
        pos.to_string(index=False),
    ])


_client = None


def _anthropic():
    """Cached Anthropic client; API key from the environment or 3_env/.env."""
    global _client
    if _client is None:
        import anthropic
        if not os.environ.get("ANTHROPIC_API_KEY"):
            env = ROOT / "3_env" / ".env"
            for line in env.read_text().splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip()
        _client = anthropic.Anthropic()
    return _client


def _answer_text(msg) -> str:
    if getattr(msg, "stop_reason", "") == "refusal":
        return "The request was declined by the model."
    return "".join(b.text for b in msg.content if b.type == "text").strip() or "_(no answer)_"


# ── Agentic Copilot: the model fetches data on demand via tools (no huge prompt) ──
COPILOT_SYSTEM = (
    "You are the portfolio copilot for the nordIX Interest Rate Hedged Bond Fund — a precise, "
    "quantitative fixed-income analyst answering in concise institutional English. Use the tools "
    "to fetch live portfolio data (metrics, allocations, positions, time-series history) and the "
    "web to check current issuer news; do not guess figures — call a tool. Cite concrete numbers, "
    "issuers and sectors, and say clearly when something is not derivable. DV01/CS01 in €/bp."
)
COPILOT_TOOLS = [
    {"name": "get_summary", "description": "Compact snapshot of the whole portfolio (key figures, "
     "DV01/CS01 ladders, sector exposure, all bond positions).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_metrics", "description": "All headline risk & fund metrics as JSON.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_allocation", "description": "Net allocation in % of NAV, split sovereign vs. credit, "
     "by a dimension.", "input_schema": {"type": "object", "properties": {"by": {"type": "string",
      "enum": ["sector", "industry", "rating", "bucket", "country", "ccy", "rank"]}}, "required": ["by"]}},
    {"name": "get_positions", "description": "Largest positions by market value, optionally filtered by "
     "type (Bond/CDS/IRS/Future/FX).", "input_schema": {"type": "object", "properties": {
      "type": {"type": "string"}, "top": {"type": "integer"}}}},
    {"name": "get_history", "description": "Daily time series of a stored snapshot metric (e.g. nav, "
     "dur_net, cs01, spread_avg, pnl_real).", "input_schema": {"type": "object",
      "properties": {"metric": {"type": "string"}}, "required": ["metric"]}},
    {"type": "web_search_20250305", "name": "web_search", "max_uses": 6},
]


def _copilot_tool(name: str, inp: dict) -> str:
    """Run one copilot tool against the in-memory portfolio; always returns a string."""
    if name == "get_summary":
        return _portfolio_digest()
    if name == "get_metrics":
        return json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in M.items()})
    if name == "get_allocation":
        by = (inp or {}).get("by", "sector")
        return alloc_split(B, by, NAV, by.title()).to_json(orient="records")
    if name == "get_positions":
        v = POS_VIEW if not (inp or {}).get("type") else POS_VIEW[POS_VIEW["Type"] == inp["type"]]
        return v.nlargest(int((inp or {}).get("top", 15)), "MV(M)")[POS_COLS].to_json(orient="records")
    if name == "get_history":
        h = load_history()
        col = (inp or {}).get("metric", "nav")
        if not len(h) or col not in h.columns:
            return json.dumps({"note": "no history yet or unknown metric", "columns": list(h.columns)})
        out = h[["date", col]].tail(60).copy()
        out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
        return out.to_json(orient="records")
    return f"unknown tool: {name}"


def _copilot_reply(question: str) -> str:
    """Tool-using agent loop: the model plans, calls tools, then answers."""
    try:
        cl = _anthropic()
        msgs = [{"role": "user", "content": question}]
        r = None
        for _ in range(6):                              # bounded tool loop
            r = cl.messages.create(
                model="claude-opus-4-8", max_tokens=3000,
                system=[{"type": "text", "text": COPILOT_SYSTEM, "cache_control": {"type": "ephemeral"}}],
                tools=COPILOT_TOOLS, messages=msgs)
            if r.stop_reason != "tool_use":
                return _answer_text(r)
            msgs.append({"role": "assistant", "content": r.content})
            results = []
            for b in r.content:
                if getattr(b, "type", None) == "tool_use":
                    try:
                        out = _copilot_tool(b.name, b.input or {})
                    except Exception as ex:
                        out = f"tool error: {ex}"
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
            msgs.append({"role": "user", "content": results})
        return _answer_text(r)
    except Exception as e:
        return f"⚠️ Error during request: {e}"


ISSUERS = sorted(set(B["issuer"].dropna().astype(str)) | set(D["cds"]["issuer"].dropna().astype(str)))
NEWS_SYSTEM = (
    "You are a credit-research analyst for the nordIX Interest Rate Hedged Bond Fund. "
    "Task: via web search, find recent negative news on the portfolio issuers — "
    "rating downgrades and negative outlooks, profit warnings, accounting or fraud allegations, "
    "liquidity/refinancing problems, lawsuits, regulatory action, critical M&A, "
    "material spread widening. Summarise concisely, institutionally and in English: one line per "
    "affected issuer with date, key point and source (with link). Sort by severity and prioritise "
    "the last ~30 days. If you find nothing relevant for an issuer, omit it; if there is nothing "
    "at all, say so clearly. Restrict yourself exclusively to these portfolio issuers:\n\n"
    + ", ".join(ISSUERS)
)


def _news_reply(question: str) -> str:
    """Live web search for negative news on the portfolio issuers."""
    try:
        msg = _anthropic().messages.create(
            model="claude-opus-4-8", max_tokens=3000,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}],
            system=[{"type": "text", "text": NEWS_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": question}])
        return _answer_text(msg)
    except Exception as e:
        return f"⚠️ Error during web search: {e}"


# ── Layout ──────────────────────────────────────────────────────────────────
def note(text: str):
    return html.Div(text, style={**ds.LABEL_STYLE, "textTransform": "none",
                                 "letterSpacing": 0, "marginTop": "10px"})


def block(title: str, content):
    """Sektion (goldenes Label) + Panel — Standardbaustein jeder Analyse-Seite."""
    return html.Div([ds.section(title), ds.panel(content)])


def credit_toggle():
    return html.Div([
        html.Span("Source:", style={**ds.LABEL_STYLE, "marginRight": "10px"}),
        dcc.RadioItems(id="credit-src", value="Bonds", inline=True,
                       options=[{"label": s, "value": s} for s in CREDIT_SRC],
                       inputStyle={"marginRight": "5px"},
                       labelStyle={"marginRight": "18px", "fontFamily": ds.FONT["family"],
                                   "fontSize": "13px", "color": ds.COLORS["text"]}),
    ], style={"display": "flex", "alignItems": "center", "margin": "18px 0 -4px"})


def esg_grid():
    rows = [html.Div([
        html.Span("⊘ ", style={"color": ds.COLORS["negative"], "fontWeight": 700}),
        html.Span(name, style={"fontWeight": 600}),
        html.Span(f" — {crit}", style={"color": ds.COLORS["secondary"]}),
    ], style={"fontFamily": ds.FONT["family"], "fontSize": "13px", "padding": "7px 2px",
              "borderBottom": f"1px solid {ds.COLORS['border']}"}) for name, crit in ESG_EXCLUSIONS]
    return [html.Div(rows, style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "0 40px"}),
            note("Exclusion is checked pre-trade via the ESG data feed; this risk export contains no "
                 "issuer ESG fields. Holdings are treated as pre-filtered.")]


# ── Portfolio sub-tabs (one builder function each) ──────────────────────────
def _grid(boxes):
    return html.Div(boxes, style={"display": "flex", "flexWrap": "wrap", "gap": "10px",
                                  "margin": "6px 0 18px"})


def overview_board():
    """Stat board (largest figures left): fund, rates, credit, exposure."""
    C = ds.COLORS
    fund = []
    if FACTS.get("nav"):
        fund.append(stat("Fund Volume (NAV)", eur(NAV), "100% reference base"))
    if FACTS.get("gross"):
        fund.append(stat("Gross Fund Assets", eur(FACTS["gross"]), "total assets"))
    if CASH is not None:
        fund.append(stat("Cash", eur(CASH), f"{CASH/NAV:.1%} of NAV" if NAV else "", C["highlight"]))
    if FACTS.get("accrued"):
        fund.append(stat("Accrued Interest", eur(FACTS["accrued"]), "coupons / dividends"))
    fund_section = ([ds.section("Fund"), _grid(fund)] if fund else [])
    return html.Div(fund_section + [
        ds.section("Rates & Duration"),
        _grid([
            stat("Gross Rate DV01", f"{fmt(M['ir_long'])} €/bp", "bonds + futures"),
            stat("Hedge DV01", f"{fmt(M['ir_hedge'])} €/bp", f"{M['n_swaps']} payer swaps", C["negative"]),
            stat("Net DV01", f"{fmt(M['ir_net'])} €/bp", "residual rate risk"),
            stat("Spread Duration", f"{M['dur_gross']:.2f} y", "MV-weighted, gross"),
            stat("WAM", f"{M['wam']:.1f} y", "avg time to maturity"),
            stat("Net Duration", f"{M['dur_net']:.2f} y", "after swap/future hedges"),
            stat("Convexity", f"{M['conv']:.2f}", "MV-weighted"),
        ]),
        ds.section("Credit & Spread"),
        _grid([
            stat("CS01 Total", f"{fmt(M['cs01'])} €/bp",
                 f"bonds {fmt(M['cs01_bonds'])} · CDS {fmt(M['cs01_cds'])}"),
            stat("CS01 Bonds", f"{fmt(M['cs01_bonds'])} €/bp", "cash book"),
            stat("CS01 CDS", f"{fmt(M['cs01_cds'])} €/bp", "overlay", C["highlight"]),
            stat("Avg I-Spread", f"{M['spread_avg']:.0f} bp", "MV-weighted, cash book"),
            stat("Avg OAS", f"{M['oas_avg']:.0f} bp", "option-adjusted"),
            stat("Carry Efficiency", f"{M['spd']:.1f} bp/y", "spread per duration", C["highlight"]),
        ]),
        ds.section("Carry / Roll-through (bp of NAV)"),
        _grid([
            stat("Bond Spread Carry", f"{M['spread_mv']/NAV:.0f} bp", "MV-weighted I-spread, % of NAV"),
            stat("CDS Premium", f"{M['cds_prem']/NAV:+.0f} bp",
                 "net running premium, sold − bought", C["highlight"]),
            stat("Total Credit Carry", f"{(M['spread_mv'] + M['cds_prem'])/NAV:.0f} bp",
                 "bond spread + CDS premium, over risk-free"),
        ]),
        ds.section("Exposure"),
        _grid([
            stat("Credit Heat", eur(M['credit_heat']), "bond MV + CDS net"),
            stat("Nominal (FV) Bonds", eur(M['fv']), "sum of face values"),
            stat("Bond MV", eur(M['mv']), "cash book market value"),
            stat("CDS Heat (net)", eur(M['cds_notional']),
                 "notional, by protection side", C["highlight"]),
            stat("Net Exposure", f"{M['credit_heat']/NAV:.0%}", "credit heat / NAV"),
        ]),
    ])


def tab_overview():
    return ds.container([
        overview_board(),
        block("Daily PnL — T-1 · T0 · T+1", [
            ds.data_table(
                data=PNL_DISP.to_dict("records"),
                columns=[{"name": n, "id": i} for i, n in PNL_COLS],
                style_data_conditional=PNL_COND, page_action="none",
                fixed_rows={"headers": False}, style_table={**ds.TABLE_STYLE, "maxHeight": "none"}),
            note("Bonds/CDS: daily return ≈ 5-day price change ÷ 5 (T+1 extrapolates the latest trend). "
                 "Swaps: market value (NPV); daily change = NPV − NPV(T-1). Futures: MtM-neutral. "
                 "Simplified projection without a market scenario.")]),
    ], max_width=1400)


def tab_rates():
    return ds.container([
        block("Risk-free Curve vs. Portfolio Spread", [
            chart(fig_rate_vs_spread(), "cv"), note(_CV_NOTE)]),
        block("Rate Risk — DV01 ladder", chart(fig_ladder_ir(), "c1")),
        block("Curve Positioning", chart(fig_curve_waterfall(), "r1")),
        block("Hedge Book", chart(fig_swapbook(), "r2")),
    ], max_width=1400)


def tab_credit():
    return ds.container([
        credit_toggle(),
        block("Risk / Reward", chart(fig_scatter(B), "cr1")),
        block("Spread Term Structure", [
            html.Div(dropdown("spread-metric", list(SPREAD_METRICS), "I-Spread", "200px"),
                     style={"marginBottom": "8px"}),
            dcc.Graph(id="spread-curve", config={"displaylogo": False},
                      figure=fig_spread_curve(SPREAD_METRICS["I-Spread"]))]),
        block("Spread Risk — CS01 ladder", chart(fig_ladder_cs(), "c2")),
        block("Hotspots", chart(fig_heatmap(B), "cr2")),
        block("Concentration", chart(fig_issuers(B), "cr3")),
        block("Early-Warning — spread momentum quadrant", chart(fig_momentum_quadrant(B), "i3")),
        block("Spread Movers", chart(fig_movers(B), "m1")),
        block("CS01 Surface (rotatable)", chart(fig_3d_cs01_surface(), "i2")),
        block("Capital vs. Carry", chart(fig_carry_treemap(), "i4")),
        block("Free Analysis — Metric × Dimension", [
            html.Div([dropdown("exp-metric", list(EXPLORER_METRICS), "CS01 (€/bp)"),
                      dropdown("exp-dim", list(EXPLORER_DIMS), "Sector")],
                     style={"display": "flex", "gap": "14px", "marginBottom": "6px"}),
            dcc.Graph(id="exp-chart", config={"displaylogo": False})]),
    ], max_width=1400)


def tab_allokation():
    return ds.container([
        block("Guideline compliance — defensive retail fund, Art. 8+ SFDR", [
            ds.data_table(
                data=GUIDE.to_dict("records"),
                columns=[{"name": c, "id": c} for c in ["Guideline", "Actual", "Limit", "Status"]],
                style_data_conditional=GUIDE_COND, page_action="none",
                fixed_rows={"headers": False}, style_table={**ds.TABLE_STYLE, "maxHeight": "none"}),
            note("Rating quotas on the cash book; net duration after swap/future hedges.")]),
        block("ESG exclusions — binding pre-trade filters", esg_grid()),
        block(f"Fundamental screening — balance-sheet quality ({int(FUND['Flags'].gt(0).sum())} "
              f"of {len(FUND)} names flagged)", [
            ds.data_table(
                data=FUND[FUND_COLS].to_dict("records"),
                columns=[{"name": c, "id": c} for c in FUND_COLS],
                style_data_conditional=FUND_COND, filter_action="native", page_action="none",
                style_table={**ds.TABLE_STYLE, "maxHeight": "520px"}),
            note("Thresholds: ND/EBITDA > 5 · FCF/Debt < 0 · Quick < 0.5 · Fixed-Charge-Cov < 2. "
                 "Empty cells = metric not in feed. Sortable & filterable.")]),
    ], max_width=1400)


def tab_positionen():
    return ds.container([
        block(f"All positions ({len(POS)}) — filter by type, sortable & searchable", [
            html.Div(dropdown("pos-art", ["All"] + POS_TYPES, "All", "200px"),
                     style={"marginBottom": "10px"}),
            ds.data_table(
                id="pos-table", data=POS_VIEW.to_dict("records"),
                columns=[{"name": c, "id": c} for c in POS_COLS],
                filter_action="native", page_action="none",
                style_table={**ds.TABLE_STYLE, "maxHeight": "560px"})]),
        block("Portfolio Copilot — agentic Q&A over live data + web", [
            dcc.Textarea(id="chat-input",
                         placeholder="e.g. Which BBB names widened most, and is there fresh news on them?",
                         style={"width": "100%", "height": "70px", "resize": "vertical",
                                "fontFamily": ds.FONT["family"], "fontSize": "14px", "padding": "10px",
                                "border": f"1px solid {ds.COLORS['border']}", "borderRadius": "6px",
                                "backgroundColor": "#FFFFFF", "color": ds.COLORS["text"],
                                "boxSizing": "border-box"}),
            html.Div([
                html.Button("Ask", id="chat-send", n_clicks=0, style=ds.BUTTON_STYLE),
                html.Span("Claude Opus 4.8 agent: fetches metrics, allocations, positions, history "
                          "and web news via tools — may take a few seconds.",
                          style={**ds.LABEL_STYLE, "textTransform": "none", "letterSpacing": 0,
                                 "marginLeft": "14px"}),
            ], style={"display": "flex", "alignItems": "center", "marginTop": "10px"}),
            dcc.Loading(type="dot", color=ds.COLORS["primary"], children=dcc.Markdown(
                id="chat-output",
                style={"marginTop": "14px", "fontFamily": ds.FONT["family"], "fontSize": "14px",
                       "color": ds.COLORS["text"], "lineHeight": 1.5}))]),
        block("News Radar — live web search for negative news per issuer", [
            dcc.Textarea(id="news-input",
                         value="Which issuers in the portfolio currently have bad news?",
                         style={"width": "100%", "height": "70px", "resize": "vertical",
                                "fontFamily": ds.FONT["family"], "fontSize": "14px", "padding": "10px",
                                "border": f"1px solid {ds.COLORS['border']}", "borderRadius": "6px",
                                "backgroundColor": "#FFFFFF", "color": ds.COLORS["text"],
                                "boxSizing": "border-box"}),
            html.Div([
                html.Button("Search bad news", id="news-send", n_clicks=0, style=ds.BUTTON_STYLE),
                html.Span("Live web search across all portfolio issuers via Claude Opus 4.8 — "
                          "may take 20–40 s, billable.",
                          style={**ds.LABEL_STYLE, "textTransform": "none", "letterSpacing": 0,
                                 "marginLeft": "14px"}),
            ], style={"display": "flex", "alignItems": "center", "marginTop": "10px"}),
            dcc.Loading(type="dot", color=ds.COLORS["primary"], children=dcc.Markdown(
                id="news-output",
                style={"marginTop": "14px", "fontFamily": ds.FONT["family"], "fontSize": "14px",
                       "color": ds.COLORS["text"], "lineHeight": 1.5}))]),
    ], max_width=1400)


def rep_table(df: pd.DataFrame):
    """Report table: compact, tabular figures, exportable as CSV via button."""
    return ds.data_table(
        data=df.to_dict("records"),
        columns=[{"name": c, "id": c} for c in df.columns],
        page_action="none", export_format="csv", export_headers="display",
        fixed_rows={"headers": False},
        style_data_conditional=[{"if": {"filter_query": '{' + df.columns[0] + '} = "Σ Total"'},
                                 "fontWeight": 700, "background": ds.COLORS["surface"]}],
        style_cell={**ds.TABLE_CELL_STYLE, "fontVariantNumeric": "tabular-nums"}
        if hasattr(ds, "TABLE_CELL_STYLE") else {"fontVariantNumeric": "tabular-nums"},
        style_table={**ds.TABLE_STYLE, "maxHeight": "none"})


def tab_reporting():
    b = D["bonds"]
    cy = float((b["coupon"] * b["nom"]).sum() / b["mv"].sum() * 100)   # avg current yield %
    key = [
        stat("Fund Volume (NAV)", eur(NAV), FUND_META["name"]),
        stat("As of", FACTS.get("asof", "—"), f"inception {FUND_META['inception']}"),
        stat("ISIN", FUND_META["isin"], FUND_META["company"]),
        stat("TER", FUND_META["ter"], "p.a."),
        stat("Avg Rating (MVw)", avg_rating(b), f"{M['n_bonds']} bonds"),
        stat("WAM", f"{M['wam']:.2f} y", "avg time to maturity"),
        stat("Net Duration", f"{M['dur_net']:.2f} y", "after hedges", ds.COLORS["highlight"]),
        stat("Avg Current Yield", f"{cy:.2f} %", "MV-weighted"),
        stat("Avg Coupon", f"{M['coupon']:.2f} %", "running"),
        stat("Avg I-Spread", f"{M['spread_avg']:.0f} bp", f"OAS {M['oas_avg']:.0f} bp"),
    ]
    return ds.container([
        ds.section("Key Data"),
        _grid(key),
        block("Allocation by asset class (net, % NAV)",
              rep_table(alloc_assetclass(D, NAV, CASH))),
        block("Sector allocation (net, % NAV — sovereign vs. credit)",
              rep_table(alloc_split(b, "sector", NAV, "Sector"))),
        block("Industry allocation (net, % NAV)",
              rep_table(alloc_split(b, "industry", NAV, "Industry", top=20))),
        block("Rating allocation (net, % NAV)",
              rep_table(alloc_split(b, "rating", NAV, "Rating", order=RATING_ORDER))),
        block("Maturity allocation (net, % NAV)",
              rep_table(alloc_split(b, "bucket", NAV, "Maturity", order=BUCKET_LABELS))),
        block("Country allocation (net, % NAV)",
              rep_table(alloc_split(b, "country", NAV, "Country", top=25, mapper=COUNTRY_NAMES))),
        block("Currency allocation (net, % NAV)",
              rep_table(alloc_split(b, "ccy", NAV, "Currency"))),
        block("Seniority allocation (net, % NAV)",
              rep_table(alloc_split(b, "rank", NAV, "Rank"))),
        note("Net, in % of fund volume (NAV). Cash book (bonds) split sovereign vs. credit per group; "
             "CDS overlay not included here. Static data (ISIN/TER/inception) in FUND_META. "
             "Each table is exportable as CSV via “Export”."),
    ], max_width=1400)


HISTORY_SERIES = {
    "Fund Volume (NAV)": ("nav", "EUR"), "Net Duration (y)": ("dur_net", "y"),
    "Spread Duration (y)": ("dur_gross", "y"), "CS01 Total (€/bp)": ("cs01", "€/bp"),
    "Net DV01 (€/bp)": ("ir_net", "€/bp"), "Avg I-Spread (bp)": ("spread_avg", "bp"),
    "Avg OAS (bp)": ("oas_avg", "bp"), "Daily PnL (EUR)": ("pnl_real", "EUR"),
    "VaR Utilisation (%)": ("var_util", "%"), "Cash (EUR)": ("cash", "EUR"),
}


def fig_history(col: str, unit: str):
    h = load_history()
    fig = go.Figure()
    if col in h.columns and len(h):
        fig.add_scatter(x=h["date"], y=pd.to_numeric(h[col], errors="coerce"), mode="lines+markers",
                        line=dict(color=ds.HEX["primary"], width=2.5), marker=dict(size=6),
                        fill="tozeroy", fillcolor="rgba(92,114,133,.08)",
                        hovertemplate="%{x|%Y-%m-%d} · %{y:,.2f}<extra></extra>")
    fig = ds.style_figure(fig, height=420)
    return fig.update_layout(hovermode="x unified", yaxis_title=unit)


def tab_history():
    first = next(iter(HISTORY_SERIES))
    col, unit = HISTORY_SERIES[first]
    return ds.container([
        block("Time series — daily fund metrics", [
            html.Div(dropdown("hist-metric", list(HISTORY_SERIES), first, "260px"),
                     style={"marginBottom": "8px"}),
            dcc.Graph(id="hist-chart", config={"displaylogo": False}, figure=fig_history(col, unit)),
            note(f"{len(load_history())} daily snapshot(s) stored in {SNAPSHOT_STORE.name}. "
                 "History accrues automatically on every run with fresh data (one row per as-of date).")]),
    ], max_width=1400)


PF_SUBTABS = [("Overview", "overview", tab_overview),
              ("Rates", "rates", tab_rates), ("Credit", "credit", tab_credit),
              ("Allocation", "allok", tab_allokation), ("Reporting", "report", tab_reporting),
              ("Positions & AI", "pos", tab_positionen), ("History", "history", tab_history)]


def data_error_panel(title: str, detail: str):
    """Calm, clear message instead of a crash — e.g. when nad.xlsx is missing/broken."""
    return ds.container([ds.panel([
        html.Div(title, style={"fontFamily": ds.FONT["family"], "fontSize": "16px",
                               "fontWeight": 600, "color": ds.COLORS["negative"]}),
        html.Div(detail, style={"fontFamily": ds.FONT["family"], "fontSize": "13px",
                                "color": ds.COLORS["secondary"], "marginTop": "8px", "lineHeight": 1.5}),
        html.Div(f"Expected file: {XLSX}", style={**ds.LABEL_STYLE, "textTransform": "none",
                 "letterSpacing": 0, "marginTop": "10px"}),
    ])], max_width=1400)


def portfolio_analysis():
    if not PORTFOLIO_OK:
        return data_error_panel(
            "Portfolio data could not be loaded.",
            f"The market-data tabs “Markets” and “Admin” keep working. "
            f"Please check nad.xlsx (open in Excel? moved? sheets renamed?). "
            f"Technical detail: {PORTFOLIO_ERR}")
    return html.Div([dcc.Tabs(value="overview", style={"marginTop": "12px"}, children=[
        dcc.Tab(label=lbl, value=val, style=TAB_STYLE, selected_style=TAB_SELECTED, children=build())
        for lbl, val, build in PF_SUBTABS])])


# ════ creditManagement engine integration — Issuer analysis ════════════════
# This app is the shell; the engine (analysis, cashflow model, prospectus) and
# its renderers come from the creditManagement engine and share the designs theme.
CREDIT_MODES = {"Corporate": "corp", "Financial": "fin", "Sovereign / SSA": "sov"}
_CM_PATHS = [r"q:\00_pm\6_ai\0_code", r"S:\benjaminSuermann\3_env"]
# Engine liegt kanonisch in q:\ ...\0_code. Da DIESE Datei nun ebenfalls
# creditManagement.py, the engine is loaded explicitly via its path
# (module name _cm_engine) so `import creditManagement` NEVER re-imports this app.
_CM_ENGINE_FILE = r"q:\00_pm\6_ai\0_code\creditManagement.py"
_cm_mod = None

ISS_INPUT = {"flex": "1", "minWidth": "220px", "padding": "9px 12px", "fontFamily": ds.FONT["family"],
             "fontSize": "14px", "border": f"1px solid {ds.COLORS['border']}", "borderRadius": "6px",
             "backgroundColor": "#FFFFFF", "color": ds.COLORS["text"], "boxSizing": "border-box"}
ISS_DROP = {"border": f"1.5px dashed {ds.COLORS['primary']}", "borderRadius": "6px", "padding": "14px",
            "textAlign": "center", "cursor": "pointer", "margin": "10px 0", "background": ds.COLORS["surface"],
            "fontFamily": ds.FONT["family"], "fontSize": "13px", "color": ds.COLORS["secondary"]}


def _cm():
    """Lazy, cached load of the creditManagement engine via its explicit q:\\ path
    (heavy deps only on demand; collision-safe despite the identical file name)."""
    global _cm_mod
    if _cm_mod is None:
        for p in _CM_PATHS:                       # Geschwistermodule (research_db …) + designs auffindbar
            if p not in sys.path:
                sys.path.insert(0, p)
        import importlib.util
        spec = importlib.util.spec_from_file_location("_cm_engine", _CM_ENGINE_FILE)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_cm_engine"] = mod
        spec.loader.exec_module(mod)
        _cm_mod = mod
    return _cm_mod


def _cm_error(msg):
    return ds.panel(html.P(str(msg), style={"color": ds.COLORS["negative"], "fontSize": "13px",
                    "fontFamily": ds.FONT["family"], "margin": 0}))


def _status(cid):
    return html.Span(id=cid, style={**ds.LABEL_STYLE, "textTransform": "none",
                                    "letterSpacing": 0, "whiteSpace": "nowrap"})


def _issuer_controls(mode_id, inp_id, btn_id, btn_label, status_id, placeholder):
    return html.Div([
        dropdown(mode_id, list(CREDIT_MODES), "Corporate", "185px"),
        dcc.Input(id=inp_id, type="text", debounce=False, placeholder=placeholder, style=ISS_INPUT),
        html.Button(btn_label, id=btn_id, n_clicks=0, style={**ds.BUTTON_STYLE, "whiteSpace": "nowrap"}),
        _status(status_id),
    ], style={"display": "flex", "alignItems": "center", "gap": "10px", "flexWrap": "wrap"})


def search_prospectus(cm, issuer):
    """AI web search for the issuer\u2019s most recent bond prospectus/OM (one candidate)."""
    import anthropic
    client = anthropic.Anthropic(api_key=cm.API_KEY, timeout=300)
    tool = {"name": "report_prospectus",
            "description": "Report the single best-matching current bond prospectus / OM / final terms.",
            "input_schema": {"type": "object", "properties": {
                "found": {"type": "boolean", "description": "true if a usable prospectus/OM/final-terms document was located"},
                "title": {"type": "string"}, "url": {"type": "string"},
                "instrument": {"type": "string", "description": "e.g. EUR 500m 5.75% Senior Notes due 2030"},
                "date": {"type": "string"}, "note": {"type": "string", "description": "one line: why this doc, caveats"}},
                "required": ["found", "title", "url", "instrument", "date", "note"]}}
    prompt = (f"Find the most recent public bond prospectus, offering memorandum or final terms for the "
              f"issuer '{issuer}'. Prefer an actual OM/prospectus/final-terms PDF over summaries. Report "
              f"exactly one best candidate via report_prospectus; set found=false if nothing usable exists.")
    msg = client.messages.create(model=cm.MODEL_ANALYSIS, max_tokens=1500,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 6}, tool],
        messages=[{"role": "user", "content": prompt}])
    for b in msg.content:
        if getattr(b, "type", None) == "tool_use" and getattr(b, "name", "") == "report_prospectus":
            return b.input
    return None


def _prosp_confirm_card(cand):
    return ds.panel([
        html.Div("Document found — is this the right one?", style=ds.LABEL_STYLE),
        html.Div(cand.get("title", "—"), style={"fontWeight": 600, "fontSize": "14px",
                 "fontFamily": ds.FONT["family"], "marginTop": "5px", "color": ds.COLORS["text"]}),
        html.Div(" · ".join(x for x in [cand.get("instrument", ""), cand.get("date", "")] if x),
                 style={"fontSize": "12px", "color": ds.COLORS["secondary"], "fontFamily": ds.FONT["family"]}),
        html.A(cand.get("url", ""), href=cand.get("url", ""), target="_blank",
               style={"fontSize": "12px", "color": ds.COLORS["primary"], "wordBreak": "break-all"}),
        note(cand.get("note", "")) if cand.get("note") else html.Span(),
        html.Div([
            html.Button("Analyze this prospectus", id="prosp-go", n_clicks=0,
                        style={**ds.BUTTON_STYLE, "marginTop": "12px"}),
            html.Span("  or attach a different PDF above and press 'Analyze PDF'.",
                      style={**ds.LABEL_STYLE, "textTransform": "none", "letterSpacing": 0, "marginLeft": "10px"}),
        ]),
    ])


# ── Issuer-analysis sub-tabs (registry — new tools = one entry) ─────────────
def tab_iss_credit():
    return html.Div([
        block("Credit analysis — 17-point memo (Opus 4.8, web search + verification)", [
            _issuer_controls("cred-mode", "cred-input", "cred-run", "Analyze", "cred-status",
                             "Issuer (e.g. Volkswagen AG, Deutsche Bank AG)…"),
            note("Cache-first: known issuers load instantly, new ones run live (~1–2 min, billable).")]),
        dcc.Loading(type="dot", color=ds.COLORS["primary"], children=html.Div(id="cred-output")),
        dcc.Store(id="cred-store"),
    ], style={"paddingTop": "4px"})


def tab_iss_liquidity():
    return html.Div([
        block("Liquidity & cashflow model — 5-year projection + stress", [
            _issuer_controls("liqm-mode", "liqm-input", "liqm-run", "Build model", "liqm-status",
                             "Issuer…"),
            note("Collects standardized, sourced inputs; the engine projects cashflow, capital/leverage "
                 "and liquidity over 5 years and stresses them. Scenario sliders recompute instantly — no API call.")]),
        dcc.Loading(type="dot", color=ds.COLORS["primary"], children=html.Div(id="liqm-output")),
        dcc.Store(id="liqm-store"),
    ], style={"paddingTop": "4px"})


def tab_iss_prospectus():
    return html.Div([
        block("Prospectus & Recovery — Oaktree style (covenants · waterfall · recovery)", [
            html.Div([
                dcc.Input(id="prosp-issuer", type="text", debounce=False, style=ISS_INPUT,
                          placeholder="Issuer / instrument (the AI searches for the prospectus)…"),
                html.Button("Search prospectus", id="prosp-search", n_clicks=0,
                            style={**ds.BUTTON_STYLE, "whiteSpace": "nowrap"}),
                _status("prosp-status"),
            ], style={"display": "flex", "alignItems": "center", "gap": "10px", "flexWrap": "wrap"}),
            dcc.Upload(id="prosp-upload", multiple=True, style=ISS_DROP,
                       children="… or drag a prospectus PDF here / click"),
            html.Div(id="prosp-files"),
            html.Button("Analyze attached PDF", id="prosp-run-file", n_clicks=0,
                        style={**ds.BUTTON_STYLE, "background": ds.COLORS["secondary"]}),
            html.Div(id="prosp-confirm", style={"marginTop": "10px"}),
            note("Without a file, the AI searches the current bond prospectus online and asks whether the "
                 "document matches; the full analysis runs only after confirmation.")]),
        dcc.Loading(type="dot", color=ds.COLORS["primary"], children=html.Div(id="prosp-output")),
        dcc.Store(id="prosp-store"), dcc.Store(id="prosp-cand"), dcc.Store(id="prosp-files-data", data=[]),
    ], style={"paddingTop": "4px"})


ISSUER_SUBTABS = [("Credit Analysis", "credit", tab_iss_credit),
                  ("Liquidity & Stress", "liq", tab_iss_liquidity),
                  ("Prospectus & Recovery", "prosp", tab_iss_prospectus)]


def issuer_analysis():
    return html.Div([
        dcc.Download(id="cred-pdf-dl"), dcc.Download(id="liqm-pdf-dl"), dcc.Download(id="prosp-pdf-dl"),
        dcc.Tabs(value="credit", style={"marginTop": "10px"}, children=[
            dcc.Tab(label=lbl, value=val, style=TAB_STYLE, selected_style=TAB_SELECTED, children=build())
            for lbl, val, build in ISSUER_SUBTABS]),
    ])


# ══ Markets — search sentiment (Google Trends baskets, z-scored) ═════════════
# Fully integrated from sentimentCharts.py. Self-contained: a real sentiment.csv
# next to the script, else deterministic demo data — nothing breaks without a file.
# Kept deliberately small: 4 simple baskets, 2 terms each.
SENTIMENT_CSV = Path(__file__).resolve().parent / "sentiment.csv"
SENTIMENT_BASKETS = {
    "Risk-Off":  ["recession", "vix"],
    "Inflation": ["inflation", "rate hike"],
    "Credit":    ["credit spread", "high yield"],
    "Risk-On":   ["market rally", "bitcoin"],
}
SENTIMENT_TERMS = [t for terms in SENTIMENT_BASKETS.values() for t in terms]
SENTIMENT_CLR = {b: ds.CHART_PALETTE[i % len(ds.CHART_PALETTE)]
                 for i, b in enumerate(SENTIMENT_BASKETS)}
SENTIMENT_OF = {t: b for b, terms in SENTIMENT_BASKETS.items() for t in terms}


def _sentiment_demo(seed: int = 0) -> pd.DataFrame:
    """Deterministic, z-scored weekly time series per term (2 years) as a fallback."""
    rng = np.random.default_rng(seed)
    n = 104
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=n, freq="W-MON")
    out = {}
    for t in SENTIMENT_TERMS:
        x = np.zeros(n)
        for i in range(1, n):
            x[i] = 0.85 * x[i - 1] + rng.normal()      # mean-reverting Random Walk
        out[t] = (x - x.mean()) / (x.std() or 1.0)     # z-scored
    return pd.DataFrame(out, index=idx)


def sentiment_load() -> pd.DataFrame:
    """Real CSV if present & complete, else demo. A broken file breaks nothing."""
    try:
        if SENTIMENT_CSV.exists():
            df = pd.read_csv(SENTIMENT_CSV, index_col=0, parse_dates=True)
            if len(df) and all(t in df.columns for t in SENTIMENT_TERMS):
                return df
    except Exception as ex:
        print(f"[markets] sentiment.csv unlesbar, nutze Demo: {ex}")
    return _sentiment_demo()


def sentiment_agg(df: pd.DataFrame) -> pd.DataFrame:
    """Basket mean per week (only present terms, keeping it robust)."""
    return pd.DataFrame({b: df[[t for t in terms if t in df.columns]].mean(axis=1)
                         for b, terms in SENTIMENT_BASKETS.items()}, index=df.index)


def fig_sentiment_agg(a: pd.DataFrame):
    f = go.Figure()
    f.add_hline(y=0, line_color=ds.HEX["border"], line_width=1)
    for b in a.columns:
        f.add_scatter(x=a.index, y=a[b], mode="lines", name=b,
                      line=dict(color=SENTIMENT_CLR[b], width=2))
    return legend_right(ds.style_figure(f, height=400, legend=True))


def fig_sentiment_term(df: pd.DataFrame, t: str):
    b = SENTIMENT_OF.get(t, next(iter(SENTIMENT_BASKETS)))
    f = go.Figure()
    f.add_hline(y=0, line_color=ds.HEX["border"], line_width=1)
    f.add_scatter(x=df.index, y=df[t], mode="lines", name=t,
                  line=dict(color=SENTIMENT_CLR[b], width=2.5),
                  fill="tozeroy", fillcolor="rgba(92,114,133,.08)")
    return ds.style_figure(f, height=320)


def tab_sentiment():
    df0 = sentiment_load()
    return ds.container([
        html.Div([
            html.Span(id="mkt-msg", style={**ds.LABEL_STYLE, "textTransform": "none", "letterSpacing": 0}),
            html.Button("↻ Refresh", id="mkt-refresh", n_clicks=0,
                        style={**ds.BUTTON_STYLE, "marginLeft": "18px"}),
        ], style={"display": "flex", "alignItems": "center", "justifyContent": "flex-end",
                  "margin": "18px 0 2px"}),
        block("Current sentiment — Google Trends baskets, z-scored", [
            html.Div(id="mkt-cards", style={"display": "flex", "gap": "12px", "flexWrap": "wrap"}),
            note("Weekly Google Trends search intensity per theme, z-standardised over 2 years "
                 "(>0 = above-average search interest). Without sentiment.csv, demo data is used.")]),
        block("Aggregate — basket means", chart(fig_sentiment_agg(sentiment_agg(df0)), "mkt-agg")),
        block("Single term", [
            html.Div(dcc.Dropdown(
                id="mkt-term", value=SENTIMENT_TERMS[0], clearable=False,
                options=[{"label": f"{b} · {t}", "value": t}
                         for b, terms in SENTIMENT_BASKETS.items() for t in terms],
                style={"width": "300px", "fontFamily": ds.FONT["family"], "fontSize": "13px"}),
                style={"marginBottom": "8px"}),
            dcc.Graph(id="mkt-termfig", config={"displaylogo": False},
                      figure=fig_sentiment_term(df0, SENTIMENT_TERMS[0]))]),
        block("Matrix — terms × weeks", ds.data_table(
            id="mkt-matrix", page_action="native", page_size=15,
            export_format="csv", export_headers="display",
            style_table={**ds.TABLE_STYLE, "maxHeight": "none"})),
    ], max_width=1400)


# AI market report: pick a theme (asset class × region × horizon) → ~12-sentence briefing.
REPORT_ASSETS = ["Equities", "High Yield", "Investment Grade", "Rates / Govies"]
REPORT_REGIONS = ["USA", "Europe", "Asia", "Emerging Markets", "Global"]
REPORT_HORIZON = ["Tactical (weeks)", "Strategic (6–12m)"]
MARKET_REPORT_SYSTEM = (
    "You are a senior cross-asset strategist writing a concise institutional market briefing in English. "
    "Use web search for recent (last ~2 weeks) data points and cite sources inline. Write flowing prose "
    "(no bullet lists), about 12 sentences, covering: current levels & recent direction (price / spread / "
    "yield), the key macro & rates drivers, primary-market activity and flows, valuation versus history, the "
    "main risks, and a clear base-case view. Be precise and neutral; avoid hype.")


def _market_report(asset: str, region: str, horizon: str) -> str:
    try:
        msg = _anthropic().messages.create(
            model="claude-opus-4-8", max_tokens=1600,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 6}],
            system=[{"type": "text", "text": MARKET_REPORT_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"Market report — asset class: {asset}; "
                       f"region: {region}; horizon: {horizon}."}])
        texts = [b.text for b in msg.content if b.type == "text" and b.text.strip()]
        return texts[-1].strip() if texts else "_(no answer)_"   # final block, drop tool narration
    except Exception as e:
        return f"⚠️ Error generating report: {e}"


def tab_market_report():
    sel = {"fontFamily": ds.FONT["family"], "fontSize": "13px"}
    return ds.container([
        block("AI market report — pick a theme, get a ~12-sentence briefing", [
            html.Div([
                html.Div(dropdown("rpt-asset", REPORT_ASSETS, REPORT_ASSETS[0], "210px")),
                html.Div(dropdown("rpt-region", REPORT_REGIONS, REPORT_REGIONS[0], "210px")),
                html.Div(dropdown("rpt-horizon", REPORT_HORIZON, REPORT_HORIZON[0], "210px")),
            ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "12px"}),
            html.Div([
                html.Button("Generate report", id="rpt-go", n_clicks=0, style=ds.BUTTON_STYLE),
                html.Span("Live web search via Claude Opus 4.8 — ~15–30 s, billable.",
                          style={**ds.LABEL_STYLE, "textTransform": "none", "letterSpacing": 0,
                                 "marginLeft": "14px"}),
            ], style={"display": "flex", "alignItems": "center"}),
            dcc.Loading(type="dot", color=ds.COLORS["primary"], children=dcc.Markdown(
                id="rpt-out", style={"marginTop": "16px", "fontFamily": ds.FONT["family"],
                "fontSize": "14px", "color": ds.COLORS["text"], "lineHeight": 1.6}))]),
    ], max_width=1400)


MARKETS_SUBTABS = [("Report", "report", tab_market_report), ("Sentiment", "sentiment", tab_sentiment)]


def markets_analysis():
    return html.Div([dcc.Tabs(value="report", style={"marginTop": "10px"}, children=[
        dcc.Tab(label=lbl, value=val, style=TAB_STYLE, selected_style=TAB_SELECTED, children=build())
        for lbl, val, build in MARKETS_SUBTABS])])


# ══ Admin — BVI generator (Bloomberg trade tickets → BVI .xls) ══════════════
# Fully integrated from bvi.py. Excel COM (win32com) and PIL are imported LAZILY in
# the functions so the app start never fails on them.
BVI_TEMPLATE = ROOT / "0_tradingVE" / "2_work" / "0_bvi" / "bviSheetOutline.xls"
BVI_OUTDIR = r"Q:\7_NTP_nordIX_Treasury_plus\1_NAD_Manager\1_bvi"
BVI_SHEET, BVI_FIRST_ROW, BVI_MAXEDGE, BVI_FORCE_OFFSET = "BVI_Securities", 11, 2400, None
BVI_MODEL = "claude-opus-4-8"
BVI_PORTFOLIOS = {
    "42005137": {"D": "082L00", "E": "082L01", "F": "nordIX Anleihen Defensiv"},
    "61212723": {"D": "082L00", "E": "082L01", "F": "nordIX Anleihen Defensiv"},
}
BVI_DEFAULT_ACCOUNT = "42005137"
BVI_COUNTERPARTIES = [
    (("BARCLAYS",),                    "BARCIE2D",    "Barclays Bank Ireland PLC"),
    (("JP MORGAN", "JPMORGAN", "JPM"), "CHASDEFXXXX", "J.P. Morgan AG"),
    (("GOLDMAN", "GSA"),               "GOLDDEFAXXX", "Goldman Sachs Bank Europe SE"),
    (("UBS", "EUBS"),                  "UBSWDE24XXX", "UBS Europe SE"),
    (("DEUTSCHE",),                    "DEUTDEFFDSO", "Deutsche Bank AG"),
    (("HSBC",),                        "TUBDDEDDXXX", "HSBC (D)"),
    (("DONNER", "REUSCHEL"),           "CHDBDEHHXXX", "Donner & Reuschel AG"),
]
BVI_COLS = [("side", "Buy/Sell"), ("isin", "ISIN"), ("name", "Name"), ("qty", "Quantity"),
            ("price", "Clean Price"), ("ccy", "CCY"), ("interest", "Accr. Interest"), ("int_days", "Int. Days"),
            ("settle_amt", "Net"), ("trade_date", "Trade Date"), ("exec_time", "Exec Time"),
            ("settle_date", "Settle Date"), ("account", "Account"), ("broker_name", "Broker Name"),
            ("broker_bic", "Broker BIC"), ("pf_kvg", "Portfolio KVG")]
BVI_FIELDS = [c[0] for c in BVI_COLS]
BVI_SCHEMA = {"type": "object", "additionalProperties": False,
    "properties": {"trades": {"type": "array", "items": {"type": "object", "additionalProperties": False,
        "properties": {k: ({"type": "number"} if k in ("qty", "price", "interest", "settle_amt")
                           else {"type": "integer"} if k == "int_days" else {"type": "string"})
                       for k in ("side", "isin", "name", "qty", "price", "ccy", "interest", "int_days",
                                 "settle_amt", "trade_date", "exec_time", "settle_date", "account", "broker")},
        "required": ["side", "isin", "name", "qty", "price", "ccy", "interest", "int_days",
                     "settle_amt", "trade_date", "exec_time", "settle_date", "account", "broker"]}}},
    "required": ["trades"]}
BVI_PROMPT = """The sources (screenshots/PDF/text) contain Bloomberg securities trades (BLOT tickets).
Read ALL recognizable trades exactly. Field mapping per trade:
side="Buy/Sell"; isin="ISIN"; name="Issue"; qty="Quantity"(number); price="Clean Price";
ccy=currency(euro sign="EUR"); interest="Acc Int"(amount); int_days=number in "Acc Int (NNN)";
settle_amt="Net"; trade_date="Trade Date" as YYYY-MM-DD (Bloomberg shows MM/DD/YYYY);
exec_time="Entry/Exec Time" SECOND time as HH:MM:SS; settle_date="Settle Date" as YYYY-MM-DD;
account="Account"; broker="Broker Name". Amounts as plain numbers (dot=decimal, no thousands).
Dates ALWAYS with a four-digit year (2026-...); never placeholders like "yyyy".
If a date is not clearly legible, leave the field empty."""


def bvi_num(s):
    if s is None or s == "":
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip().replace("€", "").replace("$", "").replace(" ", "").replace("\xa0", "")
    if s == "":
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", "")
    return float(s)


def bvi_to_date(s):
    if isinstance(s, datetime.date):
        return s
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y", "%d/%m/%Y", "%d.%m.%y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Datum nicht erkannt: {s!r}")


def bvi_last_sunday(y, m):
    for week in reversed(calendar.monthcalendar(y, m)):
        if week[calendar.SUNDAY]:
            return datetime.date(y, m, week[calendar.SUNDAY])


def bvi_offset_for(d):
    if BVI_FORCE_OFFSET:
        return BVI_FORCE_OFFSET
    return "+02:00" if bvi_last_sunday(d.year, 3) <= d < bvi_last_sunday(d.year, 10) else "+01:00"


def bvi_exec_ts(trade_date, time_str):
    time_str = str(time_str).strip()
    if not time_str:
        return ""
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            t = datetime.datetime.strptime(time_str, fmt).time()
            return f"{trade_date.isoformat()}T{t.strftime('%H:%M:%S')}{bvi_offset_for(trade_date)}"
        except ValueError:
            continue
    raise ValueError(f"Uhrzeit nicht erkannt: {time_str!r}")


def bvi_map_side(s):
    s = str(s).strip().lstrip("﻿").upper()
    if s in ("S", "SELL", "SE", "VERKAUF", "V"):
        return "SELL"
    if s in ("B", "BUY", "BUYI", "BY", "KAUF", "K"):
        return "BUYI"
    return s


def bvi_resolve_broker(name):
    if not name:
        return None
    u = str(name).upper()
    for keys, bic, full in BVI_COUNTERPARTIES:
        if any(k in u for k in keys):
            return bic, full
    return None


def bvi_col_num(letters):
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


def bvi_try_date(s):
    if s in (None, ""):
        return None
    try:
        d = bvi_to_date(s)
    except Exception:
        return None
    return d if 2000 <= d.year <= 2100 else None


def bvi_try_num(s):
    try:
        return bvi_num(s)
    except Exception:
        return None


def bvi_ticker_of(name):
    tok = re.split(r"\s+", str(name or "").strip())
    t = re.sub(r"[^A-Za-z0-9]", "", tok[0]) if tok and tok[0] else ""
    return t.upper() or "NA"


def bvi_write_workbook(dest, rows):
    """Copy the style template and fill data rows (Excel COM, lazily imported)."""
    import win32com.client as win32
    tpl = str(BVI_TEMPLATE)
    if not os.path.exists(tpl):
        raise RuntimeError(f"Stilvorlage nicht gefunden: {tpl}")
    tmp = os.path.join(tempfile.gettempdir(), f"_bvi_tpl_{os.getpid()}_{abs(id(rows))}.xls")
    try:
        shutil.copy2(tpl, tmp)
    except Exception as e:
        raise RuntimeError(f"Template not readable ({e}). Still open in Excel?")
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    try:
        wb = xl.Workbooks.Open(tmp, IgnoreReadOnlyRecommended=True)
        ws = wb.Worksheets(BVI_SHEET)
        used = ws.UsedRange
        last = used.Row + used.Rows.Count - 1
        if last >= BVI_FIRST_ROW:                   # Beispiel-/Altzeilen leeren, Format bleibt
            ws.Range(ws.Cells(BVI_FIRST_ROW, 1), ws.Cells(last, 40)).ClearContents()
        for i, row in enumerate(rows):
            r = BVI_FIRST_ROW + i
            for col, val in row.items():
                if val == "" or val is None:
                    continue
                c = ws.Cells(r, bvi_col_num(col))
                if col in ("U", "W"):                      # Datum (Zellformat Datum)
                    c.NumberFormatLocal = "TT.MM.JJJJ"
                    c.Value = (val - datetime.date(1899, 12, 30)).days
                elif col == "V":
                    c.NumberFormatLocal = "@"
                    c.Value = val
                elif col == "L":                           # Clean Price: alle Nachkommastellen
                    c.NumberFormatLocal = "0,##########"
                    c.Value = val
                else:
                    c.Value = val
        wb.SaveAs(dest, FileFormat=56)   # 56 = xlExcel8 (.xls, wie Vorlage)
        wb.Close(SaveChanges=False)
    finally:
        xl.Quit()
        try:
            os.remove(tmp)
        except Exception:
            pass


def bvi_build_row(r):
    ccy = str(r.get("ccy") or "EUR").upper()
    td, sd = bvi_to_date(r["trade_date"]), bvi_to_date(r["settle_date"])
    idays = r.get("int_days")
    return {"A": "", "B": "NEWM", "C": "", "D": "082L00", "E": r.get("pf_kvg") or "082L01",
            "F": "nordIX Anleihen Defensiv", "G": bvi_map_side(r["side"]), "H": bvi_num(r["qty"]),
            "I": "ISIN", "J": str(r["isin"]).upper().strip(), "K": r.get("name", ""),
            "L": bvi_num(r["price"]), "M": ccy, "N": 0.0, "O": 0.0, "P": 0.0, "Q": 0.0,
            "R": bvi_num(r.get("interest")) or 0.0, "S": bvi_num(r["settle_amt"]),
            "T": int(bvi_num(idays)) if str(idays) not in ("None", "", "0") else "",
            "U": td, "V": bvi_exec_ts(td, str(r.get("exec_time") or "")), "W": sd,
            "X": ccy, "Y": "XOFF", "Z": "BIC", "AA": str(r.get("broker_bic") or "").upper(),
            "AB": r.get("broker_name") or "", "AC": "", "AD": "", "AE": 1.0, "AF": 1.0, "AG": ""}


def bvi_validate(rows):
    errs = []
    for i, r in enumerate(rows, 1):
        for f, lab in (("isin", "ISIN"), ("name", "Name"), ("side", "Buy/Sell")):
            if not str(r.get(f, "")).strip():
                errs.append(f"Row {i}: {lab} missing")
        for f, lab in (("qty", "Quantity"), ("price", "Clean Price"), ("settle_amt", "Net")):
            if bvi_try_num(r.get(f)) is None:
                errs.append(f"Row {i}: {lab} invalid ('{r.get(f)}')")
        for f, lab in (("trade_date", "Trade Date"), ("settle_date", "Settle Date")):
            if bvi_try_date(r.get(f)) is None:
                errs.append(f"Row {i}: {lab} not a valid date ('{r.get(f)}')")
        if r.get("exec_time"):
            try:
                bvi_exec_ts(datetime.date(2000, 1, 1), str(r["exec_time"]))
            except Exception:
                errs.append(f"Row {i}: Exec Time invalid ('{r.get('exec_time')}')")
    return errs


def bvi_unique_dest(base):
    dest = os.path.join(BVI_OUTDIR, base + ".xls")
    n = 2
    while os.path.exists(dest):
        dest = os.path.join(BVI_OUTDIR, f"{base}_{n}.xls")
        n += 1
    return dest


def bvi_img_block(raw):
    from PIL import Image
    im = Image.open(io.BytesIO(raw))
    im.load()
    if im.mode != "RGB":
        im = im.convert("RGB")
    m = max(im.size)
    if m > BVI_MAXEDGE:
        s = BVI_MAXEDGE / m
        im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png",
            "data": base64.standard_b64encode(buf.getvalue()).decode("ascii")}}


def bvi_build_content(sources):
    blocks, texts = [], []
    for url, fn in sources:
        raw = base64.b64decode(url.split(",", 1)[1])
        ext = os.path.splitext(fn)[1].lower()
        head = url[:30].lower()
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff") or "image/" in head:
            blocks.append(bvi_img_block(raw))
        elif ext == ".pdf" or "pdf" in head:
            blocks.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                           "data": base64.standard_b64encode(raw).decode("ascii")}})
        else:
            texts.append(f"[{fn}]\n" + raw.decode("utf-8", "replace"))
    if texts:
        blocks.append({"type": "text", "text": "Text-Quellen:\n\n" + "\n\n".join(texts)})
    blocks.append({"type": "text", "text": BVI_PROMPT})
    return blocks


def bvi_read_trades(sources):
    res = _anthropic().messages.create(model=BVI_MODEL, max_tokens=8192,
        output_config={"format": {"type": "json_schema", "schema": BVI_SCHEMA}},
        messages=[{"role": "user", "content": bvi_build_content(sources)}])
    text = next(b.text for b in res.content if b.type == "text")
    return json.loads(text).get("trades", [])


def bvi_to_row(t):
    bic, bname = "", t.get("broker", "")
    r = bvi_resolve_broker(t.get("broker", ""))
    if r:
        bic, bname = r
    acct = str(t.get("account") or "")
    pf = BVI_PORTFOLIOS.get(acct, BVI_PORTFOLIOS[BVI_DEFAULT_ACCOUNT])
    return {"side": t.get("side", ""), "isin": t.get("isin", ""), "name": t.get("name", ""),
            "qty": t.get("qty", ""), "price": t.get("price", ""), "ccy": t.get("ccy") or "EUR",
            "interest": t.get("interest", 0), "int_days": t.get("int_days", ""),
            "settle_amt": t.get("settle_amt", ""), "trade_date": t.get("trade_date", ""),
            "exec_time": t.get("exec_time", ""), "settle_date": t.get("settle_date", ""),
            "account": acct, "broker_name": bname, "broker_bic": bic, "pf_kvg": pf["E"]}


def _bvi_statusbox(title, lines, color):
    return html.Div([
        html.Div(title, style={"fontWeight": 700, "color": ds.COLORS["text"], "fontFamily": ds.FONT["family"]}),
        *[html.Div(x, style={"fontSize": "12.5px", "color": ds.COLORS["text"],
                             "fontFamily": ds.FONT["family"]}) for x in lines],
    ], style={"background": color, "border": f"1px solid {ds.COLORS['border']}",
              "borderRadius": "8px", "padding": "12px 14px"})


def _bvi_btn(label, bid, primary=False):
    base = {"padding": "9px 16px", "borderRadius": "6px", "cursor": "pointer",
            "fontFamily": ds.FONT["family"], "fontSize": "13px"}
    if primary:
        base |= {"background": ds.COLORS["primary"], "color": "#fff", "border": "none", "fontWeight": 700}
    else:
        base |= {"background": ds.COLORS["background"], "color": ds.COLORS["text"],
                 "border": f"1px solid {ds.COLORS['border']}"}
    return html.Button(label, id=bid, n_clicks=0, style=base)


def tab_bvi():
    C = ds.COLORS
    upload = dcc.Upload(id="bvi-up", multiple=True, accept="image/*,application/pdf,text/*",
        children=html.Div([
            html.Div("📋  Paste screenshot (Ctrl + V)",
                     style={"fontSize": "16px", "fontWeight": 600, "color": C["primary"]}),
            html.Div("or drag files here / click · screenshots, PDF, text · multiple allowed",
                     style={"fontSize": "12.5px", "color": C["secondary"], "marginTop": "6px"})]),
        style={"padding": "26px", "border": f"2px dashed {C['primary']}", "borderRadius": "8px",
               "textAlign": "center", "background": C["background"], "cursor": "pointer"})
    action = html.Div([
        _bvi_btn("+ Row", "bvi-add"), _bvi_btn("Clear table", "bvi-clear"),
        html.Div("one BVI file per trade · name YYYYMMDD_Ticker",
                 style={"fontSize": "12px", "color": C["secondary"]}),
        html.Div(style={"flex": "1"}),
        _bvi_btn("Create & save BVI", "bvi-save", primary=True),
    ], style={"display": "flex", "alignItems": "center", "gap": "14px", "flexWrap": "wrap",
              "marginTop": "12px", "paddingTop": "12px", "borderTop": f"1px solid {C['border']}"})
    return ds.container([
        dcc.Store(id="bvi-pasted"),
        block("BVI Generator — Bloomberg trade tickets → BVI file", [
            upload,
            dcc.Loading(type="dot", color=C["primary"], children=html.Div(
                id="bvi-msg", style={"minHeight": "18px", "margin": "10px 0 2px 2px",
                "fontSize": "13px", "color": C["primary"], "fontWeight": 600,
                "fontFamily": ds.FONT["family"]})),
            note("Vision extraction via Claude Opus 4.8 · saved to: " + BVI_OUTDIR)]),
        block("Trades — review & correct if needed", [
            ds.data_table(id="bvi-tbl", columns=[{"name": n, "id": i} for i, n in BVI_COLS], data=[],
                editable=True, row_deletable=True, page_action="none",
                style_table={**ds.TABLE_STYLE, "maxHeight": "none", "overflowX": "auto"}),
            action]),
        html.Div(id="bvi-out", style={"marginTop": "14px"}),
    ], max_width=1400)


# Admin sub-tabs (registry — more tools later = one list entry).
ADMIN_SUBTABS = [("BVI", "bvi", tab_bvi)]


def admin_analysis():
    return html.Div([dcc.Tabs(value="bvi", style={"marginTop": "10px"}, children=[
        dcc.Tab(label=lbl, value=val, style=TAB_STYLE, selected_style=TAB_SELECTED, children=build())
        for lbl, val, build in ADMIN_SUBTABS])])


TOP_TABS = [("Markets", "markets", markets_analysis),
            ("Portfolio", "pf", portfolio_analysis),
            ("Issuer", "iss", issuer_analysis),
            ("Admin", "admin", admin_analysis)]

app = Dash(__name__, title="Claudete", suppress_callback_exceptions=True)
# Polish (at the margin): hover-lift of the stat boxes, sharper edges,
# softer focus rings. Injected before </head> into the theme template.
_POLISH_CSS = """
<style>
  html{scroll-behavior:smooth}
  .stat-card{-webkit-font-smoothing:antialiased}
  .stat-card:hover{box-shadow:0 6px 16px rgba(16,24,40,.10),0 2px 5px rgba(16,24,40,.07);
    transform:translateY(-1px)}
  /* Sticky brand header */
  .cm-header{position:sticky;top:0;z-index:40}
  /* Tables: tabular figures, row hover */
  .dash-spreadsheet-container .dash-spreadsheet-inner td,
  .dash-spreadsheet-container .dash-spreadsheet-inner input{
    font-variant-numeric:tabular-nums;transition:background .12s}
  .dash-spreadsheet-container .dash-spreadsheet-inner tr:hover td{background:var(--c-tint)!important}
  /* Neutral scrollbars (read on both themes) */
  *::-webkit-scrollbar{height:10px;width:10px}
  *::-webkit-scrollbar-thumb{background:rgba(128,128,128,.34);border-radius:6px}
  *::-webkit-scrollbar-thumb:hover{background:rgba(128,128,128,.5)}
  .tab,button,.Select-control{transition:color .15s,background .15s,border-color .15s,box-shadow .15s}
  input:focus,textarea:focus{outline:none;box-shadow:0 0 0 3px rgba(92,114,133,.18)}
  ::selection{background:rgba(92,114,133,.22)}
  /* Header control cluster */
  .cm-controls{position:fixed;top:14px;right:20px;z-index:60;display:flex;gap:8px}
  .cm-ctl{font-family:'Helvetica Neue',Arial,sans-serif;font-size:13px;line-height:1;cursor:pointer;
    width:32px;height:32px;border-radius:8px;border:1px solid var(--c-border);
    background:var(--c-surface);color:var(--c-text);display:flex;align-items:center;justify-content:center}
  .cm-ctl:hover{border-color:#5C7285;box-shadow:0 2px 8px rgba(16,24,40,.12)}
  /* Compact density */
  body.cm-compact .cm-panel{padding:10px 12px!important;margin-bottom:10px!important}
  body.cm-compact .stat-card{padding:10px 13px!important;min-width:140px!important}
  body.cm-compact .dash-spreadsheet-inner td,
  body.cm-compact .dash-spreadsheet-inner th{padding:4px 8px!important;font-size:12px!important}
  /* Command palette */
  .cm-cmd{position:fixed;inset:0;z-index:9999;background:rgba(20,22,28,.46);
    display:flex;align-items:flex-start;justify-content:center;padding-top:14vh}
  .cm-cmd-box{width:min(560px,92vw);background:var(--c-surface);border:1px solid var(--c-border);
    border-radius:12px;box-shadow:0 24px 60px rgba(16,18,24,.5);overflow:hidden}
  .cm-cmd-input{width:100%;box-sizing:border-box;border:none!important;outline:none;
    padding:15px 18px;font-family:Georgia,serif;font-size:16px;background:var(--c-surface)!important;color:var(--c-text)!important}
  .cm-cmd-list{max-height:46vh;overflow:auto;border-top:1px solid var(--c-hairline)}
  .cm-cmd-item{padding:10px 18px;font-family:Georgia,serif;font-size:14px;color:var(--c-text);cursor:pointer}
  .cm-cmd-item.sel,.cm-cmd-item:hover{background:var(--c-tint)}
</style>
"""
# Ctrl+V (screenshot from clipboard) → dcc.Store 'bvi-pasted' (Admin/BVI generator).
_BVI_PASTE_JS = """
<script>
document.addEventListener('paste', function (e) {
  var t = e.target;
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
  var items = (e.clipboardData || window.clipboardData).items; if (!items) return;
  for (var i = 0; i < items.length; i++) {
    if (items[i].type && items[i].type.indexOf('image') === 0) {
      var blob = items[i].getAsFile(); var reader = new FileReader();
      reader.onload = function (ev) {
        if (window.dash_clientside && window.dash_clientside.set_props)
          window.dash_clientside.set_props('bvi-pasted', { data: { url: ev.target.result, t: Date.now() } });
      };
      reader.readAsDataURL(blob); e.preventDefault(); return;
    }
  }
});
</script>
"""
# Chrome (all client-side, no Dash callbacks): dark-mode toggle, density toggle,
# and a Ctrl/⌘+K command palette that jumps to any tab. Fails safe if the DOM shifts.
_APP_JS = """
<script>
(function(){
  var d=document.documentElement, LS=window.localStorage;
  function themeBtn(){return document.getElementById('cm-theme-btn');}
  function setTheme(t){ d.setAttribute('data-theme',t); try{LS.setItem('cm-theme',t);}catch(e){}
    var b=themeBtn(); if(b) b.textContent=(t==='dark'?'\\u2600':'\\u263E'); }
  function setDensity(c){ document.body.classList.toggle('cm-compact',!!c); try{LS.setItem('cm-density',c?'1':'0');}catch(e){} }
  try{ setTheme(LS.getItem('cm-theme')||'light'); }catch(e){}
  function tabs(){ return Array.prototype.slice.call(document.querySelectorAll('.tab')); }
  function openPalette(){
    if(document.getElementById('cm-cmd'))return;
    var ov=document.createElement('div'); ov.id='cm-cmd'; ov.className='cm-cmd';
    var box=document.createElement('div'); box.className='cm-cmd-box';
    var inp=document.createElement('input'); inp.className='cm-cmd-input'; inp.placeholder='Jump to\\u2026 (type a tab name)';
    var list=document.createElement('div'); list.className='cm-cmd-list';
    box.appendChild(inp); box.appendChild(list); ov.appendChild(box); document.body.appendChild(ov);
    var items=tabs().map(function(el){return {el:el,txt:(el.textContent||'').trim()};}).filter(function(x){return x.txt;});
    var sel=0;
    function render(){ var q=inp.value.toLowerCase();
      var f=items.filter(function(x){return x.txt.toLowerCase().indexOf(q)>=0;});
      list.innerHTML=''; f.forEach(function(x,i){ var r=document.createElement('div');
        r.className='cm-cmd-item'+(i===sel?' sel':''); r.textContent=x.txt;
        r.onmousedown=function(ev){ ev.preventDefault(); x.el.click(); close(); }; list.appendChild(r); });
      list._f=f; if(sel>=f.length)sel=Math.max(0,f.length-1); }
    function close(){ ov.remove(); document.removeEventListener('keydown',onkey,true); }
    function onkey(e){ if(e.key==='Escape'){close();e.preventDefault();}
      else if(e.key==='ArrowDown'){sel++;render();e.preventDefault();}
      else if(e.key==='ArrowUp'){sel=Math.max(0,sel-1);render();e.preventDefault();}
      else if(e.key==='Enter'){var f=list._f||[]; if(f[sel]){f[sel].el.click();close();} e.preventDefault();} }
    ov.onclick=function(e){ if(e.target===ov)close(); };
    inp.addEventListener('input',function(){sel=0;render();});
    document.addEventListener('keydown',onkey,true);
    render(); setTimeout(function(){inp.focus();},30);
  }
  function build(){ if(document.getElementById('cm-controls'))return;
    var w=document.createElement('div'); w.id='cm-controls'; w.className='cm-controls';
    function btn(txt,title,fn){ var b=document.createElement('button'); b.className='cm-ctl';
      b.textContent=txt; b.title=title; b.onclick=fn; return b; }
    var t=btn(d.getAttribute('data-theme')==='dark'?'\\u2600':'\\u263E','Toggle dark mode',
      function(){ setTheme(d.getAttribute('data-theme')==='dark'?'light':'dark'); }); t.id='cm-theme-btn';
    w.appendChild(t);
    w.appendChild(btn('\\u25A4','Toggle compact density',function(){ setDensity(!document.body.classList.contains('cm-compact')); }));
    w.appendChild(btn('\\u2318K','Command palette (Ctrl/Cmd+K)',openPalette));
    document.body.appendChild(w);
    try{ if((LS.getItem('cm-density')||'0')==='1') setDensity(true); }catch(e){}
  }
  document.addEventListener('keydown',function(e){
    if((e.ctrlKey||e.metaKey) && (e.key==='k'||e.key==='K')){ e.preventDefault(); openPalette(); } });
  var iv=setInterval(function(){ if(document.querySelector('.cm-page')){ build(); clearInterval(iv);} },200);
  window.addEventListener('load',build);
})();
</script>
"""
app.index_string = (ds.index_string().replace("</head>", _POLISH_CSS + "</head>")
                    .replace("</body>", _BVI_PASTE_JS + _APP_JS + "</body>"))
app.layout = ds.page([
    ds.brand_header("Claudete"),
    ds.container([dcc.Tabs(value="markets", children=[
        dcc.Tab(label=lbl, value=val, style=TOPTAB_STYLE, selected_style=TOPTAB_SELECTED, children=build())
        for lbl, val, build in TOP_TABS])], max_width=1460),
])


# ── Markets-Callbacks (Sentiment) ───────────────────────────────────────────
@app.callback(Output("mkt-cards", "children"), Output("mkt-agg", "figure"),
              Output("mkt-matrix", "data"), Output("mkt-matrix", "columns"),
              Output("mkt-msg", "children"), Input("mkt-refresh", "n_clicks"))
def refresh_sentiment(n):
    if n:                                   # Refresh = neue deterministische Stichprobe persistieren
        try:
            _sentiment_demo(seed=int(n)).to_csv(SENTIMENT_CSV)
        except Exception as ex:
            print(f"[markets] sentiment.csv nicht schreibbar: {ex}")
    df = sentiment_load()
    a = sentiment_agg(df)
    t = df.round(2).sort_index(ascending=False)
    t.index = t.index.date.astype(str)
    t = t.reset_index().rename(columns={"index": "Date"})
    cards = [ds.kpi_card(b, round(float(a[b].iloc[-1]), 2)) for b in a.columns]
    src = "live CSV" if SENTIMENT_CSV.exists() else "demo"
    return (cards, fig_sentiment_agg(a), t.to_dict("records"),
            [{"name": c, "id": c} for c in t.columns],
            f"{len(df)} weeks · last {df.index[-1].date()} · {src}")


@app.callback(Output("mkt-termfig", "figure"),
              Input("mkt-term", "value"), Input("mkt-refresh", "n_clicks"))
def sentiment_term_chart(t, _n):
    return fig_sentiment_term(sentiment_load(), t)


@app.callback(Output("rpt-out", "children"), Input("rpt-go", "n_clicks"),
              State("rpt-asset", "value"), State("rpt-region", "value"),
              State("rpt-horizon", "value"), prevent_initial_call=True)
def gen_report(_n, asset, region, horizon):
    return _market_report(asset or REPORT_ASSETS[0], region or REPORT_REGIONS[0],
                          horizon or REPORT_HORIZON[0])


# ── Admin-Callbacks (BVI-Generator) ─────────────────────────────────────────
@app.callback(Output("bvi-tbl", "data"), Output("bvi-msg", "children"),
              Input("bvi-up", "contents"), Input("bvi-pasted", "data"),
              Input("bvi-add", "n_clicks"), Input("bvi-clear", "n_clicks"),
              State("bvi-up", "filename"), State("bvi-tbl", "data"), prevent_initial_call=True)
def bvi_on_input(contents, pasted, _add, _clear, names, data):
    data = data or []
    trig = ctx.triggered_id
    if trig == "bvi-clear":
        return [], ""
    if trig == "bvi-add":
        return data + [{f: "" for f in BVI_FIELDS}], no_update
    if trig == "bvi-pasted":
        if not pasted or not pasted.get("url"):
            return no_update, no_update
        sources = [(pasted["url"], "einfuegen.png")]
    elif trig == "bvi-up":
        if not contents:
            return no_update, no_update
        if not isinstance(contents, list):
            contents, names = [contents], [names]
        sources = list(zip(contents, names or [f"datei{i}" for i in range(len(contents))]))
    else:
        return no_update, no_update
    try:
        trades = bvi_read_trades(sources)
    except Exception as e:
        traceback.print_exc()
        return no_update, f"Error extracting trades: {e}"
    if not trades:
        return no_update, "No trades detected — paste a larger/clearer image."
    return data + [bvi_to_row(t) for t in trades], f"{len(trades)} trade(s) extracted — please review."


@app.callback(Output("bvi-out", "children"),
              Input("bvi-save", "n_clicks"), State("bvi-tbl", "data"), prevent_initial_call=True)
def bvi_on_save(_n, data):
    rows_in = [r for r in (data or []) if str(r.get("isin", "")).strip()]
    if not rows_in:
        return _bvi_statusbox("Keine Zeilen zum Speichern.", [], ds.COLORS["negative"])
    errs = bvi_validate(rows_in)
    if errs:
        return _bvi_statusbox("Bitte zuerst korrigieren:", errs, ds.COLORS["negative"])
    saved = []
    try:
        for r in rows_in:
            d = bvi_try_date(r.get("trade_date"))
            base = f"{d.strftime('%Y%m%d')}_{bvi_ticker_of(r.get('name'))}"
            dest = bvi_unique_dest(base)
            bvi_write_workbook(dest, [bvi_build_row(r)])
            saved.append(dest)
    except Exception as e:
        traceback.print_exc()
        return _bvi_statusbox(f"Error while saving: {e}", [], ds.COLORS["negative"])
    return _bvi_statusbox(f"✓  {len(saved)} BVI-Datei(en) gespeichert",
                          [os.path.basename(p) for p in saved], ds.COLORS["positive"])


# Source links in the Issuer analysis point to /docs/<archived path>; this route
# serves the copy stored in the research archive (else Dash catches the click as an SPA route).
from flask import send_from_directory, abort as _flask_abort


def _archive_dir():
    for p in _CM_PATHS:
        if p not in sys.path:
            sys.path.insert(0, p)
    import research_db
    return str(research_db.ARCHIVE_DIR)


@app.server.route("/docs/<path:rel>")
def _serve_doc(rel):
    try:
        return send_from_directory(_archive_dir(), rel)
    except Exception:
        return _flask_abort(404)


@app.callback(Output("exp-chart", "figure"),
              Input("exp-metric", "value"), Input("exp-dim", "value"))
def update_explorer(metric: str, dim: str):
    s = explore(B, metric, dim)
    fig = go.Figure(go.Bar(
        x=s.index.astype(str), y=s.values, marker_color=ds.HEX["primary"],
        text=[f"{v:,.1f}".replace(",", "\u2009") for v in s.values],
        textposition="outside", textfont=dict(size=10)))
    fig = ds.style_figure(fig, height=460)
    return fig.update_layout(hovermode="closest")


@app.callback(Output("hist-chart", "figure"), Input("hist-metric", "value"))
def update_history(label: str):
    col, unit = HISTORY_SERIES.get(label, ("nav", "EUR"))
    return fig_history(col, unit)


@app.callback(Output("cr1", "figure"), Output("cr2", "figure"), Output("cr3", "figure"),
              Output("i3", "figure"), Output("m1", "figure"), Input("credit-src", "value"))
def update_credit(src: str):
    cdf = credit_view(D, src)
    return (fig_scatter(cdf), fig_heatmap(cdf), fig_issuers(cdf),
            fig_momentum_quadrant(cdf), fig_movers(cdf))


@app.callback(Output("spread-curve", "figure"), Input("spread-metric", "value"))
def update_spread_curve(metric: str):
    return fig_spread_curve(SPREAD_METRICS[metric])


# ── Issuer analysis: credit analysis ────────────────────────────────────────
@app.callback(Output("cred-output", "children"), Output("cred-store", "data"),
              Output("cred-status", "children"), Input("cred-run", "n_clicks"),
              State("cred-input", "value"), State("cred-mode", "value"), prevent_initial_call=True)
def run_credit(_n, company, mode_lbl):
    if not company or not company.strip():
        return no_update, no_update, "Please enter an issuer."
    try:
        cm = _cm()
    except Exception as ex:
        return _cm_error(f"Engine not loadable: {ex}"), no_update, ""
    mode = CREDIT_MODES.get(mode_lbl, "corp")
    try:
        data = cm._issuer_job(company.strip(), mode, False)
    except Exception as ex:
        return _cm_error(f"Analysis failed: {ex}"), no_update, ""
    data.setdefault("_mode", mode)
    return cm.build_output(data, mode), data, ("from cache" if data.get("_cached") else "done")


@app.callback(Output("cred-pdf-dl", "data"), Output("pdf-status", "children"),
              Input("btn-pdf", "n_clicks"), State("cred-store", "data"), prevent_initial_call=True)
def credit_pdf(n, data):
    if not n or not data or data.get("error"):
        return no_update, "No report."
    try:
        cm = _cm()
        return (dcc.send_bytes(cm.gen_pdf(data, data.get("_mode", "corp")),
                filename=f"{data.get('company', 'memo')}.pdf"), "Download started.")
    except Exception as ex:
        return no_update, f"Error: {ex}"


# ── Issuer analysis: liquidity & cashflow model ─────────────────────────────
@app.callback(Output("liqm-output", "children"), Output("liqm-store", "data"),
              Output("liqm-status", "children"), Input("liqm-run", "n_clicks"),
              State("liqm-input", "value"), State("liqm-mode", "value"), prevent_initial_call=True)
def run_liquidity(_n, company, mode_lbl):
    if not company or not company.strip():
        return no_update, no_update, "Please enter an issuer."
    try:
        cm = _cm()
    except Exception as ex:
        return _cm_error(f"Engine not loadable: {ex}"), no_update, ""
    mode = CREDIT_MODES.get(mode_lbl, "corp")
    try:
        data = cm._liquidity_job(company.strip(), mode, False)
    except Exception as ex:
        return _cm_error(f"Model failed: {ex}"), no_update, ""
    store = {"mode": mode, "company": data.get("company", ""), "commentary": data.get("commentary", ""),
             "history": data.get("history") or {},
             "inputs": {f["key"]: data.get(f["key"]) for f in cm.liquidity.LIQ_INPUTS[mode]},
             "akeys": [a["key"] for a in cm.liquidity.LIQ_ASSUMPTIONS[mode]]}
    return cm.build_liquidity_panel(data), store, ("from cache" if data.get("_cached") else "done")


def _liq_assumptions(svalues, sids, akeys):
    a = {}
    for v, i in zip(svalues, sids):
        idx = i["index"]
        if isinstance(idx, int) and 0 <= idx < len(akeys):
            a[akeys[idx]] = v
    return a


@app.callback(Output("liq-results", "children"),
              Input({"type": "liq-slider", "index": ALL}, "value"), Input("btn-liq-recompute", "n_clicks"),
              State({"type": "liq-slider", "index": ALL}, "id"),
              State({"type": "liq-input", "index": ALL}, "value"),
              State({"type": "liq-input", "index": ALL}, "id"),
              State("liqm-store", "data"), prevent_initial_call=True)
def recompute_liquidity(svalues, _n, sids, ivalues, iids, store):
    if not store or not svalues:
        return no_update
    cm = _cm()
    a = _liq_assumptions(svalues, sids, store.get("akeys", []))
    inputs = cm._collect_inputs(ivalues, iids, store.get("inputs", {}))
    return cm.build_liquidity_results(store["mode"], inputs, a, history=store.get("history"))


@app.callback(Output("liqm-pdf-dl", "data"), Output("liq-pdf-status", "children"),
              Input("btn-liq-pdf", "n_clicks"),
              State({"type": "liq-slider", "index": ALL}, "value"),
              State({"type": "liq-slider", "index": ALL}, "id"),
              State({"type": "liq-input", "index": ALL}, "value"),
              State({"type": "liq-input", "index": ALL}, "id"),
              State("liqm-store", "data"), prevent_initial_call=True)
def liquidity_pdf(n, svalues, sids, ivalues, iids, store):
    if not n or not store:
        return no_update, "No model."
    try:
        cm = _cm()
        a = _liq_assumptions(svalues, sids, store.get("akeys", []))
        inputs = cm._collect_inputs(ivalues, iids, store.get("inputs", {}))
        res = cm.liquidity.project(store["mode"], inputs, a,
                                   t0=pd.Timestamp.today().year, history=store.get("history"))
        pdf = cm.gen_liquidity_pdf(store["mode"], store.get("company", "issuer"),
                                   store.get("commentary", ""), res, a)
        return (dcc.send_bytes(pdf, filename=f"{store.get('company', 'issuer')}_liquidity.pdf"),
                "Download started.")
    except Exception as ex:
        return no_update, f"Error: {ex}"


# ── Issuer analysis: prospectus & recovery (auto-search + confirmation) ─────
@app.callback(Output("prosp-files-data", "data"), Output("prosp-files", "children"),
              Input("prosp-upload", "contents"), State("prosp-upload", "filename"),
              prevent_initial_call=True)
def stage_prospectus(contents, filenames):
    if not contents:
        return [], ""
    if not isinstance(contents, list):
        contents, filenames = [contents], [filenames]
    files = [{"name": n, "data": c} for n, c in zip(filenames, contents)]
    return files, note("Attached: " + "  ·  ".join(f["name"] for f in files))


@app.callback(Output("prosp-confirm", "children"), Output("prosp-cand", "data"),
              Output("prosp-status", "children"), Input("prosp-search", "n_clicks"),
              State("prosp-issuer", "value"), prevent_initial_call=True)
def find_prospectus(_n, issuer):
    if not issuer or not issuer.strip():
        return no_update, no_update, "Please enter an issuer."
    try:
        cm = _cm()
        cand = search_prospectus(cm, issuer.strip())
    except Exception as ex:
        return _cm_error(f"Search failed: {ex}"), no_update, ""
    if not cand or not cand.get("found"):
        return _cm_error("No prospectus found — please attach a PDF."), None, "nothing found"
    return _prosp_confirm_card(cand), cand, "found"


def _run_prospectus(cm, issuer, files):
    result = cm.run_prospectus_analysis(issuer, files)
    try:
        cm.analysis_db.save_analysis("prospectus", "prosp", result.get("company", issuer or ""), result)
    except Exception as ex:
        print(f"[pfDash] prospectus save failed: {ex}")
    return result


@app.callback(Output("prosp-output", "children"), Output("prosp-store", "data"),
              Input("prosp-go", "n_clicks"), State("prosp-issuer", "value"),
              State("prosp-cand", "data"), prevent_initial_call=True)
def analyze_prospectus_found(_n, issuer, cand):
    try:
        cm = _cm()
    except Exception as ex:
        return _cm_error(f"Engine not loadable: {ex}"), no_update
    url = (cand or {}).get("url", "")
    label = f"{(issuer or '').strip()} — use this prospectus: {url}" if url else (issuer or "").strip()
    try:
        result = _run_prospectus(cm, label, None)
    except Exception as ex:
        return _cm_error(f"Analysis failed: {ex}"), no_update
    return cm.build_prospectus_output(result), result


@app.callback(Output("prosp-output", "children", allow_duplicate=True),
              Output("prosp-store", "data", allow_duplicate=True),
              Input("prosp-run-file", "n_clicks"), State("prosp-issuer", "value"),
              State("prosp-files-data", "data"), prevent_initial_call=True)
def analyze_prospectus_file(_n, issuer, files):
    if not files:
        return no_update, no_update
    try:
        cm = _cm()
        result = _run_prospectus(cm, (issuer or "").strip(), files)
    except Exception as ex:
        return _cm_error(f"Analysis failed: {ex}"), no_update
    return cm.build_prospectus_output(result), result


@app.callback(Output("prosp-pdf-dl", "data"), Output("prosp-pdf-status", "children"),
              Input("btn-prosp-pdf", "n_clicks"), State("prosp-store", "data"), prevent_initial_call=True)
def prospectus_pdf(n, data):
    if not n or not data or data.get("error"):
        return no_update, "No report."
    try:
        cm = _cm()
        return (dcc.send_bytes(cm.gen_prospectus_pdf(data),
                filename=f"{data.get('company', 'prospectus')}_prospectus.pdf"), "Download started.")
    except Exception as ex:
        return no_update, f"Error: {ex}"


@app.callback(Output("pos-table", "data"), Input("pos-art", "value"))
def filter_positions(art: str):
    v = POS_VIEW if art == "All" else POS_VIEW[POS_VIEW["Type"] == art]
    return v.to_dict("records")


@app.callback(Output("chat-output", "children"),
              Input("chat-send", "n_clicks"), State("chat-input", "value"),
              prevent_initial_call=True)
def answer_question(_n_clicks: int, question: str):
    if not question or not question.strip():
        return "_Please enter a question._"
    return _copilot_reply(question.strip())


@app.callback(Output("news-output", "children"),
              Input("news-send", "n_clicks"), State("news-input", "value"),
              prevent_initial_call=True)
def answer_news(_n_clicks: int, question: str):
    if not question or not question.strip():
        return "_Please enter a question._"
    return _news_reply(question.strip())


if __name__ == "__main__":
    try:                                    # Konsolen ohne UTF-8 (cp1252) am Encoding härten
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(f"\n  >  Claudete im Browser oeffnen:  http://localhost:{PORT}\n")
    app.run(host="0.0.0.0", port=PORT, debug=False)
