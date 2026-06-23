"""
INVERSE BUTTERFLY 1-2-1 — relatório PDF visual (todas as variações). Lê os runtimeStatistics
(amostra COMPLETA, confiável) de reports/inverse_butterfly/sweep_ibfly.json. Sem API/throttle.
Páginas: capa · heatmap DTE×width (net TP50) · curva de width + win-rate · melhores configs +
comparação de TP · veredito/caveats.
Uso: python scripts/build_ibfly_pdf.py  -> reports/inverse_butterfly/InverseButterfly_report.pdf
"""
from __future__ import annotations
import json, re, os
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

REPO = Path(__file__).resolve().parent.parent
SWEEP = REPO / "reports" / "inverse_butterfly" / "sweep_ibfly.json"
DEST = REPO / "reports" / "inverse_butterfly" / "InverseButterfly_report.pdf"
NAVY = "#0f2b46"; GOLD = "#b8860b"; GAIN = "#1a7f37"; LOSS = "#c0392b"; GREY = "#555"
plt.rcParams.update({"font.size": 10, "figure.facecolor": "white", "text.parse_math": False})

# tag -> (DTE alvo, width σ)
CONFIGS = [
    ("ibfly_dte1", 1, 0.15),
    ("ibfly_dte4_mon", 4, 0.15), ("ibfly_dte4_mon_w40", 4, 0.40), ("ibfly_dte4_mon_w60", 4, 0.60),
    ("ibfly_dte7", 7, 0.15), ("ibfly_d7_w0.50", 7, 0.50), ("ibfly_d7_w0.60", 7, 0.60),
    ("ibfly_dte15", 15, 0.15), ("ibfly_d15_w0.40", 15, 0.40), ("ibfly_d15_w0.50", 15, 0.50), ("ibfly_d15_w0.60", 15, 0.60),
    ("ibfly_d7_w0.50", 7, 0.50), ("ibfly_d7_w0.60", 7, 0.60),
    ("ibfly_dte30", 30, 0.15), ("ibfly_w0.25", 30, 0.25), ("ibfly_w0.40", 30, 0.40),
    ("ibfly_w0.50", 30, 0.50), ("ibfly_w0.60", 30, 0.60), ("ibfly_w0.75", 30, 0.75),
    ("ibfly_dte45", 45, 0.15), ("ibfly_d45_w0.40", 45, 0.40), ("ibfly_d45_w0.50", 45, 0.50), ("ibfly_d45_w0.60", 45, 0.60),
]
DTES = [1, 4, 7, 15, 30, 45]
WIDTHS = [0.15, 0.25, 0.40, 0.50, 0.60, 0.75]

def money(s):
    m = re.search(r"\$(-?[\d,]+)", s or ""); return int(m.group(1).replace(",", "")) if m else None
def pct(s):
    m = re.search(r"/(\d+)%", s or ""); return int(m.group(1)) if m else None
def ratio(s):
    m = re.search(r"/ ([\d.]+)\s*$", s or ""); return float(m.group(1)) if m else None
def n_of(s):
    m = re.search(r"n=(\d+)", s or ""); return int(m.group(1)) if m else None

def load():
    sw = json.loads(SWEEP.read_text(encoding="utf-8"))
    data = {}
    for tag, dte, w in CONFIGS:
        rt = sw.get(tag, {}).get("runtime") or {}
        if not rt.get("HOLD mid"):
            continue
        data[(dte, w)] = {
            "hold": money(rt.get("HOLD mid", "")), "hold_wr": pct(rt.get("HOLD mid", "")),
            "tp25": money(rt.get("TP 25%", "")), "tp25_wr": pct(rt.get("TP 25%", "")),
            "tp50": money(rt.get("TP 50%", "")), "tp50_wr": pct(rt.get("TP 50%", "")),
            "tp75": money(rt.get("TP 75%", "")), "tp75_wr": pct(rt.get("TP 75%", "")),
            "n": n_of(rt.get("n / dte / W", "")), "ri": ratio(rt.get("real vs impl", "")),
        }
    return data

def best_cell(d):
    """melhor net entre hold/tp25/50/75 + rótulo da regra + WR."""
    opts = [("Hold", d["hold"], d["hold_wr"]), ("TP25", d["tp25"], d["tp25_wr"]),
            ("TP50", d["tp50"], d["tp50_wr"]), ("TP75", d["tp75"], d["tp75_wr"])]
    opts = [o for o in opts if o[1] is not None]
    return max(opts, key=lambda o: o[1]) if opts else (None, None, None)

def build():
    data = load()
    DEST.parent.mkdir(parents=True, exist_ok=True)
    tmp = DEST.with_name(DEST.stem + ".__tmp.pdf")
    with PdfPages(tmp) as pdf:
        # ---------- 1) CAPA ----------
        fig = plt.figure(figsize=(11.7, 8.3))
        fig.text(0.06, 0.92, "Inverse Butterfly 1-2-1 (SPX)", fontsize=22, fontweight="bold", color=NAVY)
        fig.text(0.06, 0.875, "Todas as variações · DTE × width × regra de saída · 5,5 anos (mid)", fontsize=12, color=GOLD)
        lines = [
            ("ESTRUTURA: +2 CALL ATM / −1 CALL (ATM−W) / −1 CALL (ATM+W) — net crédito, long-vol.", 12, NAVY),
            ("Ganha quando o mercado se MOVE (qualquer lado); perde se fica parado. Risco definido.", 10.5, "#333"),
            ("", 8, "#333"),
            ("DESTAQUES (amostra completa, runtime):", 13, GOLD),
            ("  • Win rate ALTO: 80-94% (com TP 25% chega a 92-94% — perfil consistente).", 11.5, GAIN),
            ("  • Melhor net: 45 DTE @ 0,60σ + TP50 = +$118k; 15 DTE @ 0,60σ = +$101k.", 11.5, GAIN),
            ("  • Width largo (0,50-0,60σ) nos prazos longos é a maior alavanca de retorno.", 11, "#333"),
            ("  • TP melhora retorno E consistência vs hold em quase toda a matriz.", 11, "#333"),
            ("", 8, "#333"),
            ("Pricing MID ≈ alcançável (pernas near-ATM líquidas; spread real ~$150/trade, verificado em minuto).", 9.5, GREY),
            ("Sharpe/maxDD precisos pendem de re-run limpo (log do free tier trunca o per-trade). Headwind:", 9.5, GREY),
            ("implied > realized (~0,77) — paga-se um pouco caro pelo movimento. Long-vol = lumpy por ano.", 9.5, GREY),
        ]
        y = 0.80
        for ln, sz, col in lines:
            fig.text(0.06, y, ln, fontsize=sz, color=col, va="top"); y -= 0.036*(sz/10.5)
        fig.text(0.06, 0.06, "Prop Desk Quant · 2026-06 · em validação (candidato a forward-test / diversificador long-vol)", fontsize=9, color=GREY)
        pdf.savefig(fig); plt.close(fig)

        # ---------- 2) HEATMAP net (melhor saída) DTE × width ----------
        fig, ax = plt.subplots(figsize=(11.7, 8.3))
        M = np.full((len(DTES), len(WIDTHS)), np.nan)
        for i, dte in enumerate(DTES):
            for j, w in enumerate(WIDTHS):
                d = data.get((dte, w))
                if d:
                    bn = best_cell(d)[1]
                    if bn is not None: M[i, j] = bn / 1000.0
        vmax = np.nanmax(np.abs(M))
        im = ax.imshow(M, cmap="RdYlGn", vmin=-vmax, vmax=vmax, aspect="auto")
        ax.set_xticks(range(len(WIDTHS))); ax.set_xticklabels([f"{w:g}σ" for w in WIDTHS])
        ax.set_yticks(range(len(DTES))); ax.set_yticklabels([f"{d} DTE" for d in DTES])
        for i in range(len(DTES)):
            for j in range(len(WIDTHS)):
                if not np.isnan(M[i, j]):
                    rule, net, wr = best_cell(data[(DTES[i], WIDTHS[j])])
                    ax.text(j, i, f"${net/1000:.0f}k\n{rule}/{wr}%", ha="center", va="center", fontsize=8.5,
                            color="black", fontweight="bold")
                else:
                    ax.text(j, i, "—", ha="center", va="center", fontsize=9, color="#999")
        ax.set_title("1. Matriz DTE × width — MELHOR net (5,5a, mid) + regra/WR", fontsize=15, fontweight="bold", color=NAVY, pad=14)
        fig.text(0.5, 0.045, "Verde = mais lucro. Cada célula: melhor net entre Hold/TP25/50/75 + a regra vencedora e o win-rate dela.",
                 ha="center", fontsize=9.5, color=GREY)
        plt.colorbar(im, ax=ax, fraction=0.04, pad=0.03, label="net (US$ mil)")
        fig.tight_layout(rect=[0, 0.06, 1, 1]); pdf.savefig(fig); plt.close(fig)

        # ---------- 3) curva de width (esq) + win-rate (dir) ----------
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.7, 8.3))
        fig.suptitle("2. Onde está o retorno e a consistência", fontsize=15, fontweight="bold", color=NAVY)
        # curva: net (TP50) vs width, p/ DTE 15/30/45
        for dte, c in [(15, "#2c7fb8"), (30, NAVY), (45, GOLD)]:
            xs = [w for w in WIDTHS if (dte, w) in data and data[(dte, w)]["tp50"] is not None]
            ys = [data[(dte, w)]["tp50"]/1000 for w in xs]
            if xs: ax1.plot(xs, ys, "o-", color=c, lw=2.2, label=f"{dte} DTE")
        ax1.axhline(0, color="#999", lw=0.7); ax1.set_xlabel("width (σ)"); ax1.set_ylabel("net TP50 (US$ mil)")
        ax1.set_title("Net TP50 vs width — sweet spot 0,50-0,60σ", fontsize=11); ax1.grid(alpha=0.25); ax1.legend()
        # win-rate por regra (média entre configs com aquela regra)
        rules = ["Hold", "TP 25%", "TP 50%", "TP 75%"]; keys = ["hold_wr", "tp25_wr", "tp50_wr", "tp75_wr"]
        wrs = [np.nanmean([d[k] for d in data.values() if d[k] is not None]) for k in keys]
        bars = ax2.bar(rules, wrs, color=[GREY, GAIN, NAVY, "#2c7fb8"])
        for b, v in zip(bars, wrs): ax2.text(b.get_x()+b.get_width()/2, v+0.5, f"{v:.0f}%", ha="center", fontsize=10, fontweight="bold")
        ax2.set_ylim(0, 100); ax2.set_ylabel("Win rate médio (%)"); ax2.set_title("Win rate por regra de saída", fontsize=11); ax2.grid(alpha=0.25, axis="y")
        fig.tight_layout(rect=[0, 0, 1, 0.95]); pdf.savefig(fig); plt.close(fig)

        # ---------- 4) melhores configs (barh) ----------
        fig, ax = plt.subplots(figsize=(11.7, 8.3))
        ranked = []
        for (dte, w), d in data.items():
            rule, net, wr = best_cell(d)
            if net is not None: ranked.append((f"{dte}DTE / {w:g}σ / {rule}", net, wr, d["ri"]))
        ranked.sort(key=lambda r: r[1], reverse=True); top = ranked[:12]
        labels = [r[0] for r in top][::-1]; vals = [r[1]/1000 for r in top][::-1]; wrl = [r[2] for r in top][::-1]
        bars = ax.barh(labels, vals, color=[GAIN if v > 0 else LOSS for v in vals])
        for b, v, wr in zip(bars, vals, wrl):
            ax.text(v + (1 if v >= 0 else -1), b.get_y()+b.get_height()/2, f"${v:.0f}k · WR {wr}%",
                    va="center", ha="left" if v >= 0 else "right", fontsize=9, fontweight="bold")
        ax.axvline(0, color="#999", lw=0.7); ax.set_xlabel("net 5,5a (US$ mil)")
        ax.set_title("3. Top 12 variações — net (melhor saída) + win rate", fontsize=15, fontweight="bold", color=NAVY, pad=12)
        fig.tight_layout(); pdf.savefig(fig); plt.close(fig)

        # ---------- 5) veredito / potencial / caveats ----------
        fig = plt.figure(figsize=(11.7, 8.3))
        fig.text(0.06, 0.93, "4. Potencial & leitura honesta", fontsize=18, fontweight="bold", color=NAVY)
        vl = [
            ("O POTENCIAL:", 13, GOLD),
            ("  • Família de ALTO win-rate (80-94%) e net forte nas asas largas: o melhor cenário rende", 11.5, GAIN),
            ("    +$100-118k em 5,5 anos no mid, com WR 80-90%.", 11.5, GAIN),
            ("  • TP entrega retorno E consistência — TP25 leva o WR a 92-94% (perfil de income long-vol).", 11.5, GAIN),
            ("  • Width largo (0,50-0,60σ) é a alavanca; 0,75σ já quebra (estrutura vira straddle).", 11, "#333"),
            ("  • DIVERSIFICAÇÃO: é long-vol → paga quando o book short-vol (Bull Put/IC/Batman) sangra.", 11.5, GAIN),
            ("", 8, "#333"),
            ("A LEITURA HONESTA (sem vender ilusão):", 13, GOLD),
            ("  • mid ≈ real aqui (near-ATM líquido; spread ~$150/trade verificado em minuto) — não é fantasia.", 11, "#333"),
            ("  • Sharpe/maxDD precisos pendem de re-run limpo (log do free tier trunca o per-trade dos DTEs", 11, "#333"),
            ("    de alto volume). Estimativa parcial (15DTE@0,40): Sharpe ~2,6 / maxDD ~−$8k no TP50.", 11, "#333"),
            ("  • Lumpy por ano (long-vol); NÃO há filtro de VIX confiável (testado e refutado).", 11, LOSS),
            ("  • Headwind estrutural: implied > realized (~0,77) — paga-se um pouco caro pelo movimento.", 11, LOSS),
            ("", 8, "#333"),
            ("VEREDITO: estratégia com edge REAL e perfil atraente — melhor como WIDTH largo + TP, e como", 12, NAVY),
            ("diversificador long-vol do portfólio. Próximo: re-run limpo p/ Sharpe full + forward-test.", 12, NAVY),
        ]
        y = 0.86
        for ln, sz, col in vl:
            fig.text(0.06, y, ln, fontsize=sz, color=col, va="top"); y -= 0.038*(sz/10.5)
        pdf.savefig(fig); plt.close(fig)
    try:
        os.replace(tmp, DEST); print(f">>> PDF: {DEST}")
    except PermissionError:
        alt = DEST.with_name(DEST.stem + "_NEW.pdf"); os.replace(tmp, alt)
        print(f">>> {DEST.name} aberto/travado -> salvei em {alt.name}")

if __name__ == "__main__":
    build()
