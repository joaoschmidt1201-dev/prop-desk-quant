"""
===============================================================================
 IC7 VIEWER — Iron Condor 7DTE Trade Auditor  |  v2
 Prop Desk Quant | Senior Quant Developer
===============================================================================
 Dashboard Streamlit para auditoria visual e análise de performance do IC7.

 ABAS:
   📋 Trade Inspector   — payoff chart, estrutura de strikes, P&L breakdown
   📈 Performance       — equity curve, drawdown, heatmap, IV vs Realized

 COMO RODAR:
     streamlit run scripts/ic7_viewer.py
===============================================================================
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

TRADE_LOG_PATH = Path(__file__).resolve().parent.parent / "reports" / "ic7_backtest" / "trade_log.csv"
NDX_MULTIPLIER = 100

# Paleta de cores
C = dict(
    bg         = "#0d1117",
    panel      = "#161b22",
    border     = "#30363d",
    green      = "#00c896",
    red        = "#ff4d4d",
    yellow     = "#f0e040",
    blue       = "#58a6ff",
    purple     = "#d2a8ff",
    orange     = "#ffa657",
    white      = "#e6edf3",
    dim        = "#8b949e",
)

# ─────────────────────────────────────────────────────────────────────────────
# STREAMLIT — LAYOUT E TEMA GLOBAL
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title = "IC7 Trade Auditor | NDX",
    page_icon  = "📊",
    layout     = "wide",
    initial_sidebar_state = "expanded",
)

st.markdown(f"""
<style>
    /* Background global */
    .stApp {{ background-color: {C['bg']}; color: {C['white']}; }}
    [data-testid="stSidebar"] {{ background-color: {C['panel']}; }}

    /* Metric cards */
    [data-testid="stMetric"] {{
        background-color: {C['panel']};
        border: 1px solid {C['border']};
        border-radius: 8px;
        padding: 12px 16px;
    }}
    [data-testid="stMetricLabel"]  {{ color: {C['dim']} !important; font-size: 12px; }}
    [data-testid="stMetricValue"]  {{ color: {C['white']} !important; font-size: 20px; font-weight: bold; }}
    [data-testid="stMetricDelta"]  {{ font-size: 13px; }}

    /* Selectbox */
    [data-testid="stSelectbox"] label {{ color: {C['dim']}; font-size: 13px; }}

    /* Dividers */
    hr {{ border-color: {C['border']}; margin: 8px 0; }}

    /* Strike badge */
    .strike-badge {{
        display: inline-block;
        background: {C['panel']};
        border: 1px solid {C['border']};
        border-radius: 6px;
        padding: 4px 10px;
        font-family: monospace;
        font-size: 13px;
        color: {C['white']};
        margin: 2px;
    }}
    .strike-short {{ border-color: {C['orange']}; color: {C['orange']}; }}
    .strike-long  {{ border-color: {C['blue']};   color: {C['blue']};   }}

    /* Result badge */
    .badge-win      {{ background:{C['green']}22; border:1px solid {C['green']}; color:{C['green']};
                       border-radius:6px; padding:3px 12px; font-weight:bold; font-size:13px; }}
    .badge-loss     {{ background:{C['red']}22;   border:1px solid {C['red']};   color:{C['red']};
                       border-radius:6px; padding:3px 12px; font-weight:bold; font-size:13px; }}
    .badge-maxloss  {{ background:#ff000033; border:1px solid #ff0000; color:#ff6b6b;
                       border-radius:6px; padding:3px 12px; font-weight:bold; font-size:13px; }}

    /* Section headers */
    .section-title {{
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        color: {C['dim']};
        margin-bottom: 8px;
    }}

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {{
        background-color: {C['panel']};
        border-bottom: 1px solid {C['border']};
        gap: 4px;
    }}
    .stTabs [data-baseweb="tab"] {{
        background-color: transparent;
        color: {C['dim']};
        font-family: monospace;
        font-size: 13px;
        padding: 8px 20px;
        border-radius: 6px 6px 0 0;
    }}
    .stTabs [aria-selected="true"] {{
        background-color: {C['bg']} !important;
        color: {C['white']} !important;
        border-bottom: 2px solid {C['blue']} !important;
    }}
    .stTabs [data-baseweb="tab-panel"] {{
        padding-top: 20px;
    }}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# FUNÇÕES AUXILIARES — TRADE INSPECTOR
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data
def load_trade_log(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df["exp_date"]   = pd.to_datetime(df["exp_date"]).dt.date
    return df


def ic_payoff_usd(
    S: np.ndarray,
    short_put:   float,
    long_put:    float,
    short_call:  float,
    long_call:   float,
    credit:      float,
    multiplier:  int = NDX_MULTIPLIER,
) -> np.ndarray:
    """Payoff do Iron Condor no vencimento (exercício europeu) em USD."""
    put_cost  = np.maximum(0, short_put  - S) - np.maximum(0, long_put  - S)
    call_cost = np.maximum(0, S - short_call) - np.maximum(0, S - long_call)
    return (credit - put_cost - call_cost) * multiplier


def build_payoff_chart(row: pd.Series) -> go.Figure:
    """Gráfico de payoff interativo estilo OptionsStrat."""
    sp  = row["short_put"]
    lp  = row["long_put"]
    sc  = row["short_call"]
    lc  = row["long_call"]
    credit    = row["total_credit"]
    spot_in   = row["spot_entry"]
    spot_out  = row["spot_exit"]
    bep_lo    = row["bep_lower"]
    bep_hi    = row["bep_upper"]
    em        = row["expected_move"]
    tgt_lo    = row["lower_target"]
    tgt_hi    = row["upper_target"]
    max_profit = credit * NDX_MULTIPLIER
    max_loss   = row["max_risk_usd"]

    pad   = max((lc - lp) * 0.12, spot_in * 0.03)
    x_min = lp  - pad
    x_max = lc  + pad
    S     = np.linspace(x_min, x_max, 1200)
    pnl   = ic_payoff_usd(S, sp, lp, sc, lc, credit)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=S, y=np.where(pnl >= 0, pnl, 0),
        fill="tozeroy", fillcolor="rgba(0,200,150,0.18)",
        line=dict(width=0), name="Profit Zone", hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=S, y=np.where(pnl <= 0, pnl, 0),
        fill="tozeroy", fillcolor="rgba(255,77,77,0.18)",
        line=dict(width=0), name="Loss Zone", hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=S, y=pnl,
        mode="lines",
        line=dict(color=C["white"], width=2.5),
        name="Payoff",
        hovertemplate="NDX: <b>%{x:,.0f}</b><br>P&L: <b>$%{y:,.0f}</b><extra></extra>",
    ))

    fig.add_hline(y=0, line=dict(color=C["border"], width=1, dash="solid"))

    def vline(x, color, dash, width, label, label_pos="top left"):
        fig.add_vline(
            x=x,
            line=dict(color=color, width=width, dash=dash),
            annotation_text=label,
            annotation_position=label_pos,
            annotation_font=dict(color=color, size=11, family="monospace"),
        )

    vline(spot_in,  C["blue"],   "solid",  2,   f"ENTRY<br>{spot_in:,.0f}", "top right")
    vline(tgt_hi,   C["white"],  "dot",    1.5, f"+1SD<br>{tgt_hi:,.0f}",   "top right")
    vline(tgt_lo,   C["white"],  "dot",    1.5, f"-1SD<br>{tgt_lo:,.0f}",   "top left")
    vline(bep_hi,   C["yellow"], "dash",   1.5, f"BEP+<br>{bep_hi:,.0f}",   "top right")
    vline(bep_lo,   C["yellow"], "dash",   1.5, f"BEP-<br>{bep_lo:,.0f}",   "top left")

    for strike, label, color in [
        (lp, f"LP<br>{lp:,.0f}",  C["dim"]),
        (sp, f"SP<br>{sp:,.0f}",  C["orange"]),
        (sc, f"SC<br>{sc:,.0f}",  C["orange"]),
        (lc, f"LC<br>{lc:,.0f}",  C["dim"]),
    ]:
        fig.add_annotation(
            x=strike, xref="x",
            y=0,       yref="paper",
            text=label,
            showarrow=False,
            yanchor="top",
            font=dict(color=color, size=9, family="monospace"),
            bgcolor="rgba(22,27,34,0.75)",
        )

    pnl_at_exit  = float(ic_payoff_usd(np.array([spot_out]), sp, lp, sc, lc, credit)[0])
    marker_color = C["green"] if pnl_at_exit >= 0 else C["red"]

    fig.add_trace(go.Scatter(
        x=[spot_out],
        y=[pnl_at_exit],
        mode="markers+text",
        marker=dict(symbol="diamond", size=14, color=marker_color,
                    line=dict(color=C["white"], width=1.5)),
        text=[f"  EXIT<br>  {spot_out:,.0f}"],
        textposition="middle right",
        textfont=dict(color=marker_color, size=11, family="monospace"),
        name="Exit Spot",
        hovertemplate=(
            f"<b>EXIT</b><br>NDX: <b>{spot_out:,.0f}</b><br>"
            f"P&L: <b>${pnl_at_exit:,.0f}</b><extra></extra>"
        ),
    ))

    x_mid = (sp + sc) / 2
    fig.add_annotation(
        x=x_mid, y=max_profit * 1.05,
        text=f"Max Profit: ${max_profit:,.0f}",
        showarrow=False,
        font=dict(color=C["green"], size=11, family="monospace"),
        bgcolor="rgba(22,27,34,0.80)",
    )

    result_label = row["result"]
    result_color = C["green"] if result_label == "WIN" else C["red"]

    fig.update_layout(
        title=dict(
            text=(
                f"<b>Iron Condor 7DTE — NDX</b>  |  "
                f"{row['trade_date']} → {row['exp_date']}  |  "
                f"<span style='color:{result_color}'>{result_label}</span>  "
                f"<span style='color:{result_color}'>P&L: ${row['pnl_usd']:+,.0f}</span>"
            ),
            font=dict(size=16, color=C["white"], family="monospace"),
            x=0.5, xanchor="center",
        ),
        paper_bgcolor = C["bg"],
        plot_bgcolor  = C["panel"],
        font=dict(color=C["white"], family="monospace", size=12),
        xaxis=dict(
            title="NDX Price at Expiration",
            gridcolor=C["border"], gridwidth=0.5,
            zerolinecolor=C["border"],
            tickformat=",",
            range=[x_min, x_max],
        ),
        yaxis=dict(
            title="P&L (USD)",
            gridcolor=C["border"], gridwidth=0.5,
            zerolinecolor=C["border"],
            tickprefix="$", tickformat=",",
        ),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.01,
            xanchor="right", x=1,
            font=dict(size=11),
            bgcolor=C["panel"],
            bordercolor=C["border"],
        ),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=C["panel"],
            bordercolor=C["border"],
            font=dict(color=C["white"], family="monospace"),
        ),
        margin=dict(l=60, r=40, t=80, b=60),
        height=520,
    )
    return fig


def result_badge(result: str) -> str:
    cls = {"WIN": "badge-win", "LOSS": "badge-loss", "MAX_LOSS": "badge-maxloss"}.get(result, "badge-loss")
    return f'<span class="{cls}">{result}</span>'


def delta_color(val: float) -> str:
    return "normal" if val >= 0 else "inverse"


# ─────────────────────────────────────────────────────────────────────────────
# FUNÇÕES AUXILIARES — PERFORMANCE ANALYTICS
# ─────────────────────────────────────────────────────────────────────────────

def compute_perf_stats(df: pd.DataFrame) -> dict:
    """Computes portfolio-level performance statistics."""
    wins   = df[df["result"] == "WIN"]["pnl_usd"]
    losses = df[df["result"] != "WIN"]["pnl_usd"]
    weekly = df["pnl_usd"]
    equity = weekly.cumsum()
    dd     = equity - equity.cummax()

    profit_factor = (wins.sum() / abs(losses.sum())) if losses.sum() != 0 else float("inf")
    sharpe        = (weekly.mean() / weekly.std() * math.sqrt(52)) if weekly.std() > 0 else 0.0

    return dict(
        total_pnl     = weekly.sum(),
        win_rate      = (df["result"] == "WIN").mean() * 100,
        avg_win       = wins.mean()   if len(wins)   > 0 else 0.0,
        avg_loss      = losses.mean() if len(losses) > 0 else 0.0,
        profit_factor = profit_factor,
        sharpe        = sharpe,
        max_dd        = dd.min(),
        avg_credit    = df["total_credit"].mean(),
        total_premium = df["total_credit"].sum() * NDX_MULTIPLIER,
    )


@st.cache_data
def build_equity_curve(df: pd.DataFrame) -> go.Figure:
    """Cumulative P&L curve + 4-week rolling win rate (secondary axis)."""
    dates   = [str(d) for d in df["trade_date"]]
    equity  = df["pnl_usd"].cumsum().values
    colors  = [C["green"] if r == "WIN" else C["red"] for r in df["result"]]
    roll_wr = (df["result"] == "WIN").astype(int).rolling(4, min_periods=1).mean() * 100

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=dates, y=equity,
        fill="tozeroy",
        fillcolor="rgba(0,200,150,0.07)",
        line=dict(color=C["green"], width=2.5),
        mode="lines+markers",
        marker=dict(size=9, color=colors, line=dict(color=C["bg"], width=1.5)),
        name="Equity (USD)",
        yaxis="y1",
        hovertemplate="<b>%{x}</b><br>Cumulative P&L: <b>$%{y:,.0f}</b><extra></extra>",
    ))

    fig.add_trace(go.Scatter(
        x=dates, y=roll_wr.values,
        mode="lines",
        line=dict(color=C["purple"], width=1.5, dash="dot"),
        name="4W Win Rate",
        yaxis="y2",
        opacity=0.85,
        hovertemplate="4W Win Rate: <b>%{y:.0f}%</b><extra></extra>",
    ))

    fig.add_hline(y=0, line=dict(color=C["border"], width=1), yref="y1")

    fig.update_layout(
        title=dict(
            text=(
                "<b>Equity Curve</b>"
                f"  <span style='font-size:11px; color:{C['dim']}'>"
                "+ 4-Week Rolling Win Rate</span>"
            ),
            font=dict(size=14, color=C["white"], family="monospace"),
            x=0.02,
        ),
        paper_bgcolor=C["bg"],
        plot_bgcolor=C["panel"],
        font=dict(color=C["white"], family="monospace", size=11),
        xaxis=dict(gridcolor=C["border"], tickangle=-30),
        yaxis=dict(
            title="Cumulative P&L",
            gridcolor=C["border"],
            tickprefix="$", tickformat=",",
        ),
        yaxis2=dict(
            title="Win Rate %",
            overlaying="y", side="right",
            range=[0, 105],
            showgrid=False,
            ticksuffix="%",
            tickfont=dict(color=C["purple"]),
            titlefont=dict(color=C["purple"]),
        ),
        legend=dict(
            orientation="h", y=1.04, x=0.01,
            font=dict(size=10),
            bgcolor="rgba(0,0,0,0)",
        ),
        hovermode="x unified",
        hoverlabel=dict(bgcolor=C["panel"], bordercolor=C["border"],
                        font=dict(color=C["white"])),
        margin=dict(l=70, r=70, t=60, b=60),
        height=360,
    )
    return fig


@st.cache_data
def build_drawdown_chart(df: pd.DataFrame) -> go.Figure:
    """Running drawdown from peak equity."""
    equity = df["pnl_usd"].cumsum()
    dd     = (equity - equity.cummax()).values
    dates  = [str(d) for d in df["trade_date"]]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=dd,
        fill="tozeroy",
        fillcolor="rgba(255,77,77,0.15)",
        line=dict(color=C["red"], width=2),
        mode="lines",
        name="Drawdown",
        hovertemplate="<b>%{x}</b><br>Drawdown: <b>$%{y:,.0f}</b><extra></extra>",
    ))
    fig.add_hline(y=0, line=dict(color=C["border"], width=1))

    fig.update_layout(
        title=dict(
            text="<b>Drawdown</b>  — from Running Peak",
            font=dict(size=14, color=C["white"], family="monospace"),
            x=0.02,
        ),
        paper_bgcolor=C["bg"],
        plot_bgcolor=C["panel"],
        font=dict(color=C["white"], family="monospace", size=11),
        xaxis=dict(gridcolor=C["border"], tickangle=-30),
        yaxis=dict(gridcolor=C["border"], tickprefix="$", tickformat=","),
        showlegend=False,
        hovermode="x",
        hoverlabel=dict(bgcolor=C["panel"], bordercolor=C["border"],
                        font=dict(color=C["white"])),
        margin=dict(l=70, r=20, t=50, b=60),
        height=260,
    )
    return fig


@st.cache_data
def build_pnl_distribution(df: pd.DataFrame) -> go.Figure:
    """Histogram of trade P&L outcomes — wins vs. losses."""
    wins   = df[df["result"] == "WIN"]["pnl_usd"]
    losses = df[df["result"] != "WIN"]["pnl_usd"]
    mean_v = df["pnl_usd"].mean()

    fig = go.Figure()
    if len(wins) > 0:
        fig.add_trace(go.Histogram(
            x=wins, name="WIN",
            marker_color=C["green"], opacity=0.75,
            xbins=dict(size=400),
            hovertemplate="P&L: $%{x:,.0f}<br>Trades: %{y}<extra></extra>",
        ))
    if len(losses) > 0:
        fig.add_trace(go.Histogram(
            x=losses, name="LOSS",
            marker_color=C["red"], opacity=0.75,
            xbins=dict(size=400),
            hovertemplate="P&L: $%{x:,.0f}<br>Trades: %{y}<extra></extra>",
        ))

    fig.add_vline(
        x=mean_v,
        line=dict(color=C["yellow"], width=1.5, dash="dash"),
        annotation_text=f"Avg: ${mean_v:+,.0f}",
        annotation_font=dict(color=C["yellow"], size=10, family="monospace"),
        annotation_position="top right",
    )
    fig.add_vline(x=0, line=dict(color=C["border"], width=1))

    fig.update_layout(
        title=dict(
            text="<b>P&L Distribution</b>",
            font=dict(size=14, color=C["white"], family="monospace"),
            x=0.02,
        ),
        paper_bgcolor=C["bg"],
        plot_bgcolor=C["panel"],
        font=dict(color=C["white"], family="monospace", size=11),
        barmode="overlay",
        xaxis=dict(gridcolor=C["border"], tickprefix="$", tickformat=","),
        yaxis=dict(gridcolor=C["border"], title="Trades"),
        legend=dict(font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor=C["panel"], bordercolor=C["border"],
                        font=dict(color=C["white"])),
        margin=dict(l=70, r=20, t=50, b=60),
        height=260,
    )
    return fig


@st.cache_data
def build_monthly_heatmap(df: pd.DataFrame) -> go.Figure:
    """Monthly P&L heatmap (months × years)."""
    tmp = df.copy()
    tmp["trade_date"] = pd.to_datetime(tmp["trade_date"])
    tmp["year"]  = tmp["trade_date"].dt.year
    tmp["month"] = tmp["trade_date"].dt.month

    pivot      = tmp.groupby(["year", "month"])["pnl_usd"].sum().unstack()
    month_abbr = ["Jan","Feb","Mar","Apr","May","Jun",
                  "Jul","Aug","Sep","Oct","Nov","Dec"]

    z, text = [], []
    for yr in pivot.index:
        row_z, row_t = [], []
        for mo in range(1, 13):
            if mo in pivot.columns and pd.notna(pivot.at[yr, mo]):
                v = pivot.at[yr, mo]
                row_z.append(v)
                row_t.append(f"${v:+,.0f}")
            else:
                row_z.append(None)
                row_t.append("")
        z.append(row_z)
        text.append(row_t)

    y = [str(yr) for yr in pivot.index]

    fig = go.Figure(go.Heatmap(
        z=z, x=month_abbr, y=y,
        text=text,
        texttemplate="%{text}",
        textfont=dict(size=11, family="monospace"),
        colorscale=[
            [0.00, "rgba(255,77,77,0.90)"],
            [0.45, "rgba(255,77,77,0.12)"],
            [0.50, "rgba(22,27,34,1.00)"],
            [0.55, "rgba(0,200,150,0.12)"],
            [1.00, "rgba(0,200,150,0.90)"],
        ],
        zmid=0,
        showscale=False,
        hovertemplate="<b>%{y} — %{x}</b><br>P&L: <b>$%{z:,.0f}</b><extra></extra>",
    ))

    fig.update_layout(
        title=dict(
            text="<b>Monthly P&L Heatmap</b>",
            font=dict(size=14, color=C["white"], family="monospace"),
            x=0.02,
        ),
        paper_bgcolor=C["bg"],
        plot_bgcolor=C["panel"],
        font=dict(color=C["white"], family="monospace", size=11),
        xaxis=dict(side="top"),
        margin=dict(l=70, r=20, t=70, b=20),
        height=max(160, 80 + 70 * len(y)),
    )
    return fig


@st.cache_data
def build_iv_vs_move(df: pd.DataFrame) -> go.Figure:
    """
    Scatter: IV-implied Expected Move vs. absolute realized NDX move.
    Points BELOW the diagonal = market moved less than IV predicted → premium captured.
    Points ABOVE the diagonal = realized vol exceeded IV → pressure on structure.
    """
    implied = df["expected_move"]
    actual  = (df["spot_exit"] - df["spot_entry"]).abs()
    colors  = [C["green"] if r == "WIN" else C["red"] for r in df["result"]]
    ax_max  = max(implied.max(), actual.max()) * 1.12

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=[0, ax_max], y=[0, ax_max],
        mode="lines",
        line=dict(color=C["dim"], width=1, dash="dot"),
        hoverinfo="skip",
        name="Implied = Realized",
    ))

    fig.add_trace(go.Scatter(
        x=implied, y=actual,
        mode="markers",
        marker=dict(size=10, color=colors, line=dict(color=C["bg"], width=1.5)),
        text=[str(d) for d in df["trade_date"]],
        customdata=list(zip(df["result"], df["pnl_usd"])),
        hovertemplate=(
            "<b>%{text}</b><br>"
            "IV-Implied EM: <b>±%{x:,.0f} pts</b><br>"
            "Realized Move: <b>%{y:,.0f} pts</b><br>"
            "Result: <b>%{customdata[0]}</b>  ($%{customdata[1]:+,.0f})<extra></extra>"
        ),
        name="Trades",
    ))

    fig.add_annotation(
        x=ax_max * 0.88, y=ax_max * 0.82,
        text="Implied = Realized",
        showarrow=False,
        font=dict(color=C["dim"], size=10, family="monospace"),
        bgcolor=C["bg"],
    )

    fig.update_layout(
        title=dict(
            text=(
                "<b>IV-Implied Move vs. Realized Move</b>"
                f"  <span style='font-size:11px; color:{C['dim']}'>"
                "— Below diagonal: market moved less than IV predicted</span>"
            ),
            font=dict(size=14, color=C["white"], family="monospace"),
            x=0.02,
        ),
        paper_bgcolor=C["bg"],
        plot_bgcolor=C["panel"],
        font=dict(color=C["white"], family="monospace", size=11),
        xaxis=dict(
            title="IV-Implied Expected Move (±pts)",
            gridcolor=C["border"], tickformat=",", range=[0, ax_max],
        ),
        yaxis=dict(
            title="Actual NDX Move (pts, absolute)",
            gridcolor=C["border"], tickformat=",", range=[0, ax_max],
        ),
        showlegend=False,
        hoverlabel=dict(bgcolor=C["panel"], bordercolor=C["border"],
                        font=dict(color=C["white"])),
        margin=dict(l=70, r=20, t=60, b=70),
        height=400,
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — SELETOR E RESUMO DO PORTFÓLIO
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        f"<div style='text-align:center; padding:12px 0'>"
        f"<span style='font-size:28px'>📊</span><br>"
        f"<span style='font-size:16px; font-weight:bold; color:{C['white']}'>IC7 Trade Auditor</span><br>"
        f"<span style='font-size:11px; color:{C['dim']}'>NDX Iron Condor 7DTE</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    if not TRADE_LOG_PATH.exists():
        st.error(f"trade_log.csv not found:\n{TRADE_LOG_PATH}")
        st.stop()

    df = load_trade_log(TRADE_LOG_PATH)

    # ── Resumo do portfólio ───────────────────────────────────────────────
    total     = len(df)
    wins      = (df["result"] == "WIN").sum()
    wr        = wins / total * 100
    total_pnl = df["pnl_usd"].sum()

    st.markdown(f"<p class='section-title'>Portfolio Summary</p>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    col1.metric("Trades", total)
    col2.metric("Win Rate", f"{wr:.1f}%")
    col1, col2 = st.columns(2)
    col1.metric("P&L Total", f"${total_pnl:,.0f}", delta=f"${total_pnl:,.0f}")
    col2.metric("Avg IV ATM", f"{df['iv_atm_pct'].mean():.1f}%")

    st.divider()

    # ── Seletor de trade ──────────────────────────────────────────────────
    st.markdown(f"<p class='section-title'>Select Trade</p>", unsafe_allow_html=True)

    _icons = {"WIN": "✅", "LOSS": "🔴", "MAX_LOSS": "💀"}
    options = [
        f"{_icons.get(row.result,'?')}  {row.trade_date} → {row.exp_date}  |  ${row.pnl_usd:+,.0f}"
        for row in df.itertuples()
    ]
    selected_idx = st.selectbox(
        "Select trade:",
        options=range(len(options)),
        format_func=lambda i: options[i],
        index=0,
    )

    st.divider()

    # ── Mini-tabela de todos os trades ────────────────────────────────────
    st.markdown(f"<p class='section-title'>All Trades</p>", unsafe_allow_html=True)

    mini = df[["trade_date", "result", "pnl_usd"]].copy()
    mini.columns = ["Date", "Result", "P&L ($)"]
    mini["P&L ($)"] = mini["P&L ($)"].map(lambda x: f"${x:+,.0f}")

    def _color_result(val):
        if val == "WIN":
            return f"color: {C['green']}"
        elif val == "MAX_LOSS":
            return "color: #ff6b6b"
        return f"color: {C['red']}"

    styled = mini.style.map(_color_result, subset=["Result"])
    st.dataframe(styled, use_container_width=True, height=320, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# PAINEL PRINCIPAL — ABAS
# ─────────────────────────────────────────────────────────────────────────────

tab1, tab2 = st.tabs(["📋  Trade Inspector", "📈  Performance Analytics"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 1 — TRADE INSPECTOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

with tab1:
    row = df.iloc[selected_idx]

    # ── Header do trade selecionado ───────────────────────────────────────
    result_html   = result_badge(row["result"])
    in_range_icon = "✅ INSIDE the strikes" if row["in_range"] else "❌ OUTSIDE the strikes"
    in_range_color= C["green"] if row["in_range"] else C["red"]

    st.markdown(
        f"""
        <div style='background:{C['panel']}; border:1px solid {C['border']};
                    border-radius:10px; padding:16px 24px; margin-bottom:16px;
                    display:flex; align-items:center; gap:20px;'>
            <div>
                <span style='font-size:13px; color:{C['dim']}'>Selected Trade</span><br>
                <span style='font-size:20px; font-weight:bold; font-family:monospace; color:{C['white']}'>
                    {row['trade_date']} &nbsp;→&nbsp; {row['exp_date']}
                </span>
            </div>
            <div style='margin-left:auto; text-align:right;'>
                {result_html}&nbsp;&nbsp;
                <span style='font-size:11px; color:{in_range_color}'>{in_range_icon}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Métricas principais (6 cards) ─────────────────────────────────────
    c1, c2, c3, c4, c5, c6 = st.columns(6)

    c1.metric("Entry Spot", f"{row['spot_entry']:,.0f}",
              help="NDX price at trade entry")
    c2.metric("IV ATM", f"{row['iv_atm_pct']:.1f}%",
              help="ATM Implied Volatility — Black-Scholes inversion (mid-price)")
    c3.metric("Expected Move", f"±{row['expected_move']:,.0f} pts",
              delta=f"±{row['em_pct']:.2f}%",
              help="EM = Spot × IV_ATM × √(7/365) — identical to OptionsStrat")
    c4.metric("Credit Received", f"{row['total_credit']:.2f} pts",
              delta=f"${row['total_credit'] * NDX_MULTIPLIER:,.0f} USD",
              help="Net premium received at trade open")
    c5.metric("Exit Spot", f"{row['spot_exit']:,.0f}",
              delta=f"{row['spot_exit'] - row['spot_entry']:+,.0f} pts",
              delta_color=delta_color(row["spot_exit"] - row["spot_entry"]),
              help="NDX price at expiration (exit)")
    c6.metric("Final P&L", f"${row['pnl_usd']:+,.0f}",
              delta=f"{row['pnl_points']:+.2f} pts",
              delta_color=delta_color(row["pnl_usd"]),
              help="Realized P&L (credit − exercise cost) × $100")

    # ── Card de estrutura: os 4 contratos ────────────────────────────────
    _cs = (row["constraint_satisfied"] if "constraint_satisfied" in row.index else True)
    _cs_badge = (
        f"<span style='color:{C['green']};font-size:10px'>✓ BEPs outside ±1SD</span>"
        if _cs else
        f"<span style='color:{C['yellow']};font-size:10px'>⚠ BEP Best Effort</span>"
    )
    st.markdown(
        f"""
        <div style='background:{C['panel']}; border:1px solid {C['border']};
                    border-radius:8px; padding:10px 20px; margin-top:6px;
                    font-family:monospace; font-size:13px; text-align:center;'>
            <span style='color:{C['dim']}; font-size:10px; letter-spacing:1px;
                         text-transform:uppercase; margin-right:16px'>Structure</span>
            <span style='color:{C['blue']}'>BUY&nbsp;PUT&nbsp;<b>{row['long_put']:,.0f}</b></span>
            <span style='color:{C['border']}'>&nbsp;|&nbsp;</span>
            <span style='color:{C['orange']}'>SELL&nbsp;PUT&nbsp;<b>{row['short_put']:,.0f}</b></span>
            &nbsp;&nbsp;
            <span style='color:{C['dim']}; font-size:11px'>◄&nbsp;SPOT&nbsp;{row['spot_entry']:,.0f}&nbsp;►</span>
            &nbsp;&nbsp;
            <span style='color:{C['orange']}'>SELL&nbsp;CALL&nbsp;<b>{row['short_call']:,.0f}</b></span>
            <span style='color:{C['border']}'>&nbsp;|&nbsp;</span>
            <span style='color:{C['blue']}'>BUY&nbsp;CALL&nbsp;<b>{row['long_call']:,.0f}</b></span>
            <span style='margin-left:20px'>{_cs_badge}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── Gráfico de Payoff ─────────────────────────────────────────────────
    st.plotly_chart(build_payoff_chart(row), use_container_width=True)

    st.markdown("---")

    # ── Strike Structure | BEPs | P&L Breakdown ───────────────────────────
    col_strikes, col_beps, col_decomp = st.columns([2, 2, 3])

    with col_strikes:
        st.markdown(f"<p class='section-title'>Strike Structure</p>", unsafe_allow_html=True)
        st.markdown(
            f"""
            <div style='font-family:monospace; font-size:13px; line-height:2.2'>
                <span class='strike-badge strike-long'>BUY PUT &nbsp;{row['long_put']:,.0f}</span><br>
                <span class='strike-badge strike-short'>SELL PUT {row['short_put']:,.0f}</span><br>
                <span style='font-size:11px; color:{C['dim']}'>
                    &nbsp;&nbsp;↑ Put Wing  |  Width: {row['short_put'] - row['long_put']:.0f} pts
                </span><br><br>
                <span class='strike-badge strike-short'>SELL CALL {row['short_call']:,.0f}</span><br>
                <span class='strike-badge strike-long'>BUY CALL &nbsp;{row['long_call']:,.0f}</span><br>
                <span style='font-size:11px; color:{C['dim']}'>
                    &nbsp;&nbsp;↑ Call Wing  |  Width: {row['long_call'] - row['short_call']:.0f} pts
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_beps:
        st.markdown(f"<p class='section-title'>Breakevens vs 1SD Target</p>", unsafe_allow_html=True)
        bep_delta_lo = row["bep_lower"] - row["lower_target"]
        bep_delta_hi = row["bep_upper"] - row["upper_target"]
        bep_color_lo = C["green"] if abs(bep_delta_lo) < 50 else C["yellow"]
        bep_color_hi = C["green"] if abs(bep_delta_hi) < 50 else C["yellow"]
        st.markdown(
            f"""
            <div style='font-family:monospace; font-size:13px; line-height:2.2'>
                <div style='color:{C['dim']}'>-1SD Target (lower)</div>
                <div style='color:{C['purple']}; font-size:15px; font-weight:bold'>{row['lower_target']:,.0f}</div>
                <div style='color:{C['dim']}'>Lower BEP (after credit)</div>
                <div style='color:{C['yellow']}; font-size:15px; font-weight:bold'>
                    {row['bep_lower']:,.0f}
                    <span style='font-size:11px; color:{bep_color_lo}'>({bep_delta_lo:+.0f} pts vs target)</span>
                </div>
                <br>
                <div style='color:{C['dim']}'>+1SD Target (upper)</div>
                <div style='color:{C['purple']}; font-size:15px; font-weight:bold'>{row['upper_target']:,.0f}</div>
                <div style='color:{C['dim']}'>Upper BEP (after credit)</div>
                <div style='color:{C['yellow']}; font-size:15px; font-weight:bold'>
                    {row['bep_upper']:,.0f}
                    <span style='font-size:11px; color:{bep_color_hi}'>({bep_delta_hi:+.0f} pts vs target)</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_decomp:
        st.markdown(f"<p class='section-title'>P&L Breakdown</p>", unsafe_allow_html=True)
        max_profit    = row["total_credit"] * NDX_MULTIPLIER
        max_loss      = row["max_risk_usd"]
        put_cost_usd  = row["put_cost"]  * NDX_MULTIPLIER
        call_cost_usd = row["call_cost"] * NDX_MULTIPLIER
        exit_usd      = row["exit_cost"] * NDX_MULTIPLIER
        rr = abs(max_profit / max_loss) if max_loss != 0 else float("inf")
        st.markdown(
            f"""
            <table style='font-family:monospace; font-size:12px; width:100%;
                          border-collapse:collapse; color:{C['white']}'>
                <tr style='color:{C['dim']}; font-size:11px; border-bottom:1px solid {C['border']}'>
                    <td>Item</td><td style='text-align:right'>Points</td><td style='text-align:right'>USD</td>
                </tr>
                <tr>
                    <td>Credit received</td>
                    <td style='text-align:right; color:{C['green']}'>{row['total_credit']:+.2f}</td>
                    <td style='text-align:right; color:{C['green']}'>+${row['total_credit']*NDX_MULTIPLIER:,.0f}</td>
                </tr>
                <tr>
                    <td>&nbsp;&nbsp;mid SP ({row['short_put']:.0f})</td>
                    <td style='text-align:right; color:{C['green']}'>{row['mid_sp']:+.2f}</td>
                    <td style='text-align:right; color:{C['green']}'>+${row['mid_sp']*NDX_MULTIPLIER:,.0f}</td>
                </tr>
                <tr>
                    <td>&nbsp;&nbsp;mid LP ({row['long_put']:.0f})</td>
                    <td style='text-align:right; color:{C['red']}'>{-row['mid_lp']:+.2f}</td>
                    <td style='text-align:right; color:{C['red']}'>-${row['mid_lp']*NDX_MULTIPLIER:,.0f}</td>
                </tr>
                <tr>
                    <td>&nbsp;&nbsp;mid SC ({row['short_call']:.0f})</td>
                    <td style='text-align:right; color:{C['green']}'>{row['mid_sc']:+.2f}</td>
                    <td style='text-align:right; color:{C['green']}'>+${row['mid_sc']*NDX_MULTIPLIER:,.0f}</td>
                </tr>
                <tr>
                    <td>&nbsp;&nbsp;mid LC ({row['long_call']:.0f})</td>
                    <td style='text-align:right; color:{C['red']}'>{-row['mid_lc']:+.2f}</td>
                    <td style='text-align:right; color:{C['red']}'>-${row['mid_lc']*NDX_MULTIPLIER:,.0f}</td>
                </tr>
                <tr style='border-top:1px solid {C['border']}'>
                    <td>Expiration cost</td>
                    <td style='text-align:right; color:{C['red']}'>{-row['exit_cost']:+.2f}</td>
                    <td style='text-align:right; color:{C['red']}'>-${exit_usd:,.0f}</td>
                </tr>
                <tr>
                    <td>&nbsp;&nbsp;Put wing</td>
                    <td style='text-align:right; color:{C['dim']}'>{-row['put_cost']:+.2f}</td>
                    <td style='text-align:right; color:{C['dim']}'>-${put_cost_usd:,.0f}</td>
                </tr>
                <tr>
                    <td>&nbsp;&nbsp;Call wing</td>
                    <td style='text-align:right; color:{C['dim']}'>{-row['call_cost']:+.2f}</td>
                    <td style='text-align:right; color:{C['dim']}'>-${call_cost_usd:,.0f}</td>
                </tr>
                <tr style='border-top:2px solid {C['border']}; font-weight:bold'>
                    <td>P&L FINAL</td>
                    <td style='text-align:right; color:{"#00c896" if row["pnl_usd"] >= 0 else "#ff4d4d"}'>
                        {row['pnl_points']:+.2f}
                    </td>
                    <td style='text-align:right; color:{"#00c896" if row["pnl_usd"] >= 0 else "#ff4d4d"}'>
                        ${row['pnl_usd']:+,.0f}
                    </td>
                </tr>
                <tr style='border-top:1px solid {C['border']}; color:{C['dim']}'>
                    <td>Max Profit (credit)</td>
                    <td style='text-align:right'>{row['total_credit']:.2f}</td>
                    <td style='text-align:right'>${max_profit:,.0f}</td>
                </tr>
                <tr style='color:{C['dim']}'>
                    <td>Max Loss (spread − credit)</td>
                    <td></td>
                    <td style='text-align:right'>-${max_loss:,.0f}</td>
                </tr>
                <tr style='color:{C['dim']}'>
                    <td>Risk/Reward</td>
                    <td></td>
                    <td style='text-align:right'>1 : {rr:.2f}</td>
                </tr>
            </table>
            """,
            unsafe_allow_html=True,
        )

    # ── Navegação rápida ──────────────────────────────────────────────────
    st.markdown("---")
    nav_l, nav_c, nav_r = st.columns([1, 4, 1])

    with nav_l:
        if selected_idx > 0:
            prev = df.iloc[selected_idx - 1]
            st.markdown(
                f"← Previous Trade<br>"
                f"<span style='font-size:12px; color:{C['dim']}'>{prev['trade_date']}</span>",
                unsafe_allow_html=True,
            )
    with nav_r:
        if selected_idx < len(df) - 1:
            nxt = df.iloc[selected_idx + 1]
            st.markdown(
                f"Next Trade →<br>"
                f"<span style='font-size:12px; color:{C['dim']}'>{nxt['trade_date']}</span>",
                unsafe_allow_html=True,
            )
    with nav_c:
        st.markdown(
            f"<div style='text-align:center; color:{C['dim']}; font-size:11px'>"
            f"Trade {selected_idx + 1} of {len(df)}  |  "
            f"Period: {df['trade_date'].min()} → {df['exp_date'].max()}"
            f"</div>",
            unsafe_allow_html=True,
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 2 — PERFORMANCE ANALYTICS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

with tab2:
    stats = compute_perf_stats(df)
    pf_str = f"{stats['profit_factor']:.2f}" if stats['profit_factor'] != float("inf") else "∞"

    # ── Row 1: KPIs principais ────────────────────────────────────────────
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Total P&L",      f"${stats['total_pnl']:+,.0f}")
    k2.metric("Win Rate",       f"{stats['win_rate']:.1f}%")
    k3.metric("Profit Factor",  pf_str,
              help="Gross profit ÷ gross loss — ratio acima de 1.0 indica edge positivo")
    k4.metric("Sharpe (ann.)",  f"{stats['sharpe']:.2f}",
              help="Weekly P&L Sharpe × √52 — benchmark: > 0.5 é respeitável em vol-selling")
    k5.metric("Max Drawdown",   f"${stats['max_dd']:,.0f}")
    k6.metric("Avg Credit",     f"{stats['avg_credit']:.2f} pts",
              delta=f"${stats['avg_credit'] * NDX_MULTIPLIER:,.0f} USD")

    st.markdown("---")

    # ── Row 2: Equity Curve (full width) ─────────────────────────────────
    st.plotly_chart(build_equity_curve(df), use_container_width=True)

    # ── Row 3: Drawdown + P&L Distribution (50/50) ───────────────────────
    col_dd, col_dist = st.columns(2)
    with col_dd:
        st.plotly_chart(build_drawdown_chart(df), use_container_width=True)
    with col_dist:
        st.plotly_chart(build_pnl_distribution(df), use_container_width=True)

    # ── Row 4: Monthly Heatmap (full width) ───────────────────────────────
    st.plotly_chart(build_monthly_heatmap(df), use_container_width=True)

    # ── Row 5: IV vs Realized (full width) — estratégico para o CZ ───────
    st.plotly_chart(build_iv_vs_move(df), use_container_width=True)

    # ── Row 6: Stats adicionais + Tier breakdown ──────────────────────────
    st.markdown("---")
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Avg Win",           f"${stats['avg_win']:+,.0f}")
    s2.metric("Avg Loss",          f"${stats['avg_loss']:+,.0f}")
    s3.metric("Total Premium Sold",f"${stats['total_premium']:,.0f}",
              help="Soma de todos os créditos recebidos × $100")
    s4.metric("Trades Analyzed",   len(df))

    # Tier breakdown (só aparece se a coluna existir — backward compatible)
    if "min_bid_used" in df.columns:
        st.markdown("---")
        st.markdown(
            f"<p class='section-title'>Liquidity Tier Breakdown</p>",
            unsafe_allow_html=True,
        )
        tier_counts = df["min_bid_used"].value_counts().sort_index()
        tier_total  = tier_counts.sum()
        cols = st.columns(len(tier_counts))
        tier_labels = {0.05: "Primary (bid ≥ 0.05)", 0.03: "Tier 2 (bid ≥ 0.03)", 0.01: "Tier 3 (bid ≥ 0.01)"}
        for i, (tier, count) in enumerate(tier_counts.items()):
            label = tier_labels.get(tier, f"bid ≥ {tier}")
            cols[i].metric(label, f"{count} trades", delta=f"{count/tier_total*100:.0f}%")


# ─────────────────────────────────────────────────────────────────────────────
# RODAPÉ
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(
    f"""
    <div style='text-align:center; color:{C['dim']}; font-size:10px;
                margin-top:40px; border-top:1px solid {C['border']}; padding-top:12px'>
        IC7 Trade Auditor v2  |  Prop Desk Quant  |  Senior Quant Developer<br>
        For internal use only — Cristiano (CZ)  |
        Data: <code>trade_log.csv</code>  |
        Engine: Black-Scholes IV + European Exercise
    </div>
    """,
    unsafe_allow_html=True,
)
