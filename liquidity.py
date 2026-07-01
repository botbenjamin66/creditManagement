LIQ_INPUTS = {
    "corp": [
        {"key": "revenue",          "label": "Revenue (EUR m)",                     "hint": "Latest FY revenue.", "group": "Starting position"},
        {"key": "ebitda",           "label": "EBITDA (EUR m)",                      "hint": "Latest FY EBITDA.", "group": "Starting position"},
        {"key": "net_debt",         "label": "Net debt (EUR m)",                    "hint": "Total debt minus cash.", "group": "Starting position"},
        {"key": "cash",             "label": "Cash & equivalents (EUR m)",          "hint": "Cash on hand today.", "group": "Starting position"},
        {"key": "undrawn_rcf",      "label": "Undrawn facilities (EUR m)",          "hint": "Available undrawn RCF.", "group": "Starting position"},
        {"key": "capex",            "label": "Capex p.a. (EUR m)",                  "hint": "Annual capex, positive number.", "group": "Annual drivers"},
        {"key": "cash_interest",    "label": "Cash interest p.a. (EUR m)",          "hint": "Annual cash interest, positive number.", "group": "Annual drivers"},
        {"key": "other_outflows",   "label": "Other outflows p.a. (EUR m)",         "hint": "Cash taxes + dividends + working-capital use, combined, positive number.", "group": "Annual drivers"},
        {"key": "maturities",       "label": "Debt maturities, next 4y (EUR m)",    "hint": "Debt maturing in each of the next four years.", "list": 4, "group": "Annual drivers"},
        {"key": "leverage_covenant","label": "Leverage covenant (x)",               "hint": "Net Debt/EBITDA covenant, 0 if none.", "group": "Annual drivers"},
    ],
    "fin": [
        {"key": "pre_provision_profit", "label": "Pre-provision profit p.a. (EUR m)", "hint": "Operating profit before loan losses (income minus costs).", "group": "Starting position"},
        {"key": "loans",                "label": "Customer loans (EUR m)",            "hint": "Gross customer loan book.", "group": "Starting position"},
        {"key": "cet1_capital",         "label": "CET1 capital (EUR m)",              "hint": "Common equity tier 1 amount.", "group": "Starting position"},
        {"key": "rwa",                  "label": "Risk-weighted assets (EUR m)",      "hint": "Total RWA.", "group": "Starting position"},
        {"key": "lcr",                  "label": "LCR (%)",                           "hint": "Liquidity coverage ratio.", "group": "Ratios"},
        {"key": "nsfr",                 "label": "NSFR (%)",                          "hint": "Net stable funding ratio.", "group": "Ratios"},
        {"key": "cost_of_risk_bp",      "label": "Cost of risk (bp)",                 "hint": "Annual loan-loss charge in bp of loans.", "group": "Ratios"},
        {"key": "mda_trigger",          "label": "MDA trigger / CET1 req. (%)",       "hint": "CET1 ratio at which distributions are restricted.", "group": "Ratios"},
    ],
    "sov": [
        {"key": "debt_gdp",             "label": "Debt / GDP (%)",               "hint": "General government gross debt, % of GDP.", "group": "Starting position"},
        {"key": "primary_balance",      "label": "Primary balance (% GDP)",      "hint": "Balance excluding interest, surplus positive.", "group": "Starting position"},
        {"key": "avg_cost_debt",        "label": "Average cost of debt (%)",     "hint": "Effective interest rate on the debt stock.", "group": "Starting position"},
        {"key": "interest_revenue",     "label": "Interest / Revenue (%)",       "hint": "Interest as % of government revenue.", "group": "Ratios"},
        {"key": "gross_financing_need", "label": "Gross financing need (% GDP)", "hint": "Maturing debt plus deficit, per year.", "group": "Ratios"},
        {"key": "fx_reserves_months",   "label": "FX reserves (months imports)", "hint": "Reserve cover in months of imports.", "group": "Ratios"},
        {"key": "real_growth",          "label": "Real GDP growth (%)",          "hint": "Latest real GDP growth.", "group": "Drivers"},
        {"key": "inflation",            "label": "Inflation / deflator (%)",     "hint": "Nominal GDP uplift from prices.", "group": "Drivers"},
    ],
}

LIQ_ASSUMPTIONS = {
    "corp": [
        {"key": "rev_growth",    "label": "Revenue growth (%/yr)", "min": -15, "max": 15,  "step": 0.5, "default": 2},
        {"key": "ebitda_shock",  "label": "EBITDA shock (%)",      "min": 0,   "max": 50,  "step": 1,   "default": 0},
        {"key": "rate_shock_bp", "label": "Rate shock (bp)",       "min": 0,   "max": 400, "step": 25,  "default": 0},
        {"key": "capex_flex",    "label": "Capex flex (%)",        "min": 50,  "max": 120, "step": 5,   "default": 100},
        {"key": "rcf_avail",     "label": "RCF available (%)",     "min": 0,   "max": 100, "step": 5,   "default": 100},
        {"key": "market_access", "label": "Market access (1=yes)", "min": 0,   "max": 1,   "step": 1,   "default": 1},
    ],
    "fin": [
        {"key": "income_shock",    "label": "Income shock (%)",       "min": -40, "max": 10,  "step": 1,    "default": 0},
        {"key": "cor_shock",       "label": "Cost-of-risk (x)",       "min": 1,   "max": 5,   "step": 0.25, "default": 1},
        {"key": "rwa_growth",      "label": "RWA growth (%/yr)",      "min": -5,  "max": 15,  "step": 1,    "default": 3},
        {"key": "deposit_outflow", "label": "Deposit outflow (%/yr)", "min": 0,   "max": 30,  "step": 1,    "default": 0},
        {"key": "payout",          "label": "Payout (%)",             "min": 0,   "max": 100, "step": 5,    "default": 50},
    ],
    "sov": [
        {"key": "gdp_shock",             "label": "GDP growth shock (pp)",  "min": 0,   "max": 8,   "step": 0.5, "default": 0},
        {"key": "rate_shock_bp",         "label": "Rate shock (bp)",        "min": 0,   "max": 400, "step": 25,  "default": 0},
        {"key": "primary_balance_delta", "label": "Primary balance (pp)", "min": -5, "max": 5,   "step": 0.5, "default": 0},
        {"key": "fx_shock",              "label": "FX reserve shock (%)",   "min": 0,   "max": 50,  "step": 5,   "default": 0},
    ],
}

HISTORY_KEYS = {"corp": ["revenue", "ebitda", "net_debt"], "fin": ["cet1_ratio", "lcr"], "sov": ["debt_gdp"]}

LABELS = {
    "revenue": "Revenue (EUR m)", "ebitda": "EBITDA (EUR m)", "fcf": "Free cash flow (EUR m)",
    "capex": "Capex (EUR m)", "interest": "Cash interest (EUR m)", "liquidity": "Liquidity (EUR m)",
    "net_debt": "Net debt (EUR m)", "leverage": "Net Debt/EBITDA (x)",
    "ppp": "Pre-provision profit (EUR m)", "loan_losses": "Loan losses (EUR m)",
    "net_profit": "Net profit (EUR m)", "cet1_ratio": "CET1 ratio (%)", "mda_buffer": "MDA buffer (bp)",
    "lcr": "LCR (%)", "nsfr": "NSFR (%)",
    "debt_gdp": "Debt / GDP (%)", "primary_balance": "Primary balance (% GDP)",
    "interest_revenue": "Interest / Revenue (%)", "gfn": "Gross financing need (% GDP)",
    "fx_reserves": "FX reserves (months)",
}

GROUP_ORDER = ["Starting position", "Annual drivers", "Ratios", "Drivers"]


def defaults(mode):
    return {a["key"]: a["default"] for a in LIQ_ASSUMPTIONS.get(mode, [])}


def build_inputs_schema(mode):
    props = {}
    for f in LIQ_INPUTS[mode]:
        if f.get("list"):
            props[f["key"]] = {"type": "array", "items": {"type": "number"},
                               "description": f"{f['label']} - {f['hint']} Provide {f['list']} numbers."}
        else:
            props[f["key"]] = {"type": "number", "description": f"{f['label']} - {f['hint']}"}
    hist = {k: {"type": "array", "items": {"type": "number"},
                "description": LABELS[k] + " actuals for the last 4 years, oldest first, if available."}
            for k in HISTORY_KEYS[mode]}
    props["history"] = {"type": "object", "properties": hist,
                        "description": "Recent annual actuals for chart context. Provide where available."}
    props["commentary"] = {"type": "string",
                           "description": "120-160 words, Oaktree-style: the liquidity / cash-flow quality, structural strengths and weaknesses independent of any scenario, and the single biggest vulnerability. State which inputs are disclosed versus estimated."}
    props["sources"] = {"type": "array", "items": {"type": "string"},
                        "description": "3-6 concrete dated sources actually used."}
    req = [f["key"] for f in LIQ_INPUTS[mode]] + ["commentary", "sources"]
    return {"type": "object", "properties": props, "required": req}


def _f(v, d=0.0):
    try:
        return float(v)
    except Exception:
        return d


def _flist(v, n):
    v = v if isinstance(v, list) else []
    return ([_f(x) for x in v] + [0.0] * n)[:n]


def _runway_months(liq):
    for i in range(1, len(liq)):
        if liq[i] is not None and liq[i] < 0:
            prev, cur = liq[i - 1], liq[i]
            frac = prev / (prev - cur) if (prev - cur) else 0
            return (i - 1) * 12 + 12 * max(0.0, min(1.0, frac))
    return None


def _project_corp(inp, a):
    rev0, eb0 = _f(inp.get("revenue")), _f(inp.get("ebitda"))
    capex0, intr0, other0 = _f(inp.get("capex")), _f(inp.get("cash_interest")), _f(inp.get("other_outflows"))
    cash0, rcf, nd0 = _f(inp.get("cash")), _f(inp.get("undrawn_rcf")), _f(inp.get("net_debt"))
    mats = _flist(inp.get("maturities"), 4)
    cov = _f(inp.get("leverage_covenant"))
    g, sh, rate = a["rev_growth"] / 100.0, a["ebitda_shock"] / 100.0, a["rate_shock_bp"] / 10000.0
    capexf, rcf_av, access = a["capex_flex"] / 100.0, a["rcf_avail"] / 100.0, a["market_access"] >= 0.5
    margin = eb0 / rev0 if rev0 else 0.0
    S = {k: [] for k in ["revenue", "ebitda", "fcf", "capex", "interest", "liquidity", "net_debt", "leverage"]}
    rev, eb, nd, liq = rev0, eb0, nd0, cash0 + rcf * rcf_av
    for k, v in [("revenue", rev0), ("ebitda", eb0), ("fcf", None), ("capex", capex0),
                 ("interest", intr0), ("liquidity", liq), ("net_debt", nd0),
                 ("leverage", nd0 / eb0 if eb0 else 0)]:
        S[k].append(v)
    neg_y, breach_y = None, None
    for y in range(1, 5):
        rev *= (1 + g)
        eb = rev * margin * (1 - sh)
        interest = intr0 * (1 + rate * y)
        capex = capex0 * capexf
        fcf = eb - interest - capex - other0
        mat = mats[y - 1] * (0 if access else 1)
        liq += fcf - mat
        nd -= fcf
        lev = nd / eb if eb else 0
        for k, v in [("revenue", rev), ("ebitda", eb), ("fcf", fcf), ("capex", capex),
                     ("interest", interest), ("liquidity", liq), ("net_debt", nd), ("leverage", lev)]:
            S[k].append(v)
        if neg_y is None and liq < 0:
            neg_y = y
        if breach_y is None and cov > 0 and lev > cov:
            breach_y = y
    runway = _runway_months(S["liquidity"])
    if neg_y and (breach_y is None or neg_y <= breach_y):
        constraint = f"Liquidity exhausted in year {neg_y} (no market access)"
    elif breach_y:
        constraint = f"Leverage covenant breached in year {breach_y}"
    else:
        constraint = "No binding constraint over the 4-year horizon"
    runway_txt = f"{runway:.0f} months" if runway is not None else ">48 months under this scenario"
    charts = [
        {"title": "Liquidity (no market access)", "ytitle": "EUR m", "keys": ["liquidity"], "zero": True},
        {"title": "Revenue / EBITDA / Free cash flow", "ytitle": "EUR m", "keys": ["revenue", "ebitda", "fcf"]},
        {"title": "Net leverage vs covenant", "ytitle": "x", "keys": ["leverage"], "hline": cov if cov > 0 else None},
    ]
    table = ["revenue", "ebitda", "fcf", "capex", "interest", "net_debt", "leverage", "liquidity"]
    return S, charts, table, {"runway": runway_txt, "constraint": constraint}


def _project_fin(inp, a):
    ppp0, loans0, cor_bp = _f(inp.get("pre_provision_profit")), _f(inp.get("loans")), _f(inp.get("cost_of_risk_bp"))
    cet1_0, rwa0 = _f(inp.get("cet1_capital")), _f(inp.get("rwa"))
    lcr0, nsfr0, mda = _f(inp.get("lcr")), _f(inp.get("nsfr")), _f(inp.get("mda_trigger"))
    inc_sh, cor_mult = a["income_shock"] / 100.0, a["cor_shock"]
    rwa_g, dep_out, payout = a["rwa_growth"] / 100.0, a["deposit_outflow"] / 100.0, a["payout"] / 100.0
    S = {k: [] for k in ["ppp", "loan_losses", "net_profit", "cet1_ratio", "mda_buffer", "lcr", "nsfr"]}
    cet1, rwa = cet1_0, rwa0
    cr0 = cet1_0 / rwa0 * 100 if rwa0 else 0
    for k, v in [("ppp", ppp0), ("loan_losses", loans0 * cor_bp / 10000.0), ("net_profit", None),
                 ("cet1_ratio", cr0), ("mda_buffer", (cr0 - mda) * 100), ("lcr", lcr0), ("nsfr", nsfr0)]:
        S[k].append(v)
    mda_y, lcr_y = None, None
    for y in range(1, 5):
        ppp = ppp0 * (1 - inc_sh)
        losses = loans0 * cor_bp / 10000.0 * cor_mult
        npft = ppp - losses
        npft_at = npft * 0.75 if npft > 0 else npft
        retained = npft_at * (1 - payout) if npft_at > 0 else npft_at
        cet1 += retained
        rwa *= (1 + rwa_g)
        cr = cet1 / rwa * 100 if rwa else 0
        lcr = lcr0 * (1 - dep_out) ** y
        nsfr = nsfr0 * (1 - dep_out * 0.5) ** y
        for k, v in [("ppp", ppp), ("loan_losses", losses), ("net_profit", npft_at),
                     ("cet1_ratio", cr), ("mda_buffer", (cr - mda) * 100), ("lcr", lcr), ("nsfr", nsfr)]:
            S[k].append(v)
        if mda_y is None and cr < mda:
            mda_y = y
        if lcr_y is None and lcr < 100:
            lcr_y = y
    if mda_y and (lcr_y is None or mda_y <= lcr_y):
        constraint = f"CET1 falls below the MDA trigger in year {mda_y}"
        runway_txt = f"{mda_y} year(s) of MDA headroom"
    elif lcr_y:
        constraint = f"LCR falls below 100% in year {lcr_y}"
        runway_txt = f"{lcr_y} year(s) before LCR breaches 100%"
    else:
        constraint = "Capital and liquidity buffers hold over 4 years"
        runway_txt = ">4 years of buffer under this scenario"
    charts = [
        {"title": "CET1 ratio vs MDA trigger", "ytitle": "%", "keys": ["cet1_ratio"], "hline": mda if mda else None},
        {"title": "LCR / NSFR vs 100%", "ytitle": "%", "keys": ["lcr", "nsfr"], "hline": 100},
        {"title": "Pre-provision profit vs loan losses", "ytitle": "EUR m", "keys": ["ppp", "loan_losses"]},
    ]
    table = ["ppp", "loan_losses", "net_profit", "cet1_ratio", "mda_buffer", "lcr", "nsfr"]
    return S, charts, table, {"runway": runway_txt, "constraint": constraint}


def _project_sov(inp, a):
    debt0, pb0, cod0 = _f(inp.get("debt_gdp")), _f(inp.get("primary_balance")), _f(inp.get("avg_cost_debt"))
    ir0, gfn0, fx0 = _f(inp.get("interest_revenue")), _f(inp.get("gross_financing_need")), _f(inp.get("fx_reserves_months"))
    rg0, infl = _f(inp.get("real_growth")), _f(inp.get("inflation"))
    g_real = rg0 / 100.0 - a["gdp_shock"] / 100.0
    g_nom = (1 + g_real) * (1 + infl / 100.0) - 1
    r = cod0 / 100.0 + a["rate_shock_bp"] / 10000.0
    pb = pb0 + a["primary_balance_delta"]
    fx_mult = 1 - a["fx_shock"] / 100.0
    S = {k: [] for k in ["debt_gdp", "primary_balance", "interest_revenue", "gfn", "fx_reserves"]}
    for k, v in [("debt_gdp", debt0), ("primary_balance", pb0), ("interest_revenue", ir0),
                 ("gfn", gfn0), ("fx_reserves", fx0)]:
        S[k].append(v)
    debt, cross_y = debt0, None
    for y in range(1, 5):
        debt = debt * (1 + r) / (1 + g_nom) - pb
        ir = ir0 * (1 + a["rate_shock_bp"] / 10000.0 * y * 2)
        gfn = gfn0 + max(0.0, -pb)
        fx = fx0 * (fx_mult ** y)
        for k, v in [("debt_gdp", debt), ("primary_balance", pb), ("interest_revenue", ir),
                     ("gfn", gfn), ("fx_reserves", fx)]:
            S[k].append(v)
        if cross_y is None and debt > debt0 + 15:
            cross_y = y
    delta = S["debt_gdp"][-1] - debt0
    direction = "rising" if delta > 1 else ("falling" if delta < -1 else "broadly stable")
    constraint = f"Debt/GDP {direction} ({delta:+.1f} pp to {S['debt_gdp'][-1]:.0f}%)"
    if cross_y:
        constraint += f"; +15pp threshold crossed in year {cross_y}"
    charts = [
        {"title": "Debt / GDP path", "ytitle": "% GDP", "keys": ["debt_gdp"]},
        {"title": "Gross financing need", "ytitle": "% GDP", "keys": ["gfn"]},
        {"title": "Interest/Revenue & Primary balance", "ytitle": "%", "keys": ["interest_revenue", "primary_balance"]},
    ]
    table = ["debt_gdp", "primary_balance", "interest_revenue", "gfn", "fx_reserves"]
    return S, charts, table, {"runway": f"Debt/GDP {direction}", "constraint": constraint}


_ENGINES = {"corp": _project_corp, "fin": _project_fin, "sov": _project_sov}


def project(mode, inputs, assumptions, t0=2025, history=None):
    a = defaults(mode)
    a.update({k: _f(v, a.get(k, 0)) for k, v in (assumptions or {}).items()})
    series, charts, table, head = _ENGINES[mode](inputs or {}, a)
    return {"t0": t0,
            "years_table": [str(t0 + i) for i in range(5)],
            "years_chart": [str(t0 - 4 + i) for i in range(9)],
            "series": series, "labels": LABELS, "charts": charts, "table": table,
            "headline": head, "history": history or {}}
