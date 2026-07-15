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
from dash import Dash, html, dcc, dash_table, Input, Output, State, ctx, no_update
from dash.dash_table.Format import Format, Scheme, Symbol


class ds:
    HEX = {"background": "#0E0B24", "surface": "#221E34", "border": "#2A2740", "text": "#D4CEC0",
           "ink": "#E7E1D3", "muted": "#9691A9", "hairline": "rgba(192,163,100,.13)",
           "tint": "rgba(192,163,100,.12)", "header": "#0A081C", "navy": "#C0A364",
           "primary": "#C0A364", "secondary": "#9691A9", "positive": "#6BA793",
           "negative": "#B85C6A", "highlight": "#B0885A", "info": "#8F9E86"}
    COLORS = {k: (f"var(--c-{k})" if k in ("background", "surface", "border", "text", "ink",
              "muted", "hairline", "tint", "header") else v) for k, v in HEX.items()}
    FONT = {"family": "'Georgia Pro', Georgia, 'Times New Roman', serif",
            "numeric": "'Georgia Pro', Georgia, 'Times New Roman', serif",
            "serif": "'Georgia Pro', Georgia, 'Times New Roman', serif",
            "size_title": 30, "size_subtitle": 19, "size_body": 15, "size_label": 12,
            "weight_title": 400, "weight_body": 300}
    CHART_PALETTE = ["#C0A364", "#6BA793", "#9691A9", "#B85C6A", "#8F9E86", "#B0885A"]
    AXIS_TITLE_FONT = {"family": FONT["numeric"], "size": 11, "color": HEX["muted"], "weight": "bold"}
    RADIUS = {"sm": "2px", "md": "3px", "lg": "4px"}
    SHADOW = {"sm": "inset 0 1px 0 rgba(255,255,255,.05), 0 1px 2px rgba(0,0,0,.42), 0 12px 30px rgba(0,0,0,.26)",
              "md": "inset 0 1px 0 rgba(255,255,255,.06), 0 18px 46px rgba(0,0,0,.52), 0 4px 12px rgba(0,0,0,.4)"}
    LABEL_STYLE = {"fontFamily": FONT["serif"], "fontSize": "12px",
                   "textTransform": "lowercase", "letterSpacing": "0.3px", "fontWeight": 500,
                   "color": COLORS["secondary"]}
    TITLE_STYLE = {"fontFamily": FONT["serif"], "fontSize": f"{FONT['size_title']}px",
                   "fontWeight": 400, "color": COLORS["ink"], "letterSpacing": "0", "textTransform": "lowercase"}
    NUM_STYLE = {"fontFamily": FONT["numeric"], "fontVariantNumeric": "tabular-nums", "color": COLORS["ink"]}
    GOLD_GLOSS = "linear-gradient(180deg,#D9BF87 0%,#C0A364 52%,#A2854A 100%)"
    CARD_STYLE = {"background": "linear-gradient(180deg,rgba(255,255,255,.035),rgba(255,255,255,0) 34%),"
                  + COLORS["surface"], "border": f"1px solid {COLORS['border']}",
                  "borderRadius": RADIUS["lg"], "padding": "20px 22px", "boxShadow": SHADOW["sm"]}
    BUTTON_STYLE = {"fontFamily": FONT["serif"], "fontSize": "15px", "fontWeight": 500,
                    "padding": "9px 24px", "border": "1px solid #8F7539", "borderRadius": RADIUS["md"],
                    "background": GOLD_GLOSS, "color": "#0E0B24", "cursor": "pointer",
                    "letterSpacing": "0.3px", "textTransform": "lowercase",
                    "boxShadow": "inset 0 1px 0 rgba(255,255,255,.4), 0 2px 6px rgba(0,0,0,.38)"}
    TABLE_STYLE = {"overflowX": "auto", "borderRadius": RADIUS["lg"], "maxHeight": "560px"}
    TABLE_HEADER_STYLE = {"fontFamily": FONT["family"], "fontWeight": 700, "fontSize": "11px",
                          "textTransform": "lowercase", "letterSpacing": "0.4px",
                          "backgroundColor": COLORS["header"], "color": COLORS["navy"],
                          "border": f"1px solid {COLORS['border']}", "padding": "11px 10px", "textAlign": "center"}
    TABLE_CELL_STYLE = {"fontFamily": FONT["family"], "fontSize": "13px", "padding": "9px 10px",
                        "textAlign": "left", "color": COLORS["text"], "backgroundColor": COLORS["surface"],
                        "border": f"1px solid {COLORS['border']}", "whiteSpace": "normal", "minWidth": "72px"}
    PLOTLY_LAYOUT = {"paper_bgcolor": HEX["surface"], "plot_bgcolor": HEX["surface"],
                     "font": {"family": FONT["family"], "size": 12, "color": HEX["text"]},
                     "colorway": CHART_PALETTE,
                     "xaxis": {"gridcolor": HEX["hairline"], "linecolor": HEX["border"], "zeroline": False},
                     "yaxis": {"gridcolor": HEX["hairline"], "linecolor": HEX["border"], "zeroline": False}}

    @staticmethod
    def fmt_num(v, fmt="{:+,.2f}"):
        return fmt.format(v).replace("-", "−").replace(",", " ")

    @staticmethod
    def logo(size=44):
        px = max(15, int(size * 0.5))
        return html.Div([
            html.Span("nord", style={"fontFamily": ds.FONT["numeric"], "fontWeight": 700,
                                     "color": "var(--c-logo)", "letterSpacing": "0.2px"}),
            html.Span("IX", style={"fontFamily": ds.FONT["serif"], "fontWeight": 600,
                                   "color": "var(--c-brand)", "letterSpacing": "0.2px"}),
        ], style={"fontSize": f"{px}px", "lineHeight": "1", "display": "inline-flex", "alignItems": "baseline"})

    @staticmethod
    def page(children):
        return html.Div(children, className="cm-page", style={
            "background": "linear-gradient(180deg,#16112E 0%,#0E0B24 46%,#0A0819 100%)",
            "backgroundAttachment": "fixed", "minHeight": "100vh",
            "fontFamily": ds.FONT["family"], "color": ds.COLORS["text"]})

    @staticmethod
    def container(children, max_width=1200):
        return html.Div(children, style={"maxWidth": f"{max_width}px", "margin": "0 auto", "padding": "0 22px"})

    @staticmethod
    def panel(children, pad="20px 22px"):
        return html.Div(children, className="cm-panel", style={**ds.CARD_STYLE, "padding": pad, "marginBottom": "24px"})

    @staticmethod
    def section(text):
        return html.Div([
            html.Div(style={"width": "40px", "height": "2px", "marginBottom": "11px",
                            "background": "linear-gradient(90deg,#D9BF87,rgba(192,163,100,0))",
                            "boxShadow": "0 0 9px rgba(192,163,100,.55)"}),
            html.Div(text, style={"fontFamily": ds.FONT["serif"], "fontSize": "22px", "fontWeight": 400,
                                  "letterSpacing": "0.2px", "color": ds.COLORS["ink"], "textTransform": "lowercase"})],
            style={"margin": "48px 2px 20px"})

    @staticmethod
    def brand_header(title=None, subtitle=None, meta=None):
        left = []
        if title:
            left.append(html.Div(title, style={**ds.TITLE_STYLE, "lineHeight": "1.1"}))
        if subtitle:
            left.append(html.Div(subtitle, style={**ds.LABEL_STYLE, "marginTop": "3px"}))
        return html.Div([
            html.Div([ds.logo(46)] + ([html.Div(left)] if left else []) + [
                      html.Div(meta or "", style={**ds.LABEL_STYLE, "marginLeft": "auto", "color": ds.COLORS["muted"]})],
                     style={"display": "flex", "alignItems": "center", "gap": "16px", "padding": "18px 30px",
                            "background": "linear-gradient(180deg,#12102A,#0A081C)"}),
            html.Div(style={"height": "2px",
                            "background": "linear-gradient(90deg,rgba(192,163,100,0),#C0A364 50%,rgba(192,163,100,0))"}),
            html.Div(style={"height": "1px",
                            "background": "linear-gradient(90deg,transparent,rgba(0,0,0,.55),transparent)"})],
            className="cm-header")

    @staticmethod
    def kpi_card(label, value, fmt="{:+.2f}", unit=None):
        accent = ds.COLORS["positive"] if value >= 0 else ds.COLORS["negative"]
        return html.Div([
            html.Div(style={"borderTop": f"2px solid {ds.COLORS['navy']}", "marginBottom": "12px"}),
            html.Div(label, style=ds.LABEL_STYLE),
            html.Div([
                html.Span(ds.fmt_num(value, fmt), style={**ds.NUM_STYLE, "fontWeight": 300,
                          "fontSize": "30px", "letterSpacing": "-0.5px"}),
                html.Span(f" {unit}" if unit else "", style={**ds.LABEL_STYLE, "fontSize": "12px"}),
                html.Span(" " + ("▲" if value >= 0 else "▼"),
                          style={"color": accent, "fontSize": "13px", "verticalAlign": "3px"}),
            ], style={"marginTop": "6px", "lineHeight": "1"}),
        ], className="cm-panel", style={**ds.CARD_STYLE, "borderRadius": ds.RADIUS["md"], "flex": "1",
                                        "minWidth": "140px", "padding": "14px 18px 16px"})

    @staticmethod
    def layoutNoAxes():
        return {k: v for k, v in ds.PLOTLY_LAYOUT.items() if k not in ("xaxis", "yaxis")}

    @staticmethod
    def style_figure(fig, height=360, legend=False, title=None):
        tick = {"family": ds.FONT["numeric"], "size": 11}
        axis_title = {"font": dict(ds.AXIS_TITLE_FONT)}
        lay = dict(ds.PLOTLY_LAYOUT)
        lay["xaxis"] = {**lay["xaxis"], "zeroline": False, "tickfont": tick, "title": axis_title}
        lay["yaxis"] = {**lay["yaxis"], "zeroline": False, "griddash": "dot", "gridcolor": ds.HEX["hairline"],
                        "ticks": "outside", "tickcolor": "rgba(0,0,0,0)", "tickfont": tick, "title": axis_title}
        fig.update_layout(**lay, height=height, showlegend=legend, hovermode="x unified",
            margin=dict(t=30 if (legend or title) else 12, b=30, l=8, r=64),
            legend=dict(orientation="h", y=1.13, x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=12)),
            hoverlabel=dict(bgcolor=ds.HEX["header"], bordercolor=ds.HEX["hairline"],
                            font=dict(family=ds.FONT["numeric"], size=12, color=ds.HEX["text"])),
            title=(dict(text=title, x=0, font=dict(family=ds.FONT["family"], size=ds.FONT["size_subtitle"],
                        color=ds.HEX["text"])) if title else None))
        return fig

    @staticmethod
    def axisTitles(fig, x=None, y=None):
        if x is not None:
            fig.update_layout(xaxis=dict(title=dict(text=x, font=dict(ds.AXIS_TITLE_FONT))))
        if y is not None:
            fig.update_layout(yaxis=dict(title=dict(text=y, font=dict(ds.AXIS_TITLE_FONT))))
        return fig

    @staticmethod
    def data_table(numericCols=(), **kwargs):
        base = dict(sort_action="native", fixed_rows={"headers": True}, style_table=ds.TABLE_STYLE,
            style_header={**ds.TABLE_HEADER_STYLE, "backgroundColor": ds.COLORS["header"], "border": "none",
                          "borderBottom": f"2px solid {ds.COLORS['navy']}", "color": ds.COLORS["muted"]},
            style_cell={**ds.TABLE_CELL_STYLE, "border": "none", "borderBottom": f"1px solid {ds.COLORS['hairline']}"},
            style_cell_conditional=[{"if": {"column_id": c}, "textAlign": "right", "fontFamily": ds.FONT["numeric"],
                                     "fontVariantNumeric": "tabular-nums"} for c in numericCols],
            style_data_conditional=[{"if": {"state": "active"}, "backgroundColor": ds.COLORS["tint"], "border": "none"}])
        base.update(kwargs)
        return dash_table.DataTable(**base)

    @staticmethod
    def index_string():
        return (
            "<!DOCTYPE html><html><head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}"
            "<style>"
            ":root{--c-bg:#0E0B24;--c-surface:#221E34;--c-border:#332E47;--c-text:#D4CEC0;"
            "--c-ink:#E7E1D3;--c-muted:#9691A9;--c-hairline:rgba(192,163,100,.16);--c-brand:#C0A364;"
            "--c-logo:#9691A9;--c-tint:rgba(192,163,100,.12);--c-header:#0A081C;--c-input:#1A1533;color-scheme:dark}"
            "html,body{margin:0;background:#0E0B24;color:var(--c-text);"
            "font-family:'Georgia Pro',Georgia,'Times New Roman',serif;font-weight:300;"
            "-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;text-rendering:optimizeLegibility}"
            "td,th,input,.dash-cell,.tabular{font-feature-settings:'tnum' 1,'lnum' 1}"
            "button:hover{filter:brightness(1.06)}"
            "input,textarea{background:var(--c-input)!important;color:var(--c-text)!important;"
            "border-color:var(--c-border)!important}"
            ".dash-dropdown-trigger,.dash-dropdown-content,.dash-dropdown-option{"
            "background:var(--c-input)!important;color:var(--c-text)!important;"
            "border-color:var(--c-border)!important;font-family:" + ds.FONT["family"] + "!important}"
            "</style></head><body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>")


def _project_root() -> Path:
    if os.environ.get("NAD_ROOT"):
        return Path(os.environ["NAD_ROOT"])
    here = Path(__file__).resolve()
    for base in [here.parent, *here.parents]:
        if (base / "3_env").is_dir() or (base / "0_tradingVE").is_dir():
            return base
    return here.parent


def _first_file(*cands):
    for c in cands:
        if c and Path(c).is_file():
            return Path(c)
    return None


ROOT = _project_root()
HERE = Path(__file__).resolve().parent


def _logo_uri():
    f = _first_file(os.environ.get("NAD_LOGO"), HERE / "ndxLogo.webp", ROOT / "3_env" / "ndxLogo.webp")
    return "data:image/webp;base64," + base64.b64encode(f.read_bytes()).decode() if f else None


LOGO_URI = _logo_uri()


def brand_logo(h=40):
    if LOGO_URI:
        return html.Img(src=LOGO_URI, alt="nordIX",
                        style={"height": f"{h}px", "width": "auto", "display": "block"})
    return ds.logo(h + 6)


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
              "quick": "quick ratio", "fcov": "fixed charge cov ratio",
              "cpntype": ("cpn type", "coupon type", "cpn typ", "fix/flt", "fixed/floating"),
              "sdur": ("spread duration", "oas duration", "risk duration", "oad")},
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
       "px5d", "px1m", "sp30", "sp120", "basis", "d2e", "fcf", "coupon", "sdur",
       "cs01", "bpv", "pay", "rec", "n", "px", "quick", "fcov", "npv", "npv_t1"}
DATE_AS_TEXT = {("swaps", "mat"), ("fx", "settle")}

MAT_BUCKETS = [(0, 2, "0-2y"), (2, 4, "2-4y"), (4, 6, "4-6y"), (6, 8, "6-8y"),
               (8, 10, "8-10y"), (10, 15, "10-15y"), (15, 25, "15-25y"), (25, 99, "25y+")]
BUCKET_LABELS = [b[2] for b in MAT_BUCKETS]
RATING_ORDER = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-",
                "BB+", "BB", "BB-", "NR"]


def _bucket(y: float):
    if pd.isna(y):
        return np.nan
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
    dvd = b["dur"] * b["mv"] / 1e4
    b["dv01"] = b["dv01"].fillna(dvd)
    b["flt"] = b["cpntype"].astype(str).str.contains("float|variab|vrn|frn", case=False, na=False)
    sdur = b["sdur"] if b["sdur"].notna().any() else b["dur"]
    b["cs01"] = (sdur * b["mv"] / 1e4).where(sdur.notna(), b["dv01"])
    b["bucket"] = b["mat"].apply(_bucket)

    c = d["cds"].dropna(subset=["nom"]).copy()
    c["bucket"] = c["mat"].fillna(0).apply(_bucket)

    s = d["swaps"].dropna(subset=["bpv"]).copy()
    s["mat_y"] = (pd.to_datetime(s["mat"], format="%d.%m.%Y", errors="coerce")
                  - pd.Timestamp.today()).dt.days / 365.25
    s["bucket"] = s["mat_y"].fillna(0).apply(_bucket)

    f = d["futures"].dropna(subset=["dv01"]).copy()
    f["bucket"] = f["dur"].fillna(0).apply(_bucket)

    d.update(bonds=b, cds=c, swaps=s, futures=f)
    return d


def _wavg(v, w) -> float:
    v = pd.to_numeric(v, errors="coerce")
    ok = v.notna() & w.notna()
    tw = w[ok].sum()
    return float((v[ok] * w[ok]).sum() / tw) if tw else 0.0


def metrics(d: dict[str, pd.DataFrame]) -> dict:
    b, c, s, f = d["bonds"], d["cds"], d["swaps"], d["futures"]
    mv = b["mv"].sum()
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
        dur_net=float((ir_long + ir_hedge) / mv * 1e4) if mv else 0.0,
        spread_avg=_wavg(b["spread"], b["mv"]),
        oas_avg=_wavg(b["oas"], b["mv"]),
        dts=_wavg(b["dts"], b["mv"]),
        wam=_wavg(b["mat"], b["mv"]),
        conv=_wavg(b["conv"], b["mv"]),
        coupon=_wavg(b["coupon"], b["mv"]) * 100,
        spd=_wavg(b["spd"], b["mv"]),
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


RATING_LINEAR = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-",
                 "BB+", "BB", "BB-", "B+", "B", "B-", "CCC+", "CCC", "CCC-", "CC", "C"]
RATING_SCORE = {r: i + 1 for i, r in enumerate(RATING_LINEAR)}
RATING_SCORE.update({"D": 21, "SD": 21, "DDD": 21, "DD": 21})


def portfolio_rating(d: dict[str, pd.DataFrame]) -> tuple[float | None, str]:
    num = den = 0.0
    for df, wcol in ((d["bonds"], "mv"), (d["cds"], "nom")):
        if not len(df):
            continue
        s = df["rating"].astype(str).str.strip().str.upper().map(RATING_SCORE)
        w = df[wcol]
        ok = s.notna() & w.notna()
        num += float((s[ok] * w[ok]).sum())
        den += float(w[ok].sum())
    if den <= 0:
        return None, "NR"
    avg = num / den
    return avg, RATING_LINEAR[min(len(RATING_LINEAR) - 1, max(0, round(avg) - 1))]


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
    hit = _first_file(
        os.environ.get("NAD_XLSX"),
        name if Path(name).is_absolute() else None,
        HERE / name, HERE / "data" / name, Path.cwd() / name,
        PORTFOLIO_DIR / Path(name).name)
    return str(hit or (HERE / Path(name).name))


XLSX = _resolve_xlsx(sys.argv[1] if len(sys.argv) > 1 else "nad.xlsx")
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8050


def _empty_book() -> dict[str, pd.DataFrame]:
    schema = {
        "bonds": ["id", "mv", "dv01", "dur", "cs01", "dts", "spread", "oas", "conv", "mat",
                  "coupon", "spd", "ccy", "nom", "sector", "issuer", "rating", "seg", "rank",
                  "bucket", "px5d", "px1m", "sp30", "sp120", "basis",
                  "d2e", "fcf", "quick", "fcov", "country", "industry"],
        "cds": ["id", "nom", "mv", "cs01", "dur", "sector", "issuer", "rating", "ccy", "mat",
                "bucket", "spread", "spd", "sp30", "sp120", "px5d", "px1m"],
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
    traceback.print_exc()
    D, PORTFOLIO_OK, PORTFOLIO_ERR = _empty_book(), False, str(_pf_ex)

M = metrics(D)
M["rating_score"], M["rating_letter"] = portfolio_rating(D)
B = D["bonds"]

FACTS = fund_facts(RAW0)
NAV = FACTS.get("nav") or M["mv"] or 1.0
if pd.isna(NAV) or NAV == 0:
    NAV = 1.0
CASH = FACTS.get("cash")

M["dur_spread"] = M["cs01"] / NAV * 1e4
M["dur_net"] = M["ir_net"] / NAV * 1e4

CURVES = load_curves(RAW0)

POS = positions(D)
POS_VIEW = POS.assign(**{"Nom(M)": POS["Nominal"] / 1e6, "MV(M)": POS["MV"] / 1e6}).round(
    {"Mat": 1, "Nom(M)": 1, "MV(M)": 1, "Dur": 2, "DV01/BPV": 0, "Spread": 0})
POS_COLS = ["MV(M)", "Type", "id", "Name", "Sector", "Rtg", "Ccy", "Mat", "Nom(M)",
            "Dur", "DV01/BPV", "Spread"]
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
    {"MV(M)": 1, "ND/EBITDA": 2, "FCF/Debt": 3, "Quick": 2, "FCC": 2})
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
CREDIT_VIEWS = {s: credit_view(D, s) for s in CREDIT_SRC}
_hs_full = CREDIT_VIEWS["Bond + CDS"].dropna(subset=["sector"])
HOTSPOT_SECTORS = list(_hs_full.assign(_a=_hs_full["cs01"].abs())
                       .groupby("sector")["_a"].sum().sort_values(ascending=False).index)


def _accent_rule(ac):
    return html.Div(style={"width": "30px", "height": "2px", "margin": "0 auto 13px",
                           "background": f"linear-gradient(90deg,rgba(192,163,100,0),{ac},rgba(192,163,100,0))",
                           "boxShadow": "0 0 8px rgba(192,163,100,.4)"})


def _stat_card(children, minw):
    return html.Div(children, className="stat-card", style={**ds.CARD_STYLE, "flex": "1", "minWidth": minw,
              "padding": "22px 22px 24px", "textAlign": "center", "position": "relative",
              "transition": "box-shadow .2s ease, transform .2s ease"})


def _stat_value(value, size):
    return html.Div(value, style={"fontFamily": ds.FONT["numeric"], "fontWeight": 400, "fontSize": size,
                                  "color": ds.COLORS["ink"], "marginTop": "10px", "lineHeight": 1.12,
                                  "letterSpacing": "0.3px", "fontVariantNumeric": "tabular-nums lining-nums"})


def _stat_label(label):
    return html.Div(label, style={**ds.LABEL_STYLE, "fontSize": "12px", "letterSpacing": "1.3px",
                                  "color": ds.COLORS["muted"]})


def stat(label: str, value: str, sub: str = "", accent: str | None = None):
    ac = accent or ds.COLORS["primary"]
    kids = [_accent_rule(ac), _stat_label(label), _stat_value(value, "26px")]
    if sub:
        kids.append(html.Div(sub, style={**ds.LABEL_STYLE, "textTransform": "none", "letterSpacing": "0.2px",
                                         "marginTop": "8px", "opacity": 0.85, "fontSize": "11.5px"}))
    return _stat_card(kids, "158px")


def stat_plain(label: str, value: str, accent: str | None = None):
    ac = accent or ds.COLORS["primary"]
    return _stat_card([_accent_rule(ac), _stat_label(label), _stat_value(value, "31px")], "170px")


def chart(fig, cid: str):
    return dcc.Graph(id=cid, figure=fig, config={"displaylogo": False})


def legend_right(fig):
    return fig.update_layout(legend=dict(orientation="h", y=1.14, x=1, xanchor="right"))


TAB_BORDER = "1px solid rgba(192,163,100,.32)"
TAB_GLOSS = "inset 0 1px 0 rgba(255,255,255,.06), 0 1px 3px rgba(0,0,0,.30)"
TOPTAB_STYLE = {"fontFamily": ds.FONT["serif"], "fontSize": "17px", "fontWeight": 500,
                "padding": "11px 32px", "minWidth": "150px", "textAlign": "center", "textTransform": "lowercase",
                "background": "linear-gradient(180deg,#262238,#1D1A2E)", "borderRadius": "8px",
                "border": TAB_BORDER, "color": ds.COLORS["text"],
                "letterSpacing": "0.3px", "boxShadow": TAB_GLOSS}
TOPTAB_SELECTED = dict(TOPTAB_STYLE)

TAB_STYLE = {"fontFamily": ds.FONT["serif"], "fontSize": "15px", "fontWeight": 500,
             "padding": "8px 24px", "minWidth": "118px", "textAlign": "center", "textTransform": "lowercase",
             "background": "linear-gradient(180deg,#262238,#1D1A2E)", "borderRadius": "8px",
             "border": TAB_BORDER, "color": ds.COLORS["text"], "boxShadow": TAB_GLOSS}
TAB_SELECTED = dict(TAB_STYLE)

TAB_COLORS = {"border": "transparent", "background": "transparent", "primary": "transparent"}
TOPTABS_ROW = {"display": "flex", "flexWrap": "wrap", "gap": "16px", "justifyContent": "center",
               "border": "none", "margin": "18px 0 6px"}
SUBTABS_ROW = {"display": "flex", "flexWrap": "wrap", "gap": "12px", "justifyContent": "center",
               "border": "none", "margin": "18px 0 6px"}


def fmt(v: float, dec: int = 0) -> str:
    return f"{v:,.{dec}f}".replace(",", "\u2009")


def fig_ladder_ir():
    L = ladder(D, "ir")
    fig = go.Figure()
    for col, color in [("Bonds", ds.HEX["primary"]), ("Swaps", ds.HEX["negative"]),
                       ("Futures", ds.HEX["highlight"])]:
        fig.add_bar(name=col, x=L.index, y=L[col], marker_color=color)
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
    "Δ Spread 30d (bp)":  ("sp30",  "+.0f", True),
    "Δ Spread 120d (bp)": ("sp120", "+.0f", True),
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
    p = (cdf.pivot_table(values="cs01", index="sector", columns="bucket", aggfunc="sum")
         .reindex(index=HOTSPOT_SECTORS, columns=BUCKET_LABELS))
    fig = go.Figure(go.Heatmap(
        z=p.values, x=p.columns, y=p.index, colorscale=SEQUENTIAL, showscale=False,
        text=np.where(np.isnan(p.values), "",
                      np.vectorize(lambda v: fmt(v))(np.nan_to_num(p.values))),
        texttemplate="%{text}", textfont=dict(size=10),
        hovertemplate="%{y} · %{x}: %{z:,.0f} €/bp<extra></extra>"))
    fig = ds.style_figure(fig, height=440)
    return fig.update_layout(hovermode="closest")


def fig_swapbook():
    fig = go.Figure()
    s = D["swaps"].sort_values("mat_y")
    fig.add_bar(name="Swaps", x=s["mat_y"], y=s["bpv"], width=0.35, marker_color=ds.HEX["negative"],
                customdata=np.stack([s["nom"] / 1e6, s["pay"], s["rec"]], axis=-1) if len(s) else None,
                hovertemplate="Swap · %{x:.1f}y · BPV %{y:,.0f} €/bp · %{customdata[0]:.0f}M<br>"
                              "Pay %{customdata[1]:.2f}% / Rec %{customdata[2]:.2f}%<extra></extra>")
    f = D["futures"].sort_values("dur") if len(D["futures"]) else D["futures"]
    fig.add_bar(name="Futures", x=f.get("dur", []), y=f.get("dv01", []), width=0.35,
                marker_color=ds.HEX["highlight"],
                hovertemplate="Future · %{x:.1f}y · DV01 %{y:,.0f} €/bp<extra></extra>")
    fig = ds.style_figure(fig, height=340, legend=True)
    return ds.axisTitles(fig.update_layout(hovermode="closest", barmode="overlay"), "Time to maturity (y)")


def _fv_group(mat):
    return "≤5y" if mat <= 5 else ("5–10y" if mat <= 10 else ">10y")


def fig_fair_value(cdf):
    m = {r: i for i, r in enumerate(RATING_ORDER)}
    d = cdf.dropna(subset=["spread", "mv", "mat"]).copy()
    d["notch"] = d["rating"].astype(str).str.strip().str.upper().map(m)
    d = d.dropna(subset=["notch"])
    if not len(d):
        return _empty_fig("No rated positions with a spread.", 460)
    d["mgrp"] = d["mat"].map(_fv_group)
    d["fair"] = d.groupby(["mgrp", "notch"])["spread"].transform("median")
    d["resid"] = d["spread"] - d["fair"]
    d["maty"] = np.log10(d["mat"].clip(lower=0.1))
    cheap = d["resid"] >= 0
    fig = go.Figure()
    for g, nm, col in [(d[cheap], "Cheap (buy)", ds.HEX["positive"]),
                       (d[~cheap], "Rich (trim)", ds.HEX["negative"])]:
        if not len(g):
            continue
        fig.add_trace(go.Scatter3d(
            x=g["notch"], y=g["maty"], z=g["spread"], mode="markers", name=nm,
            text=g["issuer"], customdata=np.stack([g["rating"], g["resid"], g["mat"]], axis=-1),
            marker=dict(size=np.clip(np.asarray(_bubble(g["mv"]), float), 4, 20),
                        color=col, opacity=0.85, line=dict(width=0.5, color="#FFF")),
            hovertemplate="<b>%{text}</b> (%{customdata[0]})<br>"
                          "%{customdata[2]:.1f}y · Spread %{z:.0f}bp · %{customdata[1]:+.0f}bp vs fair<extra></extra>"))
    ticks = sorted(int(i) for i in d["notch"].dropna().unique())
    lo, hi = float(d["mat"].min()), float(d["mat"].max())
    yr = [t for t in (1, 2, 3, 5, 7, 10, 15, 20, 30, 40, 50) if lo * 0.9 <= t <= hi * 1.1]
    yr = yr or sorted({max(0.1, round(lo, 1)), round(hi, 1)})
    ax = dict(backgroundcolor=ds.HEX["surface"], gridcolor=ds.HEX["hairline"],
              zerolinecolor=ds.HEX["border"], color=ds.HEX["muted"], showbackground=True)
    fig.update_layout(
        height=460, paper_bgcolor=ds.HEX["surface"], plot_bgcolor=ds.HEX["surface"],
        font=dict(family=ds.FONT["family"], size=11, color=ds.HEX["text"]),
        margin=dict(t=6, b=6, l=6, r=6), hovermode="closest",
        legend=dict(orientation="h", y=1.02, x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=12)),
        scene=dict(
            xaxis=dict(title="Rating", tickmode="array", tickvals=ticks,
                       ticktext=[RATING_ORDER[i] for i in ticks], **ax),
            yaxis=dict(title="Maturity (y)", tickmode="array",
                       tickvals=[float(np.log10(t)) for t in yr],
                       ticktext=[f"{t:g}" for t in yr], **ax),
            zaxis=dict(title="I-Spread (bp)", **ax),
            camera=dict(eye=dict(x=1.7, y=1.6, z=0.8))))
    return fig


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
    if not share.sum():
        return _empty_fig("No DTS data.", 470)
    share = share / share.sum()
    n = len(share)
    x = np.concatenate([[0], np.arange(1, n + 1) / n * 100])
    cum = np.concatenate([[0], share.cumsum().to_numpy() * 100])
    hhi = float((share ** 2).sum() * 1e4)
    top5 = float(share.head(5).sum() * 100)
    fig = go.Figure()
    fig.add_scatter(x=[0, 100], y=[0, 100], mode="lines", name="neutral (equal)", hoverinfo="skip",
                    line=dict(color=ds.HEX["muted"], width=1.5, dash="dash"))
    fig.add_annotation(x=88, y=92, xanchor="right", yanchor="bottom", showarrow=False, textangle=-45,
                       text="neutral 45°", font=dict(family=ds.FONT["family"], size=11, color=ds.HEX["muted"]))
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
    ex = (d[d["ccy"].astype(str).str.upper() != "EUR"].groupby("ccy")["mv"].sum()
          / NAV * 100).sort_values(ascending=False)
    if not len(ex):
        return _empty_fig("100% EUR — no FX exposure.", 260)
    hedged_ccy = set(D["fx"]["ccy"].astype(str).str.upper()) if len(D["fx"]) else set()
    hedged = [0.0 if str(c).upper() in hedged_ccy else float(v) for c, v in ex.items()]
    fig = go.Figure()
    fig.add_bar(name="Unhedged", x=list(ex.index), y=list(ex.values), marker_color=ds.HEX["secondary"],
                text=[f"{v:.2f}%" for v in ex.values], textposition="outside",
                hovertemplate="%{x}: %{y:.2f}% of NAV — unhedged<extra></extra>")
    fig.add_bar(name="Hedged (after FX swaps)", x=list(ex.index), y=hedged, marker_color=ds.HEX["primary"],
                text=[f"{v:.2f}%" for v in hedged], textposition="outside",
                hovertemplate="%{x}: %{y:.2f}% of NAV — after hedges<extra></extra>")
    fig.add_hline(y=5, line=dict(color=ds.HEX["negative"], width=1.5, dash="dash"))
    fig.add_annotation(x=1, y=5, xref="x domain", xanchor="right", yanchor="bottom",
        text="5% limit ", showarrow=False,
        font=dict(size=10, color=ds.HEX["negative"], family=ds.FONT["family"]))
    fig = ds.style_figure(fig, height=340, legend=True)
    fig.update_layout(barmode="group", hovermode="x unified", margin=dict(t=30, b=30, l=8, r=20))
    return ds.axisTitles(fig, None, "% of NAV")


def fig_carry_treemap():
    b = B.dropna(subset=["spd", "mv"]).assign(w=lambda x: x["spd"] * x["mv"])
    if not len(b) or not b["mv"].sum():
        return _empty_fig("No carry data.")
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
    if not len(d):
        return pd.Series(dtype=float)
    return (d.groupby("bucket").apply(lambda x: np.average(x[col], weights=x["mv"]),
            include_groups=False).reindex(BUCKET_LABELS).dropna())


def fig_spread_terms():
    isp, oas, carry = _spread_term(B, "spread"), _spread_term(B, "oas"), _spread_term(B, "spd")
    fig = go.Figure()
    fig.add_scatter(x=list(isp.index), y=isp.values, mode="lines+markers", name="I-Spread",
                    line=dict(color=ds.HEX["primary"], width=2.5), marker=dict(size=8),
                    hovertemplate="%{x}: I-Spread %{y:.0f} bp<extra></extra>")
    fig.add_scatter(x=list(oas.index), y=oas.values, mode="lines+markers", name="OAS",
                    line=dict(color=ds.HEX["secondary"], width=2.5), marker=dict(size=8),
                    hovertemplate="%{x}: OAS %{y:.0f} bp<extra></extra>")
    fig.add_scatter(x=list(carry.index), y=carry.values, mode="lines+markers", name="Carry / y",
                    line=dict(color=ds.HEX["positive"], width=2.5, dash="dot"), marker=dict(size=7),
                    hovertemplate="%{x}: Carry %{y:.1f} bp/y<extra></extra>")
    fig = ds.style_figure(fig, height=440, legend=True)
    fig.update_layout(hovermode="x unified")
    ds.axisTitles(fig, "Maturity bucket", "Spread (bp) · Carry (bp/y)")
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
def _safe_fig(fn):
    try:
        return fn()
    except Exception:
        traceback.print_exc()
        return _empty_fig("Chart not available (no data).")


FIGS = {k: _safe_fig(fn) for k, fn in FIGS.items()}


def dropdown(cid, options, value, width="260px"):
    return dcc.Dropdown(id=cid, options=[{"label": o, "value": o} for o in options],
                        value=value, clearable=False,
                        style={"width": width, "fontFamily": ds.FONT["family"], "fontSize": "13px"})


_client = None


def _load_api_key():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    envf = _first_file(os.environ.get("NAD_ENV"), HERE / ".env",
                       ROOT / "3_env" / ".env", Path.cwd() / ".env")
    if not envf:
        return
    for line in envf.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line.startswith("ANTHROPIC_API_KEY=") and "=" in line:
            os.environ.setdefault("ANTHROPIC_API_KEY",
                                  line.split("=", 1)[1].strip().strip('"').strip("'"))


def _anthropic():
    global _client
    if _client is None:
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("AI features need the 'anthropic' package — run: pip install anthropic")
        _load_api_key()
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY not set — put a .env next to the script with "
                               "ANTHROPIC_API_KEY=sk-ant-… or set it as an environment variable.")
        _client = anthropic.Anthropic()
    return _client


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
    return html.Div(boxes, style={"display": "flex", "flexWrap": "wrap", "gap": "14px",
                                  "margin": "10px 0 30px"})


def grid2(*cols):
    return html.Div([html.Div(c, style={"flex": "1 1 460px", "minWidth": "0"}) for c in cols],
                    style={"display": "flex", "flexWrap": "wrap", "gap": "26px 30px"})


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

    def stat(label, value, sub="", accent=None):
        return stat_plain(label, value, accent)

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
        ]),
        _grid([
            stat("Avg Portfolio Rating",
                 f"{M['rating_letter']}" + (f" · {M['rating_score']:.1f}" if M['rating_score'] is not None else ""),
                 "MV-weighted, 1 AAA → 21 D, incl. CDS overlay", C["highlight"]),
            stat("CS01 Total", f"{fmt(M['cs01'])} €/bp",
                 f"bonds {fmt(M['cs01_bonds'])} · CDS {fmt(M['cs01_cds'])}"),
            stat("CS01 Bonds", f"{fmt(M['cs01_bonds'])} €/bp", "cash book"),
            stat("CS01 CDS", f"{fmt(M['cs01_cds'])} €/bp", "overlay", C["highlight"]),
            stat("Avg I-Spread", f"{M['spread_avg']:.0f} bp", "MV-weighted, cash book"),
            stat("Avg CDS Spread", f"{M['cds_spread_avg']:.0f} bp", "notional-weighted, overlay", C["highlight"]),
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
        block("fx", chart(FIGS["fx_exposure"], "fx1")),
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
    cv0 = CREDIT_VIEWS[CREDIT_SRC[0]]
    return ds.container([
        credit_toggle(),
        grid2(
            html.Div([
                html.Div([html.Div(ds.section("Credit Map"), style={"flex": "1", "minWidth": "0"}),
                          dropdown("cmap-x", list(CMAP_AXES), "Duration (y)", "160px"),
                          dropdown("cmap-y", list(CMAP_AXES), "I-Spread (bp)", "160px")],
                         style={"display": "flex", "gap": "12px", "alignItems": "flex-end"}),
                ds.panel(dcc.Graph(id="cmap", config={"displaylogo": False},
                                   figure=_safe_fig(lambda: fig_credit_map(cv0))))]),
            block("Hotspots", chart(_safe_fig(lambda: fig_heatmap(cv0)), "cr2"))),
        grid2(
            block("Spread Term Structure", chart(FIGS["spread_terms"], "spread-curve")),
            block("Spread Risk", chart(FIGS["ladder_cs"], "c2"))),
        grid2(
            block("Fair Value", chart(FIGS["fair_value"], "fv2")),
            block("Carry vs. Risk", chart(FIGS["carry_risk"], "crsk"))),
        grid2(
            block("Credit Concentration", chart(FIGS["dts_concentration"], "dtsc")),
            block("Capital vs. Carry", chart(FIGS["carry_treemap"], "i4"))),
    ], max_width=1400)


def tab_positionen():
    return ds.container([
        block(f"All positions ({len(POS)})", [
            html.Div(dropdown("pos-art", ["All"] + POS_TYPES, "All", "200px"),
                     style={"marginBottom": "10px"}),
            ds.data_table(
                id="pos-table", data=POS_VIEW.to_dict("records"),
                columns=[{"name": "size", "id": "MV(M)", "type": "numeric",
                          "format": Format(precision=1, scheme=Scheme.fixed).symbol(Symbol.yes).symbol_suffix(" MM")}
                         if c == "MV(M)" else {"name": c, "id": c} for c in POS_COLS],
                filter_action="native", sort_action="native", page_action="none",
                cell_selectable=True, include_headers_on_copy_paste=True,
                export_format="xlsx", export_headers="display",
                style_cell_conditional=[{"if": {"column_id": c}, "textAlign": "center"}
                                        for c in POS_COLS if c != "Name"]
                                       + [{"if": {"column_id": "Name"}, "textAlign": "left"}],
                style_filter=FILTER_STYLE, style_table={**ds.TABLE_STYLE, "maxHeight": "80vh"})]),
    ], max_width=1400)


def rep_table(df: pd.DataFrame, export: bool = True):
    exp = dict(export_format="csv", export_headers="display") if export else {}
    return ds.data_table(
        data=df.to_dict("records"),
        columns=[{"name": c, "id": c} for c in df.columns],
        page_action="none", **exp,
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
              ("Rates", "rates", tab_rates), ("Credit", "credit", tab_credit),
              ("Positions", "pos", tab_positionen)]


def data_error_panel(title: str, detail: str):
    return ds.container([ds.panel([
        html.Div(title, style={"fontFamily": ds.FONT["family"], "fontSize": "16px",
                               "fontWeight": 600, "color": ds.COLORS["negative"]}),
        html.Div(detail, style={"fontFamily": ds.FONT["family"], "fontSize": "13px",
                                "color": ds.COLORS["secondary"], "marginTop": "8px", "lineHeight": 1.5}),
        html.Div(f"Expected file: {XLSX}", style={**ds.LABEL_STYLE, "textTransform": "none",
                 "letterSpacing": 0, "marginTop": "10px"}),
    ])], max_width=1400)


def _subtabs(value, spec, extra=(), tab_style=TAB_STYLE, sel_style=TAB_SELECTED):
    return html.Div([*extra, dcc.Tabs(value=value, style=SUBTABS_ROW, colors=TAB_COLORS, children=[
        dcc.Tab(label=l, value=v, style=tab_style, selected_style=sel_style, children=b())
        for l, v, b in spec])])


def portfolio_analysis():
    if not PORTFOLIO_OK:
        return data_error_panel(
            "Portfolio data could not be loaded.",
            f"The other tabs keep working. Please check nad.xlsx "
            f"(open in Excel? moved? sheets renamed?). Technical detail: {PORTFOLIO_ERR}")
    return _subtabs("overview", PF_SUBTABS)


CREDIT_MODES = {"Corporate": "corp", "Financial": "fin", "Insurer": "ins", "Sovereign / SSA": "sov"}
CRED_OUTDIR = os.environ.get("NAD_CREDIT_OUT") or r"Q:\00_pm\1_research\3_issuerCreditResearch"
_CM_PATHS = [os.environ.get("NAD_ENGINE_DIR", r"q:\00_pm\6_ai\0_code"), str(ROOT / "3_env")]
_CM_ENGINE_FILE = os.environ.get("NAD_ENGINE", r"q:\00_pm\6_ai\0_code\creditManagement.py")
_cm_mod = None

ISS_DROP = {"border": f"1.5px dashed {ds.COLORS['primary']}", "borderRadius": "6px", "padding": "14px",
            "textAlign": "center", "cursor": "pointer", "margin": "10px 0", "background": ds.COLORS["surface"],
            "fontFamily": ds.FONT["family"], "fontSize": "13px", "color": ds.COLORS["secondary"]}

ISS_H = "50px"
ISS_INPUT_BIG = {"flex": "1 1 220px", "minWidth": "180px", "height": ISS_H, "padding": "0 18px",
                 "fontFamily": ds.FONT["family"], "fontSize": "16px", "color": "#F5F1E7",
                 "backgroundColor": "var(--c-input)", "border": f"1px solid {ds.COLORS['border']}",
                 "borderRadius": "12px", "boxSizing": "border-box", "outline": "none"}
ISS_BTN_BIG = {**ds.BUTTON_STYLE, "whiteSpace": "nowrap", "height": ISS_H, "padding": "0 34px",
               "fontSize": "15px", "borderRadius": "12px", "flex": "0 0 auto"}
ISS_CONTROLS_ROW = {"display": "flex", "alignItems": "stretch", "gap": "10px", "flexWrap": "wrap",
                    "width": "100%"}
ISS_TITLE = {"fontFamily": ds.FONT["serif"], "fontSize": "23px", "fontWeight": 500, "letterSpacing": "0.2px",
             "color": ds.COLORS["ink"], "textAlign": "center", "textTransform": "lowercase",
             "margin": "6px auto 26px"}


def _cm():
    global _cm_mod
    if _cm_mod is None:
        if not os.path.isfile(_CM_ENGINE_FILE):
            raise RuntimeError(
                f"Research engine not found: {_CM_ENGINE_FILE}. Set NAD_ENGINE to its path, "
                "otherwise the Issuer analysis tabs stay disabled on this machine.")
        for p in _CM_PATHS:
            if p and os.path.isdir(p) and p not in sys.path:
                sys.path.insert(0, p)
        import importlib.util
        spec = importlib.util.spec_from_file_location("_cm_engine", _CM_ENGINE_FILE)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_cm_engine"] = mod
        spec.loader.exec_module(mod)
        _cm_mod = mod
    return _cm_mod


def _engine_ready():
    if not os.path.isfile(_CM_ENGINE_FILE):
        return False
    for p in _CM_PATHS:
        if p and os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)
    try:
        import importlib.util
        return importlib.util.find_spec("research_db") is not None
    except Exception:
        return False


def _cm_error(msg):
    return ds.panel(html.P(str(msg), style={"color": ds.COLORS["negative"], "fontSize": "13px",
                    "fontFamily": ds.FONT["family"], "margin": 0}))


def _status(cid):
    return html.Span(id=cid, style={**ds.LABEL_STYLE, "textTransform": "none",
                                    "letterSpacing": 0, "whiteSpace": "nowrap"})


def _iss_dropdown(cid):
    return dcc.Dropdown(id=cid, className="iss-dd", clearable=False, value="Corporate",
                        options=[{"label": o, "value": o} for o in CREDIT_MODES],
                        style={"flex": "0 0 190px", "fontFamily": ds.FONT["family"], "fontSize": "15px"})


def _issuer_controls(mode_id, inp_id, btn_id, btn_label, status_id, placeholder,
                     title=None, subtitle=None):
    head = []
    if title:
        head.append(html.Div(title, style=ISS_TITLE))
    if subtitle:
        head.append(html.Div(subtitle, style=ISS_SUBTITLE))
    return html.Div(head + [
        html.Div([
            _iss_dropdown(mode_id),
            dcc.Input(id=inp_id, type="text", debounce=False, placeholder=placeholder, style=ISS_INPUT_BIG),
            html.Button(btn_label, id=btn_id, n_clicks=0, style=ISS_BTN_BIG),
        ], style=ISS_CONTROLS_ROW),
        html.Div(_status(status_id), style={"textAlign": "center", "marginTop": "12px", "minHeight": "18px"}),
    ], style={"maxWidth": "820px", "margin": "0 auto", "width": "100%", "paddingBottom": "26px"})


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


XAIA_DIR = Path(os.environ.get("NAD_XAIA") or (ROOT / "0_tradingVE" / "1_research" / "xaia"))
BONDS_DIR = Path(os.environ.get("NAD_BONDS") or (ROOT / "0_tradingVE" / "1_research" / "bonds"))
AGENT_MAX_DOCS, AGENT_MAX_BYTES = 5, 16_000_000

RESTR_SYSTEM = (
    "You are restR.-Agent, a credit strategist who speaks with the house view of XAIA Investment, a "
    "relative-value credit manager. Your lens: value lives in relative mispricings, not directional bets. You "
    "think in the CDS-cash basis, capital-structure arbitrage, spread per unit of risk (DTS), convexity, "
    "default vs. recovery, and where consensus misprices credit. You are quantitative, contrarian and "
    "risk-aware (liquidity, jump-to-default, crowding), and you tie a view to relative value and, where "
    "useful, a concrete trade expression (basis, curve, cap-structure, index vs. single-name). Ground every "
    "answer in the attached XAIA research; where it is silent, reason from XAIA's RV framework and say so. Be "
    "concise, opinionated and specific. Answer in the user's language.")
BOND_SYSTEM = (
    "You are bond-Agent, a fixed-income credit analyst grounded in the attached bond research. You focus on "
    "issuer fundamentals and their trajectory, credit quality and rating trend, covenants and structure, "
    "seniority and recovery, sector and curve relative value, and concrete bond selection (which line, what "
    "spread, what risk). Ground every answer in the attached research; where it is silent, reason as a "
    "seasoned fundamental fixed-income analyst and say so. Be concise, specific and actionable. Answer in the "
    "user's language.")

AGENTS = {
    "restr": {"name": "restR.-Agent", "dir": XAIA_DIR, "system": RESTR_SYSTEM, "docs": None},
    "bond": {"name": "bond-Agent", "dir": BONDS_DIR, "system": BOND_SYSTEM, "docs": None},
}
AGENT_ORDER = ["bond", "restr"]


def _pdf_date(name):
    months = ["january", "february", "march", "april", "may", "june", "july", "august",
              "september", "october", "november", "december"]
    s = name.lower()
    yr = next((int(y) for y in re.findall(r"20\d\d", s)), 0)
    mo = next((i + 1 for i, m in enumerate(months) if m in s), 0)
    return yr, mo


def _agent_docs(key):
    a = AGENTS[key]
    if a["docs"] is None:
        a["docs"], tot = [], 0
        if a["dir"].is_dir():
            files = sorted([*a["dir"].glob("*.pdf"), *a["dir"].glob("*.txt")],
                           key=lambda p: (_pdf_date(p.name), p.stat().st_mtime), reverse=True)
            for f in files:
                b = f.stat().st_size
                if len(a["docs"]) >= AGENT_MAX_DOCS or tot + b > AGENT_MAX_BYTES:
                    continue
                if f.suffix.lower() == ".txt":
                    src = {"type": "text", "media_type": "text/plain",
                           "data": f.read_text(encoding="utf-8", errors="ignore")}
                else:
                    src = {"type": "base64", "media_type": "application/pdf",
                           "data": base64.b64encode(f.read_bytes()).decode()}
                a["docs"].append({"type": "document", "title": f.name, "source": src,
                                  "cache_control": {"type": "ephemeral"}})
                tot += b
    return a["docs"]


def _agent_reply(key, hist):
    a = AGENTS.get(key) or AGENTS["restr"]
    docs = _agent_docs(key if key in AGENTS else "restr")
    msgs = []
    for i, mrec in enumerate(hist):
        if i == 0 and mrec["role"] == "user" and docs:
            msgs.append({"role": "user", "content": docs + [{"type": "text", "text": mrec["content"]}]})
        else:
            msgs.append({"role": mrec["role"], "content": mrec["content"]})
    r = _anthropic().messages.create(model=BVI_MODEL, max_tokens=1100, system=a["system"], messages=msgs)
    return "".join(b.text for b in r.content if getattr(b, "type", None) == "text").strip()


def _agent_dropdown(cid):
    return dcc.Dropdown(id=cid, className="iss-dd", clearable=False, value=AGENT_ORDER[0],
                        options=[{"label": AGENTS[k]["name"], "value": k} for k in AGENT_ORDER],
                        style={"flex": "0 0 190px", "fontFamily": ds.FONT["family"], "fontSize": "15px"})


def xagent_box(prefix, placeholder):
    return ds.container([
        block("Research agents", [
            dcc.Loading(type="dot", color=ds.COLORS["primary"],
                        children=html.Div(id=f"{prefix}-chat", style={"margin": "12px 0"})),
            html.Div([
                _agent_dropdown(f"{prefix}-agent"),
                dcc.Input(id=f"{prefix}-q", type="text", debounce=False, style=ISS_INPUT_BIG, placeholder=placeholder),
                html.Button("Ask", id=f"{prefix}-send", n_clicks=0, style=ISS_BTN_BIG),
            ], style=ISS_CONTROLS_ROW),
            dcc.Store(id=f"{prefix}-hist", data=[], storage_type="session"),
        ]),
    ], max_width=1080)


def tab_iss_credit():
    return html.Div([
        ds.panel([
            _issuer_controls("cred-mode", "cred-input", "cred-run", "Analyze", "cred-status",
                             "Issuer (e.g. Volkswagen AG, Deutsche Bank AG)…",
                             title="Issuer Credit Analysis")],
            pad="30px 30px 26px"),
        dcc.Loading(type="dot", color=ds.COLORS["primary"], children=html.Div(id="cred-output")),
        dcc.Store(id="cred-store", storage_type="session"),
        xagent_box("xac", "Ask about credit, a name, relative value or a basis trade…"),
    ], style={"paddingTop": "4px"})


CREDIT_METRICS = {
    "corp": [
        {"key": "leverage", "label": "Net Debt / EBITDA", "unit": "x", "better": "down"},
        {"key": "ebitda_margin", "label": "EBITDA margin", "unit": "%", "better": "up"},
        {"key": "interest_cover", "label": "EBITDA / Interest", "unit": "x", "better": "up", "band": 1},
        {"key": "fcf_debt", "label": "FCF / Debt", "unit": "%", "better": "up", "band": 0},
        {"key": "liquidity_cover", "label": "Liquidity / 12m maturities", "unit": "x", "better": "up", "band": 1},
    ],
    "fin": [
        {"key": "cet1", "label": "CET1 ratio", "unit": "%", "better": "up"},
        {"key": "lcr", "label": "LCR", "unit": "%", "better": "up", "band": 100},
        {"key": "npl", "label": "NPL ratio", "unit": "%", "better": "down"},
        {"key": "rote", "label": "Return on tangible equity", "unit": "%", "better": "up"},
        {"key": "cost_income", "label": "Cost / Income", "unit": "%", "better": "down"},
    ],
    "ins": [
        {"key": "solvency2", "label": "Solvency II ratio", "unit": "%", "better": "up", "band": 100},
        {"key": "combined", "label": "Combined ratio", "unit": "%", "better": "down", "band": 100},
        {"key": "roe", "label": "Return on equity", "unit": "%", "better": "up"},
        {"key": "fin_leverage", "label": "Financial leverage", "unit": "%", "better": "down"},
        {"key": "interest_cover", "label": "Interest coverage", "unit": "x", "better": "up", "band": 1},
    ],
    "sov": [
        {"key": "debt_gdp", "label": "Debt / GDP", "unit": "%", "better": "down"},
        {"key": "fiscal_balance", "label": "Fiscal balance", "unit": "% GDP", "better": "up", "band": 0},
        {"key": "interest_rev", "label": "Interest / Revenue", "unit": "%", "better": "down"},
        {"key": "gfn", "label": "Gross financing need", "unit": "% GDP", "better": "down"},
        {"key": "growth", "label": "Real GDP growth", "unit": "%", "better": "up", "band": 0},
        {"key": "reserves", "label": "FX reserves", "unit": "months", "better": "up"},
    ],
}


def _metrics_schema(mode):
    mp = {}
    for m in CREDIT_METRICS[mode]:
        mp[m["key"]] = {"type": "object", "required": ["hist", "fcst"], "properties": {
            "hist": {"type": "array", "items": {"type": ["number", "null"]},
                     "description": f"{m['label']} ({m['unit']}) - last 5 fiscal years, oldest to newest, actuals."},
            "fcst": {"type": "array", "items": {"type": ["number", "null"]},
                     "description": f"{m['label']} ({m['unit']}) - next 5 years, base-case forecast."},
            "note": {"type": "string", "description": "one short clause"}}}
    return {"type": "object", "required": ["rating", "trend", "headline", "metrics"], "properties": {
        "company": {"type": "string"},
        "rating": {"type": "string", "description": "agency-style with outlook, e.g. 'BBB / stable'"},
        "trend": {"type": "string", "enum": ["improving", "stable", "deteriorating"]},
        "headline": {"type": "string", "description": "one sentence - the credit in a nutshell"},
        "biggest_risk": {"type": "string", "description": "one line"},
        "metrics": {"type": "object", "required": [m["key"] for m in CREDIT_METRICS[mode]], "properties": mp},
        "sources": {"type": "array", "items": {"type": "string"}}}}


CREDIT_MODEL = "claude-sonnet-5"


def _extract_tool(msg, name):
    for b in msg.content:
        if getattr(b, "type", None) == "tool_use" and getattr(b, "name", "") == name:
            return b.input
    return None


def _credit_metrics_job(issuer, mode):
    labels = ", ".join(f"{m['label']} ({m['unit']})" for m in CREDIT_METRICS[mode])
    tool = {"name": "report_credit",
            "description": "Report the issuer's key credit metrics with 5y history and 5y base-case forecast.",
            "input_schema": _metrics_schema(mode)}
    prompt = (
        f"You are a senior Oaktree credit analyst. For '{issuer}' (type: {mode}), assess these key credit "
        f"metrics: {labels}. For each, give 5 fiscal years of actual history (oldest to newest) and a 5-year "
        f"base-case forecast, grounded in the latest reported financials and guidance. Also give a one-sentence "
        f"headline, an agency-style rating with outlook, the credit trend, and the single biggest risk. Give "
        f"best estimates where data is not disclosed; use null only if truly unknowable.")
    cl = _anthropic()
    # Pass 1: let it research the web, then report.
    try:
        msg = cl.messages.create(model=CREDIT_MODEL, max_tokens=8000,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 6}, tool],
            messages=[{"role": "user", "content": prompt + " Search the web for current figures, then call report_credit."}])
        out = _extract_tool(msg, "report_credit")
        if out:
            return out
    except Exception:
        pass
    # Pass 2: force the structured tool from the model's own knowledge (guaranteed output).
    msg = cl.messages.create(model=CREDIT_MODEL, max_tokens=8000, tools=[tool],
        tool_choice={"type": "tool", "name": "report_credit"},
        messages=[{"role": "user", "content": prompt + " Use your own knowledge; call report_credit now."}])
    out = _extract_tool(msg, "report_credit")
    if out:
        return out
    raise RuntimeError("model returned no structured result")


def _fmt_metric(v, unit):
    if v is None:
        return "—"
    return f"{v:.1f}x" if unit == "x" else f"{v:,.1f} {unit}"


def _metric_fig(m, md, t0):
    hist = [None if v is None else float(v) for v in (md.get("hist") or [])][-5:]
    fcst = [None if v is None else float(v) for v in (md.get("fcst") or [])][:5]
    if not any(v is not None for v in hist) and not any(v is not None for v in fcst):
        return None
    yh = [t0 - len(hist) + 1 + i for i in range(len(hist))]
    fig = go.Figure()
    if hist:
        fig.add_scatter(x=yh, y=hist, mode="lines+markers", line=dict(color=ds.HEX["ink"], width=2),
                        marker=dict(size=5), hovertemplate="%{x}: %{y:,.1f}<extra></extra>")
    if fcst:
        last = next((v for v in reversed(hist) if v is not None), fcst[0])
        yf = [yh[-1] if yh else t0] + [t0 + 1 + i for i in range(len(fcst))]
        fig.add_scatter(x=yf, y=[last] + fcst, mode="lines+markers",
                        line=dict(color=ds.HEX["primary"], width=2, dash="dot"), marker=dict(size=5),
                        hovertemplate="%{x}: %{y:,.1f} (f)<extra></extra>")
    if m.get("band") is not None:
        fig.add_hline(y=m["band"], line=dict(color=ds.HEX["negative"], width=1, dash="dash"))
    latest = next((v for v in reversed(hist) if v is not None), None)
    ttl = f"{m['label']}   ·   {_fmt_metric(latest, m['unit'])}"
    fig = ds.style_figure(fig, height=210)
    fig.update_layout(showlegend=False, hovermode="x unified", margin=dict(t=32, b=22, l=8, r=12),
        title=dict(text=ttl, x=0, font=dict(family=ds.FONT["family"], size=12.5, color=ds.HEX["text"])))
    return dcc.Graph(figure=fig, config={"displaylogo": False})


def build_credit_model(mode, data, issuer=""):
    trend = str(data.get("trend", "stable")).lower()
    color = {"improving": ds.HEX["positive"], "deteriorating": ds.HEX["negative"]}.get(trend, ds.HEX["highlight"])
    t0 = pd.Timestamp.today().year
    verdict = ds.panel([
        html.Div([
            html.Span(style={"width": "12px", "height": "12px", "borderRadius": "50%", "background": color,
                             "display": "inline-block", "marginRight": "10px", "boxShadow": f"0 0 10px {color}"}),
            html.Span(data.get("rating", "—"), style={"fontFamily": ds.FONT["serif"], "fontSize": "20px",
                                                      "fontWeight": 600, "color": color}),
            html.Span(f"  ·  {issuer or data.get('company', '')} · {mode.upper()} · {trend}",
                      style={"fontFamily": ds.FONT["family"], "fontSize": "13px", "color": ds.COLORS["muted"]}),
        ], style={"display": "flex", "alignItems": "center", "flexWrap": "wrap"}),
        html.Div(data.get("headline", ""), style={"fontFamily": ds.FONT["serif"], "fontSize": "16px",
                                                  "color": ds.COLORS["ink"], "marginTop": "10px"}),
        html.Div("Key risk — " + data["biggest_risk"], style={"fontFamily": ds.FONT["family"], "fontSize": "13.5px",
                 "color": ds.COLORS["text"], "marginTop": "8px", "fontWeight": 600}) if data.get("biggest_risk") else html.Span(),
    ])
    md = data.get("metrics") or {}
    cards = []
    for m in CREDIT_METRICS.get(mode, CREDIT_METRICS["corp"]):
        g = _metric_fig(m, md.get(m["key"]) or {}, t0)
        if g:
            cards.append(html.Div(g, style={"flex": "1 1 300px", "minWidth": "280px"}))
    body = [verdict, html.Div(cards, style={"display": "flex", "flexWrap": "wrap", "gap": "8px", "marginTop": "6px"})]
    src = data.get("sources") or []
    if src:
        body.append(html.Details([
            html.Summary("sources", style={"cursor": "pointer", "color": ds.COLORS["primary"],
                "fontFamily": ds.FONT["family"], "fontSize": "12px", "margin": "10px 2px 4px"}),
            html.Div(" · ".join(str(s) for s in src), style={**ds.LABEL_STYLE, "textTransform": "none",
                     "letterSpacing": 0, "fontSize": "11.5px", "lineHeight": 1.5})]))
    return html.Div(body)


def tab_iss_liquidity():
    return html.Div([
        ds.panel([
            _issuer_controls("liqm-mode", "liqm-input", "liqm-run", "Build model", "liqm-status",
                             "Issuer…", title="Liquidity & Stress Model")],
            pad="30px 30px 26px"),
        dcc.Loading(type="dot", color=ds.COLORS["primary"], children=html.Div(id="liqm-output")),
        dcc.Store(id="liqm-store", storage_type="session"),
        xagent_box("xam", "Ask about liquidity, covenants, stress or relative value…"),
    ], style={"paddingTop": "4px"})


def tab_iss_prospectus():
    return html.Div([
        ds.panel([
            html.Div([
                html.Div("Prospectus & Recovery", style=ISS_TITLE),
                html.Div([
                    dcc.Input(id="prosp-issuer", type="text", debounce=False, style=ISS_INPUT_BIG,
                              placeholder="Issuer / instrument (the AI searches for the prospectus)…"),
                    html.Button("Search prospectus", id="prosp-search", n_clicks=0, style=ISS_BTN_BIG),
                ], style=ISS_CONTROLS_ROW),
                html.Div(_status("prosp-status"),
                         style={"textAlign": "center", "marginTop": "12px", "minHeight": "18px"}),
                dcc.Upload(id="prosp-upload", multiple=True, style=ISS_DROP,
                           children="… or drag a prospectus PDF here / click"),
                html.Div(id="prosp-files"),
                html.Div(html.Button("Analyze attached PDF", id="prosp-run-file", n_clicks=0,
                                     style={**ds.BUTTON_STYLE, "background": ds.COLORS["secondary"]}),
                         style={"textAlign": "center", "marginTop": "10px"}),
                html.Div(id="prosp-confirm", style={"marginTop": "10px"}),
            ], style={"maxWidth": "820px", "margin": "0 auto", "width": "100%", "paddingBottom": "26px"})],
            pad="30px 30px 26px"),
        dcc.Loading(type="dot", color=ds.COLORS["primary"], children=html.Div(id="prosp-output")),
        dcc.Store(id="prosp-store", storage_type="session"), dcc.Store(id="prosp-cand"),
        dcc.Store(id="prosp-files-data", data=[]),
        xagent_box("xap", "Ask about the prospectus, covenants, recovery or relative value…"),
    ], style={"paddingTop": "4px"})


ISSUER_SUBTABS = [("Credit", "credit", tab_iss_credit),
                  ("Model", "liq", tab_iss_liquidity),
                  ("Prospectus", "prosp", tab_iss_prospectus)]


def issuer_analysis():
    if not _engine_ready():
        return ds.container([ds.panel(note(
            "Issuer analysis needs the internal research engine (research_db), which is not "
            "available on this machine. Set NAD_ENGINE / NAD_ENGINE_DIR to enable it — the rest "
            "of the dashboard works normally."))])
    return _subtabs("credit", ISSUER_SUBTABS,
                    [dcc.Download(id="cred-pdf-dl"), dcc.Download(id="liqm-pdf-dl"), dcc.Download(id="prosp-pdf-dl")])


BVI_TEMPLATE = Path(os.environ.get("NAD_BVI_TEMPLATE") or (HERE / "bviSheetOutline.xls"))
BVI_OUTDIR = os.environ.get("NAD_BVI_OUT") or (
    r"Q:\7_NTP_nordIX_Treasury_plus\1_NAD_Manager\1_bvi"
    if os.path.isdir(r"Q:\7_NTP_nordIX_Treasury_plus\1_NAD_Manager") else str(HERE / "bvi_out"))
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
    try:
        import win32com.client as win32
    except ImportError:
        raise RuntimeError("BVI Excel export needs pywin32 (Windows only) — run: pip install pywin32")
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
    try:
        from PIL import Image
    except ImportError:
        raise RuntimeError("BVI screenshot reading needs Pillow — run: pip install pillow")
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
        block("BVI Generator", [
            upload,
            dcc.Loading(type="dot", color=C["primary"], children=html.Div(
                id="bvi-msg", style={"minHeight": "18px", "margin": "10px 0 2px 2px",
                "fontSize": "13px", "color": C["primary"], "fontWeight": 600,
                "fontFamily": ds.FONT["family"]})),
            note("Vision extraction via Claude Opus 4.8 · saved to: " + BVI_OUTDIR),
            html.Div(ds.data_table(id="bvi-tbl", columns=[{"name": n, "id": i} for i, n in BVI_COLS], data=[],
                editable=True, row_deletable=True, page_action="none",
                persistence=True, persistence_type="session", persisted_props=["data"],
                style_table={**ds.TABLE_STYLE, "maxHeight": "none", "overflowX": "auto"}),
                style={"marginTop": "16px"}),
            action]),
        html.Div(id="bvi-out", style={"marginTop": "14px"}),
    ], max_width=1400)


KSA_RW_SOV = {1: 0, 2: 20, 3: 50, 4: 100, 5: 100, 6: 150, 0: 100}
KSA_RW_CORP = {1: 20, 2: 50, 3: 100, 4: 100, 5: 150, 6: 150, 0: 100}
KSA_ADDON = {"cds": 0.05, "irs": 0.005, "fx": 0.04}
KSA_CPTY_RW = 0.20


def _cqs(r) -> int:
    r = str(r).strip().upper()
    if r.startswith(("AAA", "AA")):
        return 1
    if r.startswith("A"):
        return 2
    if r.startswith("BBB"):
        return 3
    if r.startswith("BB"):
        return 4
    if r.startswith("B"):
        return 5
    if r.startswith(("C", "D", "SD")):
        return 6
    return 0


def _ksa_raw():
    b, cds, sw = D["bonds"], D["cds"], D["swaps"]
    cqs_b = b["rating"].map(_cqs)
    rw_b = np.where(_gov_mask(b), cqs_b.map(KSA_RW_SOV), cqs_b.map(KSA_RW_CORP)).astype(float)
    rw_c = cds["rating"].map(_cqs).map(KSA_RW_CORP).astype(float)
    exp_cds = float(cds["nom"].abs().sum())
    rwa_cds = float((cds["nom"].clip(lower=0) * rw_c / 100).sum()) + exp_cds * KSA_ADDON["cds"] * KSA_CPTY_RW
    exp_irs = float(sw["nom"].abs().sum()) if "nom" in sw.columns else 0.0
    return [("Bonds", float(b["mv"].sum()), float((b["mv"] * rw_b / 100).sum())),
            ("CDS", exp_cds, rwa_cds),
            ("Cash", float(CASH or 0.0), 0.0),
            ("IRS", exp_irs, exp_irs * KSA_ADDON["irs"] * KSA_CPTY_RW),
            ("Futures", 0.0, 0.0),
            ("FX", float(M["fx_mv"]), 0.0)]


def ksa_table():
    cats = _ksa_raw()
    tot = sum(r for _, _, r in cats)
    rows = [{"Category": c, "Exposure": eur(e), "Ø RW": f"{(r / e * 100 if e else 0):.0f} %",
             "RWA": eur(r), "% NAV": f"{r / NAV * 100:.1f} %"} for c, e, r in cats]
    rows.append({"Category": "Σ Total", "Exposure": eur(sum(e for _, e, _ in cats)),
                 "Ø RW": "", "RWA": eur(tot), "% NAV": f"{tot / NAV * 100:.1f} %"})
    return pd.DataFrame(rows), tot, (tot / NAV * 100 if NAV else 0.0)


def _ksa_system():
    cats = _ksa_raw()
    tot = sum(r for _, _, r in cats)
    lines = "\n".join(f"- {c}: exposure {e:,.0f} EUR, RWA {r:,.0f} EUR" for c, e, r in cats)
    return (
        "You are a risk analyst inside a fixed-income fund dashboard. Answer what-if questions about the "
        "fund's KSA (Kreditrisiko-Standardansatz / Basel standardised approach for credit risk).\n\n"
        "Method: RWA = exposure x risk weight, summed over categories; Fund KSA weight = total RWA / NAV; "
        "own-funds requirement = 8% x RWA.\n"
        "Risk weights by credit-quality step — sovereigns: AAA-AA 0%, A 20%, BBB 50%, BB/B 100%, CCC+ 150%; "
        "corporates/financials: AAA-AA 20%, A 50%, BBB/BB 100%, B/CCC+ 150%; unrated 100%. CDS sold "
        "protection = reference-name corporate weight on notional (+5% counterparty add-on); IRS 0.5%x20% "
        "and FX 4%x20% counterparty add-on on notional; futures (CCP) ~0%; cash 0%.\n\n"
        f"Current fund state:\nNAV: {NAV:,.0f} EUR\nTotal RWA: {tot:,.0f} EUR\n"
        f"Fund KSA weight: {tot / NAV * 100:.1f}%\nOwn funds @8%: {tot / NAV * 100 * 0.08:.2f}% of NAV\n{lines}\n\n"
        "When the user proposes a trade, assume it is funded from cash (asset swap, NAV unchanged) unless "
        "stated. Compute the RWA delta, the new total RWA and the new Fund KSA weight (%). Keep it to 3-5 "
        "short lines, show the arithmetic, end with the new KSA weight. Rough estimate, not a regulatory "
        "figure. Answer in the user's language.")


def _ksa_chat_view(hist):
    bubbles = []
    for m in hist or []:
        u = m.get("role") == "user"
        bubbles.append(html.Div(dcc.Markdown(m.get("content", "")), style={
            "alignSelf": "flex-end" if u else "flex-start", "maxWidth": "86%", "margin": "5px 0",
            "padding": "9px 14px", "borderRadius": "12px",
            "background": ds.COLORS["tint"] if u else ds.COLORS["surface"],
            "border": f"1px solid {ds.COLORS['border']}", "fontFamily": ds.FONT["family"],
            "fontSize": "13.5px", "color": ds.COLORS["text"]}))
    return html.Div(bubbles, style={"display": "flex", "flexDirection": "column"})


def tab_ksa():
    if not PORTFOLIO_OK:
        return data_error_panel("KSA needs portfolio data.", PORTFOLIO_ERR)
    df, tot_rwa, ksa_w = ksa_table()
    key = [stat("Fund KSA Weight", f"{ksa_w:.1f} %", "Ø risk weight · RWA / NAV", ds.COLORS["highlight"]),
           stat("Own Funds @ 8%", f"{ksa_w * 0.08:.2f} %", "capital requirement, % NAV"),
           stat("Total RWA", eur(tot_rwa), "risk-weighted assets"),
           stat("Basis (NAV)", eur(NAV), "fund volume")]
    return ds.container([
        ds.section("KSA-Score"),
        _grid(key),
        block("RWA by category", rep_table(df, export=False)),
        block("Ask KSA — what-if", [
            dcc.Loading(type="dot", color=ds.COLORS["primary"],
                        children=html.Div(id="ksa-chat", style={"marginBottom": "12px"})),
            html.Div([
                dcc.Input(id="ksa-q", type="text", debounce=False, style=ISS_INPUT_BIG,
                          placeholder="e.g. how does the KSA change if I buy a 2 MM BB corporate bond?"),
                html.Button("Ask", id="ksa-send", n_clicks=0, style=ISS_BTN_BIG),
            ], style=ISS_CONTROLS_ROW),
            dcc.Store(id="ksa-hist", data=[], storage_type="session"),
        ]),
    ], max_width=1400)


ADMIN_SUBTABS = [("KSA", "ksa", tab_ksa), ("BVI", "bvi", tab_bvi)]


def admin_analysis():
    return _subtabs("ksa", ADMIN_SUBTABS)


TOP_TABS = [("Admin", "admin", admin_analysis),
            ("Portfolio", "pf", portfolio_analysis),
            ("Issuer", "iss", issuer_analysis)]

app = Dash(__name__, title="nordIX", suppress_callback_exceptions=True)
_POLISH_CSS = """
<style>
  html{scroll-behavior:smooth}
  #busy{position:fixed;inset:0;z-index:9999;display:none;flex-direction:column;align-items:center;
    justify-content:center;gap:14px;background:rgba(10,8,28,.62);backdrop-filter:blur(2px);cursor:pointer}
  #busy.busy-on{display:flex}
  .busy-ring{width:56px;height:56px;border-radius:50%;border:4px solid rgba(192,163,100,.22);
    border-top-color:#C0A364;animation:busyspin .8s linear infinite;
    box-shadow:0 0 22px rgba(192,163,100,.35)}
  @keyframes busyspin{to{transform:rotate(360deg)}}
  .busy-txt{font-family:'Georgia Pro',Georgia,serif;font-size:15px;letter-spacing:.4px;color:#D4CEC0;text-transform:lowercase}
  .busy-pct{font-family:'Georgia Pro',Georgia,serif;font-size:30px;font-weight:600;color:#E7E1D3;
    font-variant-numeric:tabular-nums;min-width:74px;text-align:center}
  .busy-hint{font-family:'Helvetica Neue',Arial,sans-serif;font-size:11px;color:#9691A9;opacity:.7}
  .stat-card{-webkit-font-smoothing:antialiased}
  .stat-card:hover{box-shadow:inset 0 1px 0 rgba(255,255,255,.07),0 10px 26px rgba(0,0,0,.42);
    transform:translateY(-1px);border-color:rgba(192,163,100,.4)}
  /* Sticky brand header */
  .cm-header{position:sticky;top:0;z-index:40;box-shadow:0 12px 34px rgba(0,0,0,.5)}
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
  .dash-spreadsheet-container .dash-filter input::placeholder{color:transparent!important}
  .dash-spreadsheet-container .dash-cell--selected,
  .dash-spreadsheet-container td.focused{background:var(--c-tint)!important;
    outline:1px solid var(--c-brand)!important}
  /* Neutral scrollbars (read on both themes) */
  *::-webkit-scrollbar{height:10px;width:10px}
  *::-webkit-scrollbar-thumb{background:rgba(128,128,128,.34);border-radius:6px}
  *::-webkit-scrollbar-thumb:hover{background:rgba(128,128,128,.5)}
  .tab,button,.dash-dropdown-trigger{transition:color .15s,background .15s,border-color .15s,box-shadow .15s}
  .tab{flex:0 0 auto!important}
  .tab-parent,.tab-container{border:none!important;box-shadow:none!important}
  .cm-header .tab-content{display:none!important}
  input:focus,textarea:focus{outline:none;box-shadow:0 0 0 3px rgba(192,163,100,.22)}
  ::selection{background:rgba(192,163,100,.26)}
  /* Single tight layout — the dense variant, always on */
  .cm-panel{padding:10px 14px!important;margin-bottom:12px!important}
  .stat-card{padding:10px 13px!important}
  .dash-spreadsheet-inner td,.dash-spreadsheet-inner th{padding:4px 8px!important;font-size:12px!important}
  /* ── dcc.Dropdown = Dash 4.1 CUSTOM dropdown. Themed via its REAL class names. ──
     Confirmed from async-dropdown.js: .dash-dropdown-trigger is the box, -content the
     menu, -option each row. The component sets INLINE background:, so !important is required. */
  .dash-dropdown-trigger,.dash-dropdown-trigger:hover,.dash-dropdown-trigger:focus,
  .dash-dropdown-trigger:active,.dash-dropdown-trigger[aria-expanded="true"]{
    background:var(--c-input)!important;color:var(--c-text)!important;
    border:1px solid rgba(192,163,100,.34)!important;border-radius:10px!important;min-height:36px;
    padding:8px 12px!important;font-family:'Helvetica Neue',Arial,sans-serif!important;font-size:13px!important;
    outline:none!important;box-shadow:inset 0 1px 0 rgba(255,255,255,.07),0 1px 2px rgba(0,0,0,.28)!important}
  .dash-dropdown-value{color:#F6F3EC!important;font-weight:500!important}
  .dash-dropdown-placeholder{color:var(--c-muted)!important}
  .dash-dropdown-trigger-icon,.dash-dropdown-clear{color:var(--c-muted)!important;
    fill:var(--c-muted)!important;stroke:var(--c-muted)!important}
  .dash-dropdown-content{background:var(--c-input)!important;color:var(--c-text)!important;
    border:1px solid var(--c-border)!important;border-radius:3px!important;overflow:hidden;
    box-shadow:0 16px 40px rgba(0,0,0,.55)!important}
  .dash-dropdown-options{background:var(--c-input)!important}
  .dash-dropdown-option{background:var(--c-input)!important;color:#EDE8DC!important;
    font-family:'Helvetica Neue',Arial,sans-serif!important;font-size:13px!important;padding:8px 12px!important}
  .dash-dropdown-option:hover,.dash-dropdown-option[data-state="checked"],
  .dash-dropdown-option[aria-selected="true"]{background:var(--c-tint)!important;color:var(--c-ink)!important}
  .dash-dropdown-search,.dash-dropdown-search-container{background:var(--c-input)!important;
    color:var(--c-text)!important;border-color:var(--c-border)!important}
  .dash-dropdown-search::placeholder{color:var(--c-muted)!important}
  .dash-dropdown-search-icon{color:var(--c-muted)!important}
  /* Issuer search bar: dropdown matched in height and radius to the input + button beside it */
  .iss-dd .dash-dropdown-trigger{min-height:50px!important;height:50px!important;font-size:15px!important;
    padding:0 16px!important;border-radius:12px!important;display:flex!important;align-items:center!important}
  .iss-dd .dash-dropdown-value{font-size:15px!important}
  .iss-dd .dash-dropdown-option{font-size:14px!important;padding:10px 14px!important}
  /* Issuer input: readable placeholder + gold focus ring to match the buttons */
  input[id$="-input"]::placeholder,input[id="prosp-issuer"]::placeholder{color:var(--c-muted)!important;opacity:.85}
  button,button:focus,button:active,button:focus-visible{outline:none!important}
  button:hover{filter:brightness(1.05)}
  /* DataTable — kill stray white behind cells */
  .dash-spreadsheet-container,.dash-spreadsheet-container .dash-spreadsheet-inner,
  .dash-spreadsheet-inner svg{background:var(--c-surface)!important}
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
app.index_string = (ds.index_string().replace("</head>", _POLISH_CSS + "</head>")
                    .replace("</body>", _BVI_PASTE_JS + "</body>"))
TOP_BUILD = {val: build for _, val, build in TOP_TABS}

app.layout = ds.page([
    html.Div([
        html.Div([
            brand_logo(40),
            dcc.Tabs(id="top-tabs", value="pf", colors=TAB_COLORS,
                     persistence=True, persistence_type="session",
                     style={"display": "flex", "flexWrap": "wrap", "gap": "12px", "border": "none"},
                     children=[dcc.Tab(label=lbl, value=val, style=TOPTAB_STYLE,
                                       selected_style=TOPTAB_SELECTED) for lbl, val, _ in TOP_TABS]),
        ], style={"display": "flex", "alignItems": "center", "gap": "30px", "flexWrap": "wrap",
                  "justifyContent": "space-between",
                  "padding": "12px 30px", "background": "linear-gradient(180deg,#12102A,#0A081C)"}),
        html.Div(style={"height": "2px",
                        "background": "linear-gradient(90deg,rgba(192,163,100,0),#C0A364 50%,rgba(192,163,100,0))"}),
        html.Div(style={"height": "1px",
                        "background": "linear-gradient(90deg,transparent,rgba(0,0,0,.55),transparent)"}),
    ], className="cm-header"),
    html.Div([html.Div(build(), id=f"sec-{val}") for _, val, build in TOP_TABS],
             style={"paddingTop": "6px"}),
    html.Div([
        html.Div(className="busy-ring"),
        html.Div("working…", className="busy-txt"),
        html.Div("0%", id="busy-pct", className="busy-pct"),
        html.Div("click to dismiss", className="busy-hint"),
    ], id="busy", className="busy-off", n_clicks=0),
    dcc.Interval(id="busy-tick", interval=350, disabled=True, n_intervals=0, max_intervals=200),
])


BUSY_SHOW = ["liqm-run", "cred-run", "prosp-search", "prosp-go", "prosp-run-file",
             "ksa-send", "xac-send", "xap-send", "xam-send"]
BUSY_HIDE_STORES = ["liqm-store", "cred-store", "prosp-store", "ksa-hist", "xac-hist", "xap-hist", "xam-hist"]
BUSY_HIDE_STATUS = ["liqm-status", "cred-status", "prosp-status"]

app.clientside_callback(
    "function(){var c=dash_clientside.callback_context;"
    "if(!c.triggered||!c.triggered.length){return window.dash_clientside.no_update;}"
    "var id=c.triggered[0].prop_id.split('.')[0];"
    "var show=" + json.dumps(BUSY_SHOW) + ";"
    "if(show.indexOf(id)>=0){return ['busy-on',false,0,'0%'];}"
    "return ['busy-off',true,0,'0%'];}",
    [Output("busy", "className"), Output("busy-tick", "disabled"),
     Output("busy-tick", "n_intervals"), Output("busy-pct", "children")],
    [Input(b, "n_clicks") for b in BUSY_SHOW]
    + [Input(s, "data") for s in BUSY_HIDE_STORES]
    + [Input(s, "children") for s in BUSY_HIDE_STATUS]
    + [Input("busy", "n_clicks")],
    prevent_initial_call=True)

app.clientside_callback(
    "function(n,cur){var v=parseInt(cur)||0;v=v+Math.max(1,Math.floor((96-v)*0.10));"
    "if(v>96){v=96;}return v+'%';}",
    Output("busy-pct", "children", allow_duplicate=True),
    Input("busy-tick", "n_intervals"), State("busy-pct", "children"),
    prevent_initial_call=True)


@app.callback([Output(f"sec-{val}", "style") for _, val, _ in TOP_TABS], Input("top-tabs", "value"))
def _toggle_top(val):
    return [{} if v == val else {"display": "none"} for _, v, _ in TOP_TABS]


@app.callback(Output("ksa-hist", "data"), Output("ksa-q", "value"),
              Input("ksa-send", "n_clicks"), Input("ksa-q", "n_submit"),
              State("ksa-q", "value"), State("ksa-hist", "data"), prevent_initial_call=True)
def ksa_ask(_n, _s, q, hist):
    q = (q or "").strip()
    if not q:
        return no_update, no_update
    hist = (hist or []) + [{"role": "user", "content": q}]
    try:
        msg = _anthropic().messages.create(model=BVI_MODEL, max_tokens=800,
                                           system=_ksa_system(), messages=hist)
        ans = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
    except Exception as ex:
        ans = f"⚠️ {ex}"
    return hist + [{"role": "assistant", "content": ans or "(no answer)"}], ""


@app.callback(Output("ksa-chat", "children"), Input("ksa-hist", "data"))
def ksa_render(hist):
    return _ksa_chat_view(hist) if hist else no_update


def _register_xagent(prefix):
    @app.callback(Output(f"{prefix}-hist", "data"), Output(f"{prefix}-q", "value"),
                  Input(f"{prefix}-send", "n_clicks"), Input(f"{prefix}-q", "n_submit"),
                  State(f"{prefix}-q", "value"), State(f"{prefix}-hist", "data"),
                  State(f"{prefix}-agent", "value"), prevent_initial_call=True)
    def _cb(_n, _s, q, hist, agent):
        q = (q or "").strip()
        if not q:
            return no_update, no_update
        who = AGENTS.get(agent, AGENTS[AGENT_ORDER[0]])["name"]
        hist = (hist or []) + [{"role": "user", "content": q}]
        try:
            ans = _agent_reply(agent or AGENT_ORDER[0], hist)
        except Exception as ex:
            ans = f"⚠️ {ex}"
        return hist + [{"role": "assistant", "content": f"**{who}:** {ans or '(no answer)'}"}], ""

    @app.callback(Output(f"{prefix}-chat", "children"), Input(f"{prefix}-hist", "data"))
    def _render(hist):
        return _ksa_chat_view(hist) if hist else no_update


_register_xagent("xac")
_register_xagent("xap")
_register_xagent("xam")


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
        os.makedirs(BVI_OUTDIR, exist_ok=True)
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


@app.callback(Output("cmap", "figure"), Output("cr2", "figure"),
              Input("credit-src", "value"), Input("cmap-x", "value"), Input("cmap-y", "value"))
def update_credit(src: str, xk: str, yk: str):
    cdf = CREDIT_VIEWS.get(src, CREDIT_VIEWS[CREDIT_SRC[0]])
    return _safe_fig(lambda: fig_credit_map(cdf, xk, yk)), _safe_fig(lambda: fig_heatmap(cdf))


@app.callback(Output("cred-store", "data"), Output("cred-status", "children"),
              Input("cred-run", "n_clicks"), State("cred-input", "value"), State("cred-mode", "value"),
              prevent_initial_call=True)
def run_credit(_n, company, mode_lbl):
    if not company or not company.strip():
        return no_update, "Please enter an issuer."
    try:
        cm = _cm()
    except Exception as ex:
        return no_update, f"Engine not loadable: {ex}"
    mode = CREDIT_MODES.get(mode_lbl, "corp")
    try:
        data = cm._issuer_job(company.strip(), mode, False)
    except Exception as ex:
        return no_update, f"Analysis failed: {ex}"
    data.setdefault("_mode", mode)
    return data, ("from cache" if data.get("_cached") else "live — done")


@app.callback(Output("cred-output", "children"), Input("cred-store", "data"))
def render_credit(data):
    if not data:
        return no_update
    try:
        return _cm().build_output(data, data.get("_mode", "corp"))
    except Exception as ex:
        return _cm_error(f"Render failed: {ex}")


@app.callback(Output("cred-pdf-dl", "data"), Output("pdf-status", "children"),
              Input("btn-pdf", "n_clicks"), State("cred-store", "data"), prevent_initial_call=True)
def credit_pdf(n, data):
    if not n or not data or data.get("error"):
        return no_update, "No report."
    try:
        pdf = _cm().gen_pdf(data, data.get("_mode", "corp"))
        if callable(pdf):
            buf = io.BytesIO(); pdf(buf); pdf = buf.getvalue()
    except Exception as ex:
        return no_update, f"Error: {ex}"
    tick = str(data.get("ticker") or "").strip()
    if not tick:
        _w = re.sub(r'[^A-Za-z0-9 ]+', "", str(data.get("company", ""))).split()
        tick = _w[0] if _w else "memo"
    tick = re.sub(r'[<>:"/\\|?*\s]+', "", tick) or "memo"
    name = f"{datetime.date.today():%Y%m%d}_{tick}"
    try:
        os.makedirs(CRED_OUTDIR, exist_ok=True)
        dest = os.path.join(CRED_OUTDIR, f"{name}.pdf")
        k = 2
        while os.path.exists(dest):
            dest = os.path.join(CRED_OUTDIR, f"{name}_{k}.pdf"); k += 1
        with open(dest, "wb") as fh:
            fh.write(pdf)
        return no_update, f"Saved: {dest}"
    except Exception as ex:
        return dcc.send_bytes(pdf, filename=f"{name}.pdf"), f"Folder unavailable — downloaded instead ({ex})."


@app.callback(Output("liqm-store", "data"), Output("liqm-status", "children"),
              Input("liqm-run", "n_clicks"), State("liqm-input", "value"), State("liqm-mode", "value"),
              prevent_initial_call=True)
def run_liquidity(_n, company, mode_lbl):
    if not company or not company.strip():
        return no_update, "Please enter an issuer."
    mode = CREDIT_MODES.get(mode_lbl, "corp")
    try:
        data = _credit_metrics_job(company.strip(), mode)
    except Exception as ex:
        return no_update, f"Model failed: {ex}"
    return {"mode": mode, "issuer": company.strip(), "data": data}, "done"


@app.callback(Output("liqm-output", "children"), Input("liqm-store", "data"))
def render_liquidity(store):
    if not store or not store.get("data"):
        return no_update
    try:
        return build_credit_model(store["mode"], store["data"], store.get("issuer", ""))
    except Exception as ex:
        return _cm_error(f"Model render failed: {ex}")


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


@app.callback(Output("prosp-store", "data"),
              Input("prosp-go", "n_clicks"), State("prosp-issuer", "value"),
              State("prosp-cand", "data"), prevent_initial_call=True)
def analyze_prospectus_found(_n, issuer, cand):
    try:
        cm = _cm()
    except Exception as ex:
        return {"_error": f"Engine not loadable: {ex}"}
    url = (cand or {}).get("url", "")
    label = f"{(issuer or '').strip()} — use this prospectus: {url}" if url else (issuer or "").strip()
    try:
        return _run_prospectus(cm, label, None)
    except Exception as ex:
        return {"_error": f"Analysis failed: {ex}"}


@app.callback(Output("prosp-store", "data", allow_duplicate=True),
              Input("prosp-run-file", "n_clicks"), State("prosp-issuer", "value"),
              State("prosp-files-data", "data"), prevent_initial_call=True)
def analyze_prospectus_file(_n, issuer, files):
    if not files:
        return no_update
    try:
        return _run_prospectus(_cm(), (issuer or "").strip(), files)
    except Exception as ex:
        return {"_error": f"Analysis failed: {ex}"}


@app.callback(Output("prosp-output", "children"), Input("prosp-store", "data"))
def render_prospectus(data):
    if not data:
        return no_update
    if data.get("_error"):
        return _cm_error(data["_error"])
    try:
        return _cm().build_prospectus_output(data)
    except Exception as ex:
        return _cm_error(f"Render failed: {ex}")


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


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(f"\n  >  Open the nordIX dashboard in your browser:  http://localhost:{PORT}\n")
    app.run(host="0.0.0.0", port=PORT, debug=False)
