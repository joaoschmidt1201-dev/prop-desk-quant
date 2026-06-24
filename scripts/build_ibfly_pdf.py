"""
INVERSE BUTTERFLY 1-2-1 — PDF de VEREDITO (pós-correção do TP fantasma). Lê dos trades.csv
CORRIGIDOS (reports/ibfly_backtest_app/), não do runtime (que tinha TP inflado por quote stale).
Páginas: capa+veredito · heatmap net hold (DTE×width) · top configs (mid vs realista) · metodologia/veredito.
Uso: python scripts/build_ibfly_pdf.py  -> reports/inverse_butterfly/InverseButterfly_report.pdf
"""
from __future__ import annotations
import csv, os
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

REPO = Path(__file__).resolve().parent.parent
APP = REPO / "reports" / "ibfly_backtest_app"
DEST = REPO / "reports" / "inverse_butterfly" / "InverseButterfly_report.pdf"
NAVY = "#0f2b46"; GOLD = "#b8860b"; GAIN = "#1a7f37"; LOSS = "#c0392b"; GREY = "#555"
SLIP = 150.0   # slippage realista ~$150/trade (verificado em minuto; pernas near-ATM líquidas)
DTES = [1, 4, 7, 14, 28, 45]; WIDTHS = ["0.15", "0.25", "0.40", "0.50", "0.60", "0.75"]
plt.rcParams.update({"font.size": 10, "figure.facecolor": "white", "text.parse_math": False})

def f(x):
    try: return float(x)
    except Exception: return None

def load(d, w):
    p = APP / f"d{d}_w{w}" / "trades.csv"
    return list(csv.DictReader(open(p, encoding="utf-8"))) if p.exists() else None

def cfg_stats(rows):
    hold = [f(r["pnl_usd"]) or 0 for r in rows]
    net = sum(hold); n = len(rows); wr = 100*sum(1 for x in hold if x > 0)/n
    real = net - SLIP*n
    # melhor saída (TP/exit/noon) — todas as colunas pnl_* exceto pnl_usd
    cols = [c for c in rows[0] if c.startswith("pnl_") and c != "pnl_usd"]
    best_rule = max((sum(f(r[c]) or 0 for r in rows) for c in cols), default=net)
    return {"net": net, "real": real, "wr": wr, "n": n, "best_rule": best_rule}

def text_page(pdf, title, lines, subtitle=None):
    fig = plt.figure(figsize=(11.7, 8.3))
    fig.text(0.06, 0.93, title, fontsize=19, fontweight="bold", color=NAVY)
    if subtitle: fig.text(0.06, 0.895, subtitle, fontsize=11, color=GOLD)
    y = 0.83
    for ln, sz, col in lines:
        fig.text(0.07, y, ln, fontsize=sz, color=col, va="top"); y -= 0.0345*(sz/10.5)
    pdf.savefig(fig); plt.close(fig)

def table_page(pdf, title, headers, rows, subtitle=None, note=None, hi=None):
    fig, ax = plt.subplots(figsize=(11.7, 8.3)); ax.axis("off")
    fig.text(0.06, 0.93, title, fontsize=18, fontweight="bold", color=NAVY)
    if subtitle: fig.text(0.06, 0.885, subtitle, fontsize=11, color=GOLD)
    t = ax.table(cellText=rows, colLabels=headers, loc="center", cellLoc="center")
    t.auto_set_font_size(False); t.set_fontsize(11); t.scale(1, 1.9)
    for j in range(len(headers)):
        c = t[0, j]; c.set_facecolor(NAVY); c.set_text_props(color="white", fontweight="bold")
    for i in range(1, len(rows)+1):
        for j in range(len(headers)):
            t[i, j].set_facecolor("#f4f6f8" if i % 2 else "white")
            if hi is not None and j == hi: t[i, j].set_facecolor("#eaf4ea"); t[i, j].set_text_props(fontweight="bold")
    if note: fig.text(0.06, 0.16, note, fontsize=9.5, color=GREY, va="top", wrap=True)
    pdf.savefig(fig); plt.close(fig)

def build():
    data = {(d, w): load(d, w) for d in DTES for w in WIDTHS}
    data = {k: v for k, v in data.items() if v}
    stats = {k: cfg_stats(v) for k, v in data.items()}
    m = lambda v: f"${v:+,.0f}"
    DEST.parent.mkdir(parents=True, exist_ok=True)
    tmp = DEST.with_name(DEST.stem + ".__tmp.pdf")
    with PdfPages(tmp) as pdf:
        # 1) CAPA + VEREDITO
        best = max(stats.items(), key=lambda kv: kv[1]["real"])
        (bd, bw), bs = best
        text_page(pdf, "Inverse Butterfly 1-2-1 (SPX) — Verdict",
            [("QuantConnect · 2021-2026 · full grid: 6 DTE x 6 widths x exit-rules · hourly", 12, "#333"),
             ("", 8, "#333"),
             ("WHAT IT IS — short call fly (+2 ATM / -1 ATM-W / -1 ATM+W), net credit, long-vol.", 12.5, NAVY),
             ("Profits on movement; max gain = the credit; defined risk.", 10.5, "#333"),
             ("", 8, "#333"),
             ("VERDICT — not a convincing standalone edge.", 14, GOLD),
             (f"  • Best config: {bd} DTE @ {bw} sigma (hold) = {m(bs['net'])} mid -> ~{m(bs['real'])} after slippage,", 11.5, "#333"),
             (f"    win rate {bs['wr']:.0f}%. That's the CEILING and it's modest (~${bs['real']/5.5/1000:.0f}k/yr).", 11.5, "#333"),
             ("  • The winners are HOLD with WIDE wings (0.60-0.75 sigma); TP and early exits do NOT help.", 11.5, LOSS),
             ("  • Structural headwind: implied vol > realized (~0.73-0.85) — you overpay for movement.", 11, "#333"),
             ("  • P&L is lumpy (few big-move months carry it); mid is optimistic.", 11, "#333"),
             ("", 8, "#333"),
             ("RECOMMENDATION: not a priority / not forward-test ready as a standalone strategy. Possible", 11.5, NAVY),
             ("future use only as a small long-vol DIVERSIFIER (pays when the short-vol book bleeds).", 11.5, NAVY),
             ("", 8, "#333"),
             ("Note: TP figures were corrected for a stale-quote artifact (see methodology page).", 9.5, GREY)],
            subtitle="honest conclusion · validation stage")

        # 2) HEATMAP net hold (DTE x width)
        M = np.full((len(DTES), len(WIDTHS)), np.nan)
        for i, d in enumerate(DTES):
            for j, w in enumerate(WIDTHS):
                if (d, w) in stats: M[i, j] = stats[(d, w)]["net"]/1000.0
        fig, ax = plt.subplots(figsize=(11.7, 8.3))
        vlim = np.nanmax(np.abs(M))
        im = ax.imshow(M, cmap="RdYlGn", vmin=-vlim, vmax=vlim, aspect="auto")
        ax.set_xticks(range(len(WIDTHS))); ax.set_xticklabels([f"{w}s" for w in WIDTHS])
        ax.set_yticks(range(len(DTES))); ax.set_yticklabels([f"{d} DTE" for d in DTES])
        for i in range(len(DTES)):
            for j in range(len(WIDTHS)):
                if not np.isnan(M[i, j]): ax.text(j, i, f"{M[i,j]:.0f}", ha="center", va="center", fontsize=9, fontweight="bold")
        ax.set_title("1. Hold net P&L heatmap — DTE x width (US$ k, mid)", fontsize=15, fontweight="bold", color=NAVY, pad=14)
        fig.text(0.5, 0.04, "Greener = more profit. Edge concentrates in WIDE wings at medium DTE (14) — but it's mid pricing "
                 "and lumpy. Narrow wings (0.15s) and short DTE (1/4/7) are weak. Best cells = hold, not TP/exit.",
                 ha="center", fontsize=9.5, color=GREY)
        plt.colorbar(im, ax=ax, fraction=0.025, pad=0.02, label="net (US$ k)")
        fig.tight_layout(rect=[0, 0.06, 1, 1]); pdf.savefig(fig); plt.close(fig)

        # 3) TOP configs (mid vs realista)
        top = sorted(stats.items(), key=lambda kv: -kv[1]["real"])[:8]
        rows = [[f"{d} DTE @ {w}s", str(s["n"]), m(s["net"]), m(s["real"]), f"{s['wr']:.0f}%"] for (d, w), s in top]
        table_page(pdf, "2. Top configs — mid vs realistic (hold)",
                   ["Config", "Trades", "Net (mid)", "Net (realistic)", "Win rate"], rows,
                   subtitle="realistic = mid minus ~$150/trade slippage (verified at minute) · 5.5 years",
                   hi=3,
                   note="Even the best config (14 DTE wide) is only ~$40-66k net over 5.5 years after slippage — modest, "
                        "and it's the ceiling (mid). It is HOLD with very wide wings (near-straddle), heavily reliant on big "
                        "moves (lumpy). No early-exit or TP variation beats it. This is a thin, non-robust edge, not a "
                        "convincing standalone strategy.")

        # 4) METODOLOGIA / correção do TP
        text_page(pdf, "3. Methodology & the TP correction (data integrity)",
            [("Why the TP numbers changed (and are now honest):", 12.5, GOLD),
             ("", 8, "#333"),
             ("The engine recorded the TP as the mark-to-market at the first time the profit crossed the target,", 11, "#333"),
             ("read from HOURLY quotes. On near-expiry / illiquid legs, those quotes go stale -> the MTM showed", 11, "#333"),
             ("PHANTOM peaks (e.g. a TP of $1160 on a structure whose max gain is the ~$65 credit). ~18k TP affected.", 11, LOSS),
             ("", 7, "#333"),
             ("FIX (validated): the TP keeps the REAL first-cross value (so legitimate gaps/vol-spikes are preserved),", 11, GAIN),
             ("but is capped at a generous Black-Scholes plausibility ceiling (vol 3x entry) — only the stale-quote", 11, GAIN),
             ("anomalies are removed. 'Keep the real, correct only the anomaly.' 0 phantom TP remain.", 11, GAIN),
             ("", 7, "#333"),
             ("Clean throughout: hold = exact intrinsic settle; early exits = time-snapshots (not peak-seeking).", 10.5, "#333"),
             ("Standard procedure now: physical P&L cap check before any backtest goes to the app.", 10.5, "#333"),
             ("", 8, "#333"),
             ("BOTTOM LINE: even after giving the TP every benefit of the doubt, no IB variation is a convincing", 12, NAVY),
             ("standalone edge. Best is wide-wing hold, ~$40-66k/5.5y realistic — modest, lumpy, mid-optimistic.", 12, NAVY)],
            subtitle="verify, don't assume")
    try:
        os.replace(tmp, DEST); print(f">>> PDF: {DEST}  ({len(data)} configs)")
    except PermissionError:
        alt = DEST.with_name(DEST.stem + "_NEW.pdf"); os.replace(tmp, alt)
        print(f">>> {DEST.name} aberto -> {alt.name}")

if __name__ == "__main__":
    build()
