"""
INVERSE BUTTERFLY — relatório PDF de apresentação (p/ Cristiano). Lê os runtimeStatistics do
sweep (reports/inverse_butterfly/sweep_ibfly.json). Páginas: capa+resumo · métricas por DTE
(HOLD/saída/TP, mid vs spread) · sensibilidade ao fill · realizado-vs-implícito · veredito.
Uso: python scripts/build_ibfly_pdf.py  -> reports/inverse_butterfly/InverseButterfly_report.pdf
"""
from __future__ import annotations
import json, re
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

REPO = Path(__file__).resolve().parent.parent
SWEEP = REPO / "reports" / "inverse_butterfly" / "sweep_ibfly.json"
DEST = REPO / "reports" / "inverse_butterfly" / "InverseButterfly_report.pdf"
NAVY = "#0f2b46"; GOLD = "#b8860b"; GAIN = "#1a7f37"; LOSS = "#c0392b"
plt.rcParams.update({"font.size": 10, "figure.facecolor": "white"})

def money(s):
    m = re.search(r"\$(-?[\d,]+)", s or "")
    return int(m.group(1).replace(",", "")) if m else None
def pct(s):
    m = re.search(r"/(\d+)%", s or "")
    return int(m.group(1)) if m else None
def midcons(s):  # "mid $X/Y% | cons $Z/W%"
    parts = (s or "").split("|"); mid = money(parts[0]); cons = money(parts[1]) if len(parts) > 1 else None
    return mid, cons

def text_page(pdf, title, lines, subtitle=None):
    fig = plt.figure(figsize=(11.7, 8.3))
    fig.text(0.06, 0.93, title, fontsize=20, fontweight="bold", color=NAVY)
    if subtitle: fig.text(0.06, 0.89, subtitle, fontsize=11, color=GOLD)
    y = 0.83
    for ln, sz, col in lines:
        fig.text(0.07, y, ln, fontsize=sz, color=col, va="top"); y -= 0.036*(sz/10.5)
    pdf.savefig(fig); plt.close(fig)

def table_page(pdf, title, headers, rows, subtitle=None, note=None):
    fig, ax = plt.subplots(figsize=(11.7, 8.3)); ax.axis("off")
    fig.text(0.06, 0.93, title, fontsize=18, fontweight="bold", color=NAVY)
    if subtitle: fig.text(0.06, 0.885, subtitle, fontsize=11, color=GOLD)
    if rows:
        t = ax.table(cellText=rows, colLabels=headers, loc="center", cellLoc="center")
        t.auto_set_font_size(False); t.set_fontsize(11); t.scale(1, 2.0)
        for j in range(len(headers)):
            c = t[0, j]; c.set_facecolor(NAVY); c.set_text_props(color="white", fontweight="bold")
        for i in range(1, len(rows)+1):
            for j in range(len(headers)):
                t[i, j].set_facecolor("#f4f6f8" if i % 2 else "white")
    if note: fig.text(0.06, 0.12, note, fontsize=9, color="#555", va="top", wrap=True)
    pdf.savefig(fig); plt.close(fig)

def build():
    sw = json.loads(SWEEP.read_text(encoding="utf-8")) if SWEEP.exists() else {}
    # ordena por DTE (ibfly_dteN) e width (ibfly_wX)
    dte_runs = []
    for tag, r in sw.items():
        rt = r.get("runtime") or {}
        if tag.startswith("ibfly_dte") and rt and not rt.get("_error"):
            dte = int(re.search(r"dte(\d+)", tag).group(1)); dte_runs.append((dte, tag, rt))
    dte_runs.sort()
    DEST.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(DEST) as pdf:
        text_page(pdf, "Inverse Butterfly 1-2-1 (SPX)",
            [("Backtest QuantConnect · 2021-2026 · resolução horária", 13, "#333"), ("", 10, "#333"),
             ("ESTRUTURA: +2 CALL ATM  /  -1 CALL (ATM+W)  /  -1 CALL (ATM-W)   (1-2-1, net CRÉDITO)", 12, NAVY),
             ("  'Tenda pra baixo': GANHA se o preço se mexe (qualquer lado), PERDE se fica parado.", 10.5, "#333"),
             ("  Long vega/gamma. Width W em múltiplos de σ. Lucro travado = crédito; risco definido.", 10.5, "#333"),
             ("", 10, "#333"),
             ("Estratégia do vídeo alemão (Castle Trader) — versão income. Pernas near-ATM (líquidas),", 10.5, "#333"),
             ("logo MUITO menos sensível a slippage que o PL5 (que tinha cauda deep-OTM).", 10.5, "#333"),
             ("", 10, "#333"),
             ("O QUE TESTAMOS: DTE 1 / 4(seg-sex) / 7 / 15 / 30 / 45, saída por DTE-restante / horário", 11, "#333"),
             ("de expiração (1DTE→12h, seg-sex→sexta abertura) / TP %, em mid e spread cheio.", 11, "#333"),
             ("", 10, "#333"),
             ("Pergunta central: a vol REALIZADA supera a IMPLÍCITA líquida de custo? (long-vol tem edge?)", 11.5, GOLD)],
            subtitle="Relatório para apresentação · Prop Desk Quant · (validação — ainda não no app)")

        # métricas por DTE: HOLD mid/cons, EXIT 7 mid, TP50 mid, real/impl, n
        rows = []
        for dte, tag, rt in dte_runs:
            hold = money(rt.get("HOLD mid", "")); holdc = money(rt.get("HOLD cons", ""))
            e7 = midcons(rt.get("EXIT 7DTE", "")); tp50 = money(rt.get("TP 50%", ""))
            rvi = rt.get("real vs impl", ""); ratio = re.search(r"/ ([\d.]+)$", rvi)
            ndte = rt.get("n / dte / W", "")
            rows.append([f"{dte} DTE",
                         f"${hold:+,.0f}" if hold is not None else "—",
                         f"${e7[0]:+,.0f}" if e7[0] is not None else "—",
                         f"${tp50:+,.0f}" if tp50 is not None else "—",
                         ratio.group(1) if ratio else "—"])
        table_page(pdf, "1. Métricas por prazo (MID, net 5 anos)",
                   ["DTE", "Hold", "Sair 7 DTE", "TP 50%", "Realiz/Impl"], rows,
                   subtitle="P&L no mid · 'Realiz/Impl' = movimento realizado ÷ implícito (>1 = favorável)",
                   note="No mid quase tudo aparece positivo (típico desta família long-vol). O teste de verdade é "
                        "o custo: ver a sensibilidade ao fill na página seguinte. Realiz/Impl < 1 = vol implícita rica.")

        # sensibilidade ao fill (HOLD mid vs cons) por DTE
        rows2 = []
        for dte, tag, rt in dte_runs:
            hold = money(rt.get("HOLD mid", "")); holdc = money(rt.get("HOLD cons", ""))
            rows2.append([f"{dte} DTE",
                          f"${hold:+,.0f}" if hold is not None else "—",
                          f"${holdc:+,.0f}" if holdc is not None else "—"])
        table_page(pdf, "2. Sensibilidade ao custo — HOLD (mid vs spread cheio)",
                   ["DTE", "Mid (otimista)", "Spread cheio (pessimista)"], rows2,
                   subtitle="a verdade está no meio · pernas near-ATM = spread bem menor que o PL5",
                   note="OBS: o 'spread cheio' usa o bid/ask HORÁRIO, que é largo/stale e exagera o custo. Como as "
                        "pernas são near-ATM (líquidas), o fill real fica perto do mid — diferente do PL5. "
                        "Recomendação: modelar slippage fixo por perna ($0,50-1,00) p/ a estimativa realista.")

        # equity curves se houver per-trade? usamos só agregados aqui (CTRADE pode truncar no 1DTE diário)
        text_page(pdf, "3. Leitura e veredito (preliminar)",
            [("Perfil: long-vol / long-gamma — ganha em movimento, sangra parado.", 12, NAVY), ("", 10, "#333"),
             ("Diferença-chave vs PL5/Burrito: pernas NEAR-ATM (líquidas) → slippage pequeno →", 11, GAIN),
             ("o edge tem chance REAL de sobreviver ao custo (ao contrário das estruturas deep-OTM).", 11, GAIN),
             ("", 10, "#333"),
             ("DTEs curtos (1 / seg-sex): tese de GAMMA (movimento intradiário/poucos dias); saída por", 10.5, "#333"),
             ("horário (12h / sexta abertura) evita o esmagamento de theta no expiry.", 10.5, "#333"),
             ("DTEs 15-45: tese de VEGA (expansão de vol) — entra barato com VIX baixo.", 10.5, "#333"),
             ("", 10, "#333"),
             ("PRÓXIMO PASSO: análise com slippage MODELADO (não o cons horário inflado) + eixo de width,", 11, GOLD),
             ("p/ cravar em quais DTE/width o edge líquido sobrevive. (Esta estratégia ainda em validação.)", 11, GOLD)],
            subtitle="conclusão honesta — em refinamento")
    print(f">>> PDF: {DEST}  ({len(dte_runs)} DTEs)")

if __name__ == "__main__":
    build()
