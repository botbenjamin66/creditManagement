import os, re, json, urllib.request
from datetime import date
from collections import OrderedDict

_UA = "nordIX-CreditPlatform/1.0 (internal research)"
_SEC_UA = os.environ.get("SEC_UA", "nordIX Research benjamin.suermann@web.de")
_TIMEOUT = int(os.environ.get("DATAFEED_TIMEOUT", "12"))


def _get_json(url, timeout=_TIMEOUT, ua=_UA):
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


_WB_INDICATORS = [
    ("NY.GDP.MKTP.CD",    "GDP (current US$ bn)",        1e-9),
    ("NY.GDP.MKTP.KD.ZG", "Real GDP growth (%)",         1.0),
    ("FP.CPI.TOTL.ZG",    "Inflation, CPI (%)",          1.0),
    ("GC.DOD.TOTL.GD.ZS", "Central govt debt (% GDP)",   1.0),
    ("GC.NLD.TOTL.GD.ZS", "Fiscal balance (% GDP)",      1.0),
    ("BN.CAB.XOKA.GD.ZS", "Current account (% GDP)",     1.0),
    ("FI.RES.TOTL.MO",    "Reserves (months imports)",   1.0),
    ("SL.UEM.TOTL.ZS",    "Unemployment (%)",            1.0),
]
_WB_STOP = {"the", "of", "republic", "federal", "kingdom", "state", "states",
            "people", "peoples", "democratic", "grand", "duchy", "principality",
            "and", "co", "cooperative"}
_WB_COUNTRIES = None


def _wb_countries():
    global _WB_COUNTRIES
    if _WB_COUNTRIES is None:
        try:
            data = _get_json("https://api.worldbank.org/v2/country?format=json&per_page=400")
            _WB_COUNTRIES = data[1] if isinstance(data, list) and len(data) > 1 else []
        except Exception:
            _WB_COUNTRIES = []
    return _WB_COUNTRIES


def _wb_code(name):
    countries = _wb_countries()
    if not countries:
        return None, None
    nl = (name or "").lower()
    for c in countries:
        if c.get("name", "").lower() == nl:
            return c["id"], c["name"]
    for c in countries:
        cn = c.get("name", "").lower()
        if cn and (cn in nl or nl in cn):
            return c["id"], c["name"]
    toks = {t for t in re.split(r"[^a-z]+", nl) if t and t not in _WB_STOP}
    best, best_score = None, 0
    for c in countries:
        ctoks = {t for t in re.split(r"[^a-z]+", c.get("name", "").lower())
                 if t and t not in _WB_STOP}
        score = len(toks & ctoks)
        if score > best_score:
            best, best_score = c, score
    return (best["id"], best["name"]) if best and best_score else (None, None)


def worldbank_block(issuer):
    code, resolved = _wb_code(issuer)
    if not code:
        return "", {}
    rows, structured = [], {}
    for ind, label, scale in _WB_INDICATORS:
        try:
            data = _get_json(f"https://api.worldbank.org/v2/country/{code}/indicator/{ind}"
                             f"?format=json&per_page=8&date=2019:2025")
            obs = data[1] if isinstance(data, list) and len(data) > 1 else []
            pairs = sorted((o["date"], o["value"]) for o in obs if o.get("value") is not None)
            if not pairs:
                continue
            rows.append(f"  {label}: " + "  ".join(f"{y}: {v*scale:,.1f}" for y, v in pairs[-5:]))
            structured[label] = {y: v * scale for y, v in pairs[-5:]}
        except Exception:
            continue
    if not rows:
        return "", {}
    return (f"World Bank data for {resolved} (source: World Bank Indicators API):\n"
            + "\n".join(rows)), structured


_EDGAR_CONCEPTS = [
    ("Revenues",                                            "Revenue", 1e-9),
    ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenue", 1e-9),
    ("NetIncomeLoss",                                       "Net income", 1e-9),
    ("Assets",                                              "Total assets", 1e-9),
    ("Liabilities",                                         "Total liabilities", 1e-9),
    ("StockholdersEquity",                                  "Equity", 1e-9),
    ("CashAndCashEquivalentsAtCarryingValue",               "Cash", 1e-9),
    ("LongTermDebtNoncurrent",                              "Long-term debt", 1e-9),
]
_EDGAR_TICKERS = None


def _edgar_tickers():
    global _EDGAR_TICKERS
    if _EDGAR_TICKERS is None:
        try:
            _EDGAR_TICKERS = _get_json("https://www.sec.gov/files/company_tickers.json", ua=_SEC_UA)
        except Exception:
            _EDGAR_TICKERS = {}
    return _EDGAR_TICKERS


def _edgar_cik(name):
    tk = _edgar_tickers()
    if not tk:
        return None
    nl = (name or "").lower().strip()
    nl_core = re.sub(r"\b(ag|se|nv|sa|plc|inc|corp|co|ltd|group|holding|holdings|the)\b",
                     "", nl).strip()
    rows = tk.values() if isinstance(tk, dict) else tk
    for r in rows:
        if nl in (str(r.get("title", "")).lower(), str(r.get("ticker", "")).lower()):
            return str(r.get("cik_str", "")).zfill(10)
    for r in rows:
        title = str(r.get("title", "")).lower()
        if nl_core and (nl_core in title or title in nl):
            return str(r.get("cik_str", "")).zfill(10)
    return None


def _annual_points(series):
    best = {}
    for u in series:
        if u.get("form") not in ("10-K", "20-F") or u.get("fp") != "FY":
            continue
        val, end, start = u.get("val"), u.get("end"), u.get("start")
        if val is None or not end:
            continue
        if start:
            try:
                days = (date.fromisoformat(end) - date.fromisoformat(start)).days
            except Exception:
                continue
            if not 350 <= days <= 380:
                continue
        try:
            yr = int(end[:4])
        except Exception:
            continue
        prev = best.get(yr)
        if prev is None or u.get("filed", "") > prev.get("filed", ""):
            best[yr] = {"fy": yr, "val": val, "filed": u.get("filed", "")}
    return [best[y] for y in sorted(best)[-4:]]


def edgar_block(issuer):
    cik = _edgar_cik(issuer)
    if not cik:
        return "", {}
    try:
        facts = _get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json", ua=_SEC_UA)
    except Exception:
        return "", {}
    usgaap = (facts.get("facts") or {}).get("us-gaap") or {}
    label_tags = OrderedDict()
    for tag, label, scale in _EDGAR_CONCEPTS:
        label_tags.setdefault(label, [scale, []])[1].append(tag)
    rows, structured = [], {}
    for label, (scale, tags) in label_tags.items():
        best = []
        for tag in tags:
            if tag not in usgaap:
                continue
            units = usgaap[tag].get("units") or {}
            pts = _annual_points(units.get("USD") or next(iter(units.values()), []))
            if pts and (not best or (pts[-1]["fy"], len(pts)) > (best[-1]["fy"], len(best))):
                best = pts
        if not best:
            continue
        rows.append(f"  {label} (US$ bn): "
                    + "  ".join(f"FY{str(u['fy'])[-2:]}: {u['val']*scale:,.1f}" for u in best))
        structured[label] = {f"FY{str(u['fy'])[-2:]}": u["val"] * scale for u in best}
    if not rows:
        return "", {}
    return (f"SEC EDGAR filings for {facts.get('entityName', issuer)} "
            f"(source: data.sec.gov XBRL companyfacts):\n" + "\n".join(rows)), structured


def bloomberg_available():
    try:
        import blpapi  # noqa: F401
        return True
    except Exception:
        return False


def bloomberg_reference(securities, fields, timeout=8):
    try:
        import blpapi
    except Exception:
        return {}
    import time as _t
    out, session = {}, None
    try:
        opts = blpapi.SessionOptions()
        opts.setServerHost(os.environ.get("BLP_HOST", "localhost"))
        opts.setServerPort(int(os.environ.get("BLP_PORT", "8194")))
        session = blpapi.Session(opts)
        if not session.start() or not session.openService("//blp/refdata"):
            return {}
        req = session.getService("//blp/refdata").createRequest("ReferenceDataRequest")
        for s in securities:
            req.append("securities", s)
        for f in fields:
            req.append("fields", f)
        session.sendRequest(req)
        deadline = _t.time() + timeout
        while _t.time() < deadline:
            ev = session.nextEvent(500)
            for m in ev:
                if not m.hasElement("securityData"):
                    continue
                sd = m.getElement("securityData")
                for i in range(sd.numValues()):
                    s = sd.getValueAsElement(i)
                    fd = s.getElement("fieldData")
                    vals = {}
                    for f in fields:
                        if fd.hasElement(f):
                            try:
                                vals[f] = fd.getElementAsFloat(f)
                            except Exception:
                                vals[f] = fd.getElementAsString(f)
                    out[s.getElementAsString("security")] = vals
            if ev.eventType() == blpapi.Event.RESPONSE:
                break
        return out
    except Exception as ex:
        print(f"[datafeeds] bloomberg_reference failed: {ex}")
        return {}
    finally:
        try:
            if session:
                session.stop()
        except Exception:
            pass


_BBG_FIELDS = ["NAME", "RTG_SP_LT_LC_ISSUER_CREDIT", "RTG_MOODY_LONG_TERM",
               "RTG_FITCH_LT_ISSUER_DEFAULT", "PX_LAST", "YLD_YTM_MID",
               "Z_SPRD_MID", "OAS_SPREAD_MID", "CDS_SPREAD_TICKER_5Y"]


def bloomberg_block(issuer, securities=None):
    if not securities or not bloomberg_available():
        return "", {}
    data = bloomberg_reference(securities, _BBG_FIELDS)
    if not data:
        return "", {}
    rows = []
    for sec, vals in data.items():
        parts = [f"{k}={v}" for k, v in vals.items() if v not in (None, "")]
        if parts:
            rows.append(f"  {sec}: " + "  ".join(parts))
    if not rows:
        return "", {}
    return (f"Bloomberg reference data for {issuer} (source: Bloomberg Desktop API, live):\n"
            + "\n".join(rows)), data


def reference_data(mode, issuer, securities=None):
    blocks, structured = [], {}

    def add(fn, *a):
        try:
            txt, st = fn(*a)
            if txt:
                blocks.append(txt)
                structured.update(st or {})
        except Exception as ex:
            print(f"[datafeeds] feed failed: {ex}")

    if mode == "sov":
        add(worldbank_block, issuer)
    elif mode == "corp":
        add(edgar_block, issuer)
    add(bloomberg_block, issuer, securities)

    if not blocks:
        return "", {}
    header = ("VERIFIED REFERENCE DATA — these figures come from authoritative feeds. "
              "Anchor every overlapping number in your analysis to these values. Where a "
              "number is not here and not in a source you retrieve, write [Not public] "
              "rather than estimating.\n\n")
    return header + "\n\n".join(blocks), structured
