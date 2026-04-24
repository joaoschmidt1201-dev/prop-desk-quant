#!/usr/bin/env python3
"""
cz_dashboard_app.py
-------------------
Interactive Options Portfolio Dashboard — Prop Desk
Two tabs: CZ Live Trading | JS Forward Testing
AI Chat powered by Claude Sonnet with full portfolio context.
"""

import json
import os
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT        = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports"
sys.path.insert(0, str(Path(__file__).parent))

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Prop Desk | Options Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── CSS ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.kpi-card {
    background: #1e2538;
    border: 1px solid #2d3548;
    border-radius: 10px;
    padding: 16px 20px;
    text-align: center;
    margin-bottom: 6px;
}
.kpi-label {
    color: #8892a4;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    margin-bottom: 6px;
}
.kpi-value { font-size: 22px; font-weight: 700; line-height: 1.2; }
.kpi-sub   { font-size: 10px; color: #8892a4; margin-top: 4px; }
.c-green   { color: #00d97e !important; }
.c-red     { color: #ff4b4b !important; }
.c-blue    { color: #4a9eff !important; }
.c-yellow  { color: #ffc107 !important; }
.c-white   { color: #e8eaf0 !important; }
.c-purple  { color: #b39ddb !important; }
.alert-red  { background:rgba(255,75,75,.12); border:1px solid rgba(255,75,75,.35);
               border-radius:8px; padding:8px 14px; margin:3px 0; color:#ff4b4b; font-size:13px; }
.alert-grn  { background:rgba(0,217,126,.12); border:1px solid rgba(0,217,126,.35);
               border-radius:8px; padding:8px 14px; margin:3px 0; color:#00d97e; font-size:13px; }
.alert-ylw  { background:rgba(255,193,7,.12);  border:1px solid rgba(255,193,7,.35);
               border-radius:8px; padding:8px 14px; margin:3px 0; color:#ffc107; font-size:13px; }
.section-title {
    font-size: 11px; font-weight: 700; letter-spacing: 1px;
    text-transform: uppercase; color: #8892a4;
    margin: 24px 0 10px 0; padding-bottom: 6px;
    border-bottom: 1px solid #2d3548;
}
.chat-container {
    background: #1a1f2e;
    border: 1px solid #2d3548;
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 12px;
}
</style>
""", unsafe_allow_html=True)


# ─── Data loaders ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_snapshot() -> dict | None:
    path = REPORTS_DIR / "trades_snapshot_latest.json"
    if not path.exists():
        candidates = sorted(REPORTS_DIR.glob("trades_snapshot_2*.json"), reverse=True)
        if not candidates:
            return None
        path = candidates[0]
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=300)
def load_history() -> pd.DataFrame:
    path = REPORTS_DIR / "trade_history.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    return df


# ─── KPI computation ──────────────────────────────────────────────────────────

def compute_kpis(trades: list[dict], history: pd.DataFrame,
                 monthly_summaries: list[dict]) -> dict:
    """
    Primary P&L values from sheet TOTAL rows (authoritative).
    Win Rate, PF, Expectancy from individual trade records.
    """
    active = [t for t in trades if t["is_active"]]
    closed = [t for t in trades if not t["is_active"]]

    # ── From sheet TOTAL rows ──
    open_pnl = sum(m["open_pnl"] for m in monthly_summaries)
    rlzd     = sum(m["rlzd"]     for m in monthly_summaries)
    delta    = sum(m["delta"]    for m in monthly_summaries)

    # ── Risk (trade level) ──
    max_loss_exp = sum(t["max_loss"]   or 0 for t in active if t.get("max_loss")   is not None)
    nc_risk      = sum(t["net_credit"] or 0 for t in active if t.get("net_credit") is not None)

    # ── Est. Daily Theta: net_credit / dte_remaining per active trade ──
    theta_daily = sum(
        (t["net_credit"] / t["dte_remaining"])
        for t in active
        if t.get("net_credit") and t.get("dte_remaining") and t["dte_remaining"] > 0
    )

    # ── DTE counts ──
    expiring_7  = sum(1 for t in active if (t.get("dte_remaining") or 999) <= 7)
    expiring_14 = sum(1 for t in active if (t.get("dte_remaining") or 999) <= 14)

    # ── At target / at stop ──
    at_target = sum(1 for t in active if (t.get("pnl_pct_max") or 0) >= 50)
    at_stop   = sum(1 for t in active if (t.get("pnl_pct_max") or 0) <= -100)

    # ── Closed trade stats ──
    closed_pnls = [t["pnl_current"] for t in closed if t.get("pnl_current") is not None]
    wins        = [p for p in closed_pnls if p > 0]
    losses      = [p for p in closed_pnls if p <= 0]
    win_rate    = len(wins) / len(closed_pnls) * 100 if closed_pnls else None
    avg_win     = sum(wins)   / len(wins)   if wins   else None
    avg_loss    = sum(losses) / len(losses) if losses else None
    best        = max(closed_pnls) if closed_pnls else None
    worst       = min(closed_pnls) if closed_pnls else None
    total_wins  = sum(wins)
    total_loss  = abs(sum(losses))
    pf          = total_wins / total_loss if total_loss > 0 else None

    # Expectancy = (WR * AvgWin) + ((1-WR) * AvgLoss)
    expectancy = None
    if win_rate is not None and avg_win is not None and avg_loss is not None:
        wr = win_rate / 100
        expectancy = (wr * avg_win) + ((1 - wr) * avg_loss)

    # Risk/Reward ratio
    rr_ratio = abs(avg_win / avg_loss) if avg_win and avg_loss else None

    # ── Alerts ──
    alerts = []
    for t in active:
        dte = t.get("dte_remaining")
        pct = t.get("pnl_pct_max")
        if dte is not None and dte <= 7:
            alerts.append(("yellow", f"CRITICAL DTE: {t['name']} — {dte} days remaining"))
        if pct is not None and pct <= -100:
            alerts.append(("red", f"STOP LOSS: {t['name']} @ {pct:.0f}% of Max Profit"))
        if pct is not None and pct >= 50:
            alerts.append(("green", f"PROFIT TARGET: {t['name']} @ {pct:.0f}% of Max Profit"))

    return {
        # P&L
        "open_pnl":          open_pnl,
        "rlzd":              rlzd,
        "total_pnl":         open_pnl + rlzd,
        "delta":             delta,
        # Risk
        "max_loss_exp":      max_loss_exp,
        "nc_risk":           nc_risk,
        "theta_daily":       theta_daily,
        "expiring_14":       expiring_14,
        "expiring_7":        expiring_7,
        # Performance
        "win_rate":          win_rate,
        "profit_factor":     pf,
        "avg_win":           avg_win,
        "avg_loss":          avg_loss,
        # Trade intelligence
        "expectancy":        expectancy,
        "rr_ratio":          rr_ratio,
        "best_trade":        best,
        "worst_trade":       worst,
        "at_target":         at_target,
        "at_stop":           at_stop,
        # Counts
        "n_active":          len(active),
        "n_closed":          len(closed_pnls),
        # Lists
        "alerts":            alerts,
        "active_list":       active,
        "closed_list":       closed,
        "monthly_summaries": monthly_summaries,
    }


# ─── HTML helpers ─────────────────────────────────────────────────────────────

def kpi(label: str, value: str, sub: str = "", color: str = "c-white") -> str:
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return (f'<div class="kpi-card">'
            f'<div class="kpi-label">{label}</div>'
            f'<div class="kpi-value {color}">{value}</div>'
            f'{sub_html}'
            f'</div>')


def fmt(v: float | None, prefix: str = "$", decimals: int = 0,
        sign: bool = True) -> tuple[str, str]:
    if v is None:
        return "—", "c-white"
    s = f"{prefix}{v:+,.{decimals}f}" if sign else f"{prefix}{v:,.{decimals}f}"
    color = "c-green" if v > 0 else ("c-red" if v < 0 else "c-white")
    return s, color


# ─── Charts ───────────────────────────────────────────────────────────────────

BG = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#8892a4", family="Inter, sans-serif"),
    margin=dict(l=10, r=10, t=36, b=10),
    xaxis=dict(gridcolor="#2d3548", zerolinecolor="#2d3548"),
    yaxis=dict(gridcolor="#2d3548", zerolinecolor="#2d3548"),
)


def chart_equity(history: pd.DataFrame, env_norm: str,
                 individual_trade_pnls: dict | None = None) -> go.Figure:
    if history.empty:
        return go.Figure().update_layout(**BG, title="No data")
    df = history[history["env_norm"] == env_norm].copy()
    if df.empty:
        return go.Figure().update_layout(**BG, title="No data for this environment")

    # Step 1: last pnl per (date, trade) — deduplicate Make 2x/day
    per_trade = (
        df.dropna(subset=["pnl"])
        .sort_values("date")
        .groupby(["date", "strategy"])["pnl"]
        .last()
        .unstack(level="strategy")   # rows = dates, cols = trades
    )
    if per_trade.empty:
        return go.Figure().update_layout(**BG, title="No data")

    # Step 2: inject sheet's authoritative per-trade PnLs as of today.
    # This anchors the curve endpoint to the exact values in the visual sheet,
    # correcting for timing gaps when trades close between Make runs.
    if individual_trade_pnls:
        today = pd.Timestamp.today().normalize()
        for trade_name, sheet_pnl in individual_trade_pnls.items():
            if trade_name in per_trade.columns:
                per_trade.loc[today, trade_name] = sheet_pnl
        per_trade = per_trade.sort_index()

    # Step 3: forward-fill each trade column, then sum across all trades.
    # Closed trades carry their final PnL forward so realized gains accumulate.
    portfolio = per_trade.ffill().sum(axis=1).reset_index()
    portfolio.columns = ["date", "pnl"]
    portfolio = portfolio.sort_values("date")

    last  = portfolio["pnl"].iloc[-1]
    color = "#00d97e" if last >= 0 else "#ff4b4b"
    fill  = "rgba(0,217,126,0.07)" if last >= 0 else "rgba(255,75,75,0.07)"

    fig = go.Figure(go.Scatter(
        x=portfolio["date"], y=portfolio["pnl"],
        mode="lines+markers",
        line=dict(color=color, width=2.5), marker=dict(size=4),
        fill="tozeroy", fillcolor=fill, name="Total PnL",
        hovertemplate="<b>%{x|%d %b}</b><br>Total PnL: $%{y:,.0f}<extra></extra>",
    ))
    fig.add_hline(y=0, line_color="#2d3548", line_width=1)
    anchored = individual_trade_pnls is not None and bool(individual_trade_pnls)
    title = "Equity Curve — Sheet-Anchored" if anchored else "Equity Curve (Open + Realized, ffill)"
    fig.update_layout(**BG, title=title, height=280)
    return fig


def chart_monthly_pnl(monthly_summaries: list[dict]) -> go.Figure:
    if not monthly_summaries:
        return go.Figure().update_layout(**BG, title="No monthly data")
    months = [m["month"] for m in monthly_summaries]
    rlzds  = [m["rlzd"]  for m in monthly_summaries]
    opens  = [m["open_pnl"] for m in monthly_summaries]
    colors_r = ["#00d97e" if v >= 0 else "#ff4b4b" for v in rlzds]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="RLZD", x=months, y=rlzds, marker_color=colors_r,
        text=[f"${v:+,.0f}" for v in rlzds], textposition="outside",
        textfont=dict(size=10, color="#e8eaf0"),
        hovertemplate="<b>%{x}</b><br>RLZD: $%{y:,.0f}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="Open PnL", x=months, y=opens,
        marker_color="rgba(74,158,255,0.6)",
        hovertemplate="<b>%{x}</b><br>Open PnL: $%{y:,.0f}<extra></extra>",
    ))
    fig.add_hline(y=0, line_color="#2d3548", line_width=1)
    fig.update_layout(**BG, title="Monthly P&L Breakdown", height=280,
                      barmode="group", legend=dict(orientation="h", y=1.1))
    return fig


def chart_win_loss_donut(kpis: dict) -> go.Figure:
    closed = kpis["closed_list"]
    closed_pnls = [t["pnl_current"] for t in closed if t.get("pnl_current") is not None]
    if not closed_pnls:
        return go.Figure().update_layout(**BG, title="No closed trades")
    wins   = sum(1 for p in closed_pnls if p > 0)
    losses = sum(1 for p in closed_pnls if p <= 0)
    fig = go.Figure(go.Pie(
        labels=["Winners", "Losers"],
        values=[wins, losses],
        hole=0.6,
        marker=dict(colors=["#00d97e", "#ff4b4b"]),
        textinfo="label+percent",
        textfont=dict(color="#e8eaf0", size=12),
        hovertemplate="<b>%{label}</b>: %{value} trades (%{percent})<extra></extra>",
    ))
    wr = kpis["win_rate"]
    fig.add_annotation(
        text=f"{wr:.1f}%<br><span style='font-size:11px'>Win Rate</span>" if wr else "—",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=20, color="#e8eaf0"),
    )
    fig.update_layout(**BG, title="Win / Loss Distribution", height=280,
                      showlegend=False)
    return fig


def chart_active_pct(active: list[dict]) -> go.Figure:
    trades = [t for t in active if t.get("pnl_pct_max") is not None]
    if not trades:
        # Fallback: show PnL bar
        tw = [t for t in active if t.get("pnl_current") is not None]
        if not tw:
            return go.Figure().update_layout(**BG, title="No active trades")
        names  = [t["name"] for t in tw]
        pnls   = [t["pnl_current"] for t in tw]
        colors = ["#00d97e" if p >= 0 else "#ff4b4b" for p in pnls]
        fig = go.Figure(go.Bar(
            x=names, y=pnls, marker_color=colors,
            text=[f"${p:,.0f}" for p in pnls], textposition="outside",
            textfont=dict(size=10, color="#e8eaf0"),
        ))
        fig.update_layout(**BG, title="Active Trades: Open PnL", height=280)
        return fig
    names  = [t["name"] for t in trades]
    pcts   = [t["pnl_pct_max"] for t in trades]
    colors = []
    for p in pcts:
        if p >= 50:      colors.append("#00d97e")
        elif p >= 0:     colors.append("#4a9eff")
        elif p >= -100:  colors.append("#ffc107")
        else:            colors.append("#ff4b4b")
    fig = go.Figure(go.Bar(
        x=names, y=pcts, marker_color=colors,
        text=[f"{p:.0f}%" for p in pcts], textposition="outside",
        textfont=dict(size=10, color="#e8eaf0"),
        hovertemplate="<b>%{x}</b><br>%% Max: %{y:.1f}%%<extra></extra>",
    ))
    fig.add_hline(y=50,   line_dash="dash", line_color="#00d97e", opacity=0.5,
                  annotation_text="Target 50%",   annotation_font_color="#00d97e")
    fig.add_hline(y=-100, line_dash="dash", line_color="#ff4b4b", opacity=0.5,
                  annotation_text="Stop -100%",   annotation_font_color="#ff4b4b")
    fig.add_hline(y=0, line_color="#2d3548", line_width=1)
    fig.update_layout(**BG, title="Active Trades: % of Max Profit", height=280)
    return fig


def chart_closed_pnl(closed: list[dict]) -> go.Figure:
    trades = [t for t in closed if t.get("pnl_current") is not None]
    if not trades:
        return go.Figure().update_layout(**BG, title="No closed trades")
    trades_s = sorted(trades, key=lambda t: t["pnl_current"])
    names  = [t["name"] for t in trades_s]
    pnls   = [t["pnl_current"] for t in trades_s]
    colors = ["#00d97e" if p >= 0 else "#ff4b4b" for p in pnls]
    fig = go.Figure(go.Bar(
        x=names, y=pnls, marker_color=colors,
        text=[f"${p:,.0f}" for p in pnls], textposition="outside",
        textfont=dict(size=9, color="#e8eaf0"),
        hovertemplate="<b>%{x}</b><br>PnL: $%{y:,.0f}<extra></extra>",
    ))
    fig.add_hline(y=0, line_color="#2d3548", line_width=1)
    fig.update_layout(**BG, title="Closed Trades PnL (worst to best)",
                      height=300, xaxis_tickangle=-35)
    return fig


def chart_dte_countdown(active: list[dict]) -> go.Figure:
    trades = [t for t in active if t.get("dte_remaining") is not None]
    if not trades:
        return go.Figure().update_layout(**BG, title="No active trades")
    trades_s = sorted(trades, key=lambda t: t["dte_remaining"])
    names = [t["name"] for t in trades_s]
    dtes  = [t["dte_remaining"] for t in trades_s]
    colors = []
    for d in dtes:
        if d <= 7:    colors.append("#ff4b4b")
        elif d <= 14: colors.append("#ffc107")
        elif d <= 21: colors.append("#4a9eff")
        else:         colors.append("#00d97e")
    fig = go.Figure(go.Bar(
        y=names, x=dtes, orientation="h", marker_color=colors,
        text=[f"{d}d" for d in dtes], textposition="outside",
        textfont=dict(size=10, color="#e8eaf0"),
        hovertemplate="<b>%{y}</b><br>DTE: %{x}<extra></extra>",
    ))
    fig.add_vline(x=7,  line_dash="dash", line_color="#ff4b4b", opacity=0.5)
    fig.add_vline(x=14, line_dash="dash", line_color="#ffc107", opacity=0.4)
    bg_dte = {k: v for k, v in BG.items() if k != "margin"}
    fig.update_layout(**bg_dte, title="DTE Countdown", height=max(200, len(trades) * 44),
                      xaxis_title="Days to Expiration",
                      margin=dict(l=180, r=10, t=36, b=10))
    return fig


# ─── AI Context builder ────────────────────────────────────────────────────────

def build_ai_system_prompt(trades: list[dict], kpis: dict, env_label: str) -> str:
    active = kpis["active_list"]
    closed = kpis["closed_list"]

    lines = [
        "You are a senior quant analyst and options portfolio manager at a proprietary trading desk.",
        "",
        "DESK METHODOLOGY:",
        "- Trade only macro index ETFs/indices: SPX, NDX, RUT, SPY, QQQ, IWM, GLD, SLV",
        "- Minimum 7 DTE at entry. No intraday, no directional bets.",
        "- Hybrid TastyTrade + Technical Analysis: IV Rank, Probability of Profit, chart structure alignment.",
        "- Strategies: Iron Condors (IC), Batman (BAT), RJL, Half-Bat, Hybrid Bat, Bull/Bear Spreads.",
        "- Management: close at 50% profit target; stop at -100% of max credit received.",
        "",
        f"CURRENT PORTFOLIO — {env_label}",
        f"  Open PnL    : ${kpis['open_pnl']:+,.0f}",
        f"  Realized PnL: ${kpis['rlzd']:+,.0f}",
        f"  Total PnL   : ${kpis['total_pnl']:+,.0f}",
        f"  Portfolio Delta: {kpis['delta']:+.0f}",
        f"  Max Loss Exposed: ${kpis['max_loss_exp']:,.0f}",
        f"  Net Credit at Risk: ${kpis['nc_risk']:,.0f}",
        f"  Est. Daily Theta: ${kpis['theta_daily']:,.0f}/day" if kpis['theta_daily'] else "  Est. Daily Theta: N/A",
        f"  Win Rate: {kpis['win_rate']:.1f}%" if kpis['win_rate'] else "  Win Rate: N/A",
        f"  Profit Factor: {kpis['profit_factor']:.2f}" if kpis['profit_factor'] else "  Profit Factor: N/A",
        f"  Expectancy: ${kpis['expectancy']:+,.0f}/trade" if kpis['expectancy'] else "  Expectancy: N/A",
        f"  Active: {kpis['n_active']} trades | Closed: {kpis['n_closed']} trades",
        "",
        f"ACTIVE TRADES ({len(active)}):",
    ]
    for t in sorted(active, key=lambda x: x.get("pnl_pct_max") or 0):
        pnl  = t.get("pnl_current")
        pct  = t.get("pnl_pct_max")
        dte  = t.get("dte_remaining")
        dlta = t.get("delta_current")
        nc   = t.get("net_credit")
        ml   = t.get("max_loss")
        lw   = t.get("lw_be")
        up   = t.get("up_be")
        parts = [f"  {t['name']}"]
        if pnl  is not None: parts.append(f"PnL=${pnl:+,.0f}")
        if pct  is not None: parts.append(f"({pct:+.0f}% max)")
        if dte  is not None: parts.append(f"DTE={dte}")
        if dlta is not None: parts.append(f"Delta={dlta:+.0f}")
        if nc:               parts.append(f"NC=${nc:,.0f}")
        if ml:               parts.append(f"MaxLoss=${ml:,.0f}")
        if lw:               parts.append(f"LwBE={lw:.1f}")
        if up:               parts.append(f"UpBE={up:.1f}")
        lines.append(" | ".join(parts))

    lines.append("")
    lines.append(f"CLOSED TRADES ({len(closed)}) — sorted by impact:")
    closed_s = sorted([t for t in closed if t.get("pnl_current") is not None],
                      key=lambda x: abs(x["pnl_current"]), reverse=True)
    for t in closed_s:
        pnl = t.get("pnl_current")
        pct = t.get("pnl_pct_max")
        nc  = t.get("net_credit")
        result = "WIN" if (pnl or 0) > 0 else "LOSS"
        line = f"  [{result}] {t['name']}: ${pnl:+,.0f}"
        if pct is not None: line += f" ({pct:+.0f}% max)"
        if nc:               line += f" | NC=${nc:,.0f}"
        lines.append(line)

    lines += [
        "",
        "YOUR ROLE:",
        "- Be concise, professional, and strictly data-driven.",
        "- Only reference data provided above. Never hallucinate prices or metrics.",
        "- When analyzing a trade, always consider: DTE urgency, P&L%, Delta exposure, and structural risk.",
        "- Flag immediately anything at stop loss or critical DTE.",
        "- Provide actionable recommendations (close, hold, roll, adjust).",
        "- When asked about correlations, analyze the full book for common risk factors.",
    ]
    return "\n".join(lines)


# ─── AI streaming ─────────────────────────────────────────────────────────────

def stream_ai_response(messages: list[dict], system_prompt: str):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        yield "Configure `ANTHROPIC_API_KEY` to enable AI analysis."
        return
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=system_prompt,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield text
    except Exception as e:
        yield f"Error: {e}"


# ─── Tab renderer ─────────────────────────────────────────────────────────────

def render_tab(trades_env: list[dict], history: pd.DataFrame,
               env_norm: str, env_label: str, gen_dt: str,
               monthly_summaries: list[dict],
               individual_trade_pnls: dict | None = None):

    k = compute_kpis(trades_env, history, monthly_summaries)
    active = k["active_list"]
    closed = k["closed_list"]

    # ── Alerts ──
    if k["alerts"]:
        with st.expander(f"⚠️  {len(k['alerts'])} alert(s)", expanded=True):
            for color, msg in k["alerts"]:
                css = {"red": "alert-red", "green": "alert-grn", "yellow": "alert-ylw"}[color]
                st.markdown(f'<div class="{css}">{msg}</div>', unsafe_allow_html=True)

    # ── KPIs Row 1: P&L Overview ──
    st.markdown('<div class="section-title">P&L Overview</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)

    v, col = fmt(k["open_pnl"])
    c1.markdown(kpi("Open PnL", v, f"{k['n_active']} active position(s)", col), unsafe_allow_html=True)

    v, col = fmt(k["rlzd"])
    c2.markdown(kpi("Realized PnL", v, f"{k['n_closed']} closed trade(s)", col), unsafe_allow_html=True)

    v, col = fmt(k["total_pnl"])
    c3.markdown(kpi("Total P&L", v, "Open + Realized", col), unsafe_allow_html=True)

    v, _ = fmt(k["delta"], prefix="", sign=True)
    dl = abs(k["delta"])
    col = "c-red" if dl > 150 else "c-yellow" if dl > 80 else "c-blue"
    sub = "DANGER: high directional bias" if dl > 150 else "CAUTION" if dl > 80 else "Balanced"
    c4.markdown(kpi("Portfolio Delta", v, sub, col), unsafe_allow_html=True)

    # ── KPIs Row 2: Risk Management ──
    st.markdown('<div class="section-title">Risk Management</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)

    v = f"${k['max_loss_exp']:,.0f}" if k['max_loss_exp'] else "—"
    c1.markdown(kpi("Max Loss Exposed", v, "sum of active max losses", "c-yellow"), unsafe_allow_html=True)

    v = f"${k['nc_risk']:,.0f}" if k['nc_risk'] else "—"
    c2.markdown(kpi("Net Credit at Risk", v, "premium on active trades", "c-blue"), unsafe_allow_html=True)

    v = f"${k['theta_daily']:,.0f}/day" if k['theta_daily'] else "—"
    c3.markdown(kpi("Est. Daily Theta", v, "approx. time decay earned/day", "c-purple"), unsafe_allow_html=True)

    exp14 = k["expiring_14"]
    exp7  = k["expiring_7"]
    col_e = "c-red" if exp7 > 0 else "c-yellow" if exp14 > 0 else "c-green"
    sub_e = f"{exp7} in ≤7 DTE" if exp7 > 0 else "No urgent expirations"
    c4.markdown(kpi("Expiring ≤14 DTE", str(exp14), sub_e, col_e), unsafe_allow_html=True)

    # ── KPIs Row 3: Performance ──
    st.markdown('<div class="section-title">Performance Metrics</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)

    wr = k["win_rate"]
    v  = f"{wr:.1f}%" if wr is not None else "—"
    wl_wins   = sum(1 for p in [t.get("pnl_current") for t in closed if t.get("pnl_current") is not None] if p > 0)
    wl_losses = sum(1 for p in [t.get("pnl_current") for t in closed if t.get("pnl_current") is not None] if p <= 0)
    col = "c-green" if (wr or 0) >= 60 else "c-yellow" if (wr or 0) >= 50 else "c-red"
    c1.markdown(kpi("Win Rate", v, f"{wl_wins}W / {wl_losses}L", col), unsafe_allow_html=True)

    pf  = k["profit_factor"]
    v   = f"{pf:.2f}" if pf is not None else "—"
    col = "c-green" if (pf or 0) >= 1.5 else "c-yellow" if (pf or 0) >= 1.0 else "c-red"
    sub = "Excellent" if (pf or 0) >= 2 else "Good" if (pf or 0) >= 1.5 else "Marginal" if (pf or 0) >= 1 else "Negative edge"
    c2.markdown(kpi("Profit Factor", v, sub, col), unsafe_allow_html=True)

    v, col = fmt(k["avg_win"])
    c3.markdown(kpi("Avg Winner", v, "avg closed winning trade", col), unsafe_allow_html=True)

    v, col = fmt(k["avg_loss"])
    c4.markdown(kpi("Avg Loser", v, "avg closed losing trade", col), unsafe_allow_html=True)

    # ── KPIs Row 4: Trade Intelligence ──
    st.markdown('<div class="section-title">Trade Intelligence</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)

    exp = k["expectancy"]
    v, col = fmt(exp)
    sub_exp = "Positive edge" if (exp or 0) > 0 else "Negative edge"
    c1.markdown(kpi("Expectancy", v, f"{sub_exp} per trade", col), unsafe_allow_html=True)

    rr = k["rr_ratio"]
    v  = f"{rr:.2f}x" if rr is not None else "—"
    col = "c-green" if (rr or 0) >= 1 else "c-yellow"
    c2.markdown(kpi("Risk / Reward", v, "avg win / avg loss", col), unsafe_allow_html=True)

    v, col = fmt(k["best_trade"])
    c3.markdown(kpi("Best Trade", v, "", col), unsafe_allow_html=True)

    v, col = fmt(k["worst_trade"])
    c4.markdown(kpi("Worst Trade", v, "", col), unsafe_allow_html=True)

    # ── Monthly Breakdown ──
    if monthly_summaries:
        st.markdown('<div class="section-title">Monthly Breakdown (Sheet TOTAL Rows)</div>',
                    unsafe_allow_html=True)
        rows_m = []
        for m in monthly_summaries:
            op = m["open_pnl"]; rz = m["rlzd"]
            dl = m["delta"];    mp = m["max_profit"]
            rows_m.append({
                "Month":       m["month"],
                "Open PnL":    f"${op:+,.0f}" if op else "—",
                "Realized":    f"${rz:+,.0f}" if rz else "—",
                "Total":       f"${op+rz:+,.0f}",
                "Delta":       f"{dl:+.0f}" if dl else "—",
                "Max Profit":  f"${mp:,.0f}" if mp else "—",
            })
        # Totals row
        tot_op = sum(m["open_pnl"] for m in monthly_summaries)
        tot_rz = sum(m["rlzd"]     for m in monthly_summaries)
        tot_dl = sum(m["delta"]    for m in monthly_summaries)
        rows_m.append({
            "Month": "TOTAL",
            "Open PnL":  f"${tot_op:+,.0f}",
            "Realized":  f"${tot_rz:+,.0f}",
            "Total":     f"${tot_op+tot_rz:+,.0f}",
            "Delta":     f"{tot_dl:+.0f}",
            "Max Profit": "—",
        })
        st.dataframe(pd.DataFrame(rows_m), use_container_width=True, hide_index=True)

    # ── Charts ──
    st.markdown('<div class="section-title">Analytics</div>', unsafe_allow_html=True)
    ch1, ch2 = st.columns(2)
    with ch1:
        st.plotly_chart(chart_equity(history, env_norm, individual_trade_pnls),
                        use_container_width=True, config={"displayModeBar": False})
    with ch2:
        st.plotly_chart(chart_monthly_pnl(monthly_summaries),
                        use_container_width=True, config={"displayModeBar": False})

    ch3, ch4 = st.columns(2)
    with ch3:
        st.plotly_chart(chart_win_loss_donut(k),
                        use_container_width=True, config={"displayModeBar": False})
    with ch4:
        if active:
            st.plotly_chart(chart_active_pct(active),
                            use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No active trades.")

    if active:
        st.plotly_chart(chart_dte_countdown(active),
                        use_container_width=True, config={"displayModeBar": False})

    if closed:
        st.plotly_chart(chart_closed_pnl(closed),
                        use_container_width=True, config={"displayModeBar": False})

    # ── Active trades detail ──
    if active:
        st.markdown('<div class="section-title">Active Positions — Detail</div>',
                    unsafe_allow_html=True)
        for t in sorted(active, key=lambda x: x.get("pnl_pct_max") or 0):
            pnl  = t.get("pnl_current")
            pct  = t.get("pnl_pct_max")
            dte  = t.get("dte_remaining")
            dlta = t.get("delta_current")
            nc   = t.get("net_credit")
            ml   = t.get("max_loss")
            lw   = t.get("lw_be")
            up   = t.get("up_be")
            sd   = t.get("sd")

            pnl_s = f"${pnl:+,.0f}" if pnl is not None else "—"
            pct_s = f"{pct:+.0f}%"  if pct is not None else "—"
            dte_s = f"{dte}d"        if dte is not None else "—"

            icon = "🔴" if (pct or 0) <= -100 else "🟡" if (pct or 0) < 0 else "🟢"
            with st.expander(
                f"{icon}  **{t['name']}** — PnL: {pnl_s} ({pct_s}) | DTE: {dte_s}",
                expanded=bool(t.get("alert_stop") or t.get("alert_dte"))
            ):
                m1, m2, m3, m4, m5, m6 = st.columns(6)
                m1.metric("PnL",          pnl_s)
                m2.metric("% Max Profit", pct_s)
                m3.metric("Delta",        f"{dlta:+.0f}" if dlta is not None else "—")
                m4.metric("DTE",          dte_s)
                m5.metric("Net Credit",   f"${nc:,.0f}"  if nc   else "—")
                m6.metric("Max Loss",     f"${ml:,.0f}"  if ml   else "—")
                m7, m8, m9 = st.columns(3)
                m7.metric("Lower BE",     f"{lw:.1f}" if lw else "—")
                m8.metric("Upper BE",     f"{up:.1f}" if up else "—")
                m9.metric("SD",           f"{sd:.1%}" if sd else "—")
                if t.get("strikes"):
                    st.caption(f"Strikes: {t['strikes']}")
                if t.get("underlying_price_at_open"):
                    st.caption(f"Underlying at open: {t['underlying_price_at_open']}")

    # ── Closed trades table ──
    if closed:
        st.markdown('<div class="section-title">Closed Trades</div>', unsafe_allow_html=True)
        rows_c = []
        for t in sorted(closed, key=lambda x: x.get("pnl_current") or 0, reverse=True):
            pnl = t.get("pnl_current")
            pct = t.get("pnl_pct_max")
            nc  = t.get("net_credit")
            ml  = t.get("max_loss")
            rows_c.append({
                "Trade":       t["name"],
                "Result":      "WIN"  if (pnl or 0) > 0 else "LOSS",
                "Final PnL":   f"${pnl:+,.0f}" if pnl is not None else "—",
                "% of Max":    f"{pct:+.0f}%"  if pct is not None else "—",
                "Net Credit":  f"${nc:,.0f}"   if nc  else "—",
                "Max Loss":    f"${ml:,.0f}"   if ml  else "—",
            })
        st.dataframe(pd.DataFrame(rows_c), use_container_width=True, hide_index=True)

    # ── AI Chat ──
    st.markdown('<div class="section-title">AI Portfolio Analyst</div>', unsafe_allow_html=True)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        st.warning("Set `ANTHROPIC_API_KEY` environment variable to enable AI analysis.")
    else:
        chat_key = f"chat_{env_norm}"
        if chat_key not in st.session_state:
            st.session_state[chat_key] = []

        # Quick question buttons
        quick_qs = [
            "Which trades need immediate attention?",
            "Analyze the worst performing trades",
            "Are there correlation risks in this book?",
            "Recommend management actions for each active trade",
            "How is the overall book performing vs. the strategy?",
        ]
        st.markdown("**Quick questions:**")
        cols = st.columns(len(quick_qs))
        for i, q in enumerate(quick_qs):
            if cols[i].button(q, key=f"qq_{env_norm}_{i}", use_container_width=True):
                st.session_state[chat_key].append({"role": "user", "content": q})

        # Chat history display
        for msg in st.session_state[chat_key]:
            with st.chat_message(msg["role"],
                                 avatar="🧑‍💼" if msg["role"] == "user" else "🤖"):
                st.markdown(msg["content"])

        # Chat input
        if prompt := st.chat_input(
            f"Ask anything about the {env_label} portfolio...",
            key=f"chat_input_{env_norm}"
        ):
            st.session_state[chat_key].append({"role": "user", "content": prompt})
            with st.chat_message("user", avatar="🧑‍💼"):
                st.markdown(prompt)

        # Generate response for last unanswered user message
        history_msgs = st.session_state[chat_key]
        if history_msgs and history_msgs[-1]["role"] == "user":
            system_prompt = build_ai_system_prompt(trades_env, k, env_label)
            # Only pass last 10 messages to keep context manageable
            api_messages = [{"role": m["role"], "content": m["content"]}
                            for m in history_msgs[-10:]]
            with st.chat_message("assistant", avatar="🤖"):
                response = st.write_stream(stream_ai_response(api_messages, system_prompt))
            st.session_state[chat_key].append({"role": "assistant", "content": response})

        # Clear chat button
        if st.session_state[chat_key]:
            if st.button("Clear conversation", key=f"clear_{env_norm}"):
                st.session_state[chat_key] = []
                st.rerun()

    # ── Downloads ──
    st.markdown('<div class="section-title">Export</div>', unsafe_allow_html=True)
    d1, d2 = st.columns(2)
    snapshot_json = json.dumps(
        {"environment": env_label, "generated_at": gen_dt,
         "kpis": {kk: vv for kk, vv in k.items()
                  if kk not in ("active_list", "closed_list", "alerts", "monthly_summaries")},
         "trades": trades_env},
        ensure_ascii=False, indent=2, default=str
    )
    d1.download_button(
        "Download JSON", snapshot_json,
        file_name=f"snapshot_{env_norm}_{gen_dt[:10]}.json",
        mime="application/json", use_container_width=True,
    )
    if closed:
        df_c = pd.DataFrame([{
            "trade": t["name"], "result": "WIN" if (t.get("pnl_current") or 0) > 0 else "LOSS",
            "pnl": t.get("pnl_current"), "pct_max": t.get("pnl_pct_max"),
            "net_credit": t.get("net_credit"),
        } for t in closed])
        d2.download_button(
            "Download Closed Trades CSV",
            df_c.to_csv(index=False).encode("utf-8"),
            file_name=f"closed_{env_norm}_{gen_dt[:10]}.csv",
            mime="text/csv", use_container_width=True,
        )


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    snapshot = load_snapshot()
    history  = load_history()

    if snapshot is None:
        st.error("Snapshot not found. Run: `python scripts/export_control_panel.py --gdrive-id YOUR_ID`")
        st.stop()

    trades                = snapshot.get("trades", [])
    gen_dt                = snapshot.get("generated_at", "")
    sheet_summaries       = snapshot.get("sheet_summaries", {})
    individual_trade_pnls = snapshot.get("individual_trade_pnls", {})

    cz_live    = [t for t in trades if t["environment"] == "CZ_Live"]
    js_fwd     = [t for t in trades if t["environment"] == "JS_Forward"]
    cz_monthly = sheet_summaries.get("CZ_Live",    [])
    js_monthly = sheet_summaries.get("JS_Forward", [])

    # ── Header ──
    col_h, col_r = st.columns([3, 1])
    col_h.markdown("## Prop Desk — Options Control Panel")
    col_h.markdown(
        f"<small style='color:#8892a4'>Last update: {gen_dt[:10]} &nbsp;|&nbsp; "
        f"Source: {snapshot.get('source_file','')}</small>",
        unsafe_allow_html=True
    )
    col_r.markdown(
        f"<div style='text-align:right; padding-top:14px'>"
        f"<span style='color:#8892a4; font-size:12px'>CZ Live: {len(cz_live)} trades</span><br>"
        f"<span style='color:#8892a4; font-size:12px'>JS Forward: {len(js_fwd)} trades</span>"
        f"</div>",
        unsafe_allow_html=True
    )
    st.markdown("---")

    # ── Tabs ──
    tab_cz, tab_js = st.tabs(["📈  CZ — Live Trading", "🔬  JS — Forward Test"])

    with tab_cz:
        if not cz_live and not cz_monthly:
            st.info("No CZ Live trades found in snapshot.")
        else:
            render_tab(cz_live, history, "CZ_Live", "CZ Live Trading", gen_dt, cz_monthly,
                       individual_trade_pnls=individual_trade_pnls)

    with tab_js:
        if not js_fwd and not js_monthly:
            st.info("No JS Forward trades found in snapshot.")
        else:
            render_tab(js_fwd, history, "JS_Forward", "JS Forward Test", gen_dt, js_monthly)

    # ── Footer ──
    st.markdown("---")
    st.markdown(
        "<center><small style='color:#8892a4'>"
        "Prop Desk Quant &nbsp;|&nbsp; Data: OptionStrat via Make "
        "&nbsp;|&nbsp; AI: Claude Sonnet 4.6</small></center>",
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
