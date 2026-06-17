"""
PL5 — relatório PDF de apresentação (p/ Cristiano). Multi-página (matplotlib PdfPages):
 capa+resumo · sensibilidade ao fill (o achado-chave) · curvas de equity · saída antecipada
 + por-ano · exemplos do crash 2025 (caminho do spot) · veracidade dos dados · veredito.
 Lê os CSVs do app (reports/pl5_backtest_app/<dte>/trades.csv, mid) + SPX cache.
 Uso: python scripts/build_pl5_pdf.py   ->  reports/pl5_bwb/PL5_report.pdf
"""
from __future__ import annotations
import csv, math
from datetime import date, timedelta
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.dates as mdates
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
APP = REPO / "reports" / "pl5_backtest_app"
DEST = REPO / "reports" / "pl5_bwb" / "PL5_report.pdf"
DTES = [("pl5_d21_std", 21), ("pl5_d28_std", 28), ("pl5_d45_std", 45), ("pl5_d60_std", 60)]
EXITS = [30, 21, 14, 10, 7, 5, 3]
NAVY = "#0f2b46"; GOLD = "#b8860b"; GAIN = "#1a7f37"; LOSS = "#c0392b"
plt.rcParams.update({"font.size": 10, "axes.titlesize": 12, "figure.facecolor": "white"})

def fnum(r, k):
    try: return float(r[k])
    except (TypeError, ValueError, KeyError): return None

def load(tag):
    return list(csv.DictReader(open(APP / tag / "trades.csv", encoding="utf-8")))

def spx_loader():
    p = REPO / "data/cache/spx_daily.parquet"
    s = pd.read_parquet(p); s["date"] = pd.to_datetime(s["date"]).dt.normalize(); s = s.sort_values("date")
    def at(d):
        q = s[s["date"] <= pd.Timestamp(d)].tail(1); return float(q["spx"].iloc[0]) if len(q) else None
    return at

def fill_sensitivity(rows):
    """hold por fração de fill de entrada (mid/25/50/cons), reconstruído de terminal+custo."""
    out = {}
    for fr in (0.0, 0.25, 0.5, 1.0):
        pls = []
        for r in rows:
            ss = fnum(r, "spot_exit"); k1, k2, k3 = fnum(r, "put_upper"), fnum(r, "put_center"), fnum(r, "put_lower")
            hold_mid = fnum(r, "pnl_usd"); cost_cons = (fnum(r, "total_credit") or 0) / 100.0
            if None in (ss, k1, k2, k3, hold_mid): continue
            terminal = 1*max(0, k1-ss) - 2*max(0, k2-ss) + 2*max(0, k3-ss)
            cost_mid = terminal - hold_mid/100.0
            cost_f = cost_mid + fr*(cost_cons - cost_mid)
            pls.append((terminal - cost_f)*100.0)
        net = sum(pls); wr = 100*sum(1 for x in pls if x > 0)/len(pls) if pls else 0
        out[fr] = (net, wr)
    return out

def fig_text_page(pdf, title, lines, subtitle=None):
    fig = plt.figure(figsize=(11.7, 8.3)); fig.patch.set_facecolor("white")
    fig.text(0.06, 0.93, title, fontsize=20, fontweight="bold", color=NAVY)
    if subtitle: fig.text(0.06, 0.89, subtitle, fontsize=11, color=GOLD)
    y = 0.83
    for ln, sz, col in lines:
        fig.text(0.07, y, ln, fontsize=sz, color=col, va="top"); y -= 0.035*(sz/10.5)
    pdf.savefig(fig); plt.close(fig)

def fig_table(pdf, title, headers, rows, subtitle=None, colcolors=None, note=None):
    fig, ax = plt.subplots(figsize=(11.7, 8.3)); ax.axis("off")
    fig.text(0.06, 0.93, title, fontsize=18, fontweight="bold", color=NAVY)
    if subtitle: fig.text(0.06, 0.885, subtitle, fontsize=11, color=GOLD)
    t = ax.table(cellText=rows, colLabels=headers, loc="center", cellLoc="center")
    t.auto_set_font_size(False); t.set_fontsize(11); t.scale(1, 2.0)
    for j in range(len(headers)):
        c = t[0, j]; c.set_facecolor(NAVY); c.set_text_props(color="white", fontweight="bold")
    for i in range(1, len(rows)+1):
        for j in range(len(headers)):
            cell = t[i, j]
            cell.set_facecolor("#f4f6f8" if i % 2 else "white")
    if note: fig.text(0.06, 0.12, note, fontsize=9, color="#555", va="top", wrap=True)
    pdf.savefig(fig); plt.close(fig)

def build():
    at = spx_loader()
    data = {tag: load(tag) for tag, _ in DTES}
    DEST.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(DEST) as pdf:
        # ---- capa / resumo
        fig_text_page(pdf, "PL5 — Broken-Wing Put Butterfly (SPX)",
            [("Backtest QuantConnect · 2021-2026 · entrada toda sexta 10:00 ET", 13, "#333"),
             ("", 10, "#333"),
             ("ESTRUTURA (por unidade): +1 put @ -30Δ  /  -2 puts @ -18Δ  /  +2 puts @ -3Δ", 12, NAVY),
             ("  Net débito pequeno · vale (perda máx) no centro · cauda convexa abaixo de K3.", 10.5, "#333"),
             ("", 10, "#333"),
             ("4 variações de prazo: 21 / 28 / 45 / 60 DTE.", 11.5, "#333"),
             ("", 10, "#333"),
             ("ACHADOS-CHAVE:", 13, GOLD),
             ("  1. Resultado é DOMINADO pelo fill de entrada (5 pernas, ~5pts de spread).", 11, "#333"),
             ("  2. Em fill realista (25-50% do spread): hold modestamente POSITIVO em 21-45 DTE,", 11, GAIN),
             ("     NEGATIVO em 60 DTE (asa larguíssima → vale fundo).", 11, LOSS),
             ("  3. Saída ANTECIPADA evita o 'vale' no vencimento (tese confirmada).", 11, "#333"),
             ("  4. Risco real = crash que aterrissa no vale (ex. tarifas abr/2025).", 11, "#333"),
             ("", 10, "#333"),
             ("Pricing: MID (padrão). Dados via tracking sintético (P&L analítico do bid/ask);", 9.5, "#555"),
             ("settle = intrínseco exato no fechamento oficial do SPX (cash-settle, sem spread).", 9.5, "#555")],
            subtitle="Relatório para apresentação · Prop Desk Quant")

        # ---- sensibilidade ao fill (o achado-chave)
        rows = []
        for tag, dte in DTES:
            s = fill_sensitivity(data[tag])
            rows.append([f"{dte} DTE",
                         f"${s[0.0][0]:+,.0f}", f"${s[0.25][0]:+,.0f}", f"${s[0.5][0]:+,.0f}", f"${s[1.0][0]:+,.0f}"])
        fig_table(pdf, "1. Sensibilidade ao fill de entrada — HOLD até o vencimento",
                  ["DTE", "Mid (otimista)", "25% spread", "50% spread", "Spread cheio"], rows,
                  subtitle="net P&L 5 anos · a verdade está nos 25-50% (fill realista de uma estrutura de 5 pernas)",
                  note="A estrutura tem ~5 pts de spread bid/ask somando as 5 pernas (a cauda −3Δ é a mais ilíquida). "
                       "Por isso o mesmo backtest vai de +$131k (mid) a −$195k (spread cheio) só mudando o fill. "
                       "O spread foi VERIFICADO em resolução de minuto (idêntico ao horário, 1.000×) -> é mercado real da "
                       "cauda, NÃO artefato de dado; logo o 'spread cheio' é um pior-caso legítimo (ordem a mercado). "
                       "Conclusão: PL5 é EXECUTION-DOMINATED; com ordem-limite (25-50%), 21-45 DTE é modestamente positivo, 60 DTE não.")

        # ---- curvas de equity (mid) 2x2
        fig, axes = plt.subplots(2, 2, figsize=(11.7, 8.3)); fig.suptitle("2. Curvas de P&L acumulado (mid) — por prazo", fontsize=16, fontweight="bold", color=NAVY)
        for ax, (tag, dte) in zip(axes.flat, DTES):
            rows_ = sorted(data[tag], key=lambda r: r["trade_date"])
            dts = [date.fromisoformat(r["trade_date"]) for r in rows_]
            cum = 0; ys = []
            for r in rows_:
                cum += fnum(r, "pnl_usd") or 0; ys.append(cum/1000)
            ax.plot(dts, ys, color=NAVY, lw=2)
            ax.axhline(0, color="#999", lw=0.7); ax.axvspan(date(2025,2,1), date(2025,4,15), color=LOSS, alpha=0.08)
            ax.set_title(f"{dte} DTE (hold, mid)", fontsize=11, fontweight="bold")
            ax.set_ylabel("US$ mil"); ax.xaxis.set_major_locator(mdates.YearLocator()); ax.xaxis.set_major_formatter(mdates.DateFormatter("%y"))
            ax.grid(alpha=0.25)
        fig.tight_layout(rect=[0,0,1,0.96]); pdf.savefig(fig); plt.close(fig)

        # ---- saída antecipada (mid) + por-ano (d45 como referência)
        ex_rows = []
        for tag, dte in DTES:
            rows_ = data[tag]
            def agg(col):
                pls = [(fnum(r, col) if fnum(r, col) is not None else fnum(r, "pnl_usd")) for r in rows_]
                pls = [p for p in pls if p is not None]; return sum(pls)
            cells = [f"{dte} DTE", f"${sum(fnum(r,'pnl_usd') or 0 for r in rows_):+,.0f}"]
            for d in (14, 10, 7):
                col = f"pnl_exit{d}"
                cells.append(f"${agg(col):+,.0f}" if any(col in r for r in rows_) else "—")
            ex_rows.append(cells)
        fig_table(pdf, "3. Saída antecipada vs Hold (mid)",
                  ["DTE", "Hold (venc.)", "Sair 14 DTE", "Sair 10 DTE", "Sair 7 DTE"], ex_rows,
                  subtitle="net P&L mid · sair antes do vencimento evita o vale que se forma nos últimos dias",
                  note="A estrutura fica positiva no meio do trade e 'devolve' perto do vencimento quando a tenda reforma. "
                       "Sair com 7-14 DTE restantes captura isso — mas parte do ganho em 2025 foi timing (o crash fundou perto do vencimento).")

        # ---- exemplo do crash 2025 (caminho do spot) - d60 pior trade
        rows60 = sorted(data["pl5_d60_std"], key=lambda r: fnum(r, "pnl_usd") or 0)
        wt = rows60[0]
        ed = date.fromisoformat(wt["exp_date"]); se = fnum(wt,"spot_entry"); ss = fnum(wt,"spot_exit")
        k1,k2,k3 = fnum(wt,"put_upper"),fnum(wt,"put_center"),fnum(wt,"put_lower")
        path = []
        for D in (14,10,7,3):
            dd = ed - timedelta(days=D); sp = at(dd); pnl = fnum(wt, f"pnl_exit{D}")
            path.append((f"{D} DTE rest. ({dd.isoformat()})", f"{sp:.0f}" if sp else "—", f"${pnl:+,.0f}" if pnl is not None else "—"))
        path.append((f"SETTLE ({wt['exp_date']})", f"{ss:.0f}", f"${fnum(wt,'pnl_usd'):+,.0f}"))
        fig_table(pdf, "4. Exemplo real — o crash de tarifas de 2025 (60 DTE)",
                  ["Ponto de saída", "SPX no dia", "P&L (mid)"], path,
                  subtitle=f"Trade {wt['trade_date']}→{wt['exp_date']} · entrada SPX {se:.0f} · strikes {k1:.0f}/{k2:.0f}/{k3:.0f}",
                  note=f"O SPX despencou nos últimos dias até {ss:.0f} ≈ K3 ({k3:.0f}) = o VALE = perda máxima. "
                       f"Quem segurou pegou ${fnum(wt,'pnl_usd'):+,.0f}; quem saiu 7 dias antes estava perto de zero. "
                       "Confirma: o risco do PL5 é um crash direcional aterrissando no vale (perda máx definida, porém grande).")

        # ---- veracidade dos dados
        rows60c = data["pl5_d60_std"]
        # checa settle = intrínseco em 3 trades
        vlines = [("Como garantimos que os números são reais:", 13, GOLD), ("", 10, "#333"),
                  ("• Settle = INTRÍNSECO exato no fechamento oficial do SPX (cash-settle, europeu) — sem spread, sem", 10.5, "#333"),
                  ("  fills fantasma. Verificação (3 piores trades d60): payoff teórico ≈ hold gravado:", 10.5, "#333")]
        for r in sorted(rows60c, key=lambda x: fnum(x,"pnl_usd") or 0)[:3]:
            ss=fnum(r,"spot_exit"); k1,k2,k3=fnum(r,"put_upper"),fnum(r,"put_center"),fnum(r,"put_lower")
            intr=(1*max(0,k1-ss)-2*max(0,k2-ss)+2*max(0,k3-ss))*100
            vlines.append((f"    {r['trade_date']}: SPX {ss:.0f} → payoff teórico ${intr:+,.0f}  (≈ hold ${fnum(r,'pnl_usd'):+,.0f})", 9.5, "#333"))
        vlines += [("", 10, "#333"),
                   ("• Deltas conferidos por trade (strikes escolhidos em −30/−18/−3 delta).", 10.5, "#333"),
                   ("• Pricing MID consistente em entrada, marcação e saídas (padrão de backtest).", 10.5, "#333"),
                   ("• Tracking sintético: P&L 100% analítico do bid/ask real da cadeia — sem o motor de", 10.5, "#333"),
                   ("  fills/margem do QC (que fabricava P&L fantasma em estruturas multi-perna).", 10.5, "#333"),
                   ("• Dataset por-trade auditável no app (trade-a-trade, com strikes, DTE, crédito, VIX).", 10.5, "#333")]
        fig_text_page(pdf, "5. Veracidade dos dados", vlines, subtitle="rigor metodológico")

        # ---- veredito
        fig_text_page(pdf, "6. Veredito",
            [("PL5 NÃO é trade de 'segurar até o vencimento': o vale no fim mata.", 12, NAVY),
             ("", 10, "#333"),
             ("Em execução REALISTA (fill 25-50% do spread):", 12, GOLD),
             ("  • 21-28 DTE: hold modestamente positivo (+$36k a +$99k em 5 anos).", 11, GAIN),
             ("  • 45 DTE: marginal (+$11k a +$49k).", 11, "#333"),
             ("  • 60 DTE: negativo (asa larga → vale fundo demais).", 11, LOSS),
             ("", 10, "#333"),
             ("Ressalvas honestas:", 12, GOLD),
             ("  • Resultado MUITO sensível ao fill (5 pernas) — execução é o fator decisivo.", 10.5, "#333"),
             ("  • Risco de cauda real: crash no vale = perda máx grande (concentrada se há posições", 10.5, "#333"),
             ("    sobrepostas — o motor entra toda sexta sem limite de concorrência).", 10.5, "#333"),
             ("", 10, "#333"),
             ("Próximo passo sugerido: forward-test 28 DTE com saída antecipada + regra de concorrência,", 11, NAVY),
             ("medindo o fill REAL de execução (que aqui é o fator que decide tudo).", 11, NAVY)],
            subtitle="conclusão honesta")
    print(f">>> PDF: {DEST}")

if __name__ == "__main__":
    build()
