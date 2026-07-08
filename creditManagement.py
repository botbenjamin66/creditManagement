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
from dash import Dash, html, dcc, Input, Output, State, ctx, no_update

def _project_root() -> Path:
    here = Path(__file__).resolve()
    for base in [here.parent, *here.parents]:
        if (base / "3_env" / "designs.py").exists() or (base / "0_tradingVE").is_dir():
            return base
    return Path(r"S:\benjaminSuermann")


ROOT = _project_root()
HERE = Path(__file__).resolve().parent
for _p in (str(ROOT / "3_env"), str(HERE)):
    sys.path.insert(0, _p)
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


SHEET_ALIASES = {"bonds": ("bonds",), "cds": ("cds",), "swaps": ("swaps", "irs"),
                 "futures": ("futures", "future"), "fx": ("fx",)}


def _pick_sheet(raw: dict, key: str) -> pd.DataFrame:
    lut = {str(k).strip().lower(): k for k in raw}
    for cand in SHEET_ALIASES.get(key, (key,)):
        hit = lut.get(cand.lower())
        if hit is not None and not raw[hit].empty:
            return raw[hit]
    return pd.DataFrame()


def _read_book(path: str):
    def rd(**kw):
        try:
            return pd.read_excel(path, sheet_name=None, **kw)
        except Exception:
            return {}
    return rd(), rd(header=None)


def load(raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    d: dict[str, pd.DataFrame] = {}
    for sheet, mapping in COL.items():
        src = _pick_sheet(raw, sheet)
        lut = {str(c).strip().lower(): c for c in src.columns}
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
    b["cs01"] = (b["dur"] * b["mv"] / 1e4).where(b["dur"].notna(), b["dv01"])
    b["bucket"] = b["mat"].apply(_bucket)
    b["dsp30"] = b["sp30"]
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
    b, c, s, f = d["bonds"], d["cds"], d["swaps"], d["futures"]
    mv = b["mv"].sum()
    w = b["mv"] / mv
    ir_long = b["dv01"].sum() + f.loc[f["dv01"] > 0, "dv01"].sum()
    ir_hedge = s["bpv"].sum() + f.loc[f["dv01"] < 0, "dv01"].sum()
    cw = c.dropna(subset=["spread", "nom"])
    cds_spread_avg = (float((cw["spread"] * cw["nom"].abs()).sum() / cw["nom"].abs().sum())
                      if len(cw) and cw["nom"].abs().sum() else 0.0)
    return dict(
        mv=mv, n_bonds=len(b), n_cds=len(c), n_swaps=len(s),
        ir_long=ir_long, ir_hedge=ir_hedge, ir_net=ir_long + ir_hedge,
        hedge_ratio=-ir_hedge / ir_long if ir_long else 0.0,
        cs01=b["cs01"].sum() + c["cs01"].sum(),
        cs01_bonds=b["cs01"].sum(), cs01_cds=c["cs01"].sum(),
        dur_net=float((ir_long + ir_hedge) / mv * 1e4),
        spread_avg=float((b["spread"] * w).sum()),
        oas_avg=float((b["oas"] * w).sum()),
        dts=float((b["dts"] * w).sum()),
        wam=float((b["mat"] * w).sum()),
        conv=float((b["conv"] * w).sum()),
        coupon=float((b["coupon"] * w).sum()) * 100,
        spd=float((b["spd"] * w).sum()),
        spread_mv=float((b["spread"] * b["mv"]).sum()),
        cds_prem=float((c["spread"] * c["nom"]).sum()),
        cds_spread_avg=cds_spread_avg,
        fx_mv=float(b.loc[b["ccy"] != "EUR", "mv"].sum()),
        fv=float(b["nom"].sum()),
        cds_notional=float(c["nom"].sum()),
        credit_heat=float(mv + c["nom"].sum()),
    )


def fund_facts(allsheets: dict) -> dict:
    if not allsheets:
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
           "renten": find("renten"), "asof": asof}
    return {k: v for k, v in out.items() if v is not None}


def ladder(d: dict[str, pd.DataFrame], kind: str) -> pd.DataFrame:
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


POS_TYPES = ["Bond", "CDS", "IRS", "Future", "FX"]


def positions(d: dict[str, pd.DataFrame]) -> pd.DataFrame:
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
    rows = []
    def price_leg(name, df):
        r = (df["px5d"] / 5 / 100).fillna(0)
        mv0 = df["mv"].fillna(0)
        m1, p1 = mv0 / (1 + r), mv0 * (1 + r)
        rows.append(dict(Instrument=name, mv_m1=m1.sum(), mv0=mv0.sum(), mv_p1=p1.sum(),
                         pnl_real=(mv0 - m1).sum(), pnl_proj=(p1 - mv0).sum()))
    price_leg("Bonds", d["bonds"])
    price_leg("CDS", d["cds"])
    s = d["swaps"]
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


CREDIT_SRC = ["Bond + CDS", "Bonds", "CDS"]


def credit_view(d: dict[str, pd.DataFrame], source: str) -> pd.DataFrame:
    if source == "Bonds":
        return d["bonds"]
    if source == "CDS":
        return d["cds"]
    return pd.concat([d["bonds"], d["cds"]], ignore_index=True)


IG_PREFIX = ("AAA", "AA", "A", "BBB")


def _is_ig(r) -> bool:
    return str(r).strip().upper().startswith(IG_PREFIX)


def risk_limits(d: dict[str, pd.DataFrame], m: dict) -> list:
    b = d["bonds"]
    mv = b["mv"].sum() or 1.0
    sub_ig = b.loc[~b["rating"].apply(_is_ig), "mv"].sum() / mv
    bbb = b.loc[b["rating"].astype(str).str.upper().str.startswith("BBB"), "mv"].sum() / mv
    cds_lev = d["cds"]["nom"].sum() / mv
    return [("Sub-IG (< BBB-)", sub_ig, 0.10, "le", "{:.1%}"),
            ("Triple-B (BBB)", bbb, 0.40, "le", "{:.1%}"),
            ("CDS leverage", cds_lev, 0.50, "le", "{:.1%}"),
            ("FX ≠ EUR", m["fx_mv"] / (m["mv"] or 1.0), 0.05, "le", "{:.1%}"),
            ("Net duration", m["dur_net"], (-1.0, 3.0), "range", "{:.2f} y")]


FUND_RULES = [("d2e", ">", 5.0), ("fcf", "<", 0.0), ("quick", "<", 0.5), ("fcov", "<", 2.0)]


def fundamental_screen(d: dict[str, pd.DataFrame]) -> pd.DataFrame:
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
    b = d["bonds"]
    gov = float(b[_gov_mask(b)]["mv"].sum() / nav * 100)
    cred = float(b[~_gov_mask(b)]["mv"].sum() / nav * 100)
    csh = float((cash or 0) / nav * 100)
    rest = max(0.0, 100.0 - gov - cred - csh)
    rows = [("Sovereign bonds", round(gov, 2)), ("Corporate bonds (credit)", round(cred, 2)),
            ("Cash / bank balance", round(csh, 2)), ("Other (swaps, receiv./payab.)", round(rest, 2)),
            ("Σ Total", round(gov + cred + csh + rest, 2))]
    return pd.DataFrame(rows, columns=["Asset class", "Share"])


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


def load_curves(raw: dict):
    if not raw:
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


PORTFOLIO_DIR = ROOT / "0_tradingVE" / "0_portfolios"


def _resolve_xlsx(name: str) -> str:
    p = Path(name)
    return str(p if p.is_file() else PORTFOLIO_DIR / p.name)


XLSX = _resolve_xlsx(sys.argv[1] if len(sys.argv) > 1 else "nad.xlsx")
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8050


def _empty_book() -> dict[str, pd.DataFrame]:
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


RAW, RAW0 = _read_book(XLSX)
try:
    if not RAW:
        raise ValueError("workbook unreadable or empty")
    D = load(RAW)
    PORTFOLIO_OK, PORTFOLIO_ERR = True, ""
except Exception as _pf_ex:
    import traceback as _tb
    _tb.print_exc()
    D, PORTFOLIO_OK, PORTFOLIO_ERR = _empty_book(), False, str(_pf_ex)

M = metrics(D)
B = D["bonds"]

FACTS = fund_facts(RAW0)
NAV = FACTS.get("nav") or M["mv"] or 1.0
if pd.isna(NAV) or NAV == 0:
    NAV = 1.0
CASH = FACTS.get("cash")

# All durations normalised to NAV = the fund's own price sensitivity (incl. cash drag).
M["dur_spread"] = M["cs01"] / NAV * 1e4        # fund spread duration, bonds + CDS
M["dur_net"] = M["ir_net"] / NAV * 1e4         # fund net rate duration, after hedges
M["dur_rate_gross"] = M["ir_long"] / NAV * 1e4

CURVES = load_curves(RAW0)

POS = positions(D)
POS_VIEW = POS.assign(**{"Nom(M)": POS["Nominal"] / 1e6, "MV(M)": POS["MV"] / 1e6}).round(
    {"Mat": 1, "Nom(M)": 2, "MV(M)": 2, "Dur": 2, "DV01/BPV": 0, "Spread": 0})
POS_COLS = ["Type", "id", "Name", "Sector", "Rtg", "Ccy", "Mat", "Nom(M)", "MV(M)",
            "Dur", "DV01/BPV", "Spread"]
TOP10_COLS = ["Type", "Name", "Sector", "Rtg", "Ccy", "MV(M)", "Dur", "Spread"]
FILTER_STYLE = {"backgroundColor": ds.COLORS["background"], "color": ds.COLORS["text"],
                "fontFamily": ds.FONT["numeric"], "fontSize": "12px",
                "borderBottom": f"1px solid {ds.COLORS['hairline']}"}

def eur(v: float, sign: bool = False) -> str:
    a = abs(float(v))
    pre = ("+" if v > 0 else "-" if v < 0 else "") if sign else ("-" if v < 0 else "")
    if a >= 1e6:
        return f"{pre}{a/1e6:.1f} MM EUR"
    if a >= 1e3:
        return f"{pre}{a/1e3:,.0f} TEUR".replace(",", " ")
    return f"{pre}{a:,.0f} EUR".replace(",", " ")


PNL = pnl_projection(D)
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

RISK = risk_limits(D, M)

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


def stat(label: str, value: str, sub: str = "", accent: str | None = None):
    ac = accent or ds.COLORS["primary"]
    body = [
        html.Div(label, style=ds.LABEL_STYLE),
        html.Div(value, style={"fontFamily": ds.FONT.get("numeric", ds.FONT["family"]),
                               "fontWeight": 500, "fontSize": "26px", "color": ds.COLORS["text"],
                               "marginTop": "7px", "lineHeight": 1.05, "letterSpacing": "-0.02em",
                               "fontVariantNumeric": "tabular-nums"}),
        html.Div(sub, style={**ds.LABEL_STYLE, "textTransform": "none",
                             "letterSpacing": 0, "marginTop": "6px", "opacity": 0.9}),
    ]
    return html.Div(body, className="stat-card", style={**ds.CARD_STYLE, "flex": "1", "minWidth": "158px",
              "padding": "15px 17px", "position": "relative",
              "borderLeft": f"3px solid {ac}",
              "boxShadow": "0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.05)",
              "transition": "box-shadow .18s ease, transform .18s ease"})


def chart(fig, cid: str):
    return dcc.Graph(id=cid, figure=fig, config={"displaylogo": False})


def legend_right(fig):
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
    fig.update_layout(barmode="relative")
    return legend_right(ds.style_figure(fig, height=440, legend=True))


def _sec_colors(sectors):
    return [SECTOR_COLOR.get(s, ds.HEX["border"]) for s in sectors]


def _bubble(mv):
    return np.sqrt(pd.to_numeric(mv, errors="coerce").fillna(0).clip(lower=0)) / 26


def _empty_fig(msg, height=430):
    fig = ds.style_figure(go.Figure(), height=height)
    fig.add_annotation(text=msg, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                       font=dict(family=ds.FONT["family"], size=13, color=ds.HEX["muted"]))
    return fig.update_layout(hovermode="closest")


CMAP_AXES = {
    "Duration (y)":       ("dur",    ".1f", False),
    "I-Spread (bp)":      ("spread", ".0f", False),
    "OAS (bp)":           ("oas",    ".0f", False),
    "DTS (y·bp)":         ("dts",    ".0f", False),
    "Carry Eff. (bp/y)":  ("spd",    ".1f", False),
    "Δ Spread 30d (bp)":  ("dsp30",  "+.0f", True),
    "Δ Spread 120d (bp)": ("dsp120", "+.0f", True),
    "CDS Basis (bp)":     ("basis",  "+.0f", True),
}


def fig_credit_map(cdf, xkey="Duration (y)", ykey="I-Spread (bp)"):
    xc, xf, xneg = CMAP_AXES[xkey]
    yc, yf, yneg = CMAP_AXES[ykey]
    if xc not in cdf.columns or yc not in cdf.columns:
        return _empty_fig("Metric not available for this source.", 470)
    d = cdf.dropna(subset=[xc, yc, "mv"])
    if not len(d):
        return _empty_fig("No data for this selection.", 470)
    fig = go.Figure(go.Scatter(
        x=d[xc], y=d[yc], mode="markers", text=d["issuer"], customdata=d["mv"] / 1e6,
        marker=dict(size=_bubble(d["mv"]), sizemin=4, color=_sec_colors(d["sector"]),
                    line=dict(width=1, color="#FFF"), opacity=0.9),
        hovertemplate=f"<b>%{{text}}</b><br>{xkey} %{{x:{xf}}} · {ykey} %{{y:{yf}}} · "
                      "%{customdata:.1f}M<extra></extra>"))
    if xneg:
        fig.add_vline(x=0, line=dict(color=ds.HEX["border"], width=1))
    if yneg:
        fig.add_hline(y=0, line=dict(color=ds.HEX["border"], width=1))
    fig = ds.style_figure(fig, height=440)
    return ds.axisTitles(fig.update_layout(hovermode="closest"), xkey, ykey)


def fig_heatmap(cdf):
    p = cdf.pivot_table(values="cs01", index="sector", columns="bucket",
                        aggfunc="sum").reindex(columns=BUCKET_LABELS)
    fig = go.Figure(go.Heatmap(
        z=p.values, x=p.columns, y=p.index, colorscale=SEQUENTIAL, showscale=False,
        text=np.where(np.isnan(p.values), "",
                      np.vectorize(lambda v: fmt(v))(np.nan_to_num(p.values))),
        texttemplate="%{text}", textfont=dict(size=10),
        hovertemplate="%{y} · %{x}: %{z:,.0f} €/bp<extra></extra>"))
    fig = ds.style_figure(fig, height=440)
    return fig.update_layout(hovermode="closest")


def fig_swapbook():
    s = D["swaps"].sort_values("mat_y")
    fig = go.Figure(go.Bar(
        x=s["mat_y"], y=s["bpv"], width=0.35, marker_color=ds.HEX["negative"],
        customdata=np.stack([s["nom"] / 1e6, s["pay"], s["rec"]], axis=-1),
        hovertemplate="%{x:.1f}y · BPV %{y:,.0f} €/bp · %{customdata[0]:.0f}M<br>"
                      "Pay %{customdata[1]:.2f}% / Rec %{customdata[2]:.2f}%<extra></extra>"))
    fig = ds.style_figure(fig, height=340)
    return ds.axisTitles(fig.update_layout(hovermode="closest"), "Time to maturity (y)")


FV_MATBUCKETS = [("≤5y", "circle", ds.HEX["positive"]),
                 ("5–10y", "square", ds.HEX["primary"]),
                 (">10y", "diamond", ds.HEX["secondary"])]


def _fv_group(mat):
    return "≤5y" if mat <= 5 else ("5–10y" if mat <= 10 else ">10y")


def fig_fair_value(cdf):
    m = {r: i for i, r in enumerate(RATING_ORDER)}
    d = cdf.dropna(subset=["spread", "mv", "mat"]).copy()
    d["notch"] = d["rating"].astype(str).str.strip().str.upper().map(m)
    d = d.dropna(subset=["notch"])
    if not len(d):
        return _empty_fig("No rated positions with a spread.", 440)
    d["mgrp"] = d["mat"].map(_fv_group)
    d["fair"] = np.nan
    fig = go.Figure()
    for name, _sym, shade in FV_MATBUCKETS:
        g = d[d["mgrp"] == name]
        if not len(g):
            continue
        med = g.groupby("notch")["spread"].median().sort_index()
        d.loc[g.index, "fair"] = g["notch"].map(med).values
        fig.add_scatter(x=med.index, y=med.values, mode="lines", name=f"Fair {name}",
                        line=dict(color=shade, width=1.8, dash="dot"), hoverinfo="skip")
    d["resid"] = d["spread"] - d["fair"]
    for name, sym, _shade in FV_MATBUCKETS:
        g = d[(d["mgrp"] == name) & d["resid"].notna()]
        if not len(g):
            continue
        colors = [ds.HEX["positive"] if r >= 0 else ds.HEX["negative"] for r in g["resid"]]
        fig.add_scatter(x=g["notch"], y=g["spread"], mode="markers", showlegend=False,
            text=g["issuer"], customdata=np.stack([g["rating"], g["resid"], g["mat"]], axis=-1),
            marker=dict(size=_bubble(g["mv"]), sizemin=4, color=colors, symbol=sym,
                        line=dict(width=1, color="#FFF"), opacity=0.9),
            hovertemplate="<b>%{text}</b> (%{customdata[0]}, %{customdata[2]:.1f}y)<br>"
                          "Spread %{y:.0f}bp · %{customdata[1]:+.0f}bp vs fair<extra></extra>")
    for nm, col in [("Cheap (buy)", ds.HEX["positive"]), ("Rich (trim)", ds.HEX["negative"])]:
        fig.add_scatter(x=[None], y=[None], mode="markers", name=nm,
                        marker=dict(size=10, color=col, symbol="circle"))
    ticks = sorted(int(i) for i in d["notch"].dropna().unique())
    fig = ds.style_figure(fig, height=440, legend=True)
    fig.update_layout(hovermode="closest",
        xaxis=dict(tickmode="array", tickvals=ticks, ticktext=[RATING_ORDER[i] for i in ticks]))
    ds.axisTitles(fig, "Rating", "I-Spread (bp)")
    return legend_right(fig)


def fig_carry_risk():
    d = B.dropna(subset=["dts", "spread", "mv", "dur"]).copy()
    if not len(d):
        return _empty_fig("No positions with DTS + spread.", 470)
    g = _spread_term(B, "spread")
    mids = np.array([_BUCKET_MID[l] for l in g.index], dtype=float)
    slope = float(np.polyfit(mids, g.values, 1)[0]) if len(g) > 1 else 0.0
    d["carry"] = d["spread"] + d["dur"] * slope
    x, y = d["dts"].to_numpy(float), d["carry"].to_numpy(float)
    fig = go.Figure(go.Scatter(
        x=x, y=y, mode="markers", text=d["issuer"],
        marker=dict(size=_bubble(d["mv"]), sizemin=4, color=_sec_colors(d["sector"]),
                    line=dict(width=1, color="#FFF"), opacity=0.9),
        hovertemplate="<b>%{text}</b><br>DTS %{x:.0f} · Carry %{y:.0f} bp/y<extra></extra>"))
    fx, fy, best = [], [], -np.inf
    for i in np.argsort(x):
        if y[i] > best:
            best = y[i]; fx.append(x[i]); fy.append(y[i])
    fig.add_scatter(x=fx, y=fy, mode="lines", line=dict(color=ds.HEX["highlight"], width=2),
                    hoverinfo="skip")
    fig = ds.style_figure(fig, height=440)
    fig.update_layout(hovermode="closest")
    return ds.axisTitles(fig, "Spread risk — DTS (y·bp)", "Expected carry (bp/y)")


def fig_dts_concentration():
    d = B.dropna(subset=["dts", "mv"])
    if not len(d):
        return _empty_fig("No DTS data.", 470)
    share = (d.assign(c=d["dts"] * d["mv"]).groupby("issuer")["c"].sum()
             .sort_values(ascending=False))
    share = share / share.sum()
    n = len(share)
    x = np.concatenate([[0], np.arange(1, n + 1) / n * 100])
    cum = np.concatenate([[0], share.cumsum().to_numpy() * 100])
    hhi = float((share ** 2).sum() * 1e4)
    top5 = float(share.head(5).sum() * 100)
    fig = go.Figure()
    fig.add_scatter(x=[0, 100], y=[0, 100], mode="lines", hoverinfo="skip",
                    line=dict(color=ds.HEX["border"], width=1, dash="dot"))
    fig.add_scatter(x=x, y=cum, mode="lines", fill="tozeroy", fillcolor="rgba(33,88,128,.10)",
                    line=dict(color=ds.HEX["primary"], width=2.5),
                    hovertemplate="Top %{x:.0f}% of names · %{y:.0f}% of DTS<extra></extra>")
    fig.add_annotation(x=2, y=98, xanchor="left", yanchor="top", showarrow=False,
        text=f"<b>HHI {hhi:,.0f}</b>   ·   Top-5 = {top5:.0f}% of DTS".replace(",", " "),
        font=dict(family=ds.FONT["family"], size=12, color=ds.HEX["text"]))
    fig = ds.style_figure(fig, height=440)
    fig.update_layout(hovermode="closest")
    return ds.axisTitles(fig, "Cumulative share of issuers (%)", "Cumulative share of DTS (%)")


def fig_fx_exposure():
    d = B.dropna(subset=["mv"])
    g = (d[d["ccy"].astype(str).str.upper() != "EUR"].groupby("ccy")["mv"].sum()
         / NAV * 100).sort_values(ascending=False)
    if not len(g):
        return _empty_fig("100% EUR — no FX exposure.", 260)
    fig = go.Figure(go.Bar(
        x=g.values, y=g.index, orientation="h", marker_color=ds.HEX["secondary"],
        text=[f"{v:.2f}%" for v in g.values], textposition="outside",
        hovertemplate="%{y}: %{x:.2f}% of NAV<extra></extra>"))
    fig.add_vline(x=5, line=dict(color=ds.HEX["negative"], width=1.5, dash="dash"))
    fig.add_annotation(x=5, y=1, yref="y domain", yanchor="bottom", xanchor="left",
        text=" 5% limit", showarrow=False,
        font=dict(size=10, color=ds.HEX["negative"], family=ds.FONT["family"]))
    fig = ds.style_figure(fig, height=max(220, 70 + 34 * len(g)))
    fig.update_layout(hovermode="closest", margin=dict(t=20, b=30, l=8, r=64))
    return ds.axisTitles(fig, "% of NAV")


def fig_carry_treemap():
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
    fig.update_layout(**ds.layoutNoAxes(), height=440, margin=dict(l=0, r=0, t=10, b=0))
    return fig


def fig_curve_signature():
    net = ladder(D, "ir")["Netto"]
    fig = go.Figure(go.Bar(
        x=net.index, y=net.values,
        marker_color=[ds.HEX["primary"] if v >= 0 else ds.HEX["negative"] for v in net.values],
        text=[f"{v:+,.0f}".replace(",", " ") for v in net.values],
        textposition="outside", textfont=dict(size=10),
        hovertemplate="%{x}: net DV01 %{y:,.0f} €/bp<extra></extra>"))
    front = net.reindex(["0-2y", "2-4y"]).sum()
    belly = net.reindex(["4-6y", "6-8y", "8-10y"]).sum()
    long_ = net.reindex(["10-15y", "15-25y", "25y+"]).sum()
    bias = "Flattener bias (long-end heavy)" if long_ > front else "Steepener bias (front heavy)"
    txt = (f"<b>Σ Net {net.sum():+,.0f} €/bp</b>  (per-bucket, offsetting) · "
           f"Front ≤4y {front:+,.0f} · Belly {belly:+,.0f} · Long >10y {long_:+,.0f}"
           f"   →  {bias}").replace(",", " ")
    fig.add_annotation(x=0, y=1.14, xref="x domain", yref="y domain", xanchor="left",
        showarrow=False, text=txt,
        font=dict(family=ds.FONT["family"], size=12, color=ds.HEX["text"]))
    fig = ds.style_figure(fig, height=400)
    fig.update_layout(hovermode="closest", margin=dict(t=48, b=30, l=8, r=64))
    return ds.axisTitles(fig, y="Net DV01 (€/bp)")


_BUCKET_MID = {lbl: (lo + hi) / 2 if hi < 90 else lo + 3 for lo, hi, lbl in MAT_BUCKETS}


def _spread_term(df: pd.DataFrame, col: str) -> pd.Series:
    d = df.dropna(subset=[col, "mv"])
    return (d.groupby("bucket").apply(lambda x: np.average(x[col], weights=x["mv"]),
            include_groups=False).reindex(BUCKET_LABELS).dropna())


def fig_spread_terms():
    isp, oas = _spread_term(B, "spread"), _spread_term(B, "oas")
    fig = go.Figure()
    fig.add_scatter(x=list(isp.index), y=isp.values, mode="lines+markers", name="I-Spread",
                    line=dict(color=ds.HEX["primary"], width=2.5), marker=dict(size=8),
                    hovertemplate="%{x}: I-Spread %{y:.0f} bp<extra></extra>")
    fig.add_scatter(x=list(oas.index), y=oas.values, mode="lines+markers", name="OAS",
                    line=dict(color=ds.HEX["secondary"], width=2.5), marker=dict(size=8),
                    hovertemplate="%{x}: OAS %{y:.0f} bp<extra></extra>")
    fig = ds.style_figure(fig, height=440, legend=True)
    fig.update_layout(hovermode="x unified")
    ds.axisTitles(fig, "Maturity bucket", "Spread (bp)")
    return legend_right(fig)


def fig_rate_vs_spread():
    fig = go.Figure()
    if CURVES is not None and "swap" in CURVES.columns:
        cx = pd.to_numeric(CURVES["tenor"], errors="coerce")
        cy = pd.to_numeric(CURVES["swap"], errors="coerce")
        base_name = "EUR swap curve"
    else:
        s = D["swaps"].dropna(subset=["mat_y", "pay"])
        sw = s.groupby(s["mat_y"].round(1))["pay"].mean().sort_index()
        cx, cy, base_name = pd.Series(sw.index), pd.Series(sw.values), "Swap fixed rate (book)"
    m = cx.notna() & cy.notna()
    cx, cy = cx[m].to_numpy(float), cy[m].to_numpy(float)
    o = np.argsort(cx); cx, cy = cx[o], cy[o]
    fig.add_scatter(name=base_name, x=cx, y=cy, mode="lines+markers",
                    line=dict(color=ds.HEX["primary"], width=2.5), marker=dict(size=6),
                    hovertemplate="%{x:.1f}y · %{y:.2f}%<extra></extra>")
    sp = _spread_term(B, "spread")
    sx = np.array([_BUCKET_MID[l] for l in sp.index], dtype=float)
    port = (np.interp(sx, cx, cy) if len(cx) else np.zeros_like(sx)) + sp.values / 100.0
    fig.add_scatter(name="Portfolio yield (swap + spread)", x=sx, y=port, mode="lines+markers",
                    line=dict(color=ds.HEX["highlight"], width=2.5), marker=dict(size=7),
                    fill="tonexty", fillcolor="rgba(33,88,128,.10)", customdata=sp.values,
                    hovertemplate="%{x:.1f}y · %{y:.2f}% (spread %{customdata:.0f} bp)<extra></extra>")
    fig = ds.style_figure(fig, height=400, legend=True)
    fig.update_layout(hovermode="x unified")
    ds.axisTitles(fig, "Maturity (y)", "Rate (%)")
    return legend_right(fig)


FIGS = {
    "rate_vs_spread": fig_rate_vs_spread, "ladder_ir": fig_ladder_ir,
    "curve_signature": fig_curve_signature, "swapbook": fig_swapbook,
    "ladder_cs": fig_ladder_cs, "carry_treemap": fig_carry_treemap,
    "fx_exposure": fig_fx_exposure, "spread_terms": fig_spread_terms,
    "fair_value": lambda: fig_fair_value(B), "carry_risk": fig_carry_risk,
    "dts_concentration": fig_dts_concentration,
}
FIGS = {k: fn() for k, fn in FIGS.items()}


def dropdown(cid, options, value, width="260px"):
    return dcc.Dropdown(id=cid, options=[{"label": o, "value": o} for o in options],
                        value=value, clearable=False,
                        style={"width": width, "fontFamily": ds.FONT["family"],
                               "fontSize": "13px"})


def _portfolio_digest() -> str:
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
        f"Gross rate DV01 {M['ir_long']:.0f} | Hedge DV01 {M['ir_hedge']:.0f} | Net {M['ir_net']:.0f} | Net duration (NAV) {M['dur_net']:.2f}y | Hedge ratio {M['hedge_ratio']:.1%}",
        f"CS01 total {M['cs01']:.0f} (bonds {M['cs01_bonds']:.0f}, CDS {M['cs01_cds']:.0f}) | Spread duration (NAV) {M['dur_spread']:.2f}y | DTS {M['dts']:.1f}",
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


COPILOT_SYSTEM = (
    "You are the portfolio copilot for the nordIX Interest Rate Hedged Bond Fund — a precise, "
    "quantitative fixed-income analyst answering in concise institutional English. Use the tools "
    "to fetch live portfolio data (metrics, allocations, positions) and the "
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
    {"type": "web_search_20250305", "name": "web_search", "max_uses": 6},
]


def _copilot_tool(name: str, inp: dict) -> str:
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
    return f"unknown tool: {name}"


def _copilot_reply(question: str) -> str:
    try:
        cl = _anthropic()
        msgs = [{"role": "user", "content": question}]
        r = None
        for _ in range(6):
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
    try:
        msg = _anthropic().messages.create(
            model="claude-opus-4-8", max_tokens=3000,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}],
            system=[{"type": "text", "text": NEWS_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": question}])
        return _answer_text(msg)
    except Exception as e:
        return f"⚠️ Error during web search: {e}"


def note(text: str):
    return html.Div(text, style={**ds.LABEL_STYLE, "textTransform": "none",
                                 "letterSpacing": 0, "marginTop": "10px"})


def block(title: str, content):
    return html.Div([ds.section(title), ds.panel(content)])


def credit_toggle():
    return html.Div([
        html.Span("Source:", style={**ds.LABEL_STYLE, "marginRight": "10px"}),
        dcc.RadioItems(id="credit-src", value="Bond + CDS", inline=True,
                       options=[{"label": s, "value": s} for s in CREDIT_SRC],
                       inputStyle={"marginRight": "5px"},
                       labelStyle={"marginRight": "18px", "fontFamily": ds.FONT["family"],
                                   "fontSize": "13px", "color": ds.COLORS["text"]}),
    ], style={"display": "flex", "alignItems": "center", "margin": "18px 0 -4px"})


def _grid(boxes):
    return html.Div(boxes, style={"display": "flex", "flexWrap": "wrap", "gap": "10px",
                                  "margin": "6px 0 18px"})


def grid2(*cols):
    return html.Div([html.Div(c, style={"flex": "1 1 460px", "minWidth": "0"}) for c in cols],
                    style={"display": "flex", "flexWrap": "wrap", "gap": "0 22px"})


def bullet(label, value, limit, kind, fmt):
    if kind == "range":
        lo, hi = limit
        ok, mark, lim_txt = lo <= value <= hi, (value - lo) / ((hi - lo) or 1.0), f"{fmt.format(lo)} … {fmt.format(hi)}"
    else:
        ok, mark, lim_txt = value <= limit, (value / limit if limit else 0.0), f"≤ {fmt.format(limit)}"
    col = ds.COLORS["primary"] if ok else ds.COLORS["negative"]
    fill = min(100.0, max(3.0, mark * 100))
    return html.Div([
        html.Div([html.Span(label, style={**ds.LABEL_STYLE, "textTransform": "none", "letterSpacing": 0}),
                  html.Span(fmt.format(value), style={"marginLeft": "auto", "fontFamily": ds.FONT["numeric"],
                            "fontWeight": 600, "color": col, "fontVariantNumeric": "tabular-nums"})],
                 style={"display": "flex", "alignItems": "baseline", "marginBottom": "5px"}),
        html.Div(html.Div(style={"width": f"{fill}%", "height": "100%", "background": col, "borderRadius": "3px"}),
                 style={"height": "6px", "background": ds.COLORS["surface"], "borderRadius": "3px",
                        "border": f"1px solid {ds.COLORS['border']}", "overflow": "hidden"}),
        html.Div(lim_txt, style={**ds.LABEL_STYLE, "textTransform": "none", "letterSpacing": 0,
                                 "fontSize": "9.5px", "marginTop": "4px", "opacity": 0.8}),
    ], style={"flex": "1 1 190px", "minWidth": "170px", "padding": "4px 2px"})


def cockpit():
    return html.Div([bullet(*r) for r in RISK],
                    style={"display": "flex", "flexWrap": "wrap", "gap": "10px 22px", "margin": "6px 0 18px"})


def overview_board():
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
    fund_section = ([_grid(fund)] if fund else [])
    return html.Div(fund_section + [
        cockpit(),
        _grid([
            stat("Gross Rate DV01", f"{fmt(M['ir_long'])} €/bp", "bonds + futures"),
            stat("Hedge DV01", f"{fmt(M['ir_hedge'])} €/bp", f"{M['n_swaps']} payer swaps", C["negative"]),
            stat("Net DV01", f"{fmt(M['ir_net'])} €/bp", "residual rate risk"),
            stat("Spread Duration", f"{M['dur_spread']:.2f} y", "fund, bonds + CDS on NAV"),
            stat("WAM", f"{M['wam']:.1f} y", "avg time to maturity"),
            stat("Net Duration", f"{M['dur_net']:.2f} y", "fund, rate after hedges on NAV"),
            stat("Convexity", f"{M['conv']:.2f}", "MV-weighted"),
        ]),
        _grid([
            stat("CS01 Total", f"{fmt(M['cs01'])} €/bp",
                 f"bonds {fmt(M['cs01_bonds'])} · CDS {fmt(M['cs01_cds'])}"),
            stat("CS01 Bonds", f"{fmt(M['cs01_bonds'])} €/bp", "cash book"),
            stat("CS01 CDS", f"{fmt(M['cs01_cds'])} €/bp", "overlay", C["highlight"]),
            stat("Avg I-Spread", f"{M['spread_avg']:.0f} bp", "MV-weighted, cash book"),
            stat("Avg OAS", f"{M['oas_avg']:.0f} bp", "option-adjusted"),
            stat("Avg CDS Spread", f"{M['cds_spread_avg']:.0f} bp", "notional-weighted, overlay", C["highlight"]),
            stat("Carry Efficiency", f"{M['spd']:.1f} bp/y", "spread per duration", C["highlight"]),
        ]),
        _grid([
            stat("Total Credit Carry", f"{(M['spread_mv'] + M['cds_prem'])/NAV:.0f} bp",
                 "bond spread + CDS premium, over risk-free"),
            stat("Bond Spread Carry", f"{M['spread_mv']/NAV:.0f} bp", "MV-weighted I-spread, % of NAV"),
            stat("CDS Premium", f"{M['cds_prem']/NAV:+.0f} bp",
                 "net running premium, sold − bought", C["highlight"]),
        ]),
        _grid([
            stat("Credit Heat", eur(M['credit_heat']), "bond MV + CDS net"),
            stat("Nominal (FV) Bonds", eur(M['fv']), "sum of face values"),
            stat("Bond MV", eur(M['mv']), "cash book market value"),
            stat("CDS Heat (net)", eur(M['cds_notional']),
                 "notional, by protection side", C["highlight"]),
            stat("Net Exposure", f"{M['credit_heat']/NAV:.0%}", "credit heat / NAV"),
        ]),
        block("FX Exposure", chart(FIGS["fx_exposure"], "fx1")),
    ], style={"paddingTop": "20px"})


def tab_overview():
    return ds.container([overview_board()], max_width=1400)


def tab_rates():
    return ds.container([
        block("Risk-free Curve vs. Portfolio Spread", chart(FIGS["rate_vs_spread"], "cv")),
        grid2(block("Rate Risk", chart(FIGS["ladder_ir"], "c1")),
              block("Curve Signature", chart(FIGS["curve_signature"], "r1"))),
        block("Hedge Book", chart(FIGS["swapbook"], "r2")),
    ], max_width=1400)


def tab_credit():
    cv0 = credit_view(D, CREDIT_SRC[0])
    return ds.container([
        credit_toggle(),
        grid2(
            block("Credit Map", [
                html.Div([dropdown("cmap-x", list(CMAP_AXES), "Duration (y)", "190px"),
                          dropdown("cmap-y", list(CMAP_AXES), "I-Spread (bp)", "190px")],
                         style={"display": "flex", "gap": "14px", "marginBottom": "8px"}),
                dcc.Graph(id="cmap", config={"displaylogo": False}, figure=fig_credit_map(cv0))]),
            block("Hotspots", chart(fig_heatmap(cv0), "cr2"))),
        grid2(
            block("Spread Term Structure", chart(FIGS["spread_terms"], "spread-curve")),
            block("Spread Risk", chart(FIGS["ladder_cs"], "c2"))),
        grid2(
            block("Fair Value", chart(FIGS["fair_value"], "fv2")),
            block("Carry vs. Risk", chart(FIGS["carry_risk"], "crsk"))),
        grid2(
            block("Credit Concentration", chart(FIGS["dts_concentration"], "dtsc")),
            block("Capital vs. Carry", chart(FIGS["carry_treemap"], "i4"))),
        block("Top 20 positions", ds.data_table(
            data=POS_VIEW.nlargest(20, "MV(M)")[TOP10_COLS].to_dict("records"),
            columns=[{"name": c, "id": c} for c in TOP10_COLS], page_action="none",
            fixed_rows={"headers": False}, style_table={**ds.TABLE_STYLE, "maxHeight": "none"})),
    ], max_width=1400)


def tab_positionen():
    return ds.container([
        block(f"All positions ({len(POS)})", [
            html.Div(dropdown("pos-art", ["All"] + POS_TYPES, "All", "200px"),
                     style={"marginBottom": "10px"}),
            ds.data_table(
                id="pos-table", data=POS_VIEW.to_dict("records"),
                columns=[{"name": c, "id": c} for c in POS_COLS],
                filter_action="native", sort_action="native", page_action="none",
                cell_selectable=True, include_headers_on_copy_paste=True,
                export_format="xlsx", export_headers="display",
                style_filter=FILTER_STYLE, style_table={**ds.TABLE_STYLE, "maxHeight": "80vh"})]),
        block("News Radar", [
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
    return ds.data_table(
        data=df.to_dict("records"),
        columns=[{"name": c, "id": c} for c in df.columns],
        page_action="none", export_format="csv", export_headers="display",
        fixed_rows={"headers": False},
        style_data_conditional=[{"if": {"filter_query": '{' + df.columns[0] + '} = "Σ Total"'},
                                 "fontWeight": 700, "background": ds.COLORS["surface"]}],
        style_cell={**getattr(ds, "TABLE_CELL_STYLE", {}), "fontFamily": ds.FONT["family"],
                    "fontSize": "13px", "fontVariantNumeric": "tabular-nums"},
        style_table={**ds.TABLE_STYLE, "maxHeight": "none"})


def tab_reporting():
    b = D["bonds"]
    cy = float((b["coupon"] * b["nom"]).sum() / b["mv"].sum() * 100)
    key = [
        stat("As of", FACTS.get("asof", "—"), FUND_META["name"]),
        stat("TER", FUND_META["ter"], "p.a."),
        stat("Avg Rating (MVw)", avg_rating(b), f"{M['n_bonds']} bonds"),
        stat("WAM", f"{M['wam']:.2f} y", "avg time to maturity"),
        stat("Net Duration", f"{M['dur_net']:.2f} y", "rate, after hedges, on NAV", ds.COLORS["highlight"]),
        stat("Avg Current Yield", f"{cy:.2f} %", "MV-weighted"),
        stat("Avg Coupon", f"{M['coupon']:.2f} %", "running"),
        stat("Avg I-Spread", f"{M['spread_avg']:.0f} bp", f"OAS {M['oas_avg']:.0f} bp"),
    ]
    return ds.container([
        ds.section("Key Data"),
        _grid(key),
        block("Allocation by asset class (net, % NAV)",
              rep_table(alloc_assetclass(D, NAV, CASH))),
        block("Sector allocation (net, % NAV)",
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


PF_SUBTABS = [("Overview", "overview", tab_overview),
              ("Credit", "credit", tab_credit), ("Rates", "rates", tab_rates),
              ("Positions & AI", "pos", tab_positionen)]


def data_error_panel(title: str, detail: str):
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


CREDIT_MODES = {"Corporate": "corp", "Financial": "fin", "Sovereign / SSA": "sov"}
_CM_PATHS = [r"q:\00_pm\6_ai\0_code", r"S:\benjaminSuermann\3_env"]
_CM_ENGINE_FILE = r"q:\00_pm\6_ai\0_code\creditManagement.py"
_cm_mod = None

ISS_INPUT = {"flex": "1", "minWidth": "220px", "padding": "9px 12px", "fontFamily": ds.FONT["family"],
             "fontSize": "14px", "border": f"1px solid {ds.COLORS['border']}", "borderRadius": "6px",
             "backgroundColor": "#FFFFFF", "color": ds.COLORS["text"], "boxSizing": "border-box"}
ISS_DROP = {"border": f"1.5px dashed {ds.COLORS['primary']}", "borderRadius": "6px", "padding": "14px",
            "textAlign": "center", "cursor": "pointer", "margin": "10px 0", "background": ds.COLORS["surface"],
            "fontFamily": ds.FONT["family"], "fontSize": "13px", "color": ds.COLORS["secondary"]}


def _cm():
    global _cm_mod
    if _cm_mod is None:
        for p in _CM_PATHS:
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


def tab_iss_credit():
    return html.Div([
        block("Credit analysis — 17-point memo (Opus 4.8, web search + verification)", [
            _issuer_controls("cred-mode", "cred-input", "cred-run", "Analyze", "cred-status",
                             "Issuer (e.g. Volkswagen AG, Deutsche Bank AG)…"),
            note("Cache-first: known issuers load instantly, new ones run live (~1–2 min, billable).")]),
        dcc.Loading(type="dot", color=ds.COLORS["primary"], children=html.Div(id="cred-output")),
        dcc.Store(id="cred-store"),
    ], style={"paddingTop": "4px"})


LIQ_MILD = {
    "corp": {"rev_growth": 5, "ebitda_shock": 0, "rate_shock_bp": 0, "capex_flex": 90, "rcf_avail": 100, "market_access": 1},
    "fin": {"income_shock": -10, "cor_shock": 1, "rwa_growth": 2, "deposit_outflow": 0, "payout": 40},
    "sov": {"gdp_shock": 0, "rate_shock_bp": 0, "primary_balance_delta": 1, "fx_shock": 0},
}
LIQ_HARSH = {
    "corp": {"rev_growth": -3, "ebitda_shock": 20, "rate_shock_bp": 200, "capex_flex": 110, "rcf_avail": 60, "market_access": 0},
    "fin": {"income_shock": 10, "cor_shock": 3, "rwa_growth": 8, "deposit_outflow": 15, "payout": 60},
    "sov": {"gdp_shock": 4, "rate_shock_bp": 200, "primary_balance_delta": -2, "fx_shock": 20},
}


def _fill_none(seq):
    out, last = list(seq), None
    for i, v in enumerate(out):
        out[i] = last if v is None else v
        last = out[i] if v is not None else last
    nxt = None
    for i in range(len(out) - 1, -1, -1):
        if out[i] is None:
            out[i] = nxt
        else:
            nxt = out[i]
    return [float(x) if x is not None else 0.0 for x in out]


def _fig_liq(label, hist_x, hist_y, fwd_x, base_y, lo, hi, hline=None):
    fig = go.Figure()
    fig.add_scatter(x=list(fwd_x) + list(fwd_x)[::-1], y=list(hi) + list(lo)[::-1], fill="toself",
                    fillcolor="rgba(78,106,134,.14)", line=dict(width=0), hoverinfo="skip", showlegend=False)
    if len(hist_x) > 1:
        fig.add_scatter(x=hist_x, y=hist_y, mode="lines+markers", line=dict(color=ds.HEX["ink"], width=2),
                        marker=dict(size=5), hovertemplate="%{x}: %{y:,.1f}<extra></extra>")
    fig.add_scatter(x=fwd_x, y=base_y, mode="lines+markers",
                    line=dict(color=ds.HEX["primary"], width=2, dash="dot"), marker=dict(size=5),
                    hovertemplate="%{x}: %{y:,.1f}<extra></extra>")
    if hline:
        fig.add_hline(y=hline, line=dict(color=ds.HEX["negative"], width=1, dash="dash"))
    fig = ds.style_figure(fig, height=230)
    return fig.update_layout(hovermode="x unified", showlegend=False,
        title=dict(text=label, x=0, font=dict(family=ds.FONT["family"], size=13, color=ds.HEX["text"])),
        margin=dict(t=34, b=24, l=8, r=14))


def build_liq_fans(mode, data, cm):
    inputs = {f["key"]: data.get(f["key"]) for f in cm.liquidity.LIQ_INPUTS[mode]}
    hist = data.get("history") or {}
    t0 = pd.Timestamp.today().year
    base = cm.liquidity.project(mode, inputs, {}, t0=t0, history=hist)
    mild = cm.liquidity.project(mode, inputs, LIQ_MILD[mode], t0=t0)
    harsh = cm.liquidity.project(mode, inputs, LIQ_HARSH[mode], t0=t0)
    labels, fwd = cm.liquidity.LABELS, [t0 + i for i in range(5)]

    def _f(v):
        try:
            return float(v)
        except Exception:
            return 0.0
    cards = []
    for key in base["table"]:
        b = base["series"].get(key)
        if not b:
            continue
        b = _fill_none(b)
        m, h = _fill_none(mild["series"].get(key, b)), _fill_none(harsh["series"].get(key, b))
        lo = [min(m[i], h[i]) for i in range(len(fwd))]
        hi = [max(m[i], h[i]) for i in range(len(fwd))]
        hv = [float(x) for x in (hist.get(key) or [])][-4:]
        if hv:
            hx, hy = [t0 - len(hv) + i for i in range(len(hv))] + [t0], hv + [b[0]]
        else:
            hx, hy = [t0], [b[0]]
        hline = None
        if key == "leverage" and _f(inputs.get("leverage_covenant")) > 0:
            hline = _f(inputs.get("leverage_covenant"))
        elif key == "cet1_ratio" and _f(inputs.get("mda_trigger")) > 0:
            hline = _f(inputs.get("mda_trigger"))
        elif key in ("lcr", "nsfr"):
            hline = 100
        cards.append(html.Div(dcc.Graph(figure=_fig_liq(labels.get(key, key), hx, hy, fwd, b, lo, hi, hline),
                     config={"displaylogo": False}), style={"flex": "1 1 330px", "minWidth": "300px"}))
    head = base.get("headline", {})
    top = ds.panel([
        html.Div(f"{data.get('company', '')} · {mode.upper()} · {head.get('constraint', '')}",
                 style={**ds.LABEL_STYLE, "textTransform": "none", "letterSpacing": 0, "fontSize": "12px"}),
        html.Div(data.get("commentary", ""), style={"fontFamily": ds.FONT["family"], "fontSize": "13px",
                 "color": ds.COLORS["text"], "marginTop": "6px", "lineHeight": 1.5})])
    return html.Div([top, html.Div(cards, style={"display": "flex", "flexWrap": "wrap", "gap": "6px"})])


def tab_iss_liquidity():
    return html.Div([
        block("Financials — history + forward range", [
            _issuer_controls("liqm-mode", "liqm-input", "liqm-run", "Build model", "liqm-status",
                             "Issuer…"),
            note("Enter an issuer and pick its type. The key financial metrics are fetched and shown as "
                 "actuals plus a forward range (favourable–adverse fan). ~15–30 s, billable.")]),
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
    rng = np.random.default_rng(seed)
    n = 104
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=n, freq="W-MON")
    out = {}
    for t in SENTIMENT_TERMS:
        x = np.zeros(n)
        for i in range(1, n):
            x[i] = 0.85 * x[i - 1] + rng.normal()
        out[t] = (x - x.mean()) / (x.std() or 1.0)
    return pd.DataFrame(out, index=idx)


def sentiment_load() -> pd.DataFrame:
    try:
        if SENTIMENT_CSV.exists():
            df = pd.read_csv(SENTIMENT_CSV, index_col=0, parse_dates=True)
            if len(df) and all(t in df.columns for t in SENTIMENT_TERMS):
                return df
    except Exception as ex:
        print(f"[markets] sentiment.csv unlesbar, nutze Demo: {ex}")
    return _sentiment_demo()


def sentiment_agg(df: pd.DataFrame) -> pd.DataFrame:
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
                  fill="tozeroy", fillcolor="rgba(33,88,128,.08)")
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
        return texts[-1].strip() if texts else "_(no answer)_"
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
    raise ValueError(f"Date not recognized: {s!r}")


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
    raise ValueError(f"Time not recognized: {time_str!r}")


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
    import win32com.client as win32
    tpl = str(BVI_TEMPLATE)
    if not os.path.exists(tpl):
        raise RuntimeError(f"Template not found: {tpl}")
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
        if last >= BVI_FIRST_ROW:
            ws.Range(ws.Cells(BVI_FIRST_ROW, 1), ws.Cells(last, 40)).ClearContents()
        for i, row in enumerate(rows):
            r = BVI_FIRST_ROW + i
            for col, val in row.items():
                if val == "" or val is None:
                    continue
                c = ws.Cells(r, bvi_col_num(col))
                if col in ("U", "W"):
                    c.NumberFormatLocal = "TT.MM.JJJJ"
                    c.Value = (val - datetime.date(1899, 12, 30)).days
                elif col == "V":
                    c.NumberFormatLocal = "@"
                    c.Value = val
                elif col == "L":
                    c.NumberFormatLocal = "0,##########"
                    c.Value = val
                else:
                    c.Value = val
        wb.SaveAs(dest, FileFormat=56)
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
        blocks.append({"type": "text", "text": "Text sources:\n\n" + "\n\n".join(texts)})
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


def tab_experts():
    return ds.container([
        block("Experts", note("Trainable knowledge experts — coming soon."))
    ], max_width=1400)


ADMIN_SUBTABS = [("Experts", "experts", tab_experts), ("BVI", "bvi", tab_bvi)]


def admin_analysis():
    return html.Div([dcc.Tabs(value="bvi", style={"marginTop": "10px"}, children=[
        dcc.Tab(label=lbl, value=val, style=TAB_STYLE, selected_style=TAB_SELECTED, children=build())
        for lbl, val, build in ADMIN_SUBTABS])])


TOP_TABS = [("Markets", "markets", markets_analysis),
            ("Portfolio", "pf", portfolio_analysis),
            ("Issuer", "iss", issuer_analysis),
            ("Admin", "admin", admin_analysis)]

app = Dash(__name__, title="nordIX", suppress_callback_exceptions=True)
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
  /* Native filter row: theme the white inputs to match the design */
  .dash-spreadsheet-container input.dash-filter--case,
  .dash-spreadsheet-container .dash-filter input,
  .dash-spreadsheet-container .dash-filter{
    background:var(--c-bg)!important;color:var(--c-text)!important;border:none!important;
    font-family:'Helvetica Neue',Arial,sans-serif!important;font-size:12px!important;font-style:normal!important}
  .dash-spreadsheet-container .dash-filter{border-bottom:1px solid var(--c-hairline)!important}
  .dash-spreadsheet-container .dash-filter input::placeholder{color:var(--c-muted)!important;opacity:.75}
  .dash-spreadsheet-container .dash-cell--selected,
  .dash-spreadsheet-container td.focused{background:var(--c-tint)!important;
    outline:1px solid var(--c-brand)!important}
  /* Neutral scrollbars (read on both themes) */
  *::-webkit-scrollbar{height:10px;width:10px}
  *::-webkit-scrollbar-thumb{background:rgba(128,128,128,.34);border-radius:6px}
  *::-webkit-scrollbar-thumb:hover{background:rgba(128,128,128,.5)}
  .tab,button,.Select-control{transition:color .15s,background .15s,border-color .15s,box-shadow .15s}
  input:focus,textarea:focus{outline:none;box-shadow:0 0 0 3px rgba(14,58,95,.16)}
  ::selection{background:rgba(14,58,95,.16)}
  /* Header control cluster */
  .cm-controls{position:fixed;top:14px;right:20px;z-index:60;display:flex;gap:8px}
  .cm-ctl{font-family:'Helvetica Neue',Arial,sans-serif;font-size:13px;line-height:1;cursor:pointer;
    width:32px;height:32px;border-radius:8px;border:1px solid var(--c-border);
    background:var(--c-surface);color:var(--c-text);display:flex;align-items:center;justify-content:center}
  .cm-ctl:hover{border-color:var(--c-brand);box-shadow:0 2px 8px rgba(14,58,95,.14)}
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
    padding:15px 18px;font-family:'Helvetica Neue',Arial,sans-serif;font-size:16px;background:var(--c-surface)!important;color:var(--c-text)!important}
  .cm-cmd-list{max-height:46vh;overflow:auto;border-top:1px solid var(--c-hairline)}
  .cm-cmd-item{padding:10px 18px;font-family:'Helvetica Neue',Arial,sans-serif;font-size:14px;color:var(--c-text);cursor:pointer}
  .cm-cmd-item.sel,.cm-cmd-item:hover{background:var(--c-tint)}
</style>
"""
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
    ds.brand_header(""),
    ds.container([dcc.Tabs(value="pf", children=[
        dcc.Tab(label=lbl, value=val, style=TOPTAB_STYLE, selected_style=TOPTAB_SELECTED, children=build())
        for lbl, val, build in TOP_TABS])], max_width=1460),
])


@app.callback(Output("mkt-cards", "children"), Output("mkt-agg", "figure"),
              Output("mkt-matrix", "data"), Output("mkt-matrix", "columns"),
              Output("mkt-msg", "children"), Input("mkt-refresh", "n_clicks"))
def refresh_sentiment(n):
    if n:
        try:
            _sentiment_demo(seed=int(n)).to_csv(SENTIMENT_CSV)
        except Exception as ex:
            print(f"[markets] sentiment.csv not writable: {ex}")
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
        sources = list(zip(contents, names or [f"file{i}" for i in range(len(contents))]))
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
        return _bvi_statusbox("No rows to save.", [], ds.COLORS["negative"])
    errs = bvi_validate(rows_in)
    if errs:
        return _bvi_statusbox("Please fix these first:", errs, ds.COLORS["negative"])
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
    return _bvi_statusbox(f"✓  {len(saved)} BVI file(s) saved",
                          [os.path.basename(p) for p in saved], ds.COLORS["positive"])


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


@app.callback(Output("cmap", "figure"), Output("cr2", "figure"),
              Input("credit-src", "value"), Input("cmap-x", "value"), Input("cmap-y", "value"))
def update_credit(src: str, xk: str, yk: str):
    cdf = credit_view(D, src)
    return fig_credit_map(cdf, xk, yk), fig_heatmap(cdf)


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
        panel = build_liq_fans(mode, data, cm)
    except Exception as ex:
        return _cm_error(f"Model failed: {ex}"), no_update, ""
    return panel, {"mode": mode}, ("from cache" if data.get("_cached") else "done")


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


@app.callback(Output("news-output", "children"),
              Input("news-send", "n_clicks"), State("news-input", "value"),
              prevent_initial_call=True)
def answer_news(_n_clicks: int, question: str):
    if not question or not question.strip():
        return "_Please enter a question._"
    return _news_reply(question.strip())


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(f"\n  >  Open the nordIX dashboard in your browser:  http://localhost:{PORT}\n")
    app.run(host="0.0.0.0", port=PORT, debug=False)
