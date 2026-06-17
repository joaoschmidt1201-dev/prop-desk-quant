"""
INVERSE BUTTERFLY 1-2-1 — presentation PDF (for Cristiano), ENGLISH. Reads runtimeStatistics from
reports/inverse_butterfly/sweep_ibfly.json (+ dte7 patched from CTRADE). Pages: cover/how-it-works ·
results by DTE · results by width · EXECUTION VERIFICATION (minute vs hourly — the applied PL5 lesson) ·
verdict. Honest framing: present MID + a modeled realistic slippage; the hourly 'cons' is a VERIFIED
stale-quote artifact for these near-ATM legs (do NOT use it).
Uso: python scripts/build_ibfly_pdf.py  -> reports/inverse_butterfly/InverseButterfly_report.pdf
"""
from __future__ import annotations
import json, re, os
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

REPO = Path(__file__).resolve().parent.parent
SWEEP = REPO / "reports" / "inverse_butterfly" / "sweep_ibfly.json"
DEST = REPO / "reports" / "inverse_butterfly" / "InverseButterfly_report.pdf"
NAVY = "#0f2b46"; GOLD = "#b8860b"; GAIN = "#1a7f37"; LOSS = "#c0392b"; GREY = "#555"
# verified at minute (ibfly_d30_minchk): real entry spread ~$150/trade (median); hourly erratic w/ spikes
SLIP = 150.0   # modeled real round-trip-ish entry spread per trade (from minute verification, w0.15)
plt.rcParams.update({"font.size": 10, "figure.facecolor": "white", "text.parse_math": False})

def money(s):
    m = re.search(r"\$(-?[\d,]+)", s or ""); return int(m.group(1).replace(",", "")) if m else None
def pct(s):
    m = re.search(r"/(\d+)%", s or ""); return int(m.group(1)) if m else None
def ratio(s):
    m = re.search(r"/ ([\d.]+)\s*$", s or ""); return m.group(1) if m else "—"
def n_of(s):
    m = re.search(r"n=(\d+)", s or ""); return int(m.group(1)) if m else 0

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
    t.auto_set_font_size(False); t.set_fontsize(11); t.scale(1, 2.0)
    for j in range(len(headers)):
        c = t[0, j]; c.set_facecolor(NAVY); c.set_text_props(color="white", fontweight="bold")
    for i in range(1, len(rows)+1):
        for j in range(len(headers)):
            t[i, j].set_facecolor("#f4f6f8" if i % 2 else "white")
            if hi is not None and j == hi:
                t[i, j].set_facecolor("#eaf4ea"); t[i, j].set_text_props(fontweight="bold")
    if note: fig.text(0.06, 0.17, note, fontsize=9.5, color=GREY, va="top", wrap=True)
    pdf.savefig(fig); plt.close(fig)

def build():
    sw = json.loads(SWEEP.read_text(encoding="utf-8"))
    def rt(tag): return sw.get(tag, {}).get("runtime") or {}
    DTES = [(f"ibfly_dte{d}", d) for d in (1, 4, 7, 15, 30, 45)]
    WIDS = [("ibfly_dte30", "0.15σ", 30), ("ibfly_w0.25", "0.25σ", 50), ("ibfly_w0.40", "0.40σ", 80)]
    m = lambda v: f"${v:+,.0f}"
    DEST.parent.mkdir(parents=True, exist_ok=True)
    tmp = DEST.with_name(DEST.stem + ".__tmp.pdf")
    with PdfPages(tmp) as pdf:
        # 1) COVER
        text_page(pdf, "Inverse Butterfly 1-2-1 (SPX)",
            [("QuantConnect backtest · 2021-2026 · SPX weeklys · hourly data (validation stage)", 12.5, "#333"),
             ("", 8, "#333"),
             ("WHAT IT IS — a long-volatility structure (the inverse of an iron fly).", 13, NAVY),
             ("Per unit:  +2 calls at-the-money  /  -1 call (ATM-W)  /  -1 call (ATM+W).  Net CREDIT.", 11.5, "#333"),
             ("It MAKES money when the market MOVES (either direction) and LOSES if it sits still. Long", 10.5, "#333"),
             ("gamma/vega. Width W set in multiples of the implied 1-sigma move.", 10.5, "#333"),
             ("", 8, "#333"),
             ("WHAT WE TESTED — horizons 1/4/7/15/30/45 DTE; widths 0.15 / 0.25 / 0.40 sigma; exits by", 12, NAVY),
             ("DTE-remaining, expiry-day clock, and profit-target. (German 'Castle Trader' income version.)", 11, "#333"),
             ("", 8, "#333"),
             ("HEADLINE", 13.5, GOLD),
             ("  1.  Execution is CLEAN (verified): near-ATM legs are liquid, real spread ~$150/trade. The", 11.5, GAIN),
             ("      scary -$175k hourly 'worst case' is a stale-quote ARTIFACT (page 4) — opposite of PL5.", 11, "#333"),
             ("  2.  But the HOLD edge is THIN: mid hold is only +$6-14k/5y and does NOT survive even light", 11.5, LOSS),
             ("      slippage; the daily 1/4-DTE variants accumulate cost over 1,200+ trades and go negative.", 11, "#333"),
             ("  3.  The VIABLE form is profit-target + WIDE wings: TP 50% is +$21-74k; 0.40-sigma holds +$38k.", 11.5, GAIN),
             ("      Structural headwind: implied vol > realized (0.73-0.85) — you overpay for movement.", 11, "#333"),
             ("", 8, "#333"),
             ("Still in validation — NOT in the app yet.", 10, GREY)],
            subtitle="Presentation report · Prop Desk Quant · 2026-06")

        # 2) RESULTS BY DTE
        rows = []
        for tag, d in DTES:
            r = rt(tag); h = money(r.get("HOLD mid", "")); n = n_of(r.get("n / dte / W", ""))
            realistic = (h - 0.5*SLIP*n) if h is not None else None
            rows.append([f"{d} DTE", str(n) if n else "—",
                         m(h) if h is not None else "—",
                         m(realistic) if realistic is not None else "—",
                         (lambda v: m(v) if v is not None else "—")(money(r.get("TP 50%", ""))),
                         ratio(r.get("real vs impl", ""))])
        table_page(pdf, "1. Results by horizon (mid pricing)",
                   ["DTE", "Trades", "Hold (mid)", "Hold (realistic)", "TP 50%", "Realiz/Impl"], rows,
                   subtitle="net P&L over 5 years · 'realistic' = mid minus modeled real slippage (~$150/trade, see p.4)",
                   hi=4,
                   note="Hold at mid is modest and noisy; net of the verified ~$150/trade spread it goes marginal/negative "
                        "(the daily 1/4-DTE variants accumulate cost over 1,200+ entries). TP 50% is shown at MID and is "
                        "GROSS of the exit spread (closing at the target also pays slippage) — net of the round-trip it is "
                        "marginal-to-positive, best at wide width. Realiz/Impl < 1 = implied vol richer than realized.")

        # 3) RESULTS BY WIDTH
        rows = []
        for tag, lab, W in WIDS:
            r = rt(tag); h = money(r.get("HOLD mid", "")); n = n_of(r.get("n / dte / W", "")); wr = pct(r.get("HOLD mid", ""))
            realistic = (h - 0.5*SLIP*n) if h is not None else None
            rows.append([lab, f"~{W} pts", f"{wr}%" if wr else "—",
                         m(h) if h is not None else "—",
                         m(realistic) if realistic is not None else "—",
                         (lambda v: m(v) if v is not None else "—")(money(r.get("TP 50%", "")))])
        table_page(pdf, "2. Results by width (30 DTE, mid pricing)",
                   ["Width", "approx W", "Win rate", "Hold (mid)", "Hold (realistic)", "TP 50%"], rows,
                   subtitle="wider wings = bigger profit per move, lower hit rate",
                   hi=4,
                   note="Widening the wings raises the dollar payoff per move (+$6k -> +$20k -> +$38k at mid) while the "
                        "win rate falls (90% -> 79%). The wider structures survive the modeled slippage best, so width is "
                        "the most promising structural lever to lift the edge above execution cost.")

        # 4) EXECUTION VERIFICATION (the star)
        text_page(pdf, "4. Execution check — we verified the spread (the PL5 lesson)",
            [("On PL5 we learned NOT to trust an aggregate, and NOT to assume. So we verified this one.", 12, GOLD),
             ("", 8, "#333"),
             ("THE WORRY.  At hourly data, the worst-case ('cross every leg') hold looks catastrophic:", 11.5, NAVY),
             ("  30 DTE: +$5.7k at mid  vs  -$175k at full hourly bid/ask. A 4-leg structure shouldn't cost that.", 10.5, "#333"),
             ("", 7, "#333"),
             ("THE TEST.  We re-ran 30 DTE on MINUTE data (2025) and measured the entry spread per trade:", 11.5, NAVY),
             ("  • MINUTE spread: consistent, ~$115-310/trade (median ~$150).", 11, GAIN),
             ("  • HOURLY spread: erratic, $95 up to $5,580/trade (median ~$1,090) — stale-quote spikes.", 11, LOSS),
             ("  • Where the hourly quote happened to be tight, it matched minute; where stale, it inflated 7-37x.", 10.5, "#333"),
             ("", 7, "#333"),
             ("THE VERDICT.  These legs are near-ATM and LIQUID. The hourly 'cons' is a STALE-QUOTE ARTIFACT;", 11.5, GAIN),
             ("the real execution cost is small (~$150/trade). So we IGNORE the -$175k and use the modeled", 11, "#333"),
             ("~$150/trade for the 'realistic' columns. (This is the OPPOSITE of PL5, whose -3-delta tail had", 11, "#333"),
             ("a genuinely wide spread that held up at minute — there the worst case was real.)", 11, "#333"),
             ("", 7, "#333"),
             ("Why hourly lies here: a far-from-busy option's last hourly quote can be stale/wide; near-ATM", 10, GREY),
             ("minute quotes refresh constantly. Same data vendor, different sampling — minute is the truth.", 10, GREY)],
            subtitle="methodology — verify, don't assume")

        # 5) VERDICT
        d30 = rt("ibfly_dte30"); w40 = rt("ibfly_w0.40")
        text_page(pdf, "5. Verdict (preliminary — still validating)",
            [("Execution is clean (verified), but the BUY-AND-HOLD edge is too thin to survive even light", 12, NAVY),
             ("slippage. The strategy is only viable as PROFIT-TARGET + WIDE wings — not hold-to-expiry.", 12, NAVY),
             ("", 8, "#333"),
             ("What we can say with the data:", 12, GOLD),
             ("  • Execution is NOT the problem (verified): real spread ~$150/trade, not the -$175k artifact.", 11, GAIN),
             ("  • The lever that works is WIDTH: 0.40 sigma holds +$38k at mid, most robust after slippage.", 11, GAIN),
             ("  • TP 50% beats hold at mid (+$21-74k); net of round-trip slippage it is marginal-to-positive", 11, "#333"),
             ("    (best at wide width) — taking profit is still the right exit, but the net edge is borderline.", 11, "#333"),
             ("  • The headwind is structural: Realiz/Impl 0.73-0.85 — you overpay for movement.", 11, LOSS),
             ("", 8, "#333"),
             ("Honest caveats:", 12, GOLD),
             ("  • Hourly data; the minute check validates the spread but full-span numbers remain hourly.", 10.5, "#333"),
             ("  • Thin 30-DTE hold turns marginal after the (small, real) slippage — width/TP carry the edge.", 10.5, "#333"),
             ("  • Long-vol P&L is lumpy (a few big moves make the year) — needs the lumpiness shown forward.", 10.5, "#333"),
             ("", 8, "#333"),
             ("Suggested next step: forward-test the WIDE (0.40 sigma) variant with a profit-target exit, on", 11, NAVY),
             ("a few liquid index underlyings — execution is clean, so the open question is purely the edge.", 11, NAVY)],
            subtitle="honest conclusion")
    try:
        os.replace(tmp, DEST); print(f">>> PDF: {DEST}")
    except PermissionError:
        alt = DEST.with_name(DEST.stem + "_NEW.pdf"); os.replace(tmp, alt)
        print(f">>> {DEST.name} aberto/travado -> salvei em {alt.name}")

if __name__ == "__main__":
    build()
