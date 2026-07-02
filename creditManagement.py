import dash, json, anthropic, base64, io, os, sys, time, re
import pandas as pd
try:
    from json_repair import repair_json as _repair_json
except ImportError:
    _repair_json = None
from dash import dcc, html, Input, Output, State, ALL
from pathlib import Path
from datetime import datetime

import research_db, datafeeds, verify, jobs, analysis_db, liquidity, knowledge

USE_VERIFY    = os.environ.get("CREDIT_VERIFY", "1") != "0"
USE_FEEDS     = os.environ.get("CREDIT_FEEDS", "1") != "0"
USE_ARCHIVE   = os.environ.get("CREDIT_ARCHIVE", "1") != "0"
USE_KNOWLEDGE = os.environ.get("CREDIT_KNOWLEDGE", "1") != "0"


def _knowledge(scope):
    if not USE_KNOWLEDGE:
        return ""
    try:
        return knowledge.context_for(scope)
    except Exception as ex:
        print(f"[DEBUG] knowledge load failed: {ex}")
        return ""
WEB_SEARCH_TOOL    = {"type": "web_search_20250305", "name": "web_search", "max_uses": 15}
VERIFY_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}

# ── Config ────────────────────────────────────────────────────────────────────

from dotenv import load_dotenv; load_dotenv(r"S:\benjaminSuermann\3_env\.env")
API_KEY   = os.environ["ANTHROPIC_API_KEY"]
MODEL_ANALYSIS = "claude-opus-4-8"
MODEL_ADVISOR  = "claude-opus-4-8"
MODEL_CHAT     = "claude-haiku-4-5"
LOGO_PATH = Path(__file__).parent / "logo.png"
LOGO_B64  = base64.b64encode(LOGO_PATH.read_bytes()).decode() if LOGO_PATH.exists() else ""

# The system reads this Excel live on every portfolio request (mtime-cached).
PORTFOLIO_PATH = Path(os.environ.get("PORTFOLIO_PATH", r"S:\benjaminSuermann\pfExcel.xlsx"))

sys.path.insert(0, r"S:\benjaminSuermann\3_env")
import pyDashDesign as _D
VF  = _D.FONT["family"]
VFH = _D.FONT["family"]
C   = {
    "bg":      _D.COLORS["background"],
    "surface": _D.COLORS["surface"],
    "border":  _D.COLORS["border"],
    "navy":    _D.COLORS["primary"],
    "ink":     _D.COLORS["text"],
    "accent":  _D.COLORS["positive"],
    "rose":    _D.COLORS["negative"],
    "muted":   _D.COLORS["secondary"],
    "green":   _D.COLORS["positive"],
    "red":     _D.COLORS["negative"],
}

# ── Mode Configs ──────────────────────────────────────────────────────────────

# ── Standardised periods + fixed KPI rows ─────────────────────────────────────
# Fixed so that 10 reports for 10 issuers carry the SAME rows in the SAME order.
# The model only fills values; metrics and periods are owned by the code.

FIXED_YEARS = {
    "corp": ["FY21", "FY22", "FY23", "FY24", "FY25e"],
    "fin":  ["FY21", "FY22", "FY23", "FY24", "FY25e"],
    "sov":  ["2021", "2022", "2023", "2024", "2025p"],
}

FIXED_KPIS = {
    "corp": ["Revenue (EUR bn)", "EBITDA margin (%)", "FCF (EUR bn)",
             "Net Debt/EBITDA (x)", "EBITDA/Interest (x)", "FFO/Net Debt (%)",
             "Capex/Revenue (%)", "Equity ratio (%)"],
    "fin":  ["CET1 ratio (%)", "Total Capital ratio (%)", "Leverage ratio (%)",
             "MDA buffer (bp)", "NPL ratio (%)", "Coverage ratio (%)",
             "LCR (%)", "NSFR (%)", "MREL (% RWA)", "CIR (%)", "RoTE (%)"],
    "sov":  ["Real GDP growth (%)", "Debt/GDP (%)", "Primary balance (% GDP)",
             "Fiscal balance (% GDP)", "Gross financing need (% GDP)",
             "Interest/Revenue (%)", "Current account (% GDP)",
             "FX reserves (months imports)"],
}

# ── Controlled vocabulary (renders as standardised chips) ─────────────────────
TREND = {
    "improving":     ("Improving",      C["green"]),
    "stable":        ("Stable",         C["muted"]),
    "deteriorating": ("Deteriorating",  C["red"]),
}
PEER_VERDICT = {
    "stronger": ("Stronger vs peers",      C["green"]),
    "in_line":  ("In line with peers",     C["muted"]),
    "weaker":   ("Weaker vs peers",        C["red"]),
}
VERIFY_CHIP = {
    "supported":           ("Source-verified",  C["green"]),
    "partially_supported": ("Partly verified",  C["rose"]),
    "unsupported":         ("Unverified",       C["red"]),
    "contradicted":        ("Contradicted",     C["red"]),
}
# Prospectus & Recovery controlled vocabulary
COV_STRENGTH = {
    "creditor_friendly": ("Creditor-protective",       C["green"]),
    "balanced":          ("Balanced terms",            C["muted"]),
    "issuer_friendly":   ("Issuer-friendly / loose",   C["red"]),
}
RECOVERY = {
    "high":     ("Recovery 70-100%", C["green"]),
    "moderate": ("Recovery 40-70%",  C["muted"]),
    "low":      ("Recovery 0-40%",   C["red"]),
}

# ── Meta fields per mode ──────────────────────────────────────────────────────
META_SPEC = {
    "corp": {
        "country":       "Country of domicile.",
        "sector":        "Sector, max 3 words.",
        "rating_sp":     "S&P issuer rating or empty.",
        "rating_moodys": "Moody's or empty.",
        "rating_fitch":  "Fitch or empty.",
    },
    "fin": {
        "country":          "Country of domicile.",
        "institution_type": "e.g. universal bank, Pfandbrief bank, savings bank, insurer.",
        "rating_sp":        "S&P issuer rating or empty.",
        "rating_moodys":    "Moody's or empty.",
        "rating_fitch":     "Fitch or empty.",
        "cet1":             "Current CET1 ratio, e.g. 13.4%.",
        "mrel":             "Current MREL ratio or empty.",
    },
    "sov": {
        "country":       "Country / home country.",
        "issuer_type":   "Sovereign | Supranational | Agency | Sub-Sovereign.",
        "rating_sp":     "S&P long-term rating or empty.",
        "rating_moodys": "Moody's or empty.",
        "rating_fitch":  "Fitch or empty.",
        "debt_gdp":      "Debt/GDP in % latest year, e.g. 63.5%.",
        "cds_5y":        "CDS 5Y in basis points current or empty.",
    },
}

# ── Section specs ─────────────────────────────────────────────────────────────
# One source of truth: drives the rendered order/labels AND the tool input schema
# (the "brief" becomes the schema field description). Every section carries a
# trend enum; "kpi" sections carry a fixed KPI grid; "peer" sections a verdict.

SECTION_SPEC = {
    "corp": [
        {"key": "business_model", "label": "1.  Business Model - Moat - Market Position",
         "brief": "100-150 words. How the company earns money; segments with revenue share %; the concrete competitive moat and its source; pricing power with evidence; recurring vs one-time revenue split."},
        {"key": "customers_backlog", "label": "2.  Customer Concentration - Order Backlog",
         "brief": "100-130 words. Largest customers and their revenue share %; contract terms and duration; order backlog in months of revenue; geographic revenue spread; customer concentration risk."},
        {"key": "competitors_swot", "label": "3.  Competitors - SWOT - Cyclicality",
         "brief": "100-130 words. 3-4 named direct competitors with concrete metric comparison; evidenced strengths; weaknesses with their mechanism; demonstrated behaviour through the last recession."},
        {"key": "capital_structure", "label": "4.  Capital Structure - Maturities - Covenants",
         "brief": "130-160 words. Debt by instrument and maturity with amounts; largest single maturity and its refinancing relevance; RCF size and drawn/undrawn; financial covenants with current headroom; secured vs unsecured mix; weighted average maturity and coupon."},
        {"key": "structural_subordination", "label": "5.  Structure - Subordination - Guarantees - Priority Claims",
         "brief": "120-150 words. Which legal entity issues the analysed bonds and where the operating cash and assets sit; structural and contractual subordination; upstream/downstream guarantees and their enforceability; ring-fencing; priority claims ranking ahead of senior unsecured (IFRS pension deficit, IFRS16 lease liabilities, factoring, secured debt); net implication for senior unsecured holders."},
        {"key": "financials", "label": "6.  Financial Metrics - EBITDA - FCF", "kpi": True,
         "brief": "50-70 words. Read of the financial trajectory and the single most important trend for creditors."},
        {"key": "liquidity", "label": "7.  Liquidity - Off-Balance - Maturities",
         "brief": "100-130 words. Cash on hand today; undrawn committed facilities; next 24 months of maturities by year and amount; liquidity runway in months under no market access; off-balance-sheet obligations."},
        {"key": "management", "label": "8.  Management - Capital Allocation - Event Risk",
         "brief": "100-130 words. Leadership team and tenure; historical capital-allocation track record; dominant owner or PE sponsor and its horizon; creditor vs shareholder orientation; shareholder remuneration (dividends, buybacks) and event risk (M&A, LBO, spin-off) with concrete figures."},
        {"key": "industry_macro", "label": "9.  Industry - Macro - Regulation",
         "brief": "100-130 words. Position in the industry cycle with concrete indicators; cost structure and operating leverage; FX exposure of revenue vs cost; demand drivers; relevant regulation."},
        {"key": "esg_transition", "label": "10. ESG - Transition Risk - Sustainable Funding",
         "brief": "100-130 words. Material ESG and transition risks that affect the spread: carbon/emissions exposure and decarbonisation capex; stranded-asset and regulatory transition risk; green/sustainability-linked bonds outstanding and any coupon step-ups; governance controversies; concrete impact on funding cost and investor base."},
        {"key": "stress_scenarios", "label": "11. Stress Scenarios - Covenant Headroom",
         "brief": "120-150 words. Scenario 1 at -20% EBITDA: resulting Net Debt/EBITDA and covenant test outcome. Scenario 2 at -35% EBITDA: liquidity runway in months. Name the concrete triggering event for each."},
        {"key": "risks", "label": "12. Credit Risks - Red Flags",
         "brief": "100-130 words. The 3-4 largest credit risks, each with transmission mechanism and numbers; which specific maturity becomes unservable and under what condition; which covenant breaches first."},
        {"key": "recovery_triggers", "label": "13. Recovery - Rating Triggers",
         "brief": "120-150 words. Recovery prospects for senior unsecured in a default: asset coverage and an estimated recovery band; expected-loss framing vs probability of default. Forward rating triggers: the concrete metric thresholds (e.g. Net Debt/EBITDA, FFO/Net Debt) at which S&P, Moody's and Fitch have signalled an upgrade or downgrade, and the distance to each threshold today."},
        {"key": "peer_group", "label": "14. Peer Group - Positioning", "peer": True,
         "brief": "130-160 words. 3-4 named direct credit peers with rationale; concrete comparison of leverage, margin and coverage; explicit verdict whether this issuer is a safer or riskier debtor and why."},
        {"key": "credit_curve", "label": "15. Credit Curve - Structural Positioning",
         "brief": "110-140 words. Critical maturity on the timeline; next covenant test date; positioning logic short vs long with concrete maturities and the reason."},
        {"key": "refi_toolkit", "label": "16. Refi Toolkit - Capital Markets History",
         "brief": "130-160 words. Available instruments (RCF, Schuldschein, EMTN, CP, asset sales); bond issuance over the last 5 years with date, size and coupon; rating actions over the last 3 years; demonstrated market access in 2020 and 2022."},
        {"key": "management_agenda", "label": "17. Management Agenda - Strategic Decisions - Trade-offs", "peer": True,
         "brief": "150-180 words. The 2-3 strategic questions management must answer over the next 12-24 months from a creditor's perspective (e.g. growth vs deleveraging, refinancing the next major maturity, dividends/buybacks vs debt reduction, M&A vs organic investment, the capex cycle). For each question, name the realistic options, the trade-off each entails, and its concrete credit implication. State the decisions taken so far and the philosophy and risk appetite they reveal (creditor vs shareholder orientation, track record of delivering on guidance). Close by comparing how 1-2 named peers' management teams approach the same questions, and set peer_verdict to whether this management is a stronger, in-line or weaker steward of creditor interests than that peer set."},
    ],
    "fin": [
        {"key": "business_model", "label": "1.  Business Model - Revenue Profile - Segments",
         "brief": "120-150 words. Split of net interest income / fee income / trading in % of total income with year; business segments with income share; geographic diversification; cost-income-ratio trend over 3 years; structural profitability issues; management track record on cost and de-risking programmes."},
        {"key": "asset_quality", "label": "2.  Asset Quality - NPL - Stage 2 - Coverage",
         "brief": "130-150 words. NPL ratio current and 3-year trend; Stage 2 share of the loan book; coverage ratio vs the last cycle peak; cost of risk in bp; forbearance practice and transparency; development across the cycle with concrete numbers."},
        {"key": "loan_book_risks", "label": "3.  Loan Book - Concentrations - High-Risk Portfolios",
         "brief": "130-150 words. Loan book by sector, product and region; largest concentrations named concretely; share of CRE, leveraged finance, non-IG corporates and emerging markets in % of the book; collateral policy with typical LTVs and haircuts; off-balance risks (guarantees, committed lines, derivative counterparty)."},
        {"key": "sovereign_nexus", "label": "4.  Sovereign Nexus - Govvie Exposure - Feedback Loop",
         "brief": "100-130 words. Exposure to the home and peripheral sovereigns (government-bond holdings as % of CET1 and of total assets); the sovereign-bank feedback loop; dependence on the home economy and public-sector counterparties; concentration to government-linked borrowers; how a sovereign downgrade transmits to the bank's own rating and funding."},
        {"key": "stress_credit", "label": "5.  Stress Tests - Credit Risk - Legacy",
         "brief": "120-140 words. Internal and regulatory stress-test results: CET1 depletion in the adverse scenario; sensitivity to recession, unemployment and property-price falls with numbers; legacy issues (legacy NPLs, legal risks) and run-down progress; disclosure transparency."},
        {"key": "liabilities", "label": "6.  Liability Side - Deposit Structure - Capital Stack",
         "brief": "130-150 words. Liability structure: retail/SME deposits vs corporate/institutional vs wholesale in %; deposit stickiness with rationale and deposit beta; share of insured/granular deposits; capital-stack composition: covered bonds, senior preferred, senior non-preferred, T2, AT1 with volumes."},
        {"key": "funding", "label": "7.  Funding - Maturities - Wholesale Dependence",
         "brief": "130-150 words. Maturity structure of senior, covered and central-bank funding with amounts and years; funding cliffs over the next 2-3 years; dependence on central-bank funding in % of liabilities; short-term wholesale funding (CP, interbank); secured vs unsecured issuance spread historically."},
        {"key": "liquidity", "label": "8.  Liquidity - LCR - NSFR - Buffer",
         "brief": "120-140 words. LCR current and trend; NSFR current; quality of the liquidity buffer: HQLA Level 1 vs Level 2 in %; central-bank eligibility of the buffer; internal liquidity limits and compliance in stress."},
        {"key": "capital", "label": "9.  Capital - CET1 - MDA - Distribution Capacity", "kpi": True,
         "brief": "60-80 words. Read of capital buffers and distribution capacity: distance to the MDA trigger, the Pillar 2 requirement (P2R) and guidance (P2G), the countercyclical buffer, and AT1 coupon / distributable-items (ADI) headroom."},
        {"key": "mrel_bailin", "label": "10. MREL - TLAC - Bail-in Capacity - Cascade",
         "brief": "130-150 words. MREL/TLAC ratio current vs requirement with buffer; tiering of bail-in-able liabilities: NPS/T2/AT1 volumes and rank in the liability cascade; preferred resolution strategy (bail-in vs sale vs bridge bank); grandfathering risks from CRR III / BRRD changes."},
        {"key": "banking_book_market", "label": "11. Banking Book - NII Stability - Market Risk",
         "brief": "120-140 words. NII stability: current NII and sensitivity to +/-100bp; EVE sensitivity and duration gap; interest-rate-risk hedging policy; share of volatile income (trading/FV/OCI) of total income; CIR trend and concrete efficiency programmes."},
        {"key": "governance", "label": "12. Governance - Risk Culture - Resolution",
         "brief": "120-140 words. Board composition and independence; risk-culture indicators (audit findings, limit breaches, supervisory measures over 3 years); material special audits or conditions; maturity of the recovery and resolution plan; ESG and reputation risks and their effect on the funding profile."},
        {"key": "esg_funding", "label": "13. ESG - Financed Emissions - Sustainable Funding",
         "brief": "100-130 words. Material ESG factors priced into the bank's spread: financed-emissions and transition exposure of the loan book; green/social/sustainability bond issuance and investor demand; governance controversies and litigation; net effect on funding cost and the breadth of the investor base."},
        {"key": "peer_group", "label": "14. Peer Group - Capital - Asset Quality - Funding", "peer": True,
         "brief": "130-160 words. 3-4 named direct credit peers (same type and region) with rationale; concrete comparison: CET1, NPL, LCR, MREL buffer, NII margin, CIR; explicit verdict on capital, asset quality and funding strength."},
        {"key": "refi_toolkit", "label": "15. Refi Toolkit - Issuance History - Investor Base",
         "brief": "130-160 words. Available instruments (covered bonds, SNP, SP, T2, AT1, Schuldschein, CP, ECP); issuance history over 5 years with date, size, instrument and coupon of key deals; breadth of the investor base; order-book quality; market access in 2020 and 2022; rating actions over 3 years."},
        {"key": "management_agenda", "label": "16. Management Agenda - Strategic Decisions - Trade-offs", "peer": True,
         "brief": "150-180 words. The 2-3 strategic questions the bank's management must answer over the next 12-24 months from a creditor's perspective (e.g. capital distribution vs retention and MDA protection, MREL/AT1 build, cost programme vs revenue investment, de-risking vs growth in higher-yield books, M&A or consolidation). For each question, name the realistic options, the trade-off each entails, and its concrete impact on capital, funding or asset quality. State the decisions taken so far and the philosophy and risk appetite they reveal. Close by comparing how 1-2 named peer banks' management teams approach the same questions, and set peer_verdict to whether this management is a stronger, in-line or weaker steward of creditor interests than that peer set."},
    ],
    "sov": [
        {"key": "economic_profile", "label": "1.  Economic Structure - GDP - Growth Drivers",
         "brief": "120-150 words. Nominal GDP and GDP per capita with year; real growth over 3 years and the IMF forecast; economic structure by sector in % of GDP; main growth drivers and structural weaknesses; unemployment and demographic trend; external competitiveness."},
        {"key": "fiscal_position", "label": "2.  Fiscal Position - Debt Ratio - Deficit - Path", "kpi": True,
         "brief": "50-70 words. Read of the fiscal path and the credibility of the consolidation plan."},
        {"key": "debt_sustainability", "label": "3.  Debt Sustainability - Interest Burden - Funding Needs",
         "brief": "130-150 words. Debt by currency, instrument and maturity with shares; average remaining maturity and share of fixed-rate; effective average coupon vs market yield; interest burden as % of revenue and trend; gross financing need over 3 years with amounts; rollover risk and the largest maturity cliffs."},
        {"key": "external_position", "label": "4.  Current Account - FX Reserves - External Debt",
         "brief": "120-140 words. Current-account balance as % of GDP over 3 years; FX reserves in USD bn and as months of import cover; gross external debt as % of GDP; share of FX-denominated debt; net international investment position; vulnerability to capital outflows."},
        {"key": "monetary_policy", "label": "5.  Monetary Policy - Currency - Inflation",
         "brief": "110-130 words. Currency regime (own currency / union / board); inflation current vs central-bank target; policy rate and direction; central-bank independence; room for manoeuvre; for euro-area members the relevance of ECB facilities (TPI/APP)."},
        {"key": "institutions", "label": "6.  Institutions - Governance - Political Stability",
         "brief": "120-140 words. World Bank governance indicators (Rule of Law, Government Effectiveness, Control of Corruption) with values; political stability and government continuity; the political calendar (upcoming elections, reform momentum); quality of statistical reporting; transparency to the IMF; rule of law and investor protection; geopolitical and alliance risks."},
        {"key": "ssa_structure", "label": "7.  SSA Structure - Guarantee Framework - Mandate",
         "brief": "120-140 words. For sovereigns: embedding in supranational frameworks (EU, ESM, IMF programmes) with conditionality and availability. For SSAs: exact legal basis, guarantor and guarantee structure (explicit/implicit), capital structure with paid-in and callable capital, mandate and policy role, rating link to the guarantor, preferred-creditor status if relevant."},
        {"key": "contingent_liabilities", "label": "8.  Contingent Liabilities - SOEs - Climate Fiscal Risk",
         "brief": "110-140 words. Contingent liabilities that can migrate onto the sovereign balance sheet: state-owned enterprises, banking-sector support, explicit and implicit guarantees, PPPs, pension and demographic obligations with magnitude in % of GDP. Climate and ESG fiscal risk: exposure to physical and transition costs and any quantified fiscal impact."},
        {"key": "liquidity", "label": "9.  Liquidity - IMF Access - Multilateral Lines",
         "brief": "110-130 words. Available liquidity reserves (cash balance, sovereign-fund assets); IMF credit lines and programmes (type, size, terms); access to ESM/EFSM/SURE or comparable mechanisms; central-bank facilities; for SSAs: own liquidity buffers, treasury pools and short-term instruments."},
        {"key": "stress_scenarios", "label": "10. Stress Scenarios - Recession - Rate Shock - Currency",
         "brief": "120-150 words. Scenario 1 recession -2% GDP: impact on debt ratio and deficit. Scenario 2 rate shock +200bp: extra interest burden as % of GDP and financing need. Scenario 3 currency or external shock: reserve cover and external financing gap. State the trigger and a realistic probability per scenario."},
        {"key": "risks", "label": "11. Credit Risks - Red Flags - Vulnerabilities",
         "brief": "110-130 words. The 3-4 largest credit risks with concrete transmission mechanism; the Debt/GDP level at which a restructuring discussion becomes realistic; vulnerability to external-financing withdrawal; political risk and willingness to pay; contagion risk; institutional weaknesses that undermine creditor protection."},
        {"key": "peer_group", "label": "12. Peer Group - Country Comparison", "peer": True,
         "brief": "130-160 words. 3-4 named credit peers (similar rating, region, issuer type) with rationale; concrete comparison: Debt/GDP, primary balance, interest burden, FX reserves, CDS; explicit verdict on fiscal stability, market access and institutional quality."},
        {"key": "credit_curve", "label": "13. Credit Curve - Yield Spread - CDS",
         "brief": "110-140 words. Current yield curve with concrete maturities and yields; CDS curve and 12-month spread path; ASW vs the swap curve; critical maturities and short-vs-long positioning logic; for SSAs the spread vs Bund/OAT and peer SSAs; secondary-market liquidity."},
        {"key": "refi_toolkit", "label": "14. Refi Toolkit - Instruments - Issuance History",
         "brief": "130-160 words. Available instruments (T-bills, notes, bonds, green/social bonds, syndications, private placements, IMF/ESM facilities); issuance history over 3 years with date, size, maturity and coupon of key deals; investor base (central banks, asset managers, retail); order-book quality at recent syndications; market access in 2020 and 2022."},
        {"key": "policy_agenda", "label": "15. Policy Agenda - Fiscal Decisions - Trade-offs", "peer": True,
         "brief": "150-180 words. The 2-3 policy decisions the government and fiscal authorities must take over the next 12-24 months from a creditor's perspective (e.g. fiscal consolidation pace vs growth support, pension or structural reform, debt-issuance strategy and maturity management, energy or subsidy policy, compliance with the EU fiscal framework). For each, name the realistic options, the trade-off each entails, and its concrete impact on the debt path, financing need or market access. State the decisions taken so far and the policy philosophy and reform credibility they reveal. Close by comparing how 1-2 named peer sovereigns approach the same questions, and set peer_verdict to whether this issuer's policymaking protects creditors more strongly, in line, or more weakly than that peer set."},
    ],
}

# Rendered order/labels derive from the spec — single source of truth.
SECTIONS = {mode: [(s["key"], s["label"]) for s in specs]
            for mode, specs in SECTION_SPEC.items()}


# ── Prospectus & Recovery spec ────────────────────────────────────────────────
# A self-contained analysis driven by a bond prospectus / offering memorandum
# and/or an issuer name. Oaktree-style: read the document for what it ALLOWS,
# size every basket in numbers, and price recovery, not optimism.
# Flags per section drive both the schema and the rendered chips/tables:
#   cov      -> covenant-strength chip (creditor_friendly / balanced / issuer_friendly)
#   peer     -> peer_verdict chip
#   recovery -> recovery-band chip (high / moderate / low)
#   table    -> a fixed-column waterfall table; the model supplies rows only.

PROSP_META_SPEC = {
    "issuer":        "Issuing legal entity the notes are issued out of.",
    "parent":        "Ultimate parent / group name if different, else empty.",
    "instrument":    "Full instrument line, e.g. 'EUR 500m 5.75% Senior Secured Notes due 2030'.",
    "ranking":       "Ranking, e.g. Senior Secured 1L / Senior Unsecured / Subordinated.",
    "security":      "Security package one-liner, or 'Unsecured'.",
    "governing_law": "Governing law of the notes (e.g. New York, English, German).",
    "sponsor":       "PE sponsor / dominant owner, or 'Listed / no sponsor'.",
    "rating_sp":     "S&P issue rating or empty.",
    "rating_moodys": "Moody's issue rating or empty.",
    "rating_fitch":  "Fitch issue rating or empty.",
}

# Fixed table headers — the model supplies rows only, columns are owned by code
# so every report carries the SAME columns in the SAME order.
PROSP_TABLE_COLS = {
    "capital_structure_waterfall": ["Instrument / Claim", "Amount (EURm)", "Rank", "Security / Collateral"],
    "recovery_estimate":           ["Instrument / Claim", "Claim (EURm)", "Value Available (EURm)", "Est. Recovery %", "Band"],
}

PROSPECTUS_SECTION_SPEC = [
    {"key": "instrument_terms", "label": "1.  Instrument & Key Economic Terms",
     "brief": "110-140 words. The issuing entity and format (Reg S / 144A); size, coupon (fixed / FRN / PIK toggle), maturity; the call schedule (non-call period, call premiums, equity claw-back, make-whole); use of proceeds (refinancing, dividend recap, M&A); ranking and listing. Flag any feature that weakens the creditor (PIK toggle, short non-call, dividend use of proceeds)."},
    {"key": "ranking_security", "label": "2.  Ranking, Security & Guarantor Coverage", "cov": True,
     "brief": "120-150 words. The security package: which assets are pledged (share pledges vs hard asset security), first vs second lien, the intercreditor agreement and payment/enforcement waterfall. Guarantor coverage as % of group EBITDA and assets; non-guarantor leakage. State concretely how strong the collateral actually is for this instrument."},
    {"key": "cov_restricted_payments", "label": "3.  Restricted Payments & Leakage Capacity", "cov": True,
     "brief": "130-160 words. The Restricted Payments covenant: the builder basket (e.g. 50% of CNI), the starter/general/permitted baskets sized in EUR and in turns of EBITDA; restricted vs unrestricted subsidiary designation; the ability to upstream cash, assets or IP to unrestricted subsidiaries; whether J.Crew / Chewy / Serta-style trapdoor blockers are present or absent; total day-one dividend and value-leakage capacity. State the creditor implication in numbers."},
    {"key": "cov_debt_liens", "label": "4.  Debt Incurrence, Ratio Debt & Liens", "cov": True,
     "brief": "130-160 words. Permitted-debt baskets and the ratio-debt test (leverage / FCCR thresholds at which more debt is allowed); free-and-clear / incremental capacity; grower baskets pegged to EBITDA or assets; the lien covenant and most-favoured-lien / anti-priming protection; the headroom for structurally senior or pari debt that dilutes this instrument. Quantify the maximum additional leverage permitted ahead of or alongside the notes."},
    {"key": "cov_asset_sales_coc", "label": "5.  Asset Sales, Change of Control & Portability", "cov": True,
     "brief": "120-150 words. The asset-sale covenant: the use-of-proceeds waterfall, the reinvestment period and the de minimis thresholds. The change-of-control put at 101 and its real value. Portability conditions (leverage-based portability that switches off the CoC put on an LBO) and anti-layering. State whether a creditor is actually protected in a sale or sponsor change."},
    {"key": "cov_ebitda_definitions", "label": "6.  EBITDA Definition, Add-backs & Capacity Leakage", "cov": True,
     "brief": "120-150 words. The definition of Consolidated EBITDA: uncapped run-rate cost-savings and synergy add-backs, the look-forward period, pro-forma and exceptional adjustments. Show how aggressive add-backs inflate reported EBITDA and therefore every ratio-based basket, covenant test and portability trigger simultaneously. This is the central Oaktree red-flag area — quantify the likely gap between adjusted and clean EBITDA."},
    {"key": "lme_protections", "label": "7.  LME Protections - Trapdoor & Uptiering Blockers", "cov": True,
     "brief": "140-180 words. The defences against liability-management exercises (LME) and creditor-on-creditor violence. Address each item concretely and state explicitly whether it is PRESENT or ABSENT, with the clause and the capacity in numbers where relevant: (1) J.Crew blocker - does the documentation prevent transferring material assets or IP into an unrestricted or non-guarantor subsidiary (the trapdoor)? (2) Serta blocker / pro rata sharing protection - do the sacred rights require all-affected-lender consent so a majority cannot prime the minority in a non-pro-rata up-tiering? (3) Unrestricted-subsidiary basket - the size and conditions of the capacity to designate unrestricted subsidiaries and the value that can leak through it, in EUR and turns of EBITDA. (4) Open-market-purchase exception - is there an open-market-purchase carve-out to the pro rata sharing / ratable-treatment requirement (the Serta loophole)? (5) Pro rata sharing requirement - is an amendment to it a protected sacred right? Conclude with the net LME vulnerability of this instrument and set cov_strength accordingly."},
    {"key": "covenant_rationale", "label": "8.  Why the Package Looks Like This",
     "brief": "130-160 words. The negotiating logic behind the terms: issuer credit quality, the primary-market window (hot vs distressed), investor demand and oversubscription, the sponsor's documented pattern across prior deals, and any reverse-flex or tightening during syndication. Explain WHY the covenants are loose or tight here, not just that they are. Tie the package to who held the pen and why."},
    {"key": "structural_subordination", "label": "9.  Structural & Contractual Subordination",
     "brief": "110-140 words. Where the operating assets and cash sit relative to the issuing entity (opco vs holdco); priority of secured and local operating-company debt; pension and lease claims ranking ahead; drop-down and non-guarantor exposure. State concretely how far this instrument sits from the assets and what ranks ahead of it in a default."},
    {"key": "peer_covenant", "label": "10. Peer Covenant Comparison", "peer": True,
     "brief": "130-160 words. 3-4 comparable recent deals (same sector, rating band and sponsor type) named concretely with date and instrument. Compare RP / leakage capacity, leverage cushion in the ratio-debt test, add-back aggressiveness and CoC portability. Give an explicit verdict on whether this documentation is tighter or looser than the current market standard, and set peer_verdict accordingly."},
    {"key": "capital_structure_waterfall", "label": "11. Capital Structure & Priority Waterfall", "table": True,
     "brief": "60-90 words of narrative on the pro-forma capital structure and where the analysed instrument sits. Then supply the table rows: one row per instrument from the most senior claim to equity, columns Instrument / Claim, Amount (EURm), Rank, Security / Collateral."},
    {"key": "recovery_going_concern", "label": "12. Going-Concern Recovery", "recovery": True,
     "brief": "130-160 words. Build the going-concern recovery: a distressed/normalised EBITDA, the enterprise-value multiple with its basis (peer trading and transaction comps), the resulting EV, then the EV waterfall through claims ranking ahead to the analysed instrument and the estimated recovery %. State the key assumption that drives the outcome and set recovery_band."},
    {"key": "recovery_liquidation", "label": "13. Liquidation / Downside Recovery", "recovery": True,
     "brief": "120-150 words. The asset-based downside: liquidation values by asset class with realistic haircuts, secured and priority claims taken first, residual to the analysed instrument and the downside recovery %. State the gap between the going-concern and liquidation outcomes and what determines which one applies. Set recovery_band for this downside case."},
    {"key": "recovery_estimate", "label": "14. Estimated Recovery by Instrument", "table": True, "recovery": True,
     "brief": "60-90 words of narrative summarising recovery across the capital structure. Then supply the table rows: one row per instrument, columns Instrument / Claim, Claim (EURm), Value Available (EURm), Est. Recovery %, Band. Set recovery_band to the overall expected recovery for the analysed instrument."},
    {"key": "risks_redflags", "label": "15. Document Red Flags & Hidden Risks",
     "brief": "120-150 words. The 3-4 most dangerous structural features for a creditor (uncapped add-backs, unrestricted-subsidiary leakage, leverage-based portability, thin guarantor coverage, J.Crew-style trapdoors, open-market-purchase up-tiering exposure, weak intercreditor terms). For each, state the mechanism and its concrete impact on value leakage or recovery. Be specific about which clause enables it."},
    {"key": "oaktree_verdict", "label": "16. Oaktree Verdict: Covenant Quality & Recovery", "cov": True, "recovery": True,
     "brief": "130-160 words. The integrated verdict: overall covenant quality (creditor_friendly / balanced / issuer_friendly via cov_strength), the expected recovery band (via recovery_band), and the spread / price at which the documented risk is adequately compensated. Close with a clear credit stance — buy at the right level, hold, or avoid — and the single decisive reason. Think like Oaktree: protection and margin of safety over yield."},
]

PROSP_SECTIONS = [(s["key"], s["label"]) for s in PROSPECTUS_SECTION_SPEC]


PLACEHOLDER = {
    "corp": "Enter issuer  (e.g. Volkswagen AG, Deutsche Telekom)",
    "fin":  "Enter issuer  (e.g. Deutsche Bank AG, ING Groep, Commerzbank)",
    "sov":  "Enter issuer  (e.g. Federal Republic of Germany, KfW, EIB, Italy, France)",
}

def clean(text):
    text = re.sub(r'<cite[^>]*>', '', text)
    text = re.sub(r'</cite>', '', text)
    return text.strip()

def render_kpi_table(t):
    if not t:
        return html.Span()
    metrics = t.get("metrics", [])
    years   = t.get("years",   [])
    data    = t.get("data",    [])
    th_sty  = {"background": C["navy"], "color": "white", "fontSize": "10px",
                "fontFamily": VF, "fontWeight": "700", "padding": "6px 10px",
                "textAlign": "right", "letterSpacing": "0.05em"}
    td_sty  = {"fontSize": "12px", "fontFamily": VF, "padding": "5px 10px",
                "textAlign": "right", "color": C["ink"], "borderBottom": "1px solid " + C["border"]}
    tlbl    = {**td_sty, "textAlign": "left", "fontWeight": "600", "color": C["navy"],
               "minWidth": "180px"}
    header  = [html.Th("", style={**th_sty, "textAlign": "left"})] + [html.Th(y, style=th_sty) for y in years]
    rows    = []
    for i, metric in enumerate(metrics):
        vals = data[i] if i < len(data) else []
        cells = [html.Td(metric, style=tlbl)] + [html.Td(vals[j] if j < len(vals) else "—", style=td_sty) for j in range(len(years))]
        bg = C["bg"] if i % 2 else C["surface"]
        rows.append(html.Tr(cells, style={"background": bg}))
    return html.Div(
        html.Table([html.Thead(html.Tr(header)), html.Tbody(rows)],
                   style={"width": "100%", "borderCollapse": "collapse", "marginTop": "14px",
                          "border": "1px solid " + C["border"]}),
        style={"overflowX": "auto", "marginBottom": "10px"}
    )

def render_table(t):
    """Generic waterfall/comparison table: {columns: [...], rows: [[...]]}.
    First column is left-aligned (labels); the rest are right-aligned (numbers)."""
    if not t:
        return html.Span()
    columns = t.get("columns", [])
    rows    = t.get("rows",    [])
    if not columns or not rows:
        return html.Span()
    th_sty = {"background": C["navy"], "color": "white", "fontSize": "10px",
              "fontFamily": VF, "fontWeight": "700", "padding": "6px 10px",
              "letterSpacing": "0.05em"}
    td_sty = {"fontSize": "12px", "fontFamily": VF, "padding": "5px 10px",
              "color": C["ink"], "borderBottom": "1px solid " + C["border"]}
    def align(j):
        return "left" if j == 0 else "right"
    header = [html.Th(c, style={**th_sty, "textAlign": align(j)}) for j, c in enumerate(columns)]
    trs = []
    for i, row in enumerate(rows):
        cells = [html.Td(row[j] if j < len(row) else "—",
                         style={**td_sty, "textAlign": align(j),
                                "fontWeight": "600" if j == 0 else "400",
                                "color": C["navy"] if j == 0 else C["ink"]})
                 for j in range(len(columns))]
        bg = C["bg"] if i % 2 else C["surface"]
        trs.append(html.Tr(cells, style={"background": bg}))
    return html.Div(
        html.Table([html.Thead(html.Tr(header)), html.Tbody(trs)],
                   style={"width": "100%", "borderCollapse": "collapse", "marginTop": "14px",
                          "border": "1px solid " + C["border"]}),
        style={"overflowX": "auto", "marginBottom": "10px"}
    )

def _fixed_kpi_table(raw, mode):
    """Force the fixed metric rows + periods; the model only supplies the values.
    Accepts either the post-processed kpi_table or a raw kpi_data row list."""
    data = None
    kt = raw.get("kpi_table") if isinstance(raw, dict) else None
    if isinstance(kt, dict):
        data = kt.get("data")
    if data is None and isinstance(raw, dict):
        data = raw.get("kpi_data")
    if data is None:
        return None
    return {"metrics": FIXED_KPIS[mode], "years": FIXED_YEARS[mode], "data": data}

# ── UI Helpers ────────────────────────────────────────────────────────────────

def card(children, accent=None):
    return html.Div(children, style={
        "background":   C["surface"],
        "borderRadius": "3px",
        "padding":      "28px 32px",
        "marginBottom": "16px",
        "border":       "1px solid " + C["border"],
        "borderTop":    "3px solid " + (accent or C["navy"]),
        "boxShadow":    "0 2px 12px rgba(2,35,60,0.08), 0 1px 3px rgba(2,35,60,0.04)",
    })

def sec_title(text):
    return html.Div(text, style={
        "color":         C["navy"],
        "fontSize":      "11px",
        "fontWeight":    "700",
        "fontFamily":    VF,
        "textTransform": "uppercase",
        "letterSpacing": "0.18em",
        "paddingBottom": "14px",
        "marginBottom":  "20px",
        "borderBottom":  "2px solid " + C["accent"],
    })

def _chip(text, col):
    return html.Span(text, style={
        "fontSize":      "8px",
        "fontWeight":    "700",
        "color":         col,
        "fontFamily":    VF,
        "textTransform": "uppercase",
        "letterSpacing": "0.08em",
        "border":        "1px solid " + col,
        "borderRadius":  "2px",
        "padding":       "1px 6px",
        "marginLeft":    "8px",
    })

def _flag_box(issues):
    if not issues:
        return html.Span()
    return html.Div([
        html.Div("Audit flags", style={
            "fontSize": "8px", "fontWeight": "700", "color": C["red"],
            "fontFamily": VF, "textTransform": "uppercase",
            "letterSpacing": "0.10em", "marginBottom": "4px"}),
        html.Ul([html.Li(i, style={"fontSize": "11px", "color": C["ink"],
                                    "fontFamily": VF, "lineHeight": "1.6"})
                 for i in issues],
                style={"margin": "0", "paddingLeft": "16px"}),
    ], style={
        "background": "rgba(168,0,0,0.05)", "border": "1px solid " + C["red"],
        "borderRadius": "2px", "padding": "8px 12px", "marginTop": "10px"})


def section_block(label, text, conf="medium", srcs=None, kpi_table=None,
                  trend=None, peer_verdict=None, cov_strength=None,
                  recovery_band=None, table=None,
                  verify_verdict=None, verify_issues=None):
    sym, col = (("***", C["green"]) if conf == "high" else ("**o", C["rose"]))
    chips = []
    if verify_verdict in VERIFY_CHIP:
        vlbl, vcol = VERIFY_CHIP[verify_verdict]
        chips.append(_chip(vlbl, vcol))
    if trend in TREND:
        tlbl, tcol = TREND[trend]
        chips.append(_chip(tlbl, tcol))
    if cov_strength in COV_STRENGTH:
        clbl, ccol = COV_STRENGTH[cov_strength]
        chips.append(_chip(clbl, ccol))
    if recovery_band in RECOVERY:
        rlbl, rcol = RECOVERY[recovery_band]
        chips.append(_chip(rlbl, rcol))
    if peer_verdict in PEER_VERDICT:
        plbl, pcol = PEER_VERDICT[peer_verdict]
        chips.append(_chip(plbl, pcol))
    return html.Div([
        html.Div([
            html.Span(label, style={
                "fontSize":      "10px",
                "fontWeight":    "700",
                "color":         C["navy"],
                "fontFamily":    VF,
                "textTransform": "uppercase",
                "letterSpacing": "0.12em",
            }),
            html.Span("  " + sym, style={"fontSize": "9px", "color": col, "fontFamily": VF}),
            *chips,
        ], style={"marginBottom": "8px"}),
        html.P(text, style={
            "lineHeight": "1.85",
            "fontSize":   "13px",
            "color":      C["ink"],
            "fontFamily": VF,
            "margin":     "0",
            "fontWeight": "400",
        }),
        render_kpi_table(kpi_table),
        render_table(table),
        _flag_box(verify_issues),
        (html.Div("Sources: " + "  -  ".join(srcs), style={
            "fontSize":   "11px",
            "color":      C["muted"],
            "fontFamily": VF,
            "marginTop":  "6px",
            "fontStyle":  "italic",
        }) if srcs else html.Span()),
    ], style={
        "marginBottom":  "26px",
        "paddingBottom": "26px",
        "borderBottom":  "1px solid " + C["border"],
        "paddingLeft":   "14px",
        "borderLeft":    "2px solid " + C["accent"],
    })

# ── Output Builder ────────────────────────────────────────────────────────────

def _verify_banner(result):
    note = result.get("_verify_overall")
    if not note:
        return html.Span()
    return html.Div([
        html.Span("AUDIT", style={
            "fontSize": "8px", "fontWeight": "700", "color": "white",
            "fontFamily": VF, "letterSpacing": "0.10em", "background": C["navy"],
            "padding": "2px 7px", "borderRadius": "2px", "marginRight": "10px"}),
        html.Span(note, style={"fontSize": "12px", "color": C["ink"],
                               "fontFamily": VF, "fontStyle": "italic"}),
    ], style={
        "display": "flex", "alignItems": "center", "padding": "10px 14px",
        "marginBottom": "18px", "background": C["bg"],
        "borderLeft": "3px solid " + C["navy"], "borderRadius": "0 2px 2px 0"})


def _doc_link(s):
    rel = research_db.doc_rel(s.get("local_path"))
    href = ("/docs/" + rel) if rel else (s.get("url") or "")
    label = s.get("title") or s.get("url") or "source"
    tag = {"attachment": "[attached] ", "web": ""}.get(s.get("kind", "web"), "")
    stored = "  ·  archived" if rel else ""
    if not href:
        return html.Li(tag + label, style={"fontSize": "11px", "color": C["muted"],
                                            "fontFamily": VF, "marginBottom": "3px"})
    return html.Li([
        html.A(tag + label, href=href, target="_blank", style={
            "fontSize": "11px", "color": C["navy"], "fontFamily": VF,
            "textDecoration": "none"}),
        html.Span(stored, style={"fontSize": "10px", "color": C["green"], "fontFamily": VF}),
    ], style={"marginBottom": "3px"})


def _sources_card(result):
    sources = result.get("_sources") or []
    if not sources:
        return html.Span()
    return card([
        sec_title("Source Library  ·  " + str(len(sources)) + " documents retrieved"),
        html.Div("These are the documents the analysis actually retrieved and "
                 "archived. Click to open the stored copy.", style={
                     "fontSize": "11px", "color": C["muted"], "fontFamily": VF,
                     "marginBottom": "12px"}),
        html.Ul([_doc_link(s) for s in sources],
                style={"margin": "0", "paddingLeft": "18px"}),
    ])


def build_output(result, mode="corp"):
    if not result:
        return card([html.P("No data - the result is empty. See terminal for details.",
                            style={"color": C["red"], "fontFamily": VF, "fontSize": "13px"})],
                    accent=C["red"])
    if result.get("error"):
        return card([html.P("Error: " + result["error"],
                            style={"color": C["red"], "fontFamily": VF, "fontSize": "13px"})],
                    accent=C["red"])

    company = result.get("company", "")
    ticker  = result.get("ticker", "")
    as_of   = result.get("as_of", "")
    secs    = result.get("sections") or {}

    blocks = []
    for key, lbl in SECTIONS[mode]:
        raw = secs.get(key) or {}
        if isinstance(raw, dict):
            text      = clean(raw.get("text", ""))
            conf      = raw.get("confidence", "medium")
            srcs      = raw.get("sources", [])
            kpi_table = _fixed_kpi_table(raw, mode)
            trend     = raw.get("trend")
            verdict   = raw.get("peer_verdict")
            vverdict  = raw.get("verify_verdict")
            vissues   = raw.get("verify_issues")
        else:
            text = clean(str(raw))
            conf, srcs, kpi_table, trend, verdict = "medium", [], None, None, None
            vverdict, vissues = None, None
        if text:
            blocks.append(section_block(lbl, text, conf, srcs, kpi_table, trend, verdict,
                                        verify_verdict=vverdict, verify_issues=vissues))

    title_text = "Credit Memo  -  " + company.upper()
    if ticker:
        title_text += "  [" + ticker + "]"
    if as_of:
        title_text += "   ·   " + as_of

    if not blocks:
        blocks = [html.P(
            "Analysis loaded, but no sections found. Keys: " + str(list(secs.keys())),
            style={"color": C["red"], "fontFamily": VF, "fontSize": "13px"})]

    return [card([
        sec_title(title_text),
        html.Div([
            html.Button("Download PDF", id="btn-pdf", n_clicks=0, style={
                "padding":       "8px 20px",
                "fontSize":      "11px",
                "fontWeight":    "700",
                "letterSpacing": "0.08em",
                "fontFamily":    VF,
                "cursor":        "pointer",
                "border":        "none",
                "borderRadius":  "3px",
                "background":    C["navy"],
                "color":         "white",
            }),
            html.Span(id="pdf-status", style={
                "fontSize":   "12px",
                "color":      C["muted"],
                "fontFamily": VF,
                "marginLeft": "14px",
            }),
        ], style={
            "display":       "flex",
            "alignItems":    "center",
            "marginBottom":  "20px",
            "paddingBottom": "18px",
            "borderBottom":  "1px solid " + C["border"],
        }),
        _verify_banner(result),
        html.Div(blocks),
    ]), _sources_card(result)]

def _prosp_table(raw, key):
    """Promote the model's row list into the renderer's fixed-column table shape."""
    if not isinstance(raw, dict):
        return None
    rows = raw.get("rows")
    if rows is None or key not in PROSP_TABLE_COLS:
        return None
    return {"columns": PROSP_TABLE_COLS[key], "rows": rows}


def build_prospectus_output(result):
    if not result:
        return card([html.P("No data - the result is empty. See terminal for details.",
                            style={"color": C["red"], "fontFamily": VF, "fontSize": "13px"})],
                    accent=C["red"])
    if result.get("error"):
        return card([html.P("Error: " + result["error"],
                            style={"color": C["red"], "fontFamily": VF, "fontSize": "13px"})],
                    accent=C["red"])

    company = result.get("company", "")
    meta    = result.get("meta") or {}
    instr   = meta.get("instrument", "")
    as_of   = result.get("as_of", "")
    secs    = result.get("sections") or {}

    blocks = []
    for key, lbl in PROSP_SECTIONS:
        raw = secs.get(key) or {}
        if isinstance(raw, dict):
            text     = clean(raw.get("text", ""))
            conf     = raw.get("confidence", "medium")
            srcs     = raw.get("sources", [])
            covs     = raw.get("cov_strength")
            recb     = raw.get("recovery_band")
            verdict  = raw.get("peer_verdict")
            table    = _prosp_table(raw, key)
            vverdict = raw.get("verify_verdict")
            vissues  = raw.get("verify_issues")
        else:
            text = clean(str(raw))
            conf, srcs, covs, recb, verdict, table = "medium", [], None, None, None, None
            vverdict, vissues = None, None
        if text or table:
            blocks.append(section_block(lbl, text, conf, srcs, kpi_table=None,
                                        trend=None, peer_verdict=verdict,
                                        cov_strength=covs, recovery_band=recb, table=table,
                                        verify_verdict=vverdict, verify_issues=vissues))

    title_text = "Prospectus & Recovery  -  " + company.upper()
    if instr:
        title_text += "   ·   " + instr
    if as_of:
        title_text += "   ·   " + as_of

    if not blocks:
        blocks = [html.P(
            "Analysis loaded, but no sections found. Keys: " + str(list(secs.keys())),
            style={"color": C["red"], "fontFamily": VF, "fontSize": "13px"})]

    return [card([
        sec_title(title_text),
        html.Div([
            html.Button("Download PDF", id="btn-prosp-pdf", n_clicks=0, style={
                "padding": "8px 20px", "fontSize": "11px", "fontWeight": "700",
                "letterSpacing": "0.08em", "fontFamily": VF, "cursor": "pointer",
                "border": "none", "borderRadius": "3px",
                "background": C["navy"], "color": "white",
            }),
            html.Span(id="prosp-pdf-status", style={
                "fontSize": "12px", "color": C["muted"],
                "fontFamily": VF, "marginLeft": "14px",
            }),
        ], style={
            "display": "flex", "alignItems": "center", "marginBottom": "20px",
            "paddingBottom": "18px", "borderBottom": "1px solid " + C["border"],
        }),
        _verify_banner(result),
        html.Div(blocks),
    ]), _sources_card(result)]


def build_market_output(result):
    if not result:
        return card([html.P("No data - the result is empty.",
                            style={"color": C["red"], "fontFamily": VF, "fontSize": "13px"})],
                    accent=C["red"])
    if result.get("error"):
        return card([html.P("Error: " + result["error"],
                            style={"color": C["red"], "fontFamily": VF, "fontSize": "13px"})],
                    accent=C["red"])
    seg = result.get("_segment", "")
    reg = result.get("_region", "")
    secs = result.get("sections") or {}
    blocks = []
    for key, lbl in MARKET_SECTIONS:
        raw = secs.get(key) or {}
        if isinstance(raw, dict):
            text, srcs = clean(raw.get("text", "")), raw.get("sources", [])
        else:
            text, srcs = clean(str(raw)), []
        if text:
            blocks.append(section_block(lbl, text, "medium", srcs))
    title = "Market Report  -  " + seg + "  ·  " + reg
    if result.get("as_of"):
        title += "  ·  " + result["as_of"]
    children = [sec_title(title)]
    if result.get("headline"):
        children.append(html.P(result["headline"], style={
            "fontSize": "14px", "fontWeight": "600", "color": C["navy"], "fontFamily": VF,
            "lineHeight": "1.7", "marginBottom": "20px", "paddingBottom": "16px",
            "borderBottom": "1px solid " + C["border"]}))
    children.append(html.Div(blocks))
    return [card(children), _sources_card(result)]


# ── Liquidity & Stress rendering ──────────────────────────────────────────────

def _liq_series_full(k, forecast, history):
    hist = history.get(k) if isinstance(history, dict) else None
    hist = [None if v is None else float(v) for v in (hist or [])][-4:]
    hist = [None] * (4 - len(hist)) + hist
    fc = [None if v is None else round(float(v), 2) for v in forecast.get(k, [])]
    return hist + fc


def _liq_fig(spec, years_chart, t0, forecast, history, labels):
    traces = [{"x": years_chart, "y": _liq_series_full(k, forecast, history),
               "type": "scatter", "mode": "lines+markers", "name": labels.get(k, k),
               "connectgaps": True} for k in spec["keys"]]
    shapes = [{"type": "line", "x0": str(t0), "x1": str(t0), "xref": "x", "yref": "paper",
               "y0": 0, "y1": 1, "line": {"color": C["muted"], "width": 1, "dash": "dot"}}]
    if spec.get("zero"):
        shapes.append({"type": "line", "xref": "paper", "x0": 0, "x1": 1, "yref": "y",
                       "y0": 0, "y1": 0, "line": {"color": C["red"], "width": 1.2, "dash": "dash"}})
    if spec.get("hline") is not None:
        hl = spec["hline"]
        shapes.append({"type": "line", "xref": "paper", "x0": 0, "x1": 1, "yref": "y",
                       "y0": hl, "y1": hl, "line": {"color": C["red"], "width": 1.2, "dash": "dot"}})
    fig = {"data": traces, "layout": {
        "title": {"text": spec["title"], "font": {"size": 12, "family": VF, "color": C["navy"]}},
        "height": 290, "margin": {"l": 52, "r": 18, "t": 38, "b": 30},
        "paper_bgcolor": C["surface"], "plot_bgcolor": C["surface"],
        "colorway": [C["navy"], C["rose"], C["green"], C["muted"]],
        "font": {"family": VF, "size": 10, "color": C["ink"]},
        "yaxis": {"title": spec.get("ytitle", ""), "gridcolor": C["border"], "zeroline": False},
        "xaxis": {"gridcolor": C["border"]},
        "annotations": [{"x": str(t0), "y": 1, "yref": "paper", "yanchor": "bottom",
                         "text": "today", "showarrow": False,
                         "font": {"size": 8, "color": C["muted"]}}],
        "legend": {"orientation": "h", "y": -0.18, "font": {"size": 9}},
        "shapes": shapes}}
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


def _liq_num(v):
    if v is None:
        return "—"
    return f"{v:,.1f}"


def _liq_table(keys, years, series, labels):
    th = {"background": C["navy"], "color": "white", "fontSize": "10px", "fontFamily": VF,
          "fontWeight": "700", "padding": "6px 10px", "textAlign": "right"}
    td = {"fontSize": "11px", "fontFamily": VF, "padding": "5px 10px", "textAlign": "right",
          "color": C["ink"], "borderBottom": "1px solid " + C["border"]}
    header = [html.Th("", style={**th, "textAlign": "left"})] + [html.Th(y, style=th) for y in years]
    rows = []
    for i, k in enumerate(keys):
        vals = series.get(k, [])
        cells = [html.Td(labels.get(k, k), style={**td, "textAlign": "left", "fontWeight": "600",
                                                  "color": C["navy"], "minWidth": "160px"})]
        cells += [html.Td(_liq_num(vals[j]) if j < len(vals) else "—", style=td) for j in range(len(years))]
        rows.append(html.Tr(cells, style={"background": C["bg"] if i % 2 else C["surface"]}))
    return html.Div(html.Table([html.Thead(html.Tr(header)), html.Tbody(rows)],
                    style={"width": "100%", "borderCollapse": "collapse", "marginTop": "14px",
                           "border": "1px solid " + C["border"]}),
                    style={"overflowX": "auto"})


def build_liquidity_results(mode, inputs, assumptions, history=None):
    res = liquidity.project(mode, inputs, assumptions, t0=datetime.now().year, history=history)
    series, labels = res["series"], res["labels"]
    head = res["headline"]
    lbl = {"fontSize": "8px", "fontWeight": "700", "color": C["muted"], "fontFamily": VF,
           "textTransform": "uppercase", "letterSpacing": "0.10em"}
    headline = html.Div([
        html.Div([html.Div("Runway / horizon", style=lbl),
                  html.Div(head["runway"], style={"fontSize": "20px", "fontWeight": "700",
                                                  "color": C["navy"], "fontFamily": VFH})],
                 style={"flex": "1"}),
        html.Div([html.Div("Binding constraint", style=lbl),
                  html.Div(head["constraint"], style={"fontSize": "13px", "fontWeight": "600",
                                                      "color": C["rose"], "fontFamily": VF})],
                 style={"flex": "1.4"}),
    ], style={"display": "flex", "gap": "20px", "padding": "14px 16px", "marginBottom": "14px",
              "background": C["bg"], "borderLeft": "3px solid " + C["navy"], "borderRadius": "0 2px 2px 0"})
    charts = html.Div([_liq_fig(s, res["years_chart"], res["t0"], series, res["history"], labels)
                       for s in res["charts"]],
                      style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(320px, 1fr))",
                             "gap": "12px"})
    return html.Div([headline, charts, _liq_table(res["table"], res["years_table"], series, labels)])


def _liq_input_fields(mode, inputs):
    flbl = {"fontSize": "10px", "fontWeight": "600", "color": C["navy"],
            "fontFamily": VF, "marginBottom": "3px"}
    glbl = {"fontSize": "9px", "fontWeight": "700", "color": C["muted"], "fontFamily": VF,
            "textTransform": "uppercase", "letterSpacing": "0.10em", "margin": "6px 0 8px"}

    def field(f):
        key = f["key"]
        if f.get("list"):
            vals = inputs.get(key) if isinstance(inputs.get(key), list) else []
            inner = html.Div([dcc.Input(type="number", id={"type": "liq-input", "index": f"{key}#{j}"},
                                        value=(vals[j] if j < len(vals) else 0),
                                        style={**INP, "width": "60px", "padding": "5px 6px", "marginRight": "4px"})
                              for j in range(f["list"])], style={"display": "flex", "flexWrap": "wrap"})
        else:
            inner = dcc.Input(type="number", id={"type": "liq-input", "index": key},
                              value=inputs.get(key), style={**INP, "padding": "5px 7px"})
        return html.Div([html.Div(f["label"], style=flbl), inner])

    groups = []
    for g in liquidity.GROUP_ORDER:
        items = [f for f in liquidity.LIQ_INPUTS[mode] if f.get("group") == g]
        if not items:
            continue
        groups.append(html.Div([
            html.Div(g, style=glbl),
            html.Div([field(f) for f in items], style={"display": "grid",
                     "gridTemplateColumns": "repeat(auto-fit, minmax(190px, 1fr))", "gap": "10px"}),
        ], style={"marginBottom": "8px"}))
    return html.Div(groups)


def build_liquidity_panel(data):
    if not data:
        return html.Span()
    if data.get("error"):
        return card([html.P("Error: " + data["error"],
                            style={"color": C["red"], "fontFamily": VF, "fontSize": "13px"})],
                    accent=C["red"])
    mode = data.get("_liqmode", "corp")
    inputs = {f["key"]: data.get(f["key"]) for f in liquidity.LIQ_INPUTS[mode]}
    sliders = []
    for i, a in enumerate(liquidity.LIQ_ASSUMPTIONS[mode]):
        sliders.append(html.Div([
            html.Div(a["label"], style={"fontSize": "10px", "fontWeight": "600",
                                        "color": C["navy"], "fontFamily": VF, "marginBottom": "2px"}),
            dcc.Slider(id={"type": "liq-slider", "index": i}, min=a["min"], max=a["max"],
                       step=a["step"], value=a["default"],
                       marks={a["min"]: str(a["min"]), a["max"]: str(a["max"])},
                       tooltip={"placement": "bottom", "always_visible": True}),
        ], style={"marginBottom": "16px"}))
    results = build_liquidity_results(mode, inputs, liquidity.defaults(mode), history=data.get("history"))
    mode_lbl = {"corp": "Corporate", "fin": "Financial", "sov": "Sovereign / SSA"}[mode]
    title = "Liquidity & Stress  -  " + data.get("company", "").upper() + "   ·   " + mode_lbl
    children = [sec_title(title)]
    children.append(html.Div([
        html.Button("Recompute", id="btn-liq-recompute", n_clicks=0,
                    style={**BTN, "padding": "8px 20px", "background": C["rose"]}),
        html.Button("Download PDF", id="btn-liq-pdf", n_clicks=0,
                    style={**BTN, "padding": "8px 20px", "marginLeft": "10px"}),
        html.Span(id="liq-pdf-status", style={"fontSize": "12px", "color": C["muted"],
                                              "fontFamily": VF, "marginLeft": "14px"}),
    ], style={"marginBottom": "16px"}))
    if data.get("commentary"):
        children.append(html.P(data["commentary"], style={
            "fontSize": "13px", "lineHeight": "1.8", "color": C["ink"], "fontFamily": VF,
            "marginBottom": "16px", "paddingBottom": "14px", "borderBottom": "1px solid " + C["border"]}))
    children.append(html.Details([
        html.Summary("Model inputs (editable)", style={
            "fontSize": "11px", "fontWeight": "700", "color": C["navy"], "fontFamily": VF,
            "cursor": "pointer", "marginBottom": "12px", "textTransform": "uppercase",
            "letterSpacing": "0.08em"}),
        _liq_input_fields(mode, inputs),
        html.Div("Edit any figure, then press Recompute. Inputs are the model's sourced "
                 "estimates - correct them before relying on the output.",
                 style={"fontSize": "10px", "color": C["muted"], "fontFamily": VF,
                        "marginTop": "8px", "fontStyle": "italic"}),
    ], style={"marginBottom": "18px", "padding": "12px 14px", "background": C["bg"],
              "border": "1px solid " + C["border"], "borderRadius": "2px"}))
    children.append(html.Div([
        html.Div([html.Div("Scenario assumptions", style={
            "fontSize": "10px", "fontWeight": "700", "color": C["navy"], "fontFamily": VF,
            "textTransform": "uppercase", "letterSpacing": "0.12em", "marginBottom": "14px"})] + sliders,
            style={"width": "270px", "flexShrink": "0", "marginRight": "26px"}),
        html.Div(id="liq-results", children=results, style={"flex": "1", "minWidth": "0"}),
    ], style={"display": "flex", "alignItems": "flex-start"}))
    return [card(children), _sources_card(data)]


# ── PDF ───────────────────────────────────────────────────────────────────────

def gen_pdf(result, mode="corp"):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    HRFlowable, KeepTogether, Table, TableStyle)
    from reportlab.lib import colors
    import html as _html

    def esc(t):
        return _html.escape(str(t), quote=False)

    NAVY   = colors.HexColor("#02233C")
    INK    = colors.HexColor("#001625")
    ACCENT = colors.HexColor("#B8D1E5")
    BG     = colors.HexColor("#F2F1EF")
    MUTED  = colors.HexColor("#5a6e7f")

    TOP_CHROME = 2.4 * cm    # height of the navy header band
    BOT_CHROME = 1.7 * cm    # height of the navy footer band
    PAD        = 0.85 * cm   # breathing room between chrome and text

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=TOP_CHROME + PAD,      # keeps text below header on every page
        bottomMargin=BOT_CHROME + PAD,   # keeps text above footer on every page
    )

    body_sty  = ParagraphStyle("body",  fontName="Helvetica",          fontSize=9.5,
                               textColor=INK,   leading=15.5, spaceAfter=6,  wordWrap="LTR",
                               allowWidows=1, allowOrphans=1)
    head_sty  = ParagraphStyle("head",  fontName="Helvetica-Bold",     fontSize=9,
                               textColor=NAVY,  leading=13,   spaceBefore=18, spaceAfter=4)
    muted_sty = ParagraphStyle("muted", fontName="Helvetica",          fontSize=7,
                               textColor=MUTED, leading=11)
    src_sty   = ParagraphStyle("src",   fontName="Helvetica-Oblique",  fontSize=7,
                               textColor=MUTED, leading=11,   spaceBefore=3)
    title_sty = ParagraphStyle("title", fontName="Helvetica-Bold",     fontSize=18,
                               textColor=NAVY,  leading=22,   spaceAfter=4)
    company = result.get("company", "")
    ticker  = result.get("ticker", "")
    as_of   = result.get("as_of", "")
    secs    = result.get("sections") or {}

    def draw_chrome(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, 0, A4[0], BOT_CHROME, fill=1, stroke=0)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.white)
        canvas.drawString(2*cm, 0.65*cm,
                          "NORD-IX Asset Management  -  Confidential  -  Internal Use Only")
        canvas.drawRightString(A4[0]-2*cm, 0.65*cm, "Page " + str(doc.page))
        canvas.setFillColor(NAVY)
        canvas.rect(0, A4[1]-TOP_CHROME, A4[0], TOP_CHROME, fill=1, stroke=0)
        if LOGO_PATH.exists():
            canvas.drawImage(str(LOGO_PATH), 2*cm, A4[1]-2.05*cm,
                             width=3.5*cm, height=1.3*cm,
                             preserveAspectRatio=True, mask="auto")
        else:
            canvas.setFont("Helvetica-Bold", 14)
            canvas.setFillColor(colors.white)
            canvas.drawString(2*cm, A4[1]-1.6*cm, "nordIX")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(ACCENT)
        canvas.drawRightString(A4[0]-2*cm, A4[1]-1.55*cm,
                               "CREDIT REPORT  -  INTERNAL  -  CONFIDENTIAL")
        canvas.restoreState()

    # No leading Spacer needed — topMargin already clears the header chrome
    story = [
        Paragraph(
            "<b>" + esc(company.upper()) + "</b>" +
            ("  <font color='#5a6e7f' size='10'>[" + esc(ticker) + "]</font>" if ticker else ""),
            title_sty),
        Paragraph(
            "Credit Memo  –  " + datetime.now().strftime("%d %B %Y") +
            ("  –  " + esc(as_of) if as_of else "") +
            "  –  NORD-IX Asset Management",
            muted_sty),
        HRFlowable(width="100%", thickness=2, color=ACCENT, spaceBefore=10, spaceAfter=10),
    ]
    if result.get("_verify_overall"):
        story.append(Paragraph(
            "<b>Audit:</b> " + esc(result["_verify_overall"]), src_sty))
        story.append(Spacer(1, 0.2 * cm))

    BADGE = {"high": "***", "medium": "**o", "low": "o"}
    TREND_HEX = {"improving": "#1a6e3c", "stable": "#5a6e7f", "deteriorating": "#a80000"}
    VERIFY_HEX = {"supported": "#1a6e3c", "partially_supported": "#AA3F69",
                  "unsupported": "#a80000", "contradicted": "#a80000"}
    for key, lbl in SECTIONS[mode]:
        raw  = secs.get(key) or {}
        text = clean(raw.get("text", "") if isinstance(raw, dict) else str(raw))
        if not text:
            continue
        conf      = raw.get("confidence", "medium") if isinstance(raw, dict) else "medium"
        srcs      = raw.get("sources", [])           if isinstance(raw, dict) else []
        kpi_table = _fixed_kpi_table(raw, mode)      if isinstance(raw, dict) else None
        trend     = raw.get("trend")                 if isinstance(raw, dict) else None
        verdict   = raw.get("peer_verdict")          if isinstance(raw, dict) else None
        vverdict  = raw.get("verify_verdict")        if isinstance(raw, dict) else None
        vissues   = raw.get("verify_issues")         if isinstance(raw, dict) else None
        badge     = BADGE.get(conf, "")
        col_hex   = "#1a6e3c" if conf == "high" else "#AA3F69"

        chip_txt = ""
        if vverdict in VERIFY_CHIP:
            chip_txt += ("  <font size='6' color='" + VERIFY_HEX[vverdict] + "'>[" +
                         esc(VERIFY_CHIP[vverdict][0].upper()) + "]</font>")
        if trend in TREND:
            chip_txt += ("  <font size='6' color='" + TREND_HEX.get(trend, "#5a6e7f") +
                         "'>[" + esc(TREND[trend][0].upper()) + "]</font>")
        if verdict in PEER_VERDICT:
            vhex = {"stronger": "#1a6e3c", "in_line": "#5a6e7f", "weaker": "#a80000"}[verdict]
            chip_txt += ("  <font size='6' color='" + vhex + "'>[" +
                         esc(PEER_VERDICT[verdict][0].upper()) + "]</font>")

        story.append(KeepTogether([
            Paragraph(
                esc(lbl.upper()) +
                "  <font size='6' color='" + col_hex + "'>" + badge + "</font>" + chip_txt,
                head_sty),
            HRFlowable(width="100%", thickness=1.5, color=ACCENT, spaceAfter=5),
        ]))
        story.append(Paragraph(esc(text), body_sty))
        if vissues:
            story.append(Paragraph(
                "<b>Audit flags:</b> " + esc("  ·  ".join(vissues)),
                ParagraphStyle("flag", fontName="Helvetica-Oblique", fontSize=7,
                               textColor=colors.HexColor("#a80000"), leading=10,
                               spaceBefore=2, spaceAfter=2)))
        if kpi_table:
            metrics = kpi_table.get("metrics", [])
            years   = kpi_table.get("years",   [])
            data    = kpi_table.get("data",    [])
            tbl_sty = ParagraphStyle("tbl", fontName="Helvetica", fontSize=8, textColor=INK, leading=11)
            hdr_sty = ParagraphStyle("tblh", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white, leading=11)
            header_row = [Paragraph("", hdr_sty)] + [Paragraph(esc(y), hdr_sty) for y in years]
            rows_pdf = [header_row]
            for i, metric in enumerate(metrics):
                vals = data[i] if i < len(data) else []
                row = [Paragraph(esc(metric), tbl_sty)] + [Paragraph(esc(str(vals[j]) if j < len(vals) else "—"), tbl_sty) for j in range(len(years))]
                rows_pdf.append(row)
            col_w = [doc.width * 0.32] + [doc.width * 0.68 / max(len(years), 1)] * len(years)
            pdf_tbl = Table(rows_pdf, colWidths=col_w)
            pdf_tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, 0),  NAVY),
                ("BACKGROUND",    (0, 1), (-1, -1), BG),
                ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, BG]),
                ("TOPPADDING",    (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING",   (0, 0), (-1, -1), 6),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
                ("ALIGN",         (1, 0), (-1, -1), "RIGHT"),
                ("GRID",          (0, 0), (-1, -1), 0.3, ACCENT),
            ]))
            story.append(Spacer(1, 0.2*cm))
            story.append(pdf_tbl)
            story.append(Spacer(1, 0.2*cm))
        if srcs:
            story.append(Paragraph("Sources: " + esc("  –  ".join(srcs)), src_sty))

    story += [
        Spacer(1, 0.8*cm),
        HRFlowable(width="100%", thickness=0.5, color=ACCENT, spaceAfter=6),
        Paragraph(
            "Produced with AI-assisted analysis. This is not investment advice. "
            "NORD-IX Asset Management GmbH.",
            muted_sty),
    ]
    doc.build(story, onFirstPage=draw_chrome, onLaterPages=draw_chrome)
    return buf.getvalue()


def gen_prospectus_pdf(result):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    HRFlowable, KeepTogether, Table, TableStyle)
    from reportlab.lib import colors
    import html as _html

    def esc(t):
        return _html.escape(str(t), quote=False)

    NAVY   = colors.HexColor("#02233C")
    INK    = colors.HexColor("#001625")
    ACCENT = colors.HexColor("#B8D1E5")
    BG     = colors.HexColor("#F2F1EF")
    MUTED  = colors.HexColor("#5a6e7f")

    TOP_CHROME = 2.4 * cm
    BOT_CHROME = 1.7 * cm
    PAD        = 0.85 * cm

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=TOP_CHROME + PAD, bottomMargin=BOT_CHROME + PAD)

    body_sty  = ParagraphStyle("body",  fontName="Helvetica",         fontSize=9.5,
                               textColor=INK,   leading=15.5, spaceAfter=6, wordWrap="LTR",
                               allowWidows=1, allowOrphans=1)
    head_sty  = ParagraphStyle("head",  fontName="Helvetica-Bold",    fontSize=9,
                               textColor=NAVY,  leading=13, spaceBefore=18, spaceAfter=4)
    muted_sty = ParagraphStyle("muted", fontName="Helvetica",         fontSize=7,
                               textColor=MUTED, leading=11)
    src_sty   = ParagraphStyle("src",   fontName="Helvetica-Oblique", fontSize=7,
                               textColor=MUTED, leading=11, spaceBefore=3)
    title_sty = ParagraphStyle("title", fontName="Helvetica-Bold",    fontSize=18,
                               textColor=NAVY,  leading=22, spaceAfter=4)

    company = result.get("company", "")
    meta    = result.get("meta") or {}
    instr   = meta.get("instrument", "")
    as_of   = result.get("as_of", "")
    secs    = result.get("sections") or {}

    def draw_chrome(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, 0, A4[0], BOT_CHROME, fill=1, stroke=0)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.white)
        canvas.drawString(2*cm, 0.65*cm,
                          "NORD-IX Asset Management  -  Confidential  -  Internal Use Only")
        canvas.drawRightString(A4[0]-2*cm, 0.65*cm, "Page " + str(doc.page))
        canvas.setFillColor(NAVY)
        canvas.rect(0, A4[1]-TOP_CHROME, A4[0], TOP_CHROME, fill=1, stroke=0)
        if LOGO_PATH.exists():
            canvas.drawImage(str(LOGO_PATH), 2*cm, A4[1]-2.05*cm,
                             width=3.5*cm, height=1.3*cm,
                             preserveAspectRatio=True, mask="auto")
        else:
            canvas.setFont("Helvetica-Bold", 14)
            canvas.setFillColor(colors.white)
            canvas.drawString(2*cm, A4[1]-1.6*cm, "nordIX")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(ACCENT)
        canvas.drawRightString(A4[0]-2*cm, A4[1]-1.55*cm,
                               "PROSPECTUS & RECOVERY  -  INTERNAL  -  CONFIDENTIAL")
        canvas.restoreState()

    story = [
        Paragraph("<b>" + esc(company.upper()) + "</b>", title_sty),
        Paragraph(
            "Prospectus & Recovery Analysis  –  " + datetime.now().strftime("%d %B %Y") +
            ("  –  " + esc(instr) if instr else "") +
            ("  –  " + esc(as_of) if as_of else "") +
            "  –  NORD-IX Asset Management",
            muted_sty),
        HRFlowable(width="100%", thickness=2, color=ACCENT, spaceBefore=10, spaceAfter=10),
    ]
    if result.get("_verify_overall"):
        story.append(Paragraph(
            "<b>Audit:</b> " + esc(result["_verify_overall"]), src_sty))
        story.append(Spacer(1, 0.2 * cm))

    BADGE   = {"high": "***", "medium": "**o", "low": "o"}
    COV_HEX = {"creditor_friendly": "#1a6e3c", "balanced": "#5a6e7f", "issuer_friendly": "#a80000"}
    REC_HEX = {"high": "#1a6e3c", "moderate": "#5a6e7f", "low": "#a80000"}
    PEER_HEX = {"stronger": "#1a6e3c", "in_line": "#5a6e7f", "weaker": "#a80000"}
    VERIFY_HEX = {"supported": "#1a6e3c", "partially_supported": "#AA3F69",
                  "unsupported": "#a80000", "contradicted": "#a80000"}

    for key, lbl in PROSP_SECTIONS:
        raw  = secs.get(key) or {}
        text = clean(raw.get("text", "") if isinstance(raw, dict) else str(raw))
        table = _prosp_table(raw, key)
        if not text and not table:
            continue
        conf    = raw.get("confidence", "medium") if isinstance(raw, dict) else "medium"
        srcs    = raw.get("sources", [])          if isinstance(raw, dict) else []
        covs    = raw.get("cov_strength")         if isinstance(raw, dict) else None
        recb    = raw.get("recovery_band")        if isinstance(raw, dict) else None
        verdict = raw.get("peer_verdict")         if isinstance(raw, dict) else None
        vverdict = raw.get("verify_verdict")      if isinstance(raw, dict) else None
        vissues  = raw.get("verify_issues")       if isinstance(raw, dict) else None
        badge   = BADGE.get(conf, "")
        col_hex = "#1a6e3c" if conf == "high" else "#AA3F69"

        chip_txt = ""
        if vverdict in VERIFY_CHIP:
            chip_txt += ("  <font size='6' color='" + VERIFY_HEX[vverdict] + "'>[" +
                         esc(VERIFY_CHIP[vverdict][0].upper()) + "]</font>")
        if covs in COV_STRENGTH:
            chip_txt += ("  <font size='6' color='" + COV_HEX[covs] + "'>[" +
                         esc(COV_STRENGTH[covs][0].upper()) + "]</font>")
        if recb in RECOVERY:
            chip_txt += ("  <font size='6' color='" + REC_HEX[recb] + "'>[" +
                         esc(RECOVERY[recb][0].upper()) + "]</font>")
        if verdict in PEER_VERDICT:
            chip_txt += ("  <font size='6' color='" + PEER_HEX[verdict] + "'>[" +
                         esc(PEER_VERDICT[verdict][0].upper()) + "]</font>")

        story.append(KeepTogether([
            Paragraph(
                esc(lbl.upper()) +
                "  <font size='6' color='" + col_hex + "'>" + badge + "</font>" + chip_txt,
                head_sty),
            HRFlowable(width="100%", thickness=1.5, color=ACCENT, spaceAfter=5),
        ]))
        if text:
            story.append(Paragraph(esc(text), body_sty))
        if vissues:
            story.append(Paragraph(
                "<b>Audit flags:</b> " + esc("  ·  ".join(vissues)),
                ParagraphStyle("flag", fontName="Helvetica-Oblique", fontSize=7,
                               textColor=colors.HexColor("#a80000"), leading=10,
                               spaceBefore=2, spaceAfter=2)))
        if table:
            columns = table.get("columns", [])
            rows    = table.get("rows", [])
            tbl_sty = ParagraphStyle("tbl", fontName="Helvetica", fontSize=8, textColor=INK, leading=11)
            hdr_sty = ParagraphStyle("tblh", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white, leading=11)
            header_row = [Paragraph(esc(c), hdr_sty) for c in columns]
            rows_pdf = [header_row]
            for row in rows:
                rows_pdf.append([Paragraph(esc(str(row[j]) if j < len(row) else "—"), tbl_sty)
                                 for j in range(len(columns))])
            ncol = max(len(columns), 1)
            col_w = [doc.width * 0.34] + [doc.width * 0.66 / max(ncol - 1, 1)] * (ncol - 1) if ncol > 1 else [doc.width]
            pdf_tbl = Table(rows_pdf, colWidths=col_w)
            pdf_tbl.setStyle(TableStyle([
                ("BACKGROUND",     (0, 0), (-1, 0),  NAVY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG]),
                ("TOPPADDING",     (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
                ("LEFTPADDING",    (0, 0), (-1, -1), 6),
                ("RIGHTPADDING",   (0, 0), (-1, -1), 6),
                ("ALIGN",          (1, 0), (-1, -1), "RIGHT"),
                ("GRID",           (0, 0), (-1, -1), 0.3, ACCENT),
            ]))
            story.append(Spacer(1, 0.2*cm))
            story.append(pdf_tbl)
            story.append(Spacer(1, 0.2*cm))
        if srcs:
            story.append(Paragraph("Sources: " + esc("  –  ".join(srcs)), src_sty))

    story += [
        Spacer(1, 0.8*cm),
        HRFlowable(width="100%", thickness=0.5, color=ACCENT, spaceAfter=6),
        Paragraph(
            "Produced with AI-assisted analysis. This is not investment advice. "
            "NORD-IX Asset Management GmbH.",
            muted_sty),
    ]
    doc.build(story, onFirstPage=draw_chrome, onLaterPages=draw_chrome)
    return buf.getvalue()


def gen_liquidity_pdf(mode, company, commentary, res, assumptions):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    import html as _html

    def esc(t):
        return _html.escape(str(t), quote=False)

    NAVY = colors.HexColor("#02233C"); INK = colors.HexColor("#001625")
    ACCENT = colors.HexColor("#B8D1E5"); MUTED = colors.HexColor("#5a6e7f")
    ROSE = colors.HexColor("#AA3F69"); GREEN = colors.HexColor("#1a6e3c")
    years, series, labels = res["years_table"], res["series"], res["labels"]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=1.8*cm, bottomMargin=1.6*cm)
    title_sty = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=17, textColor=NAVY, leading=21, spaceAfter=4)
    muted_sty = ParagraphStyle("m", fontName="Helvetica", fontSize=8, textColor=MUTED, leading=11)
    body_sty  = ParagraphStyle("b", fontName="Helvetica", fontSize=9.5, textColor=INK, leading=15, spaceAfter=6)
    head_sty  = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=10, textColor=NAVY, leading=13, spaceBefore=12, spaceAfter=5)

    def chart(spec):
        d = Drawing(460, 175)
        lc = HorizontalLineChart()
        lc.x, lc.y, lc.width, lc.height = 46, 28, 380, 130
        lc.data = [[(0 if v is None else round(v, 2)) for v in series.get(k, [])] for k in spec["keys"]]
        lc.categoryAxis.categoryNames = years
        cols = [NAVY, ROSE, GREEN, MUTED]
        for i in range(len(lc.data)):
            lc.lines[i].strokeColor = cols[i % len(cols)]
            lc.lines[i].strokeWidth = 1.6
        lc.lineLabelFormat = None
        d.add(lc)
        return d

    mode_lbl = {"corp": "Corporate", "fin": "Financial", "sov": "Sovereign / SSA"}[mode]
    a_txt = "  ·  ".join(f"{k}={v}" for k, v in (assumptions or {}).items())
    head = res["headline"]
    story = [
        Paragraph(esc(company.upper()) + "  <font size='10' color='#5a6e7f'>[" + esc(mode_lbl) + "]</font>", title_sty),
        Paragraph("Liquidity & Stress Model  -  " + datetime.now().strftime("%d %B %Y") + "  -  NORD-IX Asset Management", muted_sty),
        HRFlowable(width="100%", thickness=2, color=ACCENT, spaceBefore=8, spaceAfter=10),
        Paragraph("<b>Runway / horizon:</b> " + esc(head["runway"]), body_sty),
        Paragraph("<b>Binding constraint:</b> <font color='#AA3F69'>" + esc(head["constraint"]) + "</font>", body_sty),
        Paragraph("<b>Scenario:</b> " + esc(a_txt or "base case"), muted_sty),
    ]
    if commentary:
        story += [Paragraph("Analyst commentary", head_sty), Paragraph(esc(commentary), body_sty)]
    for spec in (res["charts"][0], res["charts"][2]):
        story.append(Paragraph(esc(spec["title"]), head_sty))
        story.append(chart(spec))
        story.append(Paragraph(esc("Lines: " + "  ·  ".join(labels.get(k, k) for k in spec["keys"])), muted_sty))

    story.append(Paragraph("Projection", head_sty))
    hdr = ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white, leading=11)
    cel = ParagraphStyle("td", fontName="Helvetica", fontSize=8, textColor=INK, leading=11)
    rows = [[Paragraph("", hdr)] + [Paragraph(esc(y), hdr) for y in years]]
    for k in res["table"]:
        vals = series.get(k, [])
        rows.append([Paragraph(esc(labels.get(k, k)), cel)] +
                    [Paragraph(esc(_liq_num(vals[j]) if j < len(vals) else "—"), cel) for j in range(len(years))])
    col_w = [doc.width * 0.30] + [doc.width * 0.70 / len(years)] * len(years)
    tbl = Table(rows, colWidths=col_w)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F1EF")]),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -1), 0.3, ACCENT)]))
    story.append(tbl)
    story += [Spacer(1, 0.6*cm),
              Paragraph("Deterministic projection from sourced inputs. Not investment advice. "
                        "NORD-IX Asset Management GmbH.", muted_sty)]
    doc.build(story)
    return buf.getvalue()

# ── Portfolio Loader ──────────────────────────────────────────────────────────
# The system reads the portfolio Excel live and caches it by file modification
# time. Each portfolio request always uses the latest saved version.

_PF = {"mtime": None, "context": None, "headline": None}

def _num(series, n):
    if series is None:
        return pd.Series([0.0] * n)
    return pd.to_numeric(series, errors="coerce").fillna(0.0)

def load_portfolio(force=False):
    """Read the portfolio Excel and return (context_text, headline_text)."""
    try:
        mt = PORTFOLIO_PATH.stat().st_mtime
    except OSError:
        return None, "Portfolio file not found at " + str(PORTFOLIO_PATH)

    if not force and _PF["mtime"] == mt and _PF["context"]:
        return _PF["context"], _PF["headline"]

    try:
        df = pd.read_excel(PORTFOLIO_PATH, sheet_name=0)
    except Exception as ex:
        return None, "Portfolio read error: " + str(ex)

    # Normalise headers: strip spaces and drop non-ASCII (fixes e.g. "moody?s").
    df.columns = [re.sub(r"[^\x00-\x7f]", "", str(c)).strip() for c in df.columns]
    n = len(df)

    mv      = _num(df.get("market value"), n)
    nominal = _num(df.get("nominal"), n)
    dur     = _num(df.get("duration"), n)
    dv01    = _num(df.get("dv01"), n)
    dts     = _num(df.get("duration times spread"), n)
    isp     = _num(df.get("i spread"), n)
    oas     = _num(df.get("oas"), n)

    total_mv = float(mv.sum())
    w_dur = float((dur * mv).sum() / total_mv) if total_mv else 0.0
    w_isp = float((isp * mv).sum() / total_mv) if total_mv else 0.0
    w_oas = float((oas * mv).sum() / total_mv) if total_mv else 0.0

    def breakdown(key):
        if key not in df.columns or not total_mv:
            return ""
        tmp = pd.DataFrame({"k": df[key].astype(str).str.strip(), "mv": mv})
        agg = tmp.groupby("k")["mv"].sum().sort_values(ascending=False)
        return "\n".join(
            f"  {k}: EUR {v/1e6:,.1f}mn ({v/total_mv*100:,.1f}%)"
            for k, v in agg.items() if v > 0 and k not in ("", "nan")
        )

    def top_issuers():
        key = "ultimate parent" if "ultimate parent" in df.columns else None
        if not key or not total_mv:
            return ""
        tmp = pd.DataFrame({"k": df[key].astype(str).str.strip(), "mv": mv})
        agg = tmp.groupby("k")["mv"].sum().sort_values(ascending=False).head(10)
        return "\n".join(
            f"  {k}: EUR {v/1e6:,.1f}mn ({v/total_mv*100:,.1f}%)"
            for k, v in agg.items() if v > 0
        )

    saved = datetime.fromtimestamp(mt).strftime("%d %B %Y %H:%M")

    context = f"""PORTFOLIO SNAPSHOT  (source: {PORTFOLIO_PATH.name}, last saved {saved})

Positions: {n}
Total market value: EUR {total_mv/1e6:,.1f}mn
Total nominal: EUR {float(nominal.sum())/1e6:,.1f}mn
Market-value-weighted duration: {w_dur:,.2f} yrs
Total DV01: {float(dv01.sum()):,.0f}
Total duration-times-spread (DTS): {float(dts.sum()):,.2f}
Market-value-weighted i-spread: {w_isp:,.0f} bp
Market-value-weighted OAS: {w_oas:,.0f} bp

BY RATING (market value):
{breakdown('rating') or '  n/a'}

BY SECTOR (market value):
{breakdown('sector') or '  n/a'}

BY MATURITY GROUP (market value):
{breakdown('maturity group') or '  n/a'}

BY CURRENCY (market value):
{breakdown('currency') or '  n/a'}

BY SENIORITY / RANK (market value):
{breakdown('rank') or '  n/a'}

TOP 10 ISSUERS (market value):
{top_issuers() or '  n/a'}

FULL POSITION TABLE (CSV, one row per position):
{_position_csv(df)}
"""

    headline = (f"Portfolio loaded: {n} positions  -  EUR {total_mv/1e6:,.1f}mn market value  -  "
                f"duration {w_dur:,.2f}yrs  -  i-spread {w_isp:,.0f}bp  (saved {saved})")

    _PF.update(mtime=mt, context=context, headline=headline)
    return context, headline

def _position_csv(df):
    wanted = ["ultimate parent", "issuer", "isin", "instrument", "rank", "segment",
              "sector", "industry", "subsector", "rating", "moodys", "s&p",
              "outlook", "currency", "market value", "nominal", "duration", "dv01",
              "i spread", "oas", "maturity", "maturity group", "coupon",
              "debt to ebitda", "fixed charge cov ratio", "domicile"]
    cols = [c for c in wanted if c in df.columns]
    if not cols:
        cols = list(df.columns)
    try:
        return df[cols].to_csv(index=False)
    except Exception:
        return df.to_csv(index=False)

# ── API Call: Single-Issuer Analysis ──────────────────────────────────────────

INTRO = {
    "corp": """You are a Senior Credit Analyst (Oaktree level). You analyze **{company}** as a bond issuer from a creditor's perspective. Language: English.

RESEARCH PROTOCOL — you complete this before the analysis:
1. You review at least two annual or quarterly reports (prefer the last fiscal year + prior year, or the latest quarter): IR website, SEC/EDGAR, Bundesanzeiger
2. You read at least two external research sources: rating agency reports (S&P, Moody's, Fitch), sell-side research, Bloomberg Intelligence, industry analyses
3. You start the analysis only then — you target a data base of at least 4 sources

Further sources: press releases, covenant documentation, capital markets presentation, industry indices.""",
    "fin": """You are a Senior Credit Analyst for Financial Institutions (Oaktree/BlackRock level). You analyze **{company}** as a bond issuer from a creditor's perspective. Language: English.

RESEARCH PROTOCOL — you complete this before the analysis:
1. You review at least two annual or quarterly reports (prefer the last fiscal year + prior year, or the latest quarter): IR website, annual accounts, Pillar 3 report
2. You read at least two external research sources: rating agency reports (S&P, Moody's, Fitch), EBA transparency exercise, sell-side research, Bloomberg Intelligence
3. You start the analysis only then — you target a data base of at least 4 sources

Further sources: SREP results (where public), investor presentation, covered bond programmes, regulatory disclosures.""",
    "sov": """You are a Senior Sovereign Credit Analyst (IMF/BlackRock level). You analyze **{company}** as a bond issuer (sovereign or SSA) from a creditor's perspective. Language: English.

RESEARCH PROTOCOL — you complete this before the analysis:
1. You review at least two official sources: IMF Article IV consultation, OECD Economic Outlook, World Bank data, national budget, stability programme
2. You read at least two external research sources: rating agency reports (S&P, Moody's, Fitch), sell-side research, Bloomberg Intelligence, ESM/EFSF reports
3. For SSAs additionally: issuance prospectus, capital structure, mandate description, guarantee framework
4. You target a data base of at least 4 sources""",
}

STANDARDS = """Data policy: Every number you state must come from a source you actually retrieve in this session, or from the VERIFIED REFERENCE DATA provided to you. When a figure is disclosed in such a source, you use it and you name that dated source. When a figure is NOT available, you write [Not public] — you never substitute an invented or estimated number for a fact, and you never present an unverified figure as if it were disclosed. You may add clearly-labelled qualitative context from general sector knowledge, but not invented numbers. You complete every section; where the data is missing you say so explicitly rather than guessing. An honest [Not public] is always preferred over a plausible-sounding number.

Writing standards: Subject-verb-object. Present tense. Active voice. You always place every number in context, with a unit and a year. No jargon without explanation. Each narrative section follows the same shape: you lead with the fact, then the number with its year, then the trend, then the credit implication. This keeps ten reports for ten issuers directly comparable.
FORBIDDEN words: "elevated risk" / "challenging environment" / "potentially" / "possibly" / "it remains to be seen".

You complete the research, then you call the tool `submit_credit_analysis` exactly once with the full structured result. You set `confidence` per section (high only when grounded in disclosed figures, otherwise medium, low when largely inferred), `trend` as the two-to-three-year direction of travel of that dimension, and `sources` to the concrete dated sources you actually used. You write nothing outside the tool call."""


def _section_schema(spec, mode):
    props = {
        "text":       {"type": "string", "description": spec["brief"]},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "trend":      {"type": "string",
                       "enum": ["improving", "stable", "deteriorating", "not_applicable"],
                       "description": "Direction of travel of this credit dimension over the last 2-3 years."},
        "sources":    {"type": "array", "items": {"type": "string"},
                       "description": "2-4 concrete dated sources actually used."},
    }
    required = ["text", "confidence", "trend", "sources"]
    if spec.get("peer"):
        props["peer_verdict"] = {"type": "string", "enum": ["stronger", "in_line", "weaker"],
                                 "description": "Overall standing of this issuer versus the named peer set."}
        required.append("peer_verdict")
    if spec.get("kpi"):
        props["kpi_data"] = {
            "type": "array",
            "description": ("One row per fixed metric, in this exact order: "
                            + "; ".join(FIXED_KPIS[mode]) + ". Each row is a list of "
                            + str(len(FIXED_YEARS[mode])) + " string values for the fixed periods "
                            + ", ".join(FIXED_YEARS[mode])
                            + ". Use 'n/a' only when a value is genuinely unavailable."),
            "items": {"type": "array", "items": {"type": "string"}},
        }
        required.append("kpi_data")
    return {"type": "object", "properties": props, "required": required}


def build_schema(mode):
    """Build the submit_credit_analysis input schema from SECTION_SPEC + META_SPEC."""
    sec_props  = {s["key"]: _section_schema(s, mode) for s in SECTION_SPEC[mode]}
    meta_props = {k: {"type": "string", "description": v} for k, v in META_SPEC[mode].items()}
    return {
        "type": "object",
        "properties": {
            "company":  {"type": "string", "description": "Official legal name."},
            "ticker":   {"type": "string", "description": "Bloomberg/Yahoo ticker or empty string."},
            "as_of":    {"type": "string", "description": "Reporting period and data date, e.g. 'FY24 results, data as of May 2025'."},
            "meta":     {"type": "object", "properties": meta_props,  "required": list(meta_props)},
            "sections": {"type": "object", "properties": sec_props,   "required": list(sec_props)},
        },
        "required": ["company", "ticker", "as_of", "meta", "sections"],
    }


def _postprocess(data, mode):
    """Promote each kpi_data row list into the renderer's fixed kpi_table shape."""
    secs = data.get("sections") or {}
    for spec in SECTION_SPEC[mode]:
        if spec.get("kpi"):
            s = secs.get(spec["key"])
            if isinstance(s, dict) and s.get("kpi_data") is not None:
                s["kpi_table"] = {"metrics": FIXED_KPIS[mode],
                                  "years":   FIXED_YEARS[mode],
                                  "data":    s.get("kpi_data")}
    return data


def _parse_text_json(raw):
    """Fallback parser when the model returns JSON as text instead of a tool call."""
    s, e = raw.find("{"), raw.rfind("}")
    if s == -1 or e == -1:
        raise ValueError("No JSON - raw preview: " + repr(raw[:300]))
    json_str = raw[s:e + 1]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        if _repair_json:
            return json.loads(_repair_json(json_str))
        raise


def _noop(_):
    pass


def _grounding_pipeline(client, model, kind, mode, issuer, data, msg,
                        base_messages, submit_id, attachments=None, progress=_noop):
    sources = []
    if USE_ARCHIVE:
        try:
            sources = research_db.extract_search_results(msg)
        except Exception as ex:
            print(f"[DEBUG] source capture failed: {ex}")

    if USE_VERIFY and submit_id:
        try:
            progress("Auditing & verifying")
            verdicts = verify.run_verification(
                client, model, base_messages, msg.content,
                submit_id, VERIFY_SEARCH_TOOL)
            if verdicts:
                verify.apply_verification(data, verdicts)
                extra = research_db.extract_search_results(verdicts.get("extra_msg"))
                seen = {s["url"] for s in sources}
                sources += [s for s in extra if s.get("url") and s["url"] not in seen]
                print(f"[DEBUG] verification applied: {len(verdicts.get('by_key', {}))} sections audited")
        except Exception as ex:
            print(f"[DEBUG] verification failed: {ex}")

    if USE_ARCHIVE:
        try:
            progress("Archiving sources")
            run_id = research_db.new_run_id(issuer)
            stored = research_db.store_run(
                run_id, kind, mode, issuer, data.get("as_of", ""), sources,
                attachments=attachments, verify_note=data.get("_verify_overall", ""))
            data["_sources"] = stored
            data["_run_id"] = run_id
            print(f"[DEBUG] archived {len(stored)} sources under run {run_id}")
        except Exception as ex:
            print(f"[DEBUG] archive failed: {ex}")
    return data


def run_analysis(company, mode, progress=_noop):
    progress("Loading reference data")
    prompt = INTRO[mode].format(company=company) + "\n\n" + STANDARDS + "\n\n" + _knowledge(mode)
    if USE_FEEDS:
        try:
            ref_text, _ = datafeeds.reference_data(mode, company)
            if ref_text:
                prompt += "\n\n" + ref_text
                print(f"[DEBUG] injected reference data ({len(ref_text)} chars)")
        except Exception as ex:
            print(f"[DEBUG] reference data failed: {ex}")

    tools = [
        WEB_SEARCH_TOOL,
        {"name": "submit_credit_analysis",
         "description": "Submit the completed structured credit analysis. Call this exactly once, after the research is done.",
         "input_schema": build_schema(mode)},
    ]
    base_messages = [{"role": "user", "content": prompt}]

    client = anthropic.Anthropic(api_key=API_KEY, timeout=600)
    for attempt in range(4):
        try:
            progress("Researching & analysing" + (f" (retry {attempt})" if attempt else ""))
            msg = client.messages.create(
                model=MODEL_ANALYSIS, max_tokens=18000,
                thinking={"type": "adaptive"},
                tools=tools,
                messages=base_messages)
            print(f"[DEBUG] stop_reason={msg.stop_reason}, blocks={[type(b).__name__ for b in msg.content]}")

            data, submit_id = None, None
            for b in msg.content:
                if getattr(b, "type", None) == "tool_use" and getattr(b, "name", "") == "submit_credit_analysis":
                    data = b.input
                    submit_id = getattr(b, "id", None)
                    break
            if data is None:
                raw = "".join(b.text for b in msg.content if hasattr(b, "text") and b.text).strip()
                print(f"[DEBUG] no tool_use; falling back to text JSON, len={len(raw)}")
                if not raw:
                    raise ValueError("Empty response - stop_reason=" + str(msg.stop_reason))
                data = _parse_text_json(raw)

            if not data:
                raise ValueError("Tool returned empty input")
            if "error" in data and "sections" not in data:
                raise ValueError("Model declined the analysis: " + str(data.get("error")))
            data = _postprocess(data, mode)
            print(f"[DEBUG] parsed OK, sections={list((data.get('sections') or {}).keys())}")
            data = _grounding_pipeline(client, MODEL_ANALYSIS, "issuer", mode,
                                       company, data, msg, base_messages, submit_id,
                                       progress=progress)
            return data
        except anthropic.AuthenticationError as ex:
            raise ex
        except anthropic.RateLimitError:
            print(f"[DEBUG] RateLimit - waiting 30s (attempt {attempt+1}/4)")
            time.sleep(30)
        except Exception as ex:
            print(f"[DEBUG] attempt {attempt+1}/4 failed: {ex}")
            if attempt < 3:
                time.sleep(2 ** attempt)
                continue
            raise ex


def _issuer_job(company, mode, force, progress=_noop):
    if not force:
        cached = analysis_db.recent_analysis(company, mode)
        if cached:
            progress("Loaded from cache")
            cached["_cached"] = True
            return cached
    data = run_analysis(company, mode, progress=progress)
    data["_mode"] = mode
    data["_cached"] = False
    progress("Saving")
    analysis_db.save_analysis("issuer", mode, company, data)
    return data

# ── API Call: Prospectus & Recovery ───────────────────────────────────────────

INTRO_PROSPECTUS = """You are a Senior Credit Portfolio Manager in the tradition of Oaktree Capital — a distressed-debt and credit specialist. You analyse the bond / notes of **{issuer}** from a creditor's and a recovery perspective. Language: English.

Your job is to dissect the legal and economic structure of the instrument: how the covenant package is built, WHY it is built that way, how it compares to peer deals, and what a creditor would actually recover in a default.

RESEARCH PROTOCOL — you complete this before the analysis:
1. If a bond prospectus / offering memorandum / OM / terms & conditions is attached, you read it as the PRIMARY source: ranking, security, guarantees, the full covenant package, the definitions (especially Consolidated EBITDA and its add-backs), all baskets, restricted vs unrestricted subsidiaries, change-of-control and portability.
2. You supplement with the issuer's latest financials and 2-4 comparable recent deals (same sector, rating band and sponsor type) for the peer covenant comparison.
3. For recovery you build a going-concern enterprise-value waterfall and an asset-based liquidation downside.
4. You target a data base of at least 4 concrete sources.

You think like Oaktree: you assume things go wrong, you read the document for what it ALLOWS rather than what it promises, you size every basket in numbers, and you price protection and margin of safety, not yield or optimism."""

PROSP_STANDARDS = """Data policy: Every figure and covenant detail must come from the attached document, a source you retrieve in this session, or the reference data provided. You mark data that is not in the document with [Not in document] and data that is not public with [Not public]. You may add clearly-labelled qualitative market context, but you never substitute an invented or estimated number for a fact and you never present an unverified figure as disclosed. You complete every section; where data is missing you say so explicitly rather than guessing. An honest [Not in document] / [Not public] is always preferred over a plausible-sounding number.

Writing standards: Institutional English. Subject-verb-object. Present tense. Active voice. Every number carries a unit and a reference — a EUR amount, turns of EBITDA, a %, or a clause/section of the document. For each covenant you state (a) what it permits, (b) the capacity in numbers, (c) the creditor implication. For recovery you always show the value, the claims ranking ahead, and the residual to the analysed instrument as a %. This keeps ten reports for ten deals directly comparable.
FORBIDDEN words: "elevated risk" / "challenging environment" / "potentially" / "possibly" / "it remains to be seen".

You set confidence per section (high only when grounded in the actual document or disclosed figures, otherwise medium, low when largely inferred), cov_strength on covenant sections (creditor_friendly / balanced / issuer_friendly), peer_verdict on the peer section, recovery_band on recovery sections (high = 70-100%, moderate = 40-70%, low = 0-40%), and you fill the table rows where requested. You complete the research, then you call the tool `submit_prospectus_analysis` exactly once with the full structured result. You write nothing outside the tool call."""


def _prosp_section_schema(spec):
    props = {
        "text":       {"type": "string", "description": spec["brief"]},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "sources":    {"type": "array", "items": {"type": "string"},
                       "description": "2-4 concrete dated sources actually used (document section, report, deal)."},
    }
    required = ["text", "confidence", "sources"]
    if spec.get("cov"):
        props["cov_strength"] = {"type": "string",
                                 "enum": ["creditor_friendly", "balanced", "issuer_friendly"],
                                 "description": "Creditor-friendliness of this covenant element."}
        required.append("cov_strength")
    if spec.get("peer"):
        props["peer_verdict"] = {"type": "string", "enum": ["stronger", "in_line", "weaker"],
                                 "description": "Is this documentation tighter (stronger), in line, or looser (weaker) than the peer set?"}
        required.append("peer_verdict")
    if spec.get("recovery"):
        props["recovery_band"] = {"type": "string", "enum": ["high", "moderate", "low"],
                                  "description": "Estimated recovery band: high 70-100%, moderate 40-70%, low 0-40%."}
        required.append("recovery_band")
    if spec.get("table"):
        cols = PROSP_TABLE_COLS[spec["key"]]
        props["rows"] = {
            "type": "array",
            "description": ("Table rows. Each row is a list of " + str(len(cols))
                            + " string values for the fixed columns, in this exact order: "
                            + " | ".join(cols) + ". Use 'n/a' only when genuinely unavailable."),
            "items": {"type": "array", "items": {"type": "string"}},
        }
        required.append("rows")
    return {"type": "object", "properties": props, "required": required}


def build_prospectus_schema():
    """Build the submit_prospectus_analysis input schema from the prospectus spec."""
    sec_props  = {s["key"]: _prosp_section_schema(s) for s in PROSPECTUS_SECTION_SPEC}
    meta_props = {k: {"type": "string", "description": v} for k, v in PROSP_META_SPEC.items()}
    return {
        "type": "object",
        "properties": {
            "company":  {"type": "string", "description": "Issuer legal name (used as the report title)."},
            "as_of":    {"type": "string", "description": "Document date / data date, e.g. 'OM dated March 2024, data as of FY23'."},
            "meta":     {"type": "object", "properties": meta_props, "required": list(meta_props)},
            "sections": {"type": "object", "properties": sec_props,  "required": list(sec_props)},
        },
        "required": ["company", "as_of", "meta", "sections"],
    }


def run_prospectus_analysis(issuer, files):
    """Analyse a bond prospectus (attached PDF) and/or an issuer name. Returns the structured result."""
    issuer_label = (issuer or "").strip() or "the issuer named in the attached prospectus"
    prompt = INTRO_PROSPECTUS.format(issuer=issuer_label) + "\n\n" + PROSP_STANDARDS + "\n\n" + _knowledge("prospectus")

    blocks = []
    for f in (files or []):
        blk, _note = make_file_block(f["name"], f["data"])
        if blk:
            blocks.append(blk)
    if blocks:
        blocks.append({"type": "text", "text":
                       "The above attachment is the bond prospectus / offering memorandum. "
                       "Read it as your primary source.\n\n" + prompt})
    else:
        blocks.append({"type": "text", "text":
                       "No prospectus is attached. Locate the most recent public bond "
                       "documentation for this issuer via web search and analyse it.\n\n" + prompt})

    tools = [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": 12},
        {"name": "submit_prospectus_analysis",
         "description": "Submit the completed structured prospectus & recovery analysis. Call this exactly once, after the research is done.",
         "input_schema": build_prospectus_schema()},
    ]
    base_messages = [{"role": "user", "content": blocks}]

    client = anthropic.Anthropic(api_key=API_KEY, timeout=600)
    for attempt in range(4):
        try:
            msg = client.messages.create(
                model=MODEL_ANALYSIS, max_tokens=18000,
                thinking={"type": "adaptive"},
                tools=tools,
                messages=base_messages)
            print(f"[DEBUG] prosp stop_reason={msg.stop_reason}, blocks={[type(b).__name__ for b in msg.content]}")

            data, submit_id = None, None
            for b in msg.content:
                if getattr(b, "type", None) == "tool_use" and getattr(b, "name", "") == "submit_prospectus_analysis":
                    data = b.input
                    submit_id = getattr(b, "id", None)
                    break
            if data is None:
                raw = "".join(b.text for b in msg.content if hasattr(b, "text") and b.text).strip()
                print(f"[DEBUG] prosp no tool_use; falling back to text JSON, len={len(raw)}")
                if not raw:
                    raise ValueError("Empty response - stop_reason=" + str(msg.stop_reason))
                data = _parse_text_json(raw)

            if not data:
                raise ValueError("Tool returned empty input")
            if "error" in data and "sections" not in data:
                raise ValueError("Model declined the analysis: " + str(data.get("error")))
            print(f"[DEBUG] prosp parsed OK, sections={list((data.get('sections') or {}).keys())}")
            data = _grounding_pipeline(client, MODEL_ANALYSIS, "prospectus", "prosp",
                                       issuer_label, data, msg, base_messages, submit_id,
                                       attachments=files)
            return data
        except anthropic.AuthenticationError as ex:
            raise ex
        except anthropic.RateLimitError:
            print(f"[DEBUG] prosp RateLimit - waiting 30s (attempt {attempt+1}/4)")
            time.sleep(30)
        except Exception as ex:
            print(f"[DEBUG] prosp attempt {attempt+1}/4 failed: {ex}")
            if attempt < 3:
                time.sleep(2 ** attempt)
                continue
            raise ex


# ── API Call: Market Report ───────────────────────────────────────────────────

MARKET_SEGMENTS = {"hy": "High Yield", "ig": "Investment Grade"}
MARKET_REGIONS  = {"europe": "Europe", "usa": "USA", "asia": "Asia", "row": "Rest of World"}

MARKET_SECTION_SPEC = [
    {"key": "news", "label": "1.  Current News & Market Tone",
     "brief": "150-220 words. The current state of the {seg} bond market in {reg}: spread levels and their direction over the last weeks, primary-market activity and notable new issues, fund flows, the dominant macro and rates drivers, and the prevailing risk tone (risk-on / risk-off). Ground every data point in a dated source you actually retrieve."},
    {"key": "covenants_restructuring", "label": "2.  Covenant Trends, Legal Changes & Restructurings",
     "brief": "150-220 words. Documentation and legal trends in {seg} {reg}: how covenant packages are evolving (tightening or loosening), notable liability-management exercises (LME) and creditor-on-creditor situations, J.Crew / Serta-style manoeuvres and open-market-purchase up-tiering, court rulings and legal or regulatory changes affecting creditor rights, and recent or pending restructurings. Name concrete issuers, deals and dates."},
    {"key": "bonds_bid", "label": "3.  Bonds in Demand (Bid)",
     "brief": "150-220 words. Which {seg} {reg} bonds, sectors or rating buckets are sought after right now and why: names being accumulated, sectors in favour, where investors are adding risk or duration, and the rationale (rating momentum, sector tailwind, relative value). Name concrete issuers / instruments where possible."},
    {"key": "bonds_offered", "label": "4.  Bonds Being Sold Off (Offered)",
     "brief": "150-220 words. Which {seg} {reg} bonds, sectors or rating buckets are being sold or avoided right now and why: names under pressure, sectors out of favour, falling-angel dynamics, idiosyncratic credit deterioration and crowded exits. Name concrete issuers / instruments where possible."},
]
MARKET_SECTIONS = [(s["key"], s["label"]) for s in MARKET_SECTION_SPEC]

MARKET_INTRO = """You are a senior credit market strategist. You produce a concise, current market report for the {seg} bond market in {reg}. Language: English.

RESEARCH PROTOCOL: You run live web searches for the most recent (last days to weeks) data: spread levels and direction, fund flows, new issues, rating actions, LME / restructuring news, and legal / covenant developments. You ground every claim in a dated source you actually retrieve. You never invent figures; where a number is unavailable you say so. Institutional prose, subject-verb-object, present tense, every number with a unit and a date. You complete the research, then you call the tool `submit_market_report` exactly once. You write nothing outside the tool call."""


def build_market_schema(seg, reg):
    props = {}
    for s in MARKET_SECTION_SPEC:
        props[s["key"]] = {"type": "object", "properties": {
            "text":    {"type": "string", "description": s["brief"].format(seg=seg, reg=reg)},
            "sources": {"type": "array", "items": {"type": "string"},
                        "description": "2-4 concrete dated sources actually used."}},
            "required": ["text", "sources"]}
    return {"type": "object", "properties": {
        "headline": {"type": "string", "description": "One-sentence headline on the state of this market right now."},
        "as_of":    {"type": "string", "description": "Data date, e.g. 'as of 24 June 2026'."},
        "sections": {"type": "object", "properties": props, "required": list(props)}},
        "required": ["headline", "as_of", "sections"]}


def run_market_report(segment, region, progress=_noop):
    seg = MARKET_SEGMENTS.get(segment, "High Yield")
    reg = MARKET_REGIONS.get(region, "Europe")
    progress("Researching " + seg + " " + reg)
    prompt = MARKET_INTRO.format(seg=seg, reg=reg) + "\n\n" + _knowledge("market")
    tools = [WEB_SEARCH_TOOL,
             {"name": "submit_market_report",
              "description": "Submit the structured market report. Call this exactly once, after the research is done.",
              "input_schema": build_market_schema(seg, reg)}]
    base_messages = [{"role": "user", "content": prompt}]
    client = anthropic.Anthropic(api_key=API_KEY, timeout=600)
    for attempt in range(3):
        try:
            msg = client.messages.create(
                model=MODEL_ANALYSIS, max_tokens=9000, thinking={"type": "adaptive"},
                tools=tools, messages=base_messages)
            data = None
            for b in msg.content:
                if getattr(b, "type", None) == "tool_use" and getattr(b, "name", "") == "submit_market_report":
                    data = b.input
                    break
            if data is None:
                raw = "".join(b.text for b in msg.content if hasattr(b, "text") and b.text).strip()
                if not raw:
                    raise ValueError("Empty response - stop_reason=" + str(msg.stop_reason))
                data = _parse_text_json(raw)
            if not data:
                raise ValueError("Tool returned empty input")
            data["_segment"], data["_region"] = seg, reg
            if USE_ARCHIVE:
                try:
                    progress("Archiving sources")
                    sources = research_db.extract_search_results(msg)
                    run_id = research_db.new_run_id(seg + "-" + reg)
                    data["_sources"] = research_db.store_run(
                        run_id, "market", "market", seg + " " + reg, data.get("as_of", ""), sources)
                    data["_run_id"] = run_id
                except Exception as ex:
                    print(f"[DEBUG] market archive failed: {ex}")
            return data
        except anthropic.RateLimitError:
            time.sleep(20)
        except Exception as ex:
            print(f"[DEBUG] market attempt {attempt+1}/3 failed: {ex}")
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise ex


# ── API Call: Liquidity & Stress (input gathering) ────────────────────────────

LIQ_INTRO = {
    "corp": "You are a Senior Credit Analyst (Oaktree level) building a liquidity and cash-flow model for **{company}** (corporate issuer). Language: English.",
    "fin":  "You are a Senior Financial-Institutions Credit Analyst (Oaktree/BlackRock level) building a capital and liquidity model for **{company}** (bank / financial). Language: English.",
    "sov":  "You are a Senior Sovereign Credit Analyst (IMF/BlackRock level) building a debt-sustainability and financing model for **{company}** (sovereign / SSA). Language: English.",
}

LIQ_STANDARDS = """Your task: research the issuer and return the standardised model inputs via the tool `submit_liquidity_inputs`. Use the most recent disclosed figures (annual / interim reports, rating-agency reports, official statistics). Where a line item is not separately disclosed, provide a reasoned estimate consistent with what IS disclosed, and say in the commentary which inputs are estimated rather than reported. Numbers only in the numeric fields, in the stated unit. You complete the research, then you call `submit_liquidity_inputs` exactly once. You write nothing outside the tool call."""


def _condense_analysis(data, mode):
    secs = data.get("sections") or {}
    parts = []
    for key, lbl in SECTIONS.get(mode, []):
        s = secs.get(key)
        if not isinstance(s, dict):
            continue
        t = clean(s.get("text", ""))
        if t:
            parts.append(lbl + ": " + t)
        kt = _fixed_kpi_table(s, mode)
        if kt:
            yrs = kt.get("years", [])
            for m, row in zip(kt.get("metrics", []), kt.get("data", [])):
                parts.append("  " + m + ": " + "  ".join(f"{y}={v}" for y, v in zip(yrs, row)))
    return "\n".join(parts)[:12000]


def run_liquidity(company, mode, progress=_noop):
    progress("Loading reference data")
    prompt = LIQ_INTRO[mode].format(company=company) + "\n\n" + LIQ_STANDARDS + "\n\n" + _knowledge("liquidity")
    try:
        prior = analysis_db.recent_analysis(company, mode)
    except Exception:
        prior = None
    if prior and prior.get("sections"):
        progress("Reusing saved analysis")
        prompt += ("\n\nAn existing credit analysis for this issuer is available. Extract the "
                   "numeric model inputs from it where possible and research only what is missing:\n\n"
                   + _condense_analysis(prior, mode))
    if USE_FEEDS:
        try:
            ref_text, _ = datafeeds.reference_data(mode, company)
            if ref_text:
                prompt += "\n\n" + ref_text
        except Exception as ex:
            print(f"[DEBUG] liq reference data failed: {ex}")
    tools = [WEB_SEARCH_TOOL,
             {"name": "submit_liquidity_inputs",
              "description": "Submit the standardised liquidity / cash-flow model inputs. Call this exactly once, after the research is done.",
              "input_schema": liquidity.build_inputs_schema(mode)}]
    base_messages = [{"role": "user", "content": prompt}]
    client = anthropic.Anthropic(api_key=API_KEY, timeout=600)
    for attempt in range(3):
        try:
            progress("Researching inputs" + (f" (retry {attempt})" if attempt else ""))
            msg = client.messages.create(
                model=MODEL_ANALYSIS, max_tokens=8000, thinking={"type": "adaptive"},
                tools=tools, messages=base_messages)
            data = None
            for b in msg.content:
                if getattr(b, "type", None) == "tool_use" and getattr(b, "name", "") == "submit_liquidity_inputs":
                    data = b.input
                    break
            if data is None:
                raw = "".join(b.text for b in msg.content if hasattr(b, "text") and b.text).strip()
                if not raw:
                    raise ValueError("Empty response - stop_reason=" + str(msg.stop_reason))
                data = _parse_text_json(raw)
            if not data:
                raise ValueError("Tool returned empty input")
            data["_liqmode"], data["company"] = mode, company
            if USE_ARCHIVE:
                try:
                    progress("Archiving sources")
                    sources = research_db.extract_search_results(msg)
                    run_id = research_db.new_run_id("liq-" + company)
                    data["_sources"] = research_db.store_run(
                        run_id, "liquidity", mode, company, "", sources)
                    data["_run_id"] = run_id
                except Exception as ex:
                    print(f"[DEBUG] liq archive failed: {ex}")
            return data
        except anthropic.RateLimitError:
            time.sleep(20)
        except Exception as ex:
            print(f"[DEBUG] liq attempt {attempt+1}/3 failed: {ex}")
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise ex


def _liquidity_job(company, mode, force, progress=_noop):
    ckey = "liq_" + mode
    if not force:
        cached = analysis_db.recent_analysis(company, ckey)
        if cached:
            progress("Loaded from cache")
            cached["_cached"] = True
            return cached
    data = run_liquidity(company, mode, progress=progress)
    data["_cached"] = False
    progress("Saving")
    analysis_db.save_analysis("liquidity", ckey, company, data)
    return data


# ── API Call: Portfolio Advisor ───────────────────────────────────────────────

ADVISOR_ROLE = """You are the Chief Credit Strategist for a fixed income credit portfolio. You always analyze every user input and every attached file in relation to the current portfolio shown below.

You answer in three parts and you use plain prose:
1. Relevance to the portfolio. You name the affected positions, issuers, sectors or risk buckets with concrete numbers from the portfolio (market value, weight, duration, DV01, spread).
2. Positioning implications. You state what the portfolio adds, reduces, holds or hedges, and why.
3. Risk-management conclusions. You state the concrete risks for the portfolio and how the manager controls them.

Writing standards: English. Subject-verb-object. Present tense. Active voice. You place every number in context with a unit and a year. You write institutional prose. You use no emojis, no markdown bold, no bullet symbols. You give direct judgments and you avoid hedging words such as "potentially", "possibly", "it remains to be seen". You use only the portfolio data provided and you never invent positions. When the portfolio holds nothing related, you say so directly."""

def make_file_block(name, data_uri):
    """Turn a dcc.Upload data URI into an Anthropic content block + a short note."""
    try:
        _, b64 = data_uri.split(",", 1)
    except ValueError:
        return None, f"[Could not read: {name}]"
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""

    if ext == "pdf":
        return ({"type": "document",
                 "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
                f"[PDF attached: {name}]")
    if ext in ("png", "jpg", "jpeg", "gif", "webp"):
        mt = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
              "gif": "image/gif", "webp": "image/webp"}[ext]
        return ({"type": "image",
                 "source": {"type": "base64", "media_type": mt, "data": b64}},
                f"[Image attached: {name}]")

    # Text-like or spreadsheet: decode and inline as text.
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return None, f"[Could not decode: {name}]"
    if ext in ("xlsx", "xls"):
        try:
            sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None)
            parts = []
            for sn, sdf in sheets.items():
                parts.append(f"# Sheet: {sn}\n{sdf.to_csv(index=False)}")
            text = "\n\n".join(parts)
        except Exception as ex:
            text = f"[Excel parse error: {ex}]"
    else:
        text = raw.decode("utf-8", errors="replace")
    text = text[:60000]
    return ({"type": "text", "text": f"Attached file {name}:\n{text}"},
            f"[File attached: {name}]")

def run_advisor(prompt, files, history):
    """Analyze prompt + attachments against the live portfolio. Returns (answer, note)."""
    context, _ = load_portfolio()
    if context is None:
        return None, "Portfolio not available."

    system_blocks = [
        {"type": "text", "text": ADVISOR_ROLE},
        {"type": "text", "text": context, "cache_control": {"type": "ephemeral"}},
    ]

    api_messages = []
    for h in (history or []):
        api_messages.append({"role": h["role"], "content": h["content"]})

    # Current turn: attachments first, then the user prompt.
    blocks, notes = [], []
    for f in (files or []):
        blk, note = make_file_block(f["name"], f["data"])
        if blk:
            blocks.append(blk)
        notes.append(note)
    blocks.append({"type": "text", "text": prompt})
    api_messages.append({"role": "user", "content": blocks})

    client = anthropic.Anthropic(api_key=API_KEY, timeout=600)
    for attempt in range(3):
        try:
            msg = client.messages.create(
                model=MODEL_ADVISOR, max_tokens=2800,
                system=system_blocks,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 6}],
                messages=api_messages)
            answer = "".join(b.text for b in msg.content if hasattr(b, "text") and b.text).strip()
            if not answer:
                raise ValueError("Empty response - stop_reason=" + str(msg.stop_reason))
            user_record = prompt + (("\n" + "\n".join(notes)) if notes else "")
            return answer, user_record
        except anthropic.RateLimitError:
            time.sleep(20)
        except Exception as ex:
            print(f"[DEBUG] advisor attempt {attempt+1}/3 failed: {ex}")
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise ex

# ── App ───────────────────────────────────────────────────────────────────────

app = dash.Dash(__name__, suppress_callback_exceptions=True)


from flask import send_from_directory, abort as _flask_abort

@app.server.route("/docs/<path:rel>")
def _serve_doc(rel):
    try:
        return send_from_directory(str(research_db.ARCHIVE_DIR), rel)
    except Exception:
        return _flask_abort(404)

INP = {
    "width":        "100%",
    "padding":      "10px 14px",
    "fontSize":     "13px",
    "fontFamily":   VF,
    "border":       "1px solid " + C["border"],
    "borderRadius": "2px",
    "outline":      "none",
    "boxSizing":    "border-box",
    "color":        C["ink"],
    "background":   C["surface"],
}

BTN = {
    "padding":       "10px 32px",
    "fontSize":      "11px",
    "fontWeight":    "700",
    "letterSpacing": "0.10em",
    "fontFamily":    VF,
    "background":    C["navy"],
    "color":         "white",
    "border":        "none",
    "borderRadius":  "2px",
    "cursor":        "pointer",
    "whiteSpace":    "nowrap",
    "textTransform": "uppercase",
}

def history_options(kind="issuer"):
    return [{"label": f"{a['issuer']}  ·  {a['mode']}  ·  {a['ts'][:16].replace('T', ' ')}",
             "value": a["id"]}
            for a in analysis_db.list_analyses(60, kind=kind)]


def tab_panel_issuer():
    return html.Div([
        card([
            sec_title("Single-Issuer Credit Analysis"),
            html.Div([
                dcc.Dropdown(
                    id="mode-dropdown",
                    options=[
                        {"label": "Corporate",      "value": "corp"},
                        {"label": "Financial",       "value": "fin"},
                        {"label": "Sovereign / SSA", "value": "sov"},
                    ],
                    value="corp",
                    clearable=False,
                    searchable=False,
                    style={
                        "width":        "180px",
                        "fontSize":     "12px",
                        "fontFamily":   VF,
                        "marginRight":  "12px",
                        "flexShrink":   "0",
                    },
                ),
                dcc.Input(id="company-input", type="text", debounce=False,
                          placeholder="Enter issuer...",
                          style=dict(**INP, flex="1")),
                html.Button("Run analysis", id="btn-run", n_clicks=0, style={
                    **BTN, "marginLeft": "12px",
                }),
                html.Div(id="status-msg", style={
                    "fontSize":   "12px",
                    "color":      C["muted"],
                    "fontFamily": VF,
                    "marginLeft": "14px",
                }),
            ], style={"display":"flex","alignItems":"center"}),
            html.Div([
                dcc.Dropdown(id="history-dropdown", options=history_options(),
                             placeholder="Load a previous analysis (no re-run)…",
                             clearable=True, searchable=True,
                             style={"flex": "1", "fontSize": "12px", "fontFamily": VF}),
                dcc.Checklist(id="force-refresh",
                              options=[{"label": " Force refresh (ignore cache)", "value": "force"}],
                              value=[], style={"fontSize": "11px", "fontFamily": VF,
                                               "color": C["muted"], "marginLeft": "16px",
                                               "whiteSpace": "nowrap"}),
            ], style={"display": "flex", "alignItems": "center", "marginTop": "12px"}),
        ]),
        dcc.Loading(type="circle", color=C["accent"],
                    children=html.Div(id="output")),

        # ── Follow-up questions ──
        html.Div(id="chat-section", style={"display":"none"}, children=[
            card([
                sec_title("Follow-up Questions"),
                dcc.Loading(type="circle", color=C["rose"],
                            children=html.Div(id="chat-display", style={"marginBottom": "20px"})),
                html.Div([
                    dcc.Textarea(
                        id="chat-input",
                        placeholder="Ask a follow-up question on the analysis  (e.g. How do you rate the refinancing risk versus peers?)",
                        style={
                            **INP,
                            "height":   "72px",
                            "resize":   "vertical",
                            "flex":     "1",
                            "padding":  "10px 14px",
                        },
                    ),
                    html.Button("Send", id="btn-chat", n_clicks=0, style={
                        **BTN,
                        "marginLeft":    "12px",
                        "alignSelf":     "flex-end",
                        "height":        "42px",
                        "background":    C["rose"],
                    }),
                ], style={"display": "flex", "alignItems": "flex-end"}),
                html.Div(id="chat-status", style={
                    "fontSize":   "11px",
                    "color":      C["muted"],
                    "fontFamily": VF,
                    "marginTop":  "8px",
                }),
            ]),
        ]),
    ])

def tab_panel_advisor():
    _, headline = load_portfolio()
    return html.Div([
        card([
            sec_title("Portfolio Advisor"),
            html.Div([
                html.Span(id="adv-portfolio-status", children=headline, style={
                    "fontSize":   "12px",
                    "color":      C["navy"],
                    "fontWeight": "600",
                    "fontFamily": VF,
                    "flex":       "1",
                }),
                html.Button("Reload portfolio", id="btn-reload", n_clicks=0, style={
                    **BTN, "padding": "8px 20px", "background": C["muted"],
                }),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "8px",
                       "paddingBottom": "16px", "borderBottom": "1px solid " + C["border"]}),
            html.Div(
                "The advisor reads your portfolio Excel live and analyzes every prompt and "
                "attachment against it. It focuses on positioning and risk management.",
                style={"fontSize": "12px", "color": C["muted"], "fontFamily": VF,
                       "lineHeight": "1.7", "marginBottom": "20px"}),

            dcc.Loading(type="circle", color=C["rose"],
                        children=html.Div(id="adv-display", style={"marginBottom": "20px"})),

            dcc.Upload(
                id="adv-upload",
                multiple=True,
                children=html.Div(
                    "Drag and drop files here, or click to attach  (PDF, image, CSV, TXT, XLSX)",
                    style={"fontSize": "12px", "color": C["muted"], "fontFamily": VF}),
                style={
                    "border":       "1.5px dashed " + C["accent"],
                    "borderRadius": "3px",
                    "padding":      "16px",
                    "textAlign":    "center",
                    "cursor":       "pointer",
                    "marginBottom": "10px",
                    "background":   C["bg"],
                },
            ),
            html.Div(id="adv-files-display", style={
                "fontSize": "11px", "color": C["navy"], "fontFamily": VF, "marginBottom": "12px"}),

            html.Div([
                dcc.Textarea(
                    id="adv-input",
                    placeholder="Ask the portfolio advisor  (e.g. A rating agency downgrades issuer X. What does this mean for our positioning and risk?)",
                    style={
                        **INP,
                        "height":   "92px",
                        "resize":   "vertical",
                        "flex":     "1",
                        "padding":  "10px 14px",
                    },
                ),
                html.Button("Send", id="btn-adv", n_clicks=0, style={
                    **BTN,
                    "marginLeft":    "12px",
                    "alignSelf":     "flex-end",
                    "height":        "44px",
                    "background":    C["rose"],
                }),
            ], style={"display": "flex", "alignItems": "flex-end"}),
            html.Div(id="adv-status", style={
                "fontSize":   "11px",
                "color":      C["muted"],
                "fontFamily": VF,
                "marginTop":  "8px",
            }),
        ]),
    ])

def tab_panel_prospectus():
    return html.Div([
        card([
            sec_title("Prospectus & Recovery"),
            html.Div(
                "Enter an issuer and / or attach a bond prospectus (offering memorandum). "
                "Opus 4.8 runs an Oaktree-style senior credit analysis: how the covenant "
                "package is built and why, a peer covenant comparison, and a recovery analysis "
                "(going-concern and liquidation) with an estimated recovery by instrument.",
                style={"fontSize": "12px", "color": C["muted"], "fontFamily": VF,
                       "lineHeight": "1.7", "marginBottom": "20px"}),

            dcc.Input(id="prosp-issuer", type="text", debounce=False,
                      placeholder="Enter issuer / instrument  (optional if a prospectus is attached)",
                      style=dict(**INP, marginBottom="12px")),

            dcc.Upload(
                id="prosp-upload",
                multiple=True,
                children=html.Div(
                    "Drag and drop the bond prospectus here, or click to attach  (PDF, TXT, DOCX-as-text)",
                    style={"fontSize": "12px", "color": C["muted"], "fontFamily": VF}),
                style={
                    "border": "1.5px dashed " + C["accent"], "borderRadius": "3px",
                    "padding": "16px", "textAlign": "center", "cursor": "pointer",
                    "marginBottom": "10px", "background": C["bg"],
                },
            ),
            html.Div(id="prosp-files-display", style={
                "fontSize": "11px", "color": C["navy"], "fontFamily": VF, "marginBottom": "12px"}),

            html.Div([
                html.Button("Run prospectus analysis", id="btn-prosp-run", n_clicks=0, style=BTN),
                html.Div(id="prosp-status", style={
                    "fontSize": "12px", "color": C["muted"], "fontFamily": VF,
                    "marginLeft": "14px"}),
            ], style={"display": "flex", "alignItems": "center"}),
        ]),
        dcc.Loading(type="circle", color=C["accent"],
                    children=html.Div(id="prosp-output")),
    ])


def render_library():
    runs = research_db.list_runs(80)
    if not runs:
        return html.Div("No archived research yet. Run an analysis and its sources "
                        "appear here.", style={"fontSize": "12px", "color": C["muted"],
                                               "fontFamily": VF})
    items = []
    for r in runs:
        srcs = research_db.run_sources(r["run_id"])
        head = html.Div([
            html.Span(r.get("issuer") or r["run_id"], style={
                "fontSize": "12px", "fontWeight": "700", "color": C["navy"], "fontFamily": VF}),
            html.Span("   ·   " + (r.get("kind") or "") + "   ·   " + (r.get("ts") or ""),
                      style={"fontSize": "11px", "color": C["muted"], "fontFamily": VF}),
        ])
        note = (html.Div("Audit: " + r["verify_note"], style={
            "fontSize": "11px", "color": C["muted"], "fontFamily": VF,
            "fontStyle": "italic", "marginTop": "3px"}) if r.get("verify_note") else html.Span())
        body = (html.Ul([_doc_link(s) for s in srcs],
                        style={"margin": "6px 0 0", "paddingLeft": "18px"})
                if srcs else html.Div("(no sources captured)", style={
                    "fontSize": "11px", "color": C["muted"], "fontFamily": VF}))
        items.append(html.Div([head, note, body], style={
            "padding": "12px 14px", "marginBottom": "10px", "background": C["surface"],
            "border": "1px solid " + C["border"], "borderLeft": "2px solid " + C["accent"],
            "borderRadius": "2px"}))
    return html.Div(items)


def _cmp_cell(sec):
    if not isinstance(sec, dict):
        return "—"
    v = sec.get("verify_verdict")
    return (sec.get("confidence", "—") or "—") + (f"  /  {v}" if v else "")


def build_compare(a, b):
    if not a or not b:
        return html.Div("Select two analyses, then press Compare.", style={
            "fontSize": "12px", "color": C["muted"], "fontFamily": VF})
    mode = a.get("_mode", "corp")
    sa, sb = a.get("sections") or {}, b.get("sections") or {}
    th = {"background": C["navy"], "color": "white", "fontSize": "10px", "fontFamily": VF,
          "fontWeight": "700", "padding": "6px 10px", "textAlign": "left",
          "letterSpacing": "0.05em"}
    td = {"fontSize": "11px", "fontFamily": VF, "padding": "5px 10px",
          "color": C["ink"], "borderBottom": "1px solid " + C["border"]}
    def hdr(x):
        return (x.get("company", "?") + "  ·  " + (x.get("as_of", "") or "")).strip(" ·")
    rows = []
    for i, (key, lbl) in enumerate(SECTIONS.get(mode, [])):
        ca, cb = _cmp_cell(sa.get(key)), _cmp_cell(sb.get(key))
        changed = ca != cb
        rows.append(html.Tr([
            html.Td(lbl, style={**td, "fontWeight": "600", "color": C["navy"]}),
            html.Td(ca, style=td),
            html.Td(cb, style={**td, "color": C["rose"] if changed else C["ink"],
                               "fontWeight": "700" if changed else "400"}),
        ], style={"background": C["bg"] if i % 2 else C["surface"]}))
    return card([
        sec_title("Comparison"),
        html.Table([
            html.Thead(html.Tr([html.Th("Section", style=th),
                                html.Th(hdr(a), style=th), html.Th(hdr(b), style=th)])),
            html.Tbody(rows),
        ], style={"width": "100%", "borderCollapse": "collapse",
                  "border": "1px solid " + C["border"]}),
        html.Div("Confidence / audit verdict per section. Rose = changed between the two runs.",
                 style={"fontSize": "10px", "color": C["muted"], "fontFamily": VF,
                        "marginTop": "8px", "fontStyle": "italic"}),
    ])


def tab_panel_library():
    return html.Div([
        card([
            sec_title("Research Library"),
            html.Div([
                html.Span("Every analysis archives the documents it actually retrieved. "
                          "Browse past runs and open the stored sources.", style={
                              "fontSize": "12px", "color": C["muted"], "fontFamily": VF,
                              "lineHeight": "1.7", "flex": "1"}),
                html.Button("Refresh", id="btn-lib-refresh", n_clicks=0, style={
                    **BTN, "padding": "8px 20px", "background": C["muted"]}),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "16px",
                       "paddingBottom": "16px", "borderBottom": "1px solid " + C["border"]}),
            dcc.Loading(type="circle", color=C["accent"],
                        children=html.Div(id="lib-display")),
        ]),
        card([
            sec_title("Compare two analyses"),
            html.Div([
                dcc.Dropdown(id="cmp-a", options=history_options(None), placeholder="Analysis A…",
                             style={"flex": "1", "fontSize": "12px", "fontFamily": VF}),
                dcc.Dropdown(id="cmp-b", options=history_options(None), placeholder="Analysis B…",
                             style={"flex": "1", "fontSize": "12px", "fontFamily": VF,
                                    "marginLeft": "12px"}),
                html.Button("Compare", id="btn-compare", n_clicks=0,
                            style={**BTN, "marginLeft": "12px"}),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "16px"}),
            html.Div(id="cmp-display"),
        ]),
    ])


def tab_panel_market():
    dd = {"width": "200px", "fontSize": "12px", "fontFamily": VF, "flexShrink": "0"}
    return html.Div([
        card([
            sec_title("Market Report"),
            html.Div("Select a universe; the AI generates a current market report: news and "
                     "tone, covenant & restructuring trends, bonds in demand, and bonds being "
                     "sold off.", style={"fontSize": "12px", "color": C["muted"],
                                         "fontFamily": VF, "lineHeight": "1.7", "marginBottom": "20px"}),
            html.Div([
                dcc.Dropdown(id="mkt-segment", clearable=False, searchable=False, value="hy",
                             options=[{"label": "High Yield", "value": "hy"},
                                      {"label": "Investment Grade", "value": "ig"}], style=dd),
                dcc.Dropdown(id="mkt-region", clearable=False, searchable=False, value="europe",
                             options=[{"label": "Europe", "value": "europe"},
                                      {"label": "USA", "value": "usa"},
                                      {"label": "Asia", "value": "asia"},
                                      {"label": "Rest of World", "value": "row"}],
                             style={**dd, "marginLeft": "12px"}),
                html.Button("Generate report", id="btn-mkt-run", n_clicks=0,
                            style={**BTN, "marginLeft": "12px"}),
                html.Div(id="mkt-status", style={"fontSize": "12px", "color": C["muted"],
                                                 "fontFamily": VF, "marginLeft": "14px"}),
            ], style={"display": "flex", "alignItems": "center"}),
        ]),
        dcc.Loading(type="circle", color=C["accent"], children=html.Div(id="mkt-output")),
    ])


def tab_panel_liquidity():
    return html.Div([
        card([
            sec_title("Liquidity & Stress"),
            html.Div("Pick a mode and issuer. The model gathers standardised, sourced inputs; "
                     "the engine projects cash flow, capital / leverage and liquidity over five "
                     "years and stress-tests them. Drag the assumptions to re-run the scenario "
                     "instantly - no API call.", style={"fontSize": "12px", "color": C["muted"],
                     "fontFamily": VF, "lineHeight": "1.7", "marginBottom": "20px"}),
            html.Div([
                dcc.Dropdown(id="liq-mode", clearable=False, searchable=False, value="corp",
                             options=[{"label": "Corporate", "value": "corp"},
                                      {"label": "Financial", "value": "fin"},
                                      {"label": "Sovereign / SSA", "value": "sov"}],
                             style={"width": "180px", "fontSize": "12px", "fontFamily": VF, "flexShrink": "0"}),
                dcc.Input(id="liq-company", type="text", placeholder="Enter issuer...",
                          style=dict(**INP, flex="1", marginLeft="12px")),
                html.Button("Build model", id="btn-liq-run", n_clicks=0, style={**BTN, "marginLeft": "12px"}),
                html.Div(id="liq-status", style={"fontSize": "12px", "color": C["muted"],
                                                 "fontFamily": VF, "marginLeft": "14px"}),
            ], style={"display": "flex", "alignItems": "center"}),
        ]),
        dcc.Loading(type="circle", color=C["accent"], children=html.Div(id="liq-output")),
    ])


def _knowledge_options():
    opts = [{"label": "+ New entry", "value": "__new__"}]
    for e in knowledge.list_entries():
        opts.append({"label": e["title"] + "   ·   [" + (e["scope"] or "all") + "]", "value": e["id"]})
    return opts


def tab_panel_knowledge():
    return html.Div([
        card([
            sec_title("Knowledge / Research Skills"),
            html.Div("Store the distilled viewpoint, method and red-flags from research papers. "
                     "Each note is injected into the analyses you scope it to - the model then "
                     "reasons with your house framework.", style={"fontSize": "12px",
                     "color": C["muted"], "fontFamily": VF, "lineHeight": "1.7", "marginBottom": "18px"}),
            html.Div([
                dcc.Dropdown(id="knowledge-select", options=_knowledge_options(), value="__new__",
                             clearable=False, style={"width": "380px", "fontSize": "12px", "fontFamily": VF}),
                html.Button("Delete", id="btn-know-delete", n_clicks=0,
                            style={**BTN, "marginLeft": "12px", "background": C["muted"], "padding": "8px 18px"}),
                html.Span(id="know-status", style={"fontSize": "12px", "color": C["muted"],
                                                   "fontFamily": VF, "marginLeft": "14px"}),
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "14px"}),
            dcc.Input(id="know-title", type="text",
                      placeholder="Title  (e.g. Oaktree - margin of safety in loose covenants)",
                      style=dict(**INP, marginBottom="12px")),
            html.Div("Scope - which analyses this note informs:", style={
                "fontSize": "10px", "fontWeight": "700", "color": C["navy"], "fontFamily": VF,
                "textTransform": "uppercase", "letterSpacing": "0.08em", "marginBottom": "8px"}),
            dcc.Checklist(id="know-scope", inline=True, value=["prospectus"],
                          options=[{"label": " " + s, "value": s} for s in knowledge.SCOPES],
                          style={"fontSize": "12px", "fontFamily": VF, "color": C["ink"],
                                 "marginBottom": "12px"},
                          inputStyle={"marginRight": "4px", "marginLeft": "10px"}),
            dcc.Textarea(id="know-body",
                         placeholder="Paste the distilled insight: the framework, the method, the "
                                     "red-flags, the viewpoint. Write it as guidance an analyst should follow.",
                         style={**INP, "height": "280px", "resize": "vertical", "padding": "10px 14px"}),
            html.Button("Save", id="btn-know-save", n_clicks=0, style={**BTN, "marginTop": "12px"}),
        ]),
    ])


app.layout = html.Div([
    dcc.Store(id="result-store"),
    dcc.Store(id="prosp-result-store"),
    dcc.Store(id="prosp-files", data=[]),
    dcc.Store(id="chat-history", data=[]),
    dcc.Store(id="adv-history", data=[]),
    dcc.Store(id="adv-files", data=[]),
    dcc.Store(id="job-store"),
    dcc.Interval(id="job-poll", interval=1500, disabled=True),
    dcc.Store(id="liq-job-store"),
    dcc.Store(id="liq-store"),
    dcc.Interval(id="liq-poll", interval=1500, disabled=True),
    dcc.Download(id="pdf-download"),
    dcc.Download(id="prosp-pdf-download"),
    dcc.Download(id="liq-pdf-download"),

    # ── Header ──
    html.Div([
        html.Div([
            (html.Img(src="data:image/png;base64," + LOGO_B64,
                      style={"height":"68px","width":"auto","objectFit":"contain"})
             if LOGO_B64 else
             html.Span("nordIX", style={
                 "fontSize":"32px","fontWeight":"700","color":"white","fontFamily":VFH,
             })),
        ], style={"marginRight": "36px"}),
        html.Div([
            html.Div("Fixed Income Credit Platform  ·  nordIX AG, Hamburg", style={
                "fontSize":      "12px",
                "fontWeight":    "700",
                "color":         "white",
                "fontFamily":    VF,
                "letterSpacing": "0.14em",
                "textTransform": "uppercase",
            }),
        ]),
        html.Div([
            html.Div(datetime.now().strftime("%d %B %Y").upper(), style={
                "fontSize":      "9px",
                "color":         C["accent"],
                "fontFamily":    VF,
                "letterSpacing": "0.12em",
                "textAlign":     "right",
            }),
        ], style={"marginLeft": "auto"}),
    ], style={
        "display":       "flex",
        "alignItems":    "center",
        "padding":       "16px 48px",
        "background":    C["navy"],
        "boxShadow":     "0 4px 18px rgba(2,35,60,0.22)",
    }),
    html.Div(style={
        "height":     "3px",
        "background": f"linear-gradient(90deg, {C['navy']} 0%, {C['accent']} 45%, {C['bg']} 100%)",
    }),

    # ── Tabs ──
    html.Div([
        dcc.Tabs(id="tabs", value="issuer", children=[
            dcc.Tab(label="Issuer Analysis", value="issuer",
                    style={"fontFamily": VF, "fontSize": "12px", "fontWeight": "700",
                           "letterSpacing": "0.08em", "textTransform": "uppercase",
                           "color": C["muted"], "border": "none", "padding": "14px"},
                    selected_style={"fontFamily": VF, "fontSize": "12px", "fontWeight": "700",
                           "letterSpacing": "0.08em", "textTransform": "uppercase",
                           "color": C["navy"], "borderTop": "3px solid " + C["navy"],
                           "borderBottom": "none", "padding": "14px"}),
            dcc.Tab(label="Prospectus & Recovery", value="prospectus",
                    style={"fontFamily": VF, "fontSize": "12px", "fontWeight": "700",
                           "letterSpacing": "0.08em", "textTransform": "uppercase",
                           "color": C["muted"], "border": "none", "padding": "14px"},
                    selected_style={"fontFamily": VF, "fontSize": "12px", "fontWeight": "700",
                           "letterSpacing": "0.08em", "textTransform": "uppercase",
                           "color": C["navy"], "borderTop": "3px solid " + C["navy"],
                           "borderBottom": "none", "padding": "14px"}),
            dcc.Tab(label="Market Report", value="market",
                    style={"fontFamily": VF, "fontSize": "12px", "fontWeight": "700",
                           "letterSpacing": "0.08em", "textTransform": "uppercase",
                           "color": C["muted"], "border": "none", "padding": "14px"},
                    selected_style={"fontFamily": VF, "fontSize": "12px", "fontWeight": "700",
                           "letterSpacing": "0.08em", "textTransform": "uppercase",
                           "color": C["navy"], "borderTop": "3px solid " + C["navy"],
                           "borderBottom": "none", "padding": "14px"}),
            dcc.Tab(label="Liquidity & Stress", value="liquidity",
                    style={"fontFamily": VF, "fontSize": "12px", "fontWeight": "700",
                           "letterSpacing": "0.08em", "textTransform": "uppercase",
                           "color": C["muted"], "border": "none", "padding": "14px"},
                    selected_style={"fontFamily": VF, "fontSize": "12px", "fontWeight": "700",
                           "letterSpacing": "0.08em", "textTransform": "uppercase",
                           "color": C["navy"], "borderTop": "3px solid " + C["navy"],
                           "borderBottom": "none", "padding": "14px"}),
            dcc.Tab(label="Portfolio Advisor", value="advisor",
                    style={"fontFamily": VF, "fontSize": "12px", "fontWeight": "700",
                           "letterSpacing": "0.08em", "textTransform": "uppercase",
                           "color": C["muted"], "border": "none", "padding": "14px"},
                    selected_style={"fontFamily": VF, "fontSize": "12px", "fontWeight": "700",
                           "letterSpacing": "0.08em", "textTransform": "uppercase",
                           "color": C["rose"], "borderTop": "3px solid " + C["rose"],
                           "borderBottom": "none", "padding": "14px"}),
            dcc.Tab(label="Library", value="library",
                    style={"fontFamily": VF, "fontSize": "12px", "fontWeight": "700",
                           "letterSpacing": "0.08em", "textTransform": "uppercase",
                           "color": C["muted"], "border": "none", "padding": "14px"},
                    selected_style={"fontFamily": VF, "fontSize": "12px", "fontWeight": "700",
                           "letterSpacing": "0.08em", "textTransform": "uppercase",
                           "color": C["navy"], "borderTop": "3px solid " + C["navy"],
                           "borderBottom": "none", "padding": "14px"}),
            dcc.Tab(label="Knowledge", value="knowledge",
                    style={"fontFamily": VF, "fontSize": "12px", "fontWeight": "700",
                           "letterSpacing": "0.08em", "textTransform": "uppercase",
                           "color": C["muted"], "border": "none", "padding": "14px"},
                    selected_style={"fontFamily": VF, "fontSize": "12px", "fontWeight": "700",
                           "letterSpacing": "0.08em", "textTransform": "uppercase",
                           "color": C["navy"], "borderTop": "3px solid " + C["navy"],
                           "borderBottom": "none", "padding": "14px"}),
        ]),
    ], style={"maxWidth": "1200px", "margin": "0 auto", "padding": "20px 48px 0"}),

    # Both panels stay mounted; the tab callback toggles visibility so output persists.
    html.Div([
        html.Div(id="panel-issuer",     children=tab_panel_issuer()),
        html.Div(id="panel-prospectus", children=tab_panel_prospectus(), style={"display": "none"}),
        html.Div(id="panel-market",     children=tab_panel_market(), style={"display": "none"}),
        html.Div(id="panel-liquidity",  children=tab_panel_liquidity(), style={"display": "none"}),
        html.Div(id="panel-advisor",    children=tab_panel_advisor(), style={"display": "none"}),
        html.Div(id="panel-library",    children=tab_panel_library(), style={"display": "none"}),
        html.Div(id="panel-knowledge",  children=tab_panel_knowledge(), style={"display": "none"}),
    ], style={"maxWidth":"1200px","margin":"0 auto","padding":"12px 48px 80px"}),

], style={"minHeight":"100vh","background":f"linear-gradient(155deg, #E8EDF2 0%, {C['bg']} 55%, #EEF0EC 100%)","fontFamily":VF})

# ── Callbacks ─────────────────────────────────────────────────────────────────

@app.callback(
    Output("panel-issuer",     "style"),
    Output("panel-prospectus", "style"),
    Output("panel-market",     "style"),
    Output("panel-liquidity",  "style"),
    Output("panel-advisor",    "style"),
    Output("panel-library",    "style"),
    Output("panel-knowledge",  "style"),
    Input("tabs", "value"))
def switch_tab(tab):
    hide, show = {"display": "none"}, {"display": "block"}
    panels = ["issuer", "prospectus", "market", "liquidity", "advisor", "library", "knowledge"]
    active = tab if tab in panels else "issuer"
    return [show if p == active else hide for p in panels]


@app.callback(
    Output("lib-display", "children"),
    Output("cmp-a", "options"),
    Output("cmp-b", "options"),
    Input("tabs", "value"),
    Input("btn-lib-refresh", "n_clicks"))
def refresh_library(tab, _n):
    if tab != "library":
        return dash.no_update, dash.no_update, dash.no_update
    opts = history_options(None)
    return render_library(), opts, opts


@app.callback(
    Output("cmp-display", "children"),
    Input("btn-compare", "n_clicks"),
    State("cmp-a", "value"),
    State("cmp-b", "value"),
    prevent_initial_call=True)
def do_compare(_, a, b):
    if not a or not b:
        return html.Div("Select two analyses, then press Compare.", style={
            "fontSize": "12px", "color": C["muted"], "fontFamily": VF})
    return build_compare(analysis_db.get_analysis(a), analysis_db.get_analysis(b))


@app.callback(
    Output("knowledge-select", "options"),
    Input("tabs", "value"),
    Input("btn-know-save", "n_clicks"),
    Input("btn-know-delete", "n_clicks"))
def refresh_knowledge_options(tab, _s, _d):
    return _knowledge_options()


@app.callback(
    Output("know-title", "value"),
    Output("know-scope", "value"),
    Output("know-body",  "value"),
    Input("knowledge-select", "value"))
def load_knowledge(fid):
    if not fid or fid == "__new__":
        return "", ["prospectus"], ""
    e = knowledge.get_entry(fid) or {}
    scopes = [s.strip() for s in re.split(r"[,\s]+", e.get("scope", "")) if s.strip()]
    return e.get("title", ""), scopes, e.get("body", "")


@app.callback(
    Output("know-status",      "children"),
    Output("knowledge-select", "value"),
    Input("btn-know-save",     "n_clicks"),
    State("knowledge-select",  "value"),
    State("know-title",        "value"),
    State("know-scope",        "value"),
    State("know-body",         "value"),
    prevent_initial_call=True)
def save_knowledge(_, fid, title, scope, body):
    if not title or not title.strip():
        return "Enter a title first.", dash.no_update
    new_fid = knowledge.save_entry(None if fid == "__new__" else fid,
                                   title.strip(), ", ".join(scope or []), body or "")
    if not new_fid:
        return "Save failed.", dash.no_update
    return "Saved.", new_fid


@app.callback(
    Output("know-status",      "children", allow_duplicate=True),
    Output("knowledge-select", "value",    allow_duplicate=True),
    Input("btn-know-delete",   "n_clicks"),
    State("knowledge-select",  "value"),
    prevent_initial_call=True)
def delete_knowledge(_, fid):
    if not fid or fid == "__new__":
        return "Nothing selected.", dash.no_update
    knowledge.delete_entry(fid)
    return "Deleted.", "__new__"


@app.callback(
    Output("mkt-output", "children"),
    Output("mkt-status", "children"),
    Input("btn-mkt-run", "n_clicks"),
    State("mkt-segment", "value"),
    State("mkt-region",  "value"),
    prevent_initial_call=True)
def run_mkt(_, segment, region):
    try:
        result = run_market_report(segment, region)
        analysis_db.save_analysis(
            "market", "market",
            (result.get("_segment", "") + " " + result.get("_region", "")).strip(), result)
        return build_market_output(result), ""
    except Exception as ex:
        return build_market_output({"error": str(ex)}), ""


@app.callback(
    Output("liq-job-store", "data"),
    Output("liq-poll",      "disabled"),
    Output("liq-status",    "children"),
    Output("liq-output",    "children"),
    Input("btn-liq-run",    "n_clicks"),
    State("liq-company",    "value"),
    State("liq-mode",       "value"),
    prevent_initial_call=True)
def start_liq(_, company, mode):
    if not company or not company.strip():
        return dash.no_update, True, "Please enter an issuer.", dash.no_update
    jid = jobs.start(_liquidity_job, company.strip(), mode, False)
    return {"jid": jid, "company": company.strip(), "mode": mode}, False, "Starting", html.Div()


@app.callback(
    Output("liq-output", "children", allow_duplicate=True),
    Output("liq-store",  "data"),
    Output("liq-status", "children", allow_duplicate=True),
    Output("liq-poll",   "disabled", allow_duplicate=True),
    Input("liq-poll",    "n_intervals"),
    State("liq-job-store", "data"),
    prevent_initial_call=True)
def poll_liq(_, job):
    if not job or not job.get("jid"):
        return dash.no_update, dash.no_update, dash.no_update, True
    st = jobs.poll(job["jid"])
    if not st:
        return dash.no_update, dash.no_update, dash.no_update, True
    if st["status"] == "running":
        return dash.no_update, dash.no_update, "Working: " + st["progress"], dash.no_update
    jobs.cleanup(job["jid"])
    if st["status"] == "error":
        return build_liquidity_panel({"error": st["error"]}), dash.no_update, "", True
    data = st["result"] or {}
    mode = data.get("_liqmode", job.get("mode", "corp"))
    store = {"mode": mode, "company": data.get("company", ""),
             "commentary": data.get("commentary", ""), "history": data.get("history") or {},
             "inputs": {f["key"]: data.get(f["key"]) for f in liquidity.LIQ_INPUTS[mode]},
             "akeys": [a["key"] for a in liquidity.LIQ_ASSUMPTIONS[mode]]}
    tag = "  (from cache)" if data.get("_cached") else ""
    return build_liquidity_panel(data), store, "Done" + tag, True


def _collect_inputs(values, ids, base):
    inp = dict(base or {})
    lists = {}
    for v, i in zip(values, ids):
        idx = i["index"]
        if "#" in idx:
            k, n = idx.split("#")
            lists.setdefault(k, {})[int(n)] = v
        else:
            inp[idx] = v
    for k, d in lists.items():
        inp[k] = [d.get(j, 0) for j in range(max(d) + 1)]
    return inp


@app.callback(
    Output("liq-results", "children"),
    Input({"type": "liq-slider", "index": ALL}, "value"),
    Input("btn-liq-recompute", "n_clicks"),
    State({"type": "liq-slider", "index": ALL}, "id"),
    State({"type": "liq-input", "index": ALL}, "value"),
    State({"type": "liq-input", "index": ALL}, "id"),
    State("liq-store", "data"),
    prevent_initial_call=True)
def update_liq(svalues, _n, sids, ivalues, iids, store):
    if not store or not svalues:
        return dash.no_update
    akeys = store.get("akeys", [])
    a = {}
    for v, i in zip(svalues, sids):
        idx = i["index"]
        if 0 <= idx < len(akeys):
            a[akeys[idx]] = v
    inputs = _collect_inputs(ivalues, iids, store.get("inputs", {}))
    return build_liquidity_results(store["mode"], inputs, a, history=store.get("history"))


@app.callback(
    Output("liq-pdf-download", "data"),
    Output("liq-pdf-status",   "children"),
    Input("btn-liq-pdf",       "n_clicks"),
    State({"type": "liq-slider", "index": ALL}, "value"),
    State({"type": "liq-slider", "index": ALL}, "id"),
    State({"type": "liq-input",  "index": ALL}, "value"),
    State({"type": "liq-input",  "index": ALL}, "id"),
    State("liq-store", "data"),
    prevent_initial_call=True)
def download_liq_pdf(n, svalues, sids, ivalues, iids, store):
    if not n or not store:
        return dash.no_update, "No model available."
    try:
        mode = store["mode"]
        akeys = store.get("akeys", [])
        a = {}
        for v, i in zip(svalues, sids):
            idx = i["index"]
            if 0 <= idx < len(akeys):
                a[akeys[idx]] = v
        inputs = _collect_inputs(ivalues, iids, store.get("inputs", {}))
        res = liquidity.project(mode, inputs, a, t0=datetime.now().year, history=store.get("history"))
        company = store.get("company", "issuer")
        pdf = gen_liquidity_pdf(mode, company, store.get("commentary", ""), res, a)
        today = datetime.now().strftime("%Y%m%d")
        safe_id = re.sub(r'[<>:"/\\|?*\s/]+', '_', company).strip('_') or "issuer"
        fname = today + "_" + safe_id + "_liquidity.pdf"
        folder = r"Q:\00_pm\1_research\3_issuerCreditResearch"
        if os.path.isdir(folder):
            import subprocess
            path = os.path.join(folder, fname)
            with open(path, "wb") as fh:
                fh.write(pdf)
            subprocess.Popen(["explorer", folder])
            return dash.no_update, "Saved: " + path
        return dcc.send_bytes(pdf, filename=fname), "Download started."
    except Exception as ex:
        return dash.no_update, "Error: " + str(ex)


@app.callback(
    Output("company-input", "placeholder"),
    Input("mode-dropdown",  "value"))
def update_placeholder(mode):
    return PLACEHOLDER.get(mode, "Enter issuer...")


@app.callback(
    Output("job-store",    "data"),
    Output("job-poll",     "disabled"),
    Output("status-msg",   "children"),
    Output("output",       "children"),
    Output("chat-section", "style"),
    Input("btn-run",       "n_clicks"),
    State("company-input", "value"),
    State("mode-dropdown", "value"),
    State("force-refresh", "value"),
    prevent_initial_call=True)
def start_run(_, company, mode, force):
    if not company or not company.strip():
        return dash.no_update, True, "Please enter an issuer.", dash.no_update, dash.no_update
    jid = jobs.start(_issuer_job, company.strip(), mode, bool(force))
    return ({"jid": jid, "company": company.strip(), "mode": mode}, False,
            "Starting", html.Div(), {"display": "none"})


@app.callback(
    Output("output",            "children", allow_duplicate=True),
    Output("result-store",      "data"),
    Output("status-msg",        "children", allow_duplicate=True),
    Output("chat-section",      "style",    allow_duplicate=True),
    Output("job-poll",          "disabled", allow_duplicate=True),
    Output("history-dropdown",  "options"),
    Input("job-poll",           "n_intervals"),
    State("job-store",          "data"),
    prevent_initial_call=True)
def poll_run(_, job):
    if not job or not job.get("jid"):
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, True, dash.no_update
    st = jobs.poll(job["jid"])
    if not st:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, True, dash.no_update
    if st["status"] == "running":
        return (dash.no_update, dash.no_update, "Working: " + st["progress"],
                dash.no_update, dash.no_update, dash.no_update)
    jobs.cleanup(job["jid"])
    mode = job.get("mode", "corp")
    if st["status"] == "error":
        err = {"error": st["error"], "company": job.get("company", ""), "_mode": mode}
        return build_output(err, mode), err, "", dash.no_update, True, dash.no_update
    result = st["result"] or {}
    mode = result.get("_mode", mode)
    tag = "  (from cache)" if result.get("_cached") else ""
    return (build_output(result, mode), result, "Done" + tag,
            {"display": "block"}, True, history_options())


@app.callback(
    Output("output",       "children", allow_duplicate=True),
    Output("result-store", "data",     allow_duplicate=True),
    Output("status-msg",   "children", allow_duplicate=True),
    Output("chat-section", "style",    allow_duplicate=True),
    Input("history-dropdown", "value"),
    prevent_initial_call=True)
def load_history(aid):
    if not aid:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    data = analysis_db.get_analysis(aid)
    if not data:
        return dash.no_update, dash.no_update, "Analysis not found.", dash.no_update
    mode = data.get("_mode", "corp")
    return build_output(data, mode), data, "Loaded from history.", {"display": "block"}


@app.callback(
    Output("pdf-download", "data"),
    Output("pdf-status",   "children"),
    Input("btn-pdf",       "n_clicks"),
    State("result-store",  "data"),
    prevent_initial_call=True)
def download_pdf(n_clicks, result):
    if not n_clicks or not result or result.get("error"):
        return dash.no_update, "No report available."
    try:
        mode   = result.get("_mode", "corp")
        pdf    = gen_pdf(result, mode)
        today  = datetime.now().strftime("%Y%m%d")
        raw_id = (result.get("ticker") or result.get("company", "report")).strip()
        # Strip all chars invalid in Windows filenames (incl. / which acts as path separator)
        safe_id = re.sub(r'[<>:"/\\|?*\s/]+', '_', raw_id).strip('_')
        fname  = today + "_" + safe_id + ".pdf"
        folder = r"Q:\00_pm\1_research\3_issuerCreditResearch"
        if os.path.isdir(folder):
            import subprocess
            path = os.path.join(folder, fname)
            with open(path, "wb") as fh:
                fh.write(pdf)
            subprocess.Popen(["explorer", folder])
            return dash.no_update, "Saved: " + path
        return dcc.send_bytes(pdf, filename=fname), "Download started."
    except Exception as ex:
        return dash.no_update, "Error: " + str(ex)


def chat_bubble(role, text):
    is_user = role == "user"
    return html.Div([
        html.Div(
            "You" if is_user else "Analyst",
            style={
                "fontSize":      "9px",
                "fontWeight":    "700",
                "color":         C["rose"] if is_user else C["navy"],
                "fontFamily":    VF,
                "letterSpacing": "0.12em",
                "textTransform": "uppercase",
                "marginBottom":  "4px",
            }
        ),
        html.Div(text, style={
            "fontSize":     "13px",
            "lineHeight":   "1.8",
            "color":        C["ink"],
            "fontFamily":   VF,
            "whiteSpace":   "pre-wrap",
            "background":   C["accent"] + "33" if is_user else C["bg"],
            "borderLeft":   "3px solid " + (C["rose"] if is_user else C["accent"]),
            "padding":      "10px 16px",
            "borderRadius": "0 2px 2px 0",
        }),
    ], style={"marginBottom": "18px"})


@app.callback(
    Output("chat-display",  "children"),
    Output("chat-history",  "data"),
    Output("chat-status",   "children"),
    Output("chat-input",    "value"),
    Input("btn-chat",       "n_clicks"),
    State("chat-input",     "value"),
    State("chat-history",   "data"),
    State("result-store",   "data"),
    prevent_initial_call=True)
def chat(_, question, history, result):
    if not question or not question.strip():
        return dash.no_update, dash.no_update, "Please enter a question.", dash.no_update
    if not result or result.get("error"):
        return dash.no_update, dash.no_update, "Please run an analysis first.", dash.no_update

    company = result.get("company", "this issuer")
    context = json.dumps(result, ensure_ascii=False, indent=2)

    history = history or []
    messages = [
        {
            "role": "user",
            "content": f"""You are a Managing Director in Credit Research at a leading fixed income house. Here is the full credit analysis for {company}:

{context}

You answer follow-up questions on the basis of this analysis. Style rules:
- Institutional English: factual, precise, no filler words
- No emojis, no bullet symbols, no markdown bold
- You always state numbers with a unit and a year
- You give direct judgments, no hedging phrases such as "could", "possibly", "it remains to be seen"
- You prefer flowing prose; you use lists only when structurally necessary
- Tone: like an experienced analyst in an investor meeting, not like a chatbot"""
        },
        {"role": "assistant", "content": "Understood."},
    ]
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": question.strip()})

    try:
        client  = anthropic.Anthropic(api_key=API_KEY, timeout=600)
        resp    = client.messages.create(model=MODEL_CHAT, max_tokens=1500, messages=messages)
        answer  = resp.content[0].text.strip()
        history.append({"role": "user",      "content": question.strip()})
        history.append({"role": "assistant", "content": answer})
        bubbles = [chat_bubble(m["role"], m["content"]) for m in history]
        return bubbles, history, "", ""
    except Exception as ex:
        return dash.no_update, dash.no_update, "Error: " + str(ex), dash.no_update


# ── Portfolio Advisor Callbacks ───────────────────────────────────────────────

@app.callback(
    Output("adv-portfolio-status", "children"),
    Input("btn-reload", "n_clicks"),
    prevent_initial_call=True)
def reload_portfolio(_):
    _, headline = load_portfolio(force=True)
    return headline


@app.callback(
    Output("adv-files",         "data"),
    Output("adv-files-display", "children"),
    Input("adv-upload",         "contents"),
    State("adv-upload",         "filename"),
    prevent_initial_call=True)
def stage_files(contents, filenames):
    if not contents:
        return [], ""
    if not isinstance(contents, list):
        contents, filenames = [contents], [filenames]
    files = [{"name": n, "data": c} for n, c in zip(filenames, contents)]
    label = "Attached: " + "  ·  ".join(f["name"] for f in files)
    return files, label


@app.callback(
    Output("adv-display", "children"),
    Output("adv-history", "data"),
    Output("adv-status",  "children"),
    Output("adv-input",   "value"),
    Output("adv-files",   "data", allow_duplicate=True),
    Output("adv-files-display", "children", allow_duplicate=True),
    Input("btn-adv",      "n_clicks"),
    State("adv-input",    "value"),
    State("adv-files",    "data"),
    State("adv-history",  "data"),
    prevent_initial_call=True)
def advisor(_, prompt, files, history):
    if not prompt or not prompt.strip():
        return dash.no_update, dash.no_update, "Please enter a prompt.", dash.no_update, dash.no_update, dash.no_update
    try:
        answer, user_record = run_advisor(prompt.strip(), files, history)
        if answer is None:
            return dash.no_update, dash.no_update, user_record, dash.no_update, dash.no_update, dash.no_update
        history = history or []
        history.append({"role": "user",      "content": user_record})
        history.append({"role": "assistant", "content": answer})
        bubbles = [chat_bubble(m["role"], m["content"]) for m in history]
        return bubbles, history, "", "", [], ""
    except Exception as ex:
        return dash.no_update, dash.no_update, "Error: " + str(ex), dash.no_update, dash.no_update, dash.no_update


# ── Prospectus & Recovery Callbacks ───────────────────────────────────────────

@app.callback(
    Output("prosp-files",         "data"),
    Output("prosp-files-display", "children"),
    Input("prosp-upload",         "contents"),
    State("prosp-upload",         "filename"),
    prevent_initial_call=True)
def stage_prosp_files(contents, filenames):
    if not contents:
        return [], ""
    if not isinstance(contents, list):
        contents, filenames = [contents], [filenames]
    files = [{"name": n, "data": c} for n, c in zip(filenames, contents)]
    label = "Attached: " + "  ·  ".join(f["name"] for f in files)
    return files, label


@app.callback(
    Output("prosp-output",       "children"),
    Output("prosp-result-store", "data"),
    Output("prosp-status",       "children"),
    Input("btn-prosp-run",       "n_clicks"),
    State("prosp-issuer",        "value"),
    State("prosp-files",         "data"),
    prevent_initial_call=True)
def run_prosp(_, issuer, files):
    if (not issuer or not issuer.strip()) and not files:
        return dash.no_update, dash.no_update, "Please enter an issuer or attach a prospectus."
    try:
        result = run_prospectus_analysis(issuer, files)
        analysis_db.save_analysis("prospectus", "prosp", result.get("company", issuer or ""), result)
        return build_prospectus_output(result), result, ""
    except Exception as ex:
        err = {"error": str(ex), "company": (issuer or "").strip()}
        return build_prospectus_output(err), err, ""


@app.callback(
    Output("prosp-pdf-download", "data"),
    Output("prosp-pdf-status",   "children"),
    Input("btn-prosp-pdf",       "n_clicks"),
    State("prosp-result-store",  "data"),
    prevent_initial_call=True)
def download_prosp_pdf(n_clicks, result):
    if not n_clicks or not result or result.get("error"):
        return dash.no_update, "No report available."
    try:
        pdf    = gen_prospectus_pdf(result)
        today  = datetime.now().strftime("%Y%m%d")
        raw_id = (result.get("company", "prospectus")).strip()
        safe_id = re.sub(r'[<>:"/\\|?*\s/]+', '_', raw_id).strip('_')
        fname  = today + "_" + safe_id + "_prospectus.pdf"
        folder = r"Q:\00_pm\1_research\3_issuerCreditResearch"
        if os.path.isdir(folder):
            import subprocess
            path = os.path.join(folder, fname)
            with open(path, "wb") as fh:
                fh.write(pdf)
            subprocess.Popen(["explorer", folder])
            return dash.no_update, "Saved: " + path
        return dcc.send_bytes(pdf, filename=fname), "Download started."
    except Exception as ex:
        return dash.no_update, "Error: " + str(ex)


if __name__ == "__main__":
    app.run(debug=os.environ.get("CREDIT_DEBUG", "0") == "1",
            host="127.0.0.1", port=8051, use_reloader=False, threaded=True)
