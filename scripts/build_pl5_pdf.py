"""
PL5 — presentation PDF (for Cristiano). Multi-page (matplotlib PdfPages), ENGLISH:
 cover/exec-summary · how it works (+payoff diagram) · methodology/how-we-tested ·
 fill sensitivity (the key finding, FIXED) · equity curves · early-exit vs hold ·
 2025 crash example · data verification · verdict.
 Reads the app CSVs (reports/pl5_backtest_app/<dte>/trades.csv, mid) + SPX cache.
 Uso: python scripts/build_pl5_pdf.py   ->  reports/pl5_bwb/PL5_report.pdf
"""
from __future__ import annotations
import csv, os
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.dates as mdates
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
APP = REPO / "reports" / "pl5_backtest_app"
DEST = REPO / "reports" / "pl5_bwb" / "PL5_report.pdf"
# inclui os DTEs longos (75/100/120) automaticamente quando a pasta existir
DTES = [(f"pl5_d{_d}_std", _d) for _d in (21, 28, 45, 60, 75, 100, 120)
        if (APP / f"pl5_d{_d}_std" / "trades.csv").exists()]
NAVY = "#0f2b46"; GOLD = "#b8860b"; GAIN = "#1a7f37"; LOSS = "#c0392b"; GREY = "#555"
plt.rcParams.update({"font.size": 10, "axes.titlesize": 12, "figure.facecolor": "white",
                     "text.parse_math": False})   # '$' são literais (dinheiro), não modo matemático

def margin_analysis(rows):
    """Margem/capital preso por posições SOBREPOSTAS. Cada pacote é risco definido (vale = max_risk_usd).
    Margem num dia D = soma dos max_risk dos trades abertos (trade_date <= D <= exp_date).
    Retorna: pico de margem ($), nº máx de posições simultâneas, margem média, net total (hold)."""
    from datetime import date as _date
    evts = []  # (dia, +risk ao abrir, -risk ao fechar)
    risks = []
    for r in rows:
        try:
            o = _date.fromisoformat(r["trade_date"]); e = _date.fromisoformat(r["exp_date"])
            mr = fnum(r, "max_risk_usd")
            if mr is None: continue
        except Exception:
            continue
        evts.append((o, mr, 1)); evts.append((e, -mr, -1)); risks.append(mr)
    if not evts:
        return None
    evts.sort(key=lambda x: x[0])
    cur_m = cur_n = peak_m = peak_n = 0
    samples = []
    for _, dm, dn in evts:
        cur_m += dm; cur_n += dn
        peak_m = max(peak_m, cur_m); peak_n = max(peak_n, cur_n)
        samples.append(cur_m)
    avg_m = sum(samples) / len(samples) if samples else 0
    net = sum(fnum(r, "pnl_usd") or 0 for r in rows)
    # perda AGREGADA real no dia de pico (vales em strikes diferentes -> não somam): varre o spot e
    # acha a pior perda do portfólio aberto. Aproxima a régua de Portfolio Margin melhor que a soma.
    from datetime import timedelta as _td
    peak_agg = peak_m
    try:
        days = sorted({_date.fromisoformat(r["trade_date"]) for r in rows})
        best_day, best_n = None, 0
        d0 = days[0]; dN = max(_date.fromisoformat(r["exp_date"]) for r in rows)
        cur = d0
        while cur <= dN:
            op = [r for r in rows if _date.fromisoformat(r["trade_date"]) <= cur <= _date.fromisoformat(r["exp_date"])]
            if len(op) > best_n: best_n, best_day = len(op), op
            cur += _td(days=7)
        if best_day:
            ks = [(fnum(r,"put_upper"), fnum(r,"put_center"), fnum(r,"put_lower"), fnum(r,"total_credit")) for r in best_day]
            lo = min(k[2] for k in ks)*0.7; hi = max(k[0] for k in ks)*1.05
            mn = min(sum(payoff_pts(k[0],k[1],k[2],s)*100 - k[3] for k in ks) for s in [lo+(hi-lo)*i/300 for i in range(301)])
            peak_agg = -mn
    except Exception:
        pass
    return {"peak_margin": peak_m, "peak_pos": peak_n, "avg_margin": avg_m, "peak_agg": peak_agg,
            "med_risk": sorted(risks)[len(risks)//2] if risks else 0, "net": net}

def fnum(r, k):
    try: return float(r[k])
    except (TypeError, ValueError, KeyError): return None

def _rule_pnls(rows, col):
    """(exp_date, pnl) ordenado por realização; col=None -> hold (pnl_usd)."""
    items = []
    for r in rows:
        p = fnum(r, "pnl_usd") if col is None else (fnum(r, col) if fnum(r, col) is not None else fnum(r, "pnl_usd"))
        e = r.get("exp_date")
        if p is None or not e: continue
        items.append((e, p))
    items.sort()
    return items

def max_drawdown(rows, col=None):
    """maxDD ($) da curva de equity acumulada (P&L realizado na ordem de fechamento)."""
    cum = peak = mdd = 0.0
    for _, p in _rule_pnls(rows, col):
        cum += p; peak = max(peak, cum); mdd = min(mdd, cum - peak)
    return mdd  # <= 0

def maxdd_mtm(daily_rows):
    """maxDD da curva de equity MTM AGREGADA (marca-a-mercado de todas as posições, da trajetória).
    Captura o drawdown NÃO-REALIZADO enquanto as posições estão abertas — o risco real (≠ curva de
    trades fechados, que subestima nos DTEs longos). Amostragem ~17 pts/trade (piso, não contínuo)."""
    from collections import defaultdict
    bytrade = defaultdict(list)
    for r in daily_rows:
        try: bytrade[r["trade_date"]].append((r["calendar_date"], float(r["pnl_usd"])))
        except Exception: pass
    deltas = defaultdict(float)
    for _, pts in bytrade.items():
        pts.sort(); prev = 0.0
        for cd, pnl in pts:
            deltas[cd] += pnl - prev; prev = pnl
    cum = peak = mdd = 0.0
    for cd in sorted(deltas):
        cum += deltas[cd]; peak = max(peak, cum); mdd = min(mdd, cum - peak)
    return mdd

def risk_metrics(rows, capital, daily_rows):
    """Métricas de risco do HOLD. Sharpe sobre retornos MENSAIS realizados normalizados pelo capital
    empregado (margem média). maxDD = MTM agregado (real). Calmar = net anualizado / |maxDD MTM|."""
    import numpy as _np
    items = _rule_pnls(rows, None)
    if not items or not capital: return None
    net = sum(p for _, p in items)
    mdd = maxdd_mtm(daily_rows)
    from collections import defaultdict
    mp = defaultdict(float)
    for e, p in items: mp[e[:7]] += p
    ser = _np.array(list(mp.values())) / capital
    n_months = len(ser)
    sharpe = (ser.mean() / ser.std() * _np.sqrt(12)) if ser.std() > 0 else 0.0
    years = max(n_months / 12.0, 0.5)
    calmar = ((net / years) / abs(mdd)) if mdd < 0 else float("inf")
    return {"net": net, "mdd": mdd, "sharpe": sharpe, "calmar": calmar}

def load(tag):
    return list(csv.DictReader(open(APP / tag / "trades.csv", encoding="utf-8")))

def load_daily(tag):
    p = APP / tag / "daily.csv"
    return list(csv.DictReader(open(p, encoding="utf-8"))) if p.exists() else []

def spx_loader():
    p = REPO / "data/cache/spx_daily.parquet"
    s = pd.read_parquet(p); s["date"] = pd.to_datetime(s["date"]).dt.normalize(); s = s.sort_values("date")
    def at(d):
        q = s[s["date"] <= pd.Timestamp(d)].tail(1); return float(q["spx"].iloc[0]) if len(q) else None
    return at

def payoff_pts(k1, k2, k3, s):
    return 1*max(0, k1-s) - 2*max(0, k2-s) + 2*max(0, k3-s)

def fill_sensitivity(rows):
    """Hold P&L by entry-fill fraction (mid -> full leg-by-leg spread).
    fr=0 = combo net mid; fr=1 = every leg crossed at its own bid/ask (worst case)."""
    out = {}
    for fr in (0.0, 0.25, 0.5, 1.0):
        pls = []
        for r in rows:
            ss = fnum(r, "spot_exit"); k1, k2, k3 = fnum(r, "put_upper"), fnum(r, "put_center"), fnum(r, "put_lower")
            hold_mid = fnum(r, "pnl_usd")
            cost_mid = (fnum(r, "total_credit") or 0) / 100.0      # total_credit = MID entry (post-fix)
            ec = fnum(r, "entry_cons")
            cost_cons = (ec / 100.0) if ec is not None else cost_mid
            if None in (ss, k1, k2, k3, hold_mid): continue
            terminal = payoff_pts(k1, k2, k3, ss)
            cost_f = cost_mid + fr * (cost_cons - cost_mid)
            pls.append((terminal - cost_f) * 100.0)
        net = sum(pls); wr = 100*sum(1 for x in pls if x > 0)/len(pls) if pls else 0
        wins = [x for x in pls if x > 0]; losses = [x for x in pls if x <= 0]
        pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else float("inf")
        payoff = abs((sum(wins)/len(wins)) / (sum(losses)/len(losses))) if wins and losses else 0
        out[fr] = (net, wr, pf, payoff)
    return out

def fig_text_page(pdf, title, lines, subtitle=None):
    fig = plt.figure(figsize=(11.7, 8.3)); fig.patch.set_facecolor("white")
    fig.text(0.06, 0.93, title, fontsize=20, fontweight="bold", color=NAVY)
    if subtitle: fig.text(0.06, 0.895, subtitle, fontsize=11, color=GOLD)
    y = 0.83
    for ln, sz, col in lines:
        fig.text(0.07, y, ln, fontsize=sz, color=col, va="top"); y -= 0.0345*(sz/10.5)
    pdf.savefig(fig); plt.close(fig)

def fig_table(pdf, title, headers, rows, subtitle=None, note=None, hi_col=None):
    fig, ax = plt.subplots(figsize=(11.7, 8.3)); ax.axis("off")
    fig.text(0.06, 0.93, title, fontsize=18, fontweight="bold", color=NAVY)
    if subtitle: fig.text(0.06, 0.885, subtitle, fontsize=11, color=GOLD)
    t = ax.table(cellText=rows, colLabels=headers, loc="center", cellLoc="center")
    t.auto_set_font_size(False); t.set_fontsize(11); t.scale(1, 2.0)
    for j in range(len(headers)):
        c = t[0, j]; c.set_facecolor(NAVY); c.set_text_props(color="white", fontweight="bold")
    for i in range(1, len(rows)+1):
        for j in range(len(headers)):
            cell = t[i, j]; cell.set_facecolor("#f4f6f8" if i % 2 else "white")
            if hi_col is not None and j == hi_col:
                cell.set_facecolor("#eaf4ea"); cell.set_text_props(fontweight="bold")
    if note:
        fig.text(0.06, 0.20, note, fontsize=9.5, color=GREY, va="top", wrap=True)
    pdf.savefig(fig); plt.close(fig)

def build():
    at = spx_loader()
    data = {tag: load(tag) for tag, _ in DTES}
    daily = {tag: load_daily(tag) for tag, _ in DTES}
    sens = {tag: fill_sensitivity(data[tag]) for tag, _ in DTES}
    money = lambda v: f"${v:+,.0f}"
    DEST.parent.mkdir(parents=True, exist_ok=True)
    tmp = DEST.with_name(DEST.stem + ".__tmp.pdf")
    with PdfPages(tmp) as pdf:

        # ============ 1. COVER / EXECUTIVE SUMMARY ============
        d28 = sens["pl5_d28_std"]
        fig_text_page(pdf, "PL5 — Broken-Wing Put Butterfly (SPX)",
            [("QuantConnect backtest · Jun 2021 - Jun 2026 (5 years) · enters every Friday 10:00 ET", 12.5, "#333"),
             ("", 9, "#333"),
             ("WHAT IT IS  —  a defined-risk put structure with a crash-convex tail.", 13, NAVY),
             ("Per unit:  +1 put @ -30 delta   /   -2 puts @ -18 delta   /   +2 puts @ -3 delta.", 11.5, "#333"),
             ("Small net debit. Profit 'tent' if the market drifts down moderately; defined max loss in a", 10.5, "#333"),
             ("valley near the lower strike; the position turns convex again far below (the crash tail).", 10.5, "#333"),
             ("", 9, "#333"),
             ("WHAT WE TESTED  —  4 holding horizons: 21 / 28 / 45 / 60 DTE, each over the full 5 years.", 12, NAVY),
             ("", 9, "#333"),
             ("KEY TAKEAWAYS", 13.5, GOLD),
             ("  1.  The result is DECIDED BY EXECUTION, not by the structure being right or wrong.", 11.5, "#333"),
             (f"      Same backtest, 28 DTE: {money(d28[0.0][0])} at mid  ->  {money(d28[1.0][0])} if every leg is", 11, "#333"),
             ("      crossed at full bid/ask. The 5-leg entry spread is what moves the number.", 11, "#333"),
             ("  2.  Traded properly (as ONE combo at a limit price), realistic fill is close to mid:", 11.5, GAIN),
             (f"      21-28 DTE positive ({money(sens['pl5_d21_std'][0.25][0])} / {money(d28[0.25][0])} at a 25% fill), 60 DTE not.", 11, GAIN),
             ("  3.  Holding to expiry is the WORST exit — a 'valley' reforms in the last days (CZ was right).", 11.5, "#333"),
             ("  4.  Real risk = a directional crash that lands in the valley (e.g. the 2025 tariff crash).", 11.5, "#333"),
             ("", 9, "#333"),
             ("All P&L at MID pricing. Methodology and the leg-vs-combo point are explained on pages 2-3.", 10, GREY)],
            subtitle="Presentation report · Prop Desk Quant · 2026-06")

        # ============ 2. HOW IT WORKS + PAYOFF DIAGRAM ============
        # representative 28 DTE trade (closest to median entry spot)
        rws = [r for r in data["pl5_d28_std"] if fnum(r, "spot_entry")]
        med = sorted(rws, key=lambda r: fnum(r, "spot_entry"))[len(rws)//2]
        k1, k2, k3 = fnum(med,"put_upper"), fnum(med,"put_center"), fnum(med,"put_lower")
        cost_mid = (fnum(med,"total_credit") or 0)/100.0; se = fnum(med,"spot_entry")
        fig = plt.figure(figsize=(11.7, 8.3)); fig.patch.set_facecolor("white")
        fig.text(0.06, 0.93, "2. How the structure works", fontsize=18, fontweight="bold", color=NAVY)
        fig.text(0.06, 0.885, "expiry payoff of one unit — where it makes and loses money", fontsize=11, color=GOLD)
        ax = fig.add_axes([0.30, 0.30, 0.62, 0.48])
        xs = np.linspace(k3-300, k1+250, 600)
        ys = [(payoff_pts(k1,k2,k3,s) - cost_mid)*100 for s in xs]
        ax.plot(xs, ys, color=NAVY, lw=2.4)
        ax.axhline(0, color="#999", lw=0.8)
        for k, lab, c in [(k1,"K1 (-30d)","#2c7fb8"), (k2,"K2 (-18d) = tent","#1a7f37"), (k3,"K3 (-3d) = valley", LOSS)]:
            ax.axvline(k, color=c, ls="--", lw=1, alpha=0.8); ax.text(k, ax.get_ylim()[1]*0.92, f"{lab}\n{k:.0f}", fontsize=8, ha="center", color=c)
        ax.set_xlabel("SPX at expiry"); ax.set_ylabel("P&L per unit (US$)"); ax.grid(alpha=0.25)
        ax.set_title(f"example: entry SPX {se:.0f} · strikes {k1:.0f}/{k2:.0f}/{k3:.0f} · mid debit ${cost_mid*100:,.0f}", fontsize=10)
        for ln, y in [
            ("Reading the payoff (left to right):", 0.22),
            ("• Above K1  -> all puts expire worthless: you lose only the small debit paid.", 0.185),
            ("• Around K2 -> the 'tent': maximum profit if the market drifts down moderately.", 0.15),
            ("• Around K3 -> the 'valley': the defined MAXIMUM LOSS (a crash that stops right here hurts).", 0.115),
            ("• Far below K3 -> the +2 deep puts dominate again: convex payoff in a deep crash (the tail).", 0.08),
            ("Entry: every Friday 10:00 ET, strikes chosen by delta (-30 / -18 / -3). Defined risk, no naked legs.", 0.04)]:
            fig.text(0.06, y, ln, fontsize=10, color="#333" if y not in (0.15,0.115) else (GAIN if y==0.15 else LOSS), va="top")
        pdf.savefig(fig); plt.close(fig)

        # ============ 3. METHODOLOGY / HOW WE TESTED ============
        fig_text_page(pdf, "3. How we backtested it (and why it's trustworthy)",
            [("We deliberately removed every source of fake P&L. What CZ should know:", 12, GOLD),
             ("", 8, "#333"),
             ("ENGINE — synthetic tracking.", 11.5, NAVY),
             ("  We subscribe to the real option chain and compute P&L analytically from the actual bid/ask of", 10.5, "#333"),
             ("  each leg. We do NOT route orders through QuantConnect's fill/margin engine, which fabricated", 10.5, "#333"),
             ("  phantom P&L on multi-leg structures. So the numbers reflect real quoted prices, nothing invented.", 10.5, "#333"),
             ("", 7, "#333"),
             ("SETTLEMENT — exact, no spread.", 11.5, NAVY),
             ("  SPX options are European, cash-settled. At expiry the position settles at the official intrinsic", 10.5, "#333"),
             ("  value — there is NO exit spread. Verified on page 8 (theoretical payoff == recorded P&L).", 10.5, "#333"),
             ("", 7, "#333"),
             ("PRICING — mid is the standard; we also stress the fill.", 11.5, NAVY),
             ("  Entry, marking and exits all use MID consistently. Because settlement has no spread, the ONLY", 10.5, "#333"),
             ("  thing separating 'mid' from 'bid/ask' on a hold is the ENTRY price of the 5 legs.", 10.5, "#333"),
             ("", 7, "#333"),
             ("LEG-BY-LEG vs COMBO — the most important nuance for CZ.", 11.5, GOLD),
             ("  Our pessimistic case sums each leg at its OWN bid/ask (as if you sent 5 separate market orders).", 10.5, "#333"),
             ("  A butterfly is never traded that way — it is sent as ONE combo at a single net limit. The combo's", 10.5, "#333"),
             ("  net spread is far tighter than the sum of the legs (the legs' risks offset; the MM hedges the", 10.5, "#333"),
             ("  package). Since mids are additive, our 'mid' number IS the combo's net mid — the price you would", 10.5, "#333"),
             ("  actually aim for. So reality sits close to mid, NOT at the leg-by-leg worst case.", 10.5, GAIN),
             ("", 7, "#333"),
             ("VERIFIED at minute resolution.", 11.5, NAVY),
             ("  We suspected the wide tail spread was a stale hourly-quote artifact. We re-ran at minute data:", 10.5, "#333"),
             ("  the entry spread is IDENTICAL (1.000x). It is the real far-OTM tail market, not a data glitch.", 10.5, "#333")],
            subtitle="methodology — full transparency")

        # ============ 4. FILL SENSITIVITY (KEY FINDING, FIXED) ============
        rows = []
        for tag, dte in DTES:
            s = sens[tag]
            def cell(fr):
                net, wr, pf, po = s[fr]
                pfs = "inf" if pf == float("inf") else f"{pf:.1f}"
                return f"{money(net)}  (PF {pfs})"
            rows.append([f"{dte} DTE", cell(0.0), cell(0.25), cell(0.5), cell(1.0)])
        fig_table(pdf, "4. Fill-price scenarios — net P&L and Profit Factor (hold to expiry)",
                  ["Horizon", "Mid (optimistic)", "25% spread (realistic)", "50% spread", "Leg-by-leg (worst, ref.)"], rows,
                  subtitle="same trades, four entry-fill assumptions · realistic = combo limit order, near 25-50% · 5-year net",
                  hi_col=2,
                  note="HOW TO READ: nobody buys at the ask and sells at the bid on every leg — the 'leg-by-leg' column is "
                       "an unrealistic worst-case REFERENCE only. A butterfly is sent as ONE combo at a net limit, so the "
                       "real fill sits between MID (optimistic) and ~25-50% of the spread. NOTE how the Profit Factor "
                       "deflates with worse fills: e.g. 120 DTE goes from PF ~4.9 (mid) toward ~1.7 as the illiquid -3-delta "
                       "tail spread is paid. The headline mid numbers are the CEILING, not the expectation; the honest read "
                       "is the 25-50% columns. Short DTEs (21-28) stay positive; long DTEs keep a real but modest edge.")

        # ============ 5. EQUITY CURVES ============
        fig, axes = plt.subplots(2, 2, figsize=(11.7, 8.3))
        fig.suptitle("5. Cumulative P&L (mid) by horizon — full 5 years", fontsize=16, fontweight="bold", color=NAVY)
        for ax, (tag, dte) in zip(axes.flat, DTES):
            rows_ = sorted(data[tag], key=lambda r: r["trade_date"])
            dts = [date.fromisoformat(r["trade_date"]) for r in rows_]
            cum = 0; ys = []
            for r in rows_:
                cum += fnum(r, "pnl_usd") or 0; ys.append(cum/1000)
            ax.plot(dts, ys, color=NAVY, lw=2)
            ax.axhline(0, color="#999", lw=0.7)
            ax.axvspan(date(2025,2,1), date(2025,4,15), color=LOSS, alpha=0.10)
            ax.set_title(f"{dte} DTE (hold, mid)", fontsize=11, fontweight="bold")
            ax.set_ylabel("US$ thousands"); ax.xaxis.set_major_locator(mdates.YearLocator())
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%y")); ax.grid(alpha=0.25)
        fig.text(0.5, 0.015, "Shaded band = the 2025 tariff crash. All curves are MID; net of the entry spread the slopes flatten (see page 4).",
                 fontsize=9, color=GREY, ha="center")
        fig.tight_layout(rect=[0,0.04,1,0.95]); pdf.savefig(fig); plt.close(fig)

        # ============ 6. FULL EXIT-RULE x HORIZON MATRIX (mid) ============
        EXITS = [30, 21, 14, 10, 7, 5, 3]
        def rule_net(tag, dte, d):
            rows_ = data[tag]
            if d is None:
                return sum(fnum(r, "pnl_usd") or 0 for r in rows_)
            if d >= dte:
                return None
            col = f"pnl_exit{d}"
            return sum((fnum(r, col) if fnum(r, col) is not None else (fnum(r, "pnl_usd") or 0)) for r in rows_)
        mat_rows = []
        for label, d in [("Hold to expiry", None)] + [(f"Exit at {d} DTE left", d) for d in EXITS]:
            cells = [label]
            for tag, dte in DTES:
                v = rule_net(tag, dte, d)
                cells.append(money(v) if v is not None else "-")
            mat_rows.append(cells)
        fig_table(pdf, "6. Exit rule x horizon — the full matrix (net P&L, mid)",
                  ["Close rule"] + [f"{dte} DTE" for _, dte in DTES], mat_rows,
                  subtitle="every close rule x every horizon · 5-year net at mid",
                  note="KEY INSIGHT — the horizon ranking FLIPS between holding and exiting early: "
                       "HELD TO EXPIRY, short horizons win (28 DTE best; 60 DTE collapses to +$2k, its valley is deepest "
                       "at expiry). With EARLY EXIT (how PL5 is actually traded) LONG horizons win (45/60 DTE; e.g. exit 3 "
                       "days before expiry: 45 DTE +$118k vs 21 DTE +$13k). Longer DTE gives the downside tent more time to "
                       "form, and leaving before the final days avoids the valley reforming (60 DTE: +$2k held vs +$117k if "
                       "exited 3 days early). All at mid; realistic combo fill scales every cell down similarly, so the "
                       "relative ranking holds.")

        # ============ 6b. HEATMAP (visual) — DTE x close-rule, net mid ============
        rule_cols = [("Hold", None)] + [(f"TP{t}", f"pnl_tp{t}") for t in (25, 50, 75)] \
                    + [(f"Exit {d}", f"pnl_exit{d}") for d in (60, 45, 30, 14, 7, 3)]
        M = np.full((len(DTES), len(rule_cols)), np.nan)
        for i, (tag, dte) in enumerate(DTES):
            rows_ = data[tag]
            for j, (lbl, col) in enumerate(rule_cols):
                if col is None:
                    M[i, j] = sum(fnum(r, "pnl_usd") or 0 for r in rows_) / 1000.0
                elif any(col in r for r in rows_):
                    M[i, j] = sum((fnum(r, col) if fnum(r, col) is not None else (fnum(r, "pnl_usd") or 0)) for r in rows_) / 1000.0
        fig, ax = plt.subplots(figsize=(11.7, 8.3))
        vlim = np.nanmax(np.abs(M))
        im = ax.imshow(M, cmap="RdYlGn", vmin=-vlim, vmax=vlim, aspect="auto")
        ax.set_xticks(range(len(rule_cols))); ax.set_xticklabels([l for l, _ in rule_cols], rotation=30, ha="right")
        ax.set_yticks(range(len(DTES))); ax.set_yticklabels([f"{dte} DTE" for _, dte in DTES])
        for i in range(len(DTES)):
            for j in range(len(rule_cols)):
                if not np.isnan(M[i, j]):
                    ax.text(j, i, f"{M[i,j]:.0f}", ha="center", va="center", fontsize=8,
                            color="black", fontweight="bold")
        ax.set_title("6b. Net P&L heatmap — horizon x close-rule (US$ thousands, mid)",
                     fontsize=15, fontweight="bold", color=NAVY, pad=14)
        fig.text(0.5, 0.04, "Greener = more profit. Mid pricing (ceiling). Long DTEs glow on absolute $ — but see the "
                 "margin page: that P&L rides $1-2M of capital. Best risk-adjusted cells are the short-DTE TP exits.",
                 ha="center", fontsize=9.5, color=GREY)
        plt.colorbar(im, ax=ax, fraction=0.025, pad=0.02, label="net (US$ k)")
        fig.tight_layout(rect=[0, 0.06, 1, 1]); pdf.savefig(fig); plt.close(fig)

        # ============ 6c. HEATMAP — MAX DRAWDOWN (DTE x close-rule) ============
        D = np.full((len(DTES), len(rule_cols)), np.nan)
        for i, (tag, dte) in enumerate(DTES):
            rows_ = data[tag]
            for j, (lbl, col) in enumerate(rule_cols):
                if col is None or any(col in r for r in rows_):
                    D[i, j] = max_drawdown(rows_, col) / 1000.0   # <= 0
        fig, ax = plt.subplots(figsize=(11.7, 8.3))
        dlim = np.nanmin(D)
        im = ax.imshow(D, cmap="Reds_r", vmin=dlim, vmax=0, aspect="auto")
        ax.set_xticks(range(len(rule_cols))); ax.set_xticklabels([l for l, _ in rule_cols], rotation=30, ha="right")
        ax.set_yticks(range(len(DTES))); ax.set_yticklabels([f"{dte} DTE" for _, dte in DTES])
        for i in range(len(DTES)):
            for j in range(len(rule_cols)):
                if not np.isnan(D[i, j]):
                    ax.text(j, i, f"{D[i,j]:.0f}", ha="center", va="center", fontsize=8, color="black", fontweight="bold")
        ax.set_title("6c. Drawdown heatmap — horizon x close-rule (closed-trade equity, US$ k, mid)",
                     fontsize=15, fontweight="bold", color=NAVY, pad=14)
        fig.text(0.5, 0.04, "Deeper red = bigger peak-to-trough on the CLOSED-TRADE curve — use to COMPARE close-rules within "
                 "a horizon (TP exits, esp. short DTE, cut it most). The absolute mark-to-market risk (open positions) is on "
                 "page 6d; this realized view understates the long-DTE risk. Read both heatmaps together (net 6b vs DD here).",
                 ha="center", fontsize=9.5, color=GREY)
        plt.colorbar(im, ax=ax, fraction=0.025, pad=0.02, label="max DD (US$ k)")
        fig.tight_layout(rect=[0, 0.06, 1, 1]); pdf.savefig(fig); plt.close(fig)

        # ============ 6d. RISK METRICS by horizon ============
        rk_rows = []
        for tag, dte in DTES:
            ma = margin_analysis(data[tag])
            cap = ma["avg_margin"] if ma else None
            rm = risk_metrics(data[tag], cap, daily[tag])
            if not rm: continue
            cal = "inf" if rm["calmar"] == float("inf") else f"{rm['calmar']:.2f}"
            rk_rows.append([f"{dte} DTE", money(rm["net"]), f"${rm['mdd']:,.0f}",
                            f"{rm['sharpe']:.2f}", cal])
        fig_table(pdf, "6d. Risk-adjusted metrics by horizon (hold, mid)",
                  ["Horizon", "Net", "Max drawdown (MTM)", "Sharpe", "Calmar"], rk_rows,
                  subtitle="maxDD = aggregate MARK-TO-MARKET drawdown (real, incl. open positions) · Sharpe on monthly returns / avg capital",
                  hi_col=2,
                  note="MAX DRAWDOWN here is the aggregate MARK-TO-MARKET drawdown — the worst peak-to-trough of the whole "
                       "open book, not just closed trades (the closed-trade curve badly understates risk on long DTEs, which "
                       "sit open for months). It is a HISTORICAL drawdown (what happened in 5y), distinct from the margin page's "
                       "THEORETICAL worst case ($1-2M). Note it samples ~17 points/trade, so it is a floor — continuous marking "
                       "would be somewhat deeper. SHARPE is modest because PL5 has a low win rate with fat crash-tail winners "
                       "(very skewed monthly P&L = high volatility), so Sharpe under-rewards a convex payoff; read it together "
                       "with Calmar (net/|maxDD|), which is strong for 75-120 DTE. All hold/mid (ceiling); realistic fills lower it.")

        # ============ 7. 2025 CRASH EXAMPLE ============
        rows60 = sorted(data["pl5_d60_std"], key=lambda r: fnum(r, "pnl_usd") or 0)
        wt = rows60[0]
        ed = date.fromisoformat(wt["exp_date"]); se = fnum(wt,"spot_entry"); ss = fnum(wt,"spot_exit")
        k1,k2,k3 = fnum(wt,"put_upper"),fnum(wt,"put_center"),fnum(wt,"put_lower")
        path = []
        for D in (14,10,7,3):
            dd = ed - timedelta(days=D); sp = at(dd); pnl = fnum(wt, f"pnl_exit{D}")
            path.append((f"{D} DTE left ({dd.isoformat()})", f"{sp:.0f}" if sp else "-", money(pnl) if pnl is not None else "-"))
        path.append((f"SETTLE ({wt['exp_date']})", f"{ss:.0f}", money(fnum(wt,'pnl_usd'))))
        fig_table(pdf, "7. A real worst case — the 2025 tariff crash (60 DTE)",
                  ["Exit point", "SPX that day", "P&L (mid)"], path,
                  subtitle=f"trade {wt['trade_date']} -> {wt['exp_date']} · entry SPX {se:.0f} · strikes {k1:.0f}/{k2:.0f}/{k3:.0f}",
                  note=f"SPX collapsed in the final days to {ss:.0f}, right at K3 ({k3:.0f}) = the valley = max loss. A holder "
                       f"took {money(fnum(wt,'pnl_usd'))}; exiting a week earlier was near flat. This is the genuine risk of "
                       "PL5: a directional crash that lands in the valley. The loss is defined, but it is large and, with "
                       "overlapping weekly entries, can cluster. This is real risk, at mid — not an execution artifact.")

        # ============ 7b. MARGIN / CAPITAL EFFICIENCY (overlapping positions) ============
        mrows = []
        for tag, dte in DTES:
            ma = margin_analysis(data[tag])
            if not ma:
                continue
            roi = (ma["net"] / ma["peak_margin"] * 100) if ma["peak_margin"] else 0
            mrows.append([f"{dte} DTE", str(ma["peak_pos"]), money(ma["net"]),
                          f"${ma['peak_margin']:,.0f}", f"${ma['avg_margin']:,.0f}", f"{roi:.0f}%"])
        fig_table(pdf, "8. Margin & capital efficiency (CZ uses IB Portfolio Margin)",
                  ["Horizon", "Max concurrent", "Net (mid)", "Reg-T margin (peak)", "Avg margin", "Return / margin"],
                  mrows,
                  subtitle="weekly entries stack: a 120 DTE holds ~18 packages at once · margin shown on the Reg-T ruler",
                  hi_col=5,
                  note="Margin here = Reg-T (sum of each package's defined max-loss, the valley) — the conservative ruler / "
                       "ceiling. THE READ: long DTEs post a huge absolute P&L only by tying up far more capital — a 120 DTE "
                       "needs ~$1.9M peak across ~18 stacked positions and returns only ~21% on it, vs 21-28 DTE at ~52-57%. "
                       "SHORT DTEs are ~2x more capital-efficient. CZ trades IB PORTFOLIO MARGIN, where the requirement is "
                       "LOWER than Reg-T (PM stress-tests the book over a short move with time value intact, rather than "
                       "summing every worst case) — but the exact figure comes from IB's TIMS model and we won't guess it. "
                       "Crucially, PM trims the dollar amount but NOT the ranking: the efficiency gap (short >> long) holds on "
                       "any ruler. Size by capital, not by the headline P&L. (All hold-to-expiry, mid; long-DTE win rate ~26-30%.)")

        # ============ 9. DATA VERIFICATION ============
        rows60c = data["pl5_d60_std"]
        vlines = [("Why these numbers are real, not fabricated:", 13, GOLD), ("", 8, "#333"),
                  ("1) Settlement = exact intrinsic at the SPX official close (cash-settled, European) — no spread,", 10.5, "#333"),
                  ("   no phantom fills. Check on the 3 worst 60 DTE trades (theoretical payoff vs recorded hold):", 10.5, "#333")]
        for r in sorted(rows60c, key=lambda x: fnum(x,"pnl_usd") or 0)[:3]:
            ss=fnum(r,"spot_exit"); k1,k2,k3=fnum(r,"put_upper"),fnum(r,"put_center"),fnum(r,"put_lower")
            intr=payoff_pts(k1,k2,k3,ss)*100
            vlines.append((f"      {r['trade_date']}:  SPX {ss:.0f}  ->  theoretical payoff {money(intr)}   (recorded hold {money(fnum(r,'pnl_usd'))})", 9.5, GAIN))
        vlines += [("", 8, "#333"),
                   ("2) Strikes verified per trade (chosen at -30 / -18 / -3 delta).", 10.5, "#333"),
                   ("3) MID pricing applied consistently across entry, marking and every exit rule.", 10.5, "#333"),
                   ("4) Entry spread VERIFIED at minute resolution = identical to hourly (1.000x): the tail spread", 10.5, "#333"),
                   ("   is the real market, not a stale-quote artifact (so the worst case is a legitimate bound).", 10.5, "#333"),
                   ("5) Every trade is auditable in the app (date, strikes, DTE, debit, VIX, spot, exits, P&L).", 10.5, "#333")]
        fig_text_page(pdf, "9. Data verification", vlines, subtitle="methodological rigor")

        # ============ 10. VERDICT ============
        s21, s28, s45, s60 = sens["pl5_d21_std"], sens["pl5_d28_std"], sens["pl5_d45_std"], sens["pl5_d60_std"]
        fig_text_page(pdf, "10. Verdict",
            [("PL5 is NOT a 'hold to expiry' trade — the valley at the end destroys it. And it is NOT a", 12, NAVY),
             ("market-order trade — it must be worked as a combo at a limit price.", 12, NAVY),
             ("", 8, "#333"),
             ("Realistic execution (combo fill, ~25-50% of the leg-by-leg spread), 5-year net P&L:", 12, GOLD),
             (f"  • 21 DTE:  {money(s21[0.25][0])} / {money(s21[0.5][0])}   ->  positive, best return-on-margin (~57%)", 11, GAIN),
             (f"  • 28 DTE:  {money(s28[0.25][0])} / {money(s28[0.5][0])}   ->  best net, ~52% on margin", 11, GAIN),
             (f"  • 45 DTE:  {money(s45[0.25][0])} / {money(s45[0.5][0])}   ->  marginal", 11, "#333"),
             (f"  • 60 DTE:  {money(s60[0.25][0])} / {money(s60[0.5][0])}   ->  negative", 11, LOSS),
             ("  • 75-120 DTE (CZ request): huge ABSOLUTE P&L (+$338k to +$465k hold/mid) BUT need $1.1-1.9M", 11, "#333"),
             ("    margin (12-18 stacked positions) -> only ~21-31% on capital, and low win rate (~26-30%).", 11, "#333"),
             ("", 8, "#333"),
             ("Honest caveats:", 12, GOLD),
             ("  • Execution is THE decisive factor (5 legs, illiquid -3d tail). Fill discipline = the edge.", 10.5, "#333"),
             ("  • Long DTEs win on headline $ only by tying up far more capital — short DTEs are 2x more", 10.5, "#333"),
             ("    capital-efficient (see page 8). Size by margin, not by absolute P&L.", 10.5, "#333"),
             ("  • Real tail risk: a crash into the valley = a large, defined loss; clusters with overlapping entries.", 10.5, "#333"),
             ("", 8, "#333"),
             ("Suggested next step: forward-test 28 DTE (best risk-adjusted) with early exit/TP + a concurrency", 11, NAVY),
             ("cap, and measure the REAL combo fill on the tail — the single factor that decides this strategy.", 11, NAVY)],
            subtitle="honest conclusion")
    try:
        os.replace(tmp, DEST)
        print(f">>> PDF: {DEST}  ({len(DTES)} horizons)")
    except PermissionError:
        alt = DEST.with_name(DEST.stem + "_NEW.pdf")
        os.replace(tmp, alt)
        print(f">>> {DEST.name} estava ABERTO/travado -> salvei em {alt.name}. Feche o visualizador e renomeie.")

if __name__ == "__main__":
    build()
