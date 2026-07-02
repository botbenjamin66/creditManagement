import sys, subprocess
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output
sys.path.insert(0, r"S:\benjaminSuermann\3_env")
import pyDashDesign as D
from trends_index import BASKETS, DATA, HERE

C, P = D.COLORS, D.CHART_PALETTE
TERMS = [t for v in BASKETS.values() for t in v]
CLR = {b: P[i % len(P)] for i, b in enumerate(BASKETS)}

def load():
    return pd.read_csv(DATA, index_col=0, parse_dates=True)

def agg(df):
    return pd.DataFrame({b: df[ts].mean(axis=1) for b, ts in BASKETS.items()}, index=df.index)

def fig_agg(a):
    f = go.Figure()
    f.add_hline(y=0, line_color=C["border"], line_width=1)
    for b in a.columns:
        f.add_scatter(x=a.index, y=a[b], mode="lines", name=b, line=dict(color=CLR[b], width=2))
    return D.style_figure(f, height=380, legend=True)

def fig_term(df, t):
    b = next(k for k, v in BASKETS.items() if t in v)
    f = go.Figure()
    f.add_hline(y=0, line_color=C["border"], line_width=1)
    f.add_scatter(x=df.index, y=df[t], mode="lines", name=t, line=dict(color=CLR[b], width=2.5),
        fill="tozeroy", fillcolor="rgba(92,114,133,.08)")
    return D.style_figure(f, height=300)

app = Dash(__name__)
app.title = "nordIX · Sentiment"
app.index_string = D.index_string()

app.layout = D.page([
    D.brand_header("Search Sentiment", "Google Trends · 6 Baskets · 2 Years · Z-Scored"),
    D.container([
        html.Div([
            html.Div(id="msg", style={**D.LABEL_STYLE, "fontSize": 12}),
            html.Button("↻ Refresh", id="refresh", n_clicks=0, style={**D.BUTTON_STYLE, "marginLeft": 18}),
        ], style={"display": "flex", "alignItems": "center", "justifyContent": "flex-end", "margin": "26px 0 4px"}),
        D.section("Latest Reading"),
        html.Div(id="cards", style={"display": "flex", "gap": 14, "flexWrap": "wrap"}),
        D.section("Aggregate · Basket Means"),
        D.panel(dcc.Graph(id="g-agg", config={"displayModeBar": False})),
        D.section("Single Term"),
        D.panel([
            dcc.Dropdown(id="term", clearable=False, value=TERMS[0], style={"marginBottom": 10},
                options=[{"label": f"{b} · {t}", "value": t} for b, v in BASKETS.items() for t in v]),
            dcc.Graph(id="g-term", config={"displayModeBar": False}),
        ]),
        D.section("Matrix · Terms × Weeks"),
        D.panel(D.data_table(id="matrix",
            style_data_conditional=[{"if": {"column_id": "date"}, "fontWeight": 600, "color": C["primary"]}]),
            pad="10px"),
    ]),
])

@app.callback(Output("cards", "children"), Output("g-agg", "figure"), Output("matrix", "data"),
    Output("matrix", "columns"), Output("msg", "children"), Input("refresh", "n_clicks"))
def refresh(n):
    if n:
        subprocess.run([sys.executable, str(HERE / "trends_index.py")], check=False)
    if not DATA.exists():
        return [], go.Figure(), [], [], "no data — run trends_index.py"
    df = load(); a = agg(df)
    t = df.round(2).sort_index(ascending=False)
    t.index = t.index.date.astype(str)
    t = t.reset_index().rename(columns={"index": "date"})
    return ([D.kpi_card(b, a[b].iloc[-1]) for b in a.columns], fig_agg(a), t.to_dict("records"),
        [{"name": c, "id": c} for c in t.columns], f"{len(df)} weeks · last {df.index[-1].date()}")

@app.callback(Output("g-term", "figure"), Input("term", "value"), Input("refresh", "n_clicks"))
def term_chart(t, n):
    return fig_term(load(), t) if DATA.exists() else go.Figure()

if __name__ == "__main__":
    app.run(debug=True)
