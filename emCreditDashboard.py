import sys, subprocess
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, dcc, html, dash_table, Input, Output
from trends_index import BASKETS, DATA, HERE

TERMS = [t for v in BASKETS.values() for t in v]
BG, CARD, LINE = "#0c1018", "#141a24", "#243040"
TX, MUTE, ACCENT = "#e8edf4", "#7d8aa0", "#19c2c2"
FONT = "Inter, 'Segoe UI', system-ui, sans-serif"
PALETTE = [ACCENT, "#34d399", "#f87171", "#f59e0b", "#a78bfa", "#60a5fa"]
COLOR = {b: PALETTE[i % len(PALETTE)] for i, b in enumerate(BASKETS)}

def load():
    return pd.read_csv(DATA, index_col=0, parse_dates=True)

def agg(df):
    return pd.DataFrame({b: df[ts].mean(axis=1) for b, ts in BASKETS.items()}, index=df.index)

def base(fig, title, h):
    fig.update_layout(
        title=dict(text=title, font=dict(size=15, color=TX)),
        height=h, margin=dict(t=46, b=24, l=12, r=12),
        paper_bgcolor=CARD, plot_bgcolor=CARD, font=dict(color=MUTE, family=FONT),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=1.14, x=0),
        xaxis=dict(gridcolor=LINE, zeroline=False), yaxis=dict(gridcolor=LINE, zeroline=False))
    return fig

def fig_agg(a):
    f = go.Figure()
    f.add_hline(y=0, line_color=LINE)
    for b in a.columns:
        f.add_scatter(x=a.index, y=a[b], mode="lines", line=dict(color=COLOR[b], width=2), name=b)
    return base(f, "Baskets aggregated  ·  mean z-score", 380)

def fig_term(df, term):
    b = next(k for k, v in BASKETS.items() if term in v)
    f = go.Figure()
    f.add_hline(y=0, line_color=LINE)
    f.add_scatter(x=df.index, y=df[term], mode="lines", line=dict(color=COLOR[b], width=2.5),
                  fill="tozeroy", fillcolor="rgba(25,194,194,.07)")
    return base(f, f"{b}  ·  {term}  ·  z-score", 320)

def card(label, val, color):
    return html.Div([
        html.Div(f"{val:+.2f}", style={"fontSize": 24, "fontWeight": 600, "color": color}),
        html.Div(label.upper(), style={"fontSize": 10, "letterSpacing": "1.2px", "color": MUTE, "marginTop": 4}),
    ], style={"flex": 1, "padding": "14px 16px", "background": CARD, "borderRadius": 10,
              "border": f"1px solid {LINE}", "borderTop": f"2px solid {color}"})

def panel(child, mt=18):
    return html.Div(child, style={"background": CARD, "borderRadius": 10,
                                   "border": f"1px solid {LINE}", "padding": 8, "marginTop": mt})

app = Dash(__name__)
app.title = "nordIX · Sentiment"

app.layout = html.Div([
    html.Div([
        html.Div([html.Span("nord", style={"color": TX}), html.Span("IX", style={"color": ACCENT})],
                 style={"fontSize": 22, "fontWeight": 700, "letterSpacing": "1px"}),
        html.Div("SEARCH SENTIMENT", style={"color": MUTE, "fontSize": 12, "letterSpacing": "2px"}),
        html.Button("↻ Refresh", id="refresh", n_clicks=0,
                    style={"marginLeft": "auto", "background": "transparent", "color": ACCENT,
                           "border": f"1px solid {ACCENT}", "borderRadius": 8, "padding": "8px 18px",
                           "cursor": "pointer", "fontFamily": FONT}),
    ], style={"display": "flex", "alignItems": "center", "gap": "16px",
              "padding": "8px 4px 20px", "borderBottom": f"1px solid {LINE}"}),
    html.H1("Search Sentiment · 6 baskets", style={"fontWeight": 600, "fontSize": 28, "margin": "24px 0 4px"}),
    html.Div("Google Trends · last 2 years · z-scored", style={"color": MUTE, "marginBottom": 18}),
    html.Div(id="cards", style={"display": "flex", "gap": "12px", "flexWrap": "wrap"}),
    panel(dcc.Graph(id="g-agg", config={"displayModeBar": False})),
    panel([
        dcc.Dropdown(id="term", options=[{"label": f"{b} · {t}", "value": t}
                                          for b, v in BASKETS.items() for t in v],
                     value=TERMS[0], clearable=False,
                     style={"background": BG, "color": "#000", "marginBottom": 6}),
        dcc.Graph(id="g-term", config={"displayModeBar": False}),
    ]),
    html.Div("Matrix · all terms × weeks (z-score)", style={"color": MUTE, "margin": "26px 0 8px",
                                                            "fontSize": 13, "letterSpacing": "1px"}),
    panel(dash_table.DataTable(
        id="matrix", sort_action="native", fixed_rows={"headers": True}, fixed_columns={"headers": True},
        style_table={"overflowX": "auto", "overflowY": "auto", "maxHeight": 460, "minWidth": "100%"},
        style_header={"backgroundColor": "#10151e", "color": TX, "fontWeight": 600,
                      "border": f"1px solid {LINE}", "fontFamily": FONT},
        style_cell={"backgroundColor": BG, "color": MUTE, "border": f"1px solid {LINE}",
                    "fontSize": 11, "padding": "4px 8px", "fontFamily": FONT, "minWidth": 70},
        style_cell_conditional=[{"if": {"column_id": "date"}, "minWidth": 90,
                                 "color": TX, "backgroundColor": "#10151e"}],
    ), mt=0),
    html.Div(id="msg", style={"color": MUTE, "fontSize": 12, "textAlign": "right", "marginTop": 14}),
], style={"maxWidth": 1180, "margin": "0 auto", "padding": "32px 24px 60px", "fontFamily": FONT, "color": TX})

app.index_string = """<!DOCTYPE html><html><head>{%metas%}<title>{%title%}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
{%favicon%}{%css%}<style>body{margin:0;background:#0c1018}</style></head>
<body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>"""

@app.callback(
    Output("cards", "children"), Output("g-agg", "figure"),
    Output("matrix", "data"), Output("matrix", "columns"), Output("msg", "children"),
    Input("refresh", "n_clicks"))
def refresh(n):
    if n:
        subprocess.run([sys.executable, str(HERE / "trends_index.py")], check=False)
    if not DATA.exists():
        return [], go.Figure(), [], [], "No data — run python trends_index.py"
    df = load()
    a = agg(df)
    cards = [card(b, a[b].iloc[-1], COLOR[b]) for b in a.columns]
    t = df.round(2).sort_index(ascending=False)
    t.index = t.index.date.astype(str)
    t = t.reset_index().rename(columns={"index": "date"})
    cols = [{"name": c, "id": c} for c in t.columns]
    return cards, fig_agg(a), t.to_dict("records"), cols, \
        f"{len(df)} weeks · {len(TERMS)} terms · last {df.index[-1].date()}"

@app.callback(Output("g-term", "figure"), Input("term", "value"), Input("refresh", "n_clicks"))
def term_chart(term, n):
    if not DATA.exists():
        return go.Figure()
    return fig_term(load(), term)

if __name__ == "__main__":
    app.run(debug=True)
