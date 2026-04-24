"""
===============================================================================
 MenthorQ Historical Levels Scraper — Data Lake Edition
 Prop Desk Quant | Autenticação Híbrida Playwright + Fetch Injection
===============================================================================
 Arquitetura:
   1. Browser não-headless abre MenthorQ — você faz login manualmente
   2. Você clica UMA vez no calendário → Playwright captura o nonce do POST real
   3. Para cada dia útil, o script busca o snapshot mais recente e segue a
      cadeia de previous_run_id de trás para frente até o primeiro do dia
   4. Cada snapshot gera uma linha no CSV (granularidade intraday completa)
   5. Regex extrai 6 níveis de preço (regular + 0DTE), Net GEX com sinal,
      Gamma Condition, run_id e timestamp

 SCHEMA: date, timestamp, run_id, call_res, call_res_0dte, put_sup,
         put_sup_0dte, hvl, hvl_0dte, net_gex, gamma_condition
 OUTPUT: data/menthorq_levels.csv (append progressivo — seguro p/ interrupções)
 IDEMPOTÊNCIA: dias com qualquer linha no CSV são pulados automaticamente
===============================================================================
"""

import asyncio
import csv
import random
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode, unquote_plus

from playwright.async_api import async_playwright, Page, Request


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

MENTHORQ_BASE    = "https://menthorq.com"
AJAX_ENDPOINT    = "/wp-admin/admin-ajax.php"

DATE_START       = date(2025, 12, 2)
DATE_END         = date.today()

TICKER           = "spx"
IS_INTRADAY      = "true"

OUTPUT_CSV       = Path(__file__).parent.parent / "data" / "menthorq_levels.csv"

MAX_HOPS_PER_DAY = 15     # segurança: nunca mais de 15 snapshots por dia

# Delays gaussianos entre requisições (segundos)
DELAY_MEAN       = 5.0
DELAY_STD        = 1.5
DELAY_MIN        = 3.0
DELAY_MAX        = 9.0


# ─────────────────────────────────────────────────────────────────────────────
# REGEX — EXTRAÇÃO DE NÍVEIS
# ─────────────────────────────────────────────────────────────────────────────
# Formatos reais confirmados no text_data do MenthorQ:
#
#   Regular : "Call Resistance remains Unchanged at 7100"
#             "Put Support Decreased by 50 points to 6600"
#   0DTE    : "Call Resistance 0DTE remains Unchanged at 6850"
#             "High Vol Level 0DTE Decreased by 10 points to 5720"
#   HVL     : "High Vol Level remains Unchanged at 6850"
#             "High Vol Level Decreased by 10 points to 6775"
#
# Estratégia:
#   • _LEVEL_VAL captura o número após " at " ou " to " (ambos os formatos)
#   • Lookahead (?!\s+0DTE) nos padrões regulares impede capturar variantes 0DTE
#   • 0DTE patterns exigem "0DTE" logo após o nome do nível
#   • Qualquer nível < 1000 descartado como falso positivo

_LEVEL_VAL = r".*?\s+(?:at|to)\s+([\d,]+(?:\.\d+)?)"
_MIN_LEVEL = 1_000

# Níveis regulares — lookahead (?!\s+0DTE) exclui variantes "Call Resistance 0DTE"
PATTERN_CALL = re.compile(
    r"Call\s+Resistance(?!\s+0DTE)" + _LEVEL_VAL,
    re.IGNORECASE | re.DOTALL,
)
PATTERN_PUT = re.compile(
    r"Put\s+Support(?!\s+0DTE)" + _LEVEL_VAL,
    re.IGNORECASE | re.DOTALL,
)
PATTERN_HVL = re.compile(
    r"High\s+Vol(?:atility)?\s+Level(?!\s+0DTE)" + _LEVEL_VAL,
    re.IGNORECASE | re.DOTALL,
)

# Níveis 0DTE — "0DTE" aparece imediatamente após o nome do nível
PATTERN_CALL_0DTE = re.compile(
    r"Call\s+Resistance\s+0DTE" + _LEVEL_VAL,
    re.IGNORECASE | re.DOTALL,
)
PATTERN_PUT_0DTE = re.compile(
    r"Put\s+Support\s+0DTE" + _LEVEL_VAL,
    re.IGNORECASE | re.DOTALL,
)
PATTERN_HVL_0DTE = re.compile(
    r"High\s+Vol(?:atility)?\s+Level\s+0DTE" + _LEVEL_VAL,
    re.IGNORECASE | re.DOTALL,
)

# Net GEX — sem exigir "has Increased/Decreased"; busca "is now ±VALUE[unit]"
PATTERN_NET_GEX = re.compile(
    r"Net\s+GEX\b.*?is\s+now\s+([-+]?[\d,.]+)\s*([BbMmTtKk]?)",
    re.IGNORECASE | re.DOTALL,
)
PATTERN_GAMMA_COND = re.compile(
    r"Gamma\s+Condition:\s+Currently\s+(Positive|Negative)",
    re.IGNORECASE,
)

_GEX_UNITS = {"B": 1e9, "M": 1e6, "T": 1e12, "K": 1e3, "": 1.0}


def _level(m: re.Match | None) -> float | None:
    """Extrai e valida nível de preço de um match. Descarta se < _MIN_LEVEL."""
    if m is None:
        return None
    try:
        v = float(m.group(1).replace(",", ""))
        return v if v >= _MIN_LEVEL else None
    except (ValueError, IndexError):
        return None


def _gex(m: re.Match | None) -> float | None:
    """Extrai Net GEX preservando sinal e escalando pela unidade (M/B/T)."""
    if m is None:
        return None
    try:
        value = float(m.group(1).replace(",", ""))
        unit  = (m.group(2) or "").upper()
        return value * _GEX_UNITS.get(unit, 1.0)
    except (ValueError, AttributeError):
        return None


def extract_levels(text: str) -> dict:
    """
    Extrai todos os níveis de um snapshot de text_data.
    Retorna dict com as 9 colunas analíticas do schema.
    """
    return {
        "call_res":       _level(PATTERN_CALL.search(text)),
        "call_res_0dte":  _level(PATTERN_CALL_0DTE.search(text)),
        "put_sup":        _level(PATTERN_PUT.search(text)),
        "put_sup_0dte":   _level(PATTERN_PUT_0DTE.search(text)),
        "hvl":            _level(PATTERN_HVL.search(text)),
        "hvl_0dte":       _level(PATTERN_HVL_0DTE.search(text)),
        "net_gex":        _gex(PATTERN_NET_GEX.search(text)),
        "gamma_condition": (
            m.group(1).capitalize()
            if (m := PATTERN_GAMMA_COND.search(text)) else None
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# DIAS ÚTEIS NYSE
# ─────────────────────────────────────────────────────────────────────────────

NYSE_HOLIDAYS = {
    date(2025, 12, 25),
    date(2026, 1,  1),
    date(2026, 1,  19),
    date(2026, 2,  16),
    date(2026, 4,  3),
}


def business_days(start: date, end: date) -> list[date]:
    days, current = [], start
    while current <= end:
        if current.weekday() < 5 and current not in NYSE_HOLIDAYS:
            days.append(current)
        current += timedelta(days=1)
    return days


# ─────────────────────────────────────────────────────────────────────────────
# CSV
# ─────────────────────────────────────────────────────────────────────────────

CSV_FIELDNAMES = [
    "date", "timestamp", "run_id",
    "call_res", "call_res_0dte",
    "put_sup",  "put_sup_0dte",
    "hvl",      "hvl_0dte",
    "net_gex",  "gamma_condition",
]


def load_done_dates(csv_path: Path) -> set[str]:
    """Datas com qualquer linha já extraída → pular na próxima execução."""
    if not csv_path.exists():
        return set()
    with open(csv_path, newline="", encoding="utf-8") as f:
        return {row["date"] for row in csv.DictReader(f) if row.get("date")}


def append_row(csv_path: Path, row: dict) -> None:
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
        if write_header:
            w.writeheader()
        w.writerow(row)


# ─────────────────────────────────────────────────────────────────────────────
# DELAY GAUSSIANO
# ─────────────────────────────────────────────────────────────────────────────

def human_delay() -> float:
    return max(DELAY_MIN, min(DELAY_MAX, random.gauss(DELAY_MEAN, DELAY_STD)))


# ─────────────────────────────────────────────────────────────────────────────
# CAPTURA DO NONCE VIA INTERCEPTAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

async def wait_for_nonce(page: Page) -> str:
    captured = {"security": None}

    async def handle_route(route, request: Request):
        if (
            "admin-ajax.php" in request.url
            and request.method == "POST"
            and not captured["security"]
        ):
            m = re.search(r"(?:^|&)security=([^&\s]+)", request.post_data or "")
            if m:
                captured["security"] = unquote_plus(m.group(1))
                print(f"\n  [OK] Nonce capturado: {captured['security']}")
        await route.continue_()

    await page.route("**/*", handle_route)

    print("\n" + "─" * 60)
    print("  AÇÃO: Clique em QUALQUER data no calendário MenthorQ.")
    print("  O nonce será capturado automaticamente do POST real.")
    print("─" * 60)

    for _ in range(240):   # timeout 120s
        if captured["security"]:
            break
        await asyncio.sleep(0.5)
    else:
        sys.exit("[ERRO] Timeout: nonce não capturado. Clique em uma data.")

    await page.unroute("**/*", handle_route)
    return captured["security"]


# ─────────────────────────────────────────────────────────────────────────────
# FETCH INJECTION — SNAPSHOT ÚNICO (com ou sem run_id)
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_snapshot(
    page: Page,
    trade_date: date,
    nonce: str,
    run_id: str | None = None,
) -> dict | None:
    """
    Dispara um POST via page.evaluate(fetch(...)) no contexto autenticado.
    Se run_id=None: busca o snapshot mais recente do dia.
    Se run_id=str:  busca o snapshot específico (hop na cadeia).

    Retorna dict com: text_data, run_id, previous_run_id, timestamp.
    """
    payload: dict = {
        "action":       "get_command",
        "security":     nonce,
        "command_slug": "liquidity_summary",
        "date":         trade_date.strftime("%Y-%m-%d"),
        "is_intraday":  IS_INTRADAY,
        "ticker":       TICKER,
    }
    if run_id:
        payload["run_id"] = run_id

    body = urlencode(payload)

    js = f"""
    async () => {{
        try {{
            const r = await fetch('{AJAX_ENDPOINT}', {{
                method:  'POST',
                headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
                body:    '{body}'
            }});
            if (!r.ok) return {{_err: r.status}};
            return await r.json();
        }} catch(e) {{ return {{_err: e.toString()}}; }}
    }}
    """

    try:
        raw = await page.evaluate(js)
    except Exception as exc:
        print(f"    [WARN] evaluate: {exc}")
        return None

    if not raw or raw.get("_err") or raw.get("error"):
        return None

    # Navegar na estrutura — suporta múltiplos layouts de resposta
    resource = (
        (raw.get("data") or {}).get("resource")
        or raw.get("resource")
        or raw.get("data")
        or {}
    )

    text_data = (
        resource.get("text_data")
        or raw.get("text_data")
        or ""
    )
    if not text_data:
        return None

    # Metadados do snapshot — fallbacks para diferentes nomes de campo
    r_id = (
        resource.get("run_id")
        or resource.get("id")
        or resource.get("run_key")
    )
    prev_id = (
        resource.get("previous_run_id")
        or resource.get("prev_run_id")
        or resource.get("previous_id")
    )
    timestamp = (
        resource.get("run_timestamp")   # campo confirmado na API
        or resource.get("created_at")
        or resource.get("timestamp")
        or resource.get("run_time")
        or resource.get("datetime")
        or resource.get("date")
    )

    return {
        "text_data":       text_data,
        "run_id":          r_id,
        "previous_run_id": prev_id,
        "timestamp":       timestamp,
    }


# ─────────────────────────────────────────────────────────────────────────────
# TRAVERSAL — CADEIA COMPLETA DO DIA
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_all_snapshots_for_day(
    page: Page,
    trade_date: date,
    nonce: str,
) -> list[dict]:
    """
    Busca TODOS os snapshots do dia seguindo a cadeia previous_run_id.
    Começa do mais recente e vai até o primeiro (quando previous_run_id é nulo).
    Retorna lista ordenada cronologicamente (mais antigo primeiro).

    Proteções:
      - MAX_HOPS_PER_DAY: evita loops infinitos
      - Detecção de ciclos: seen_run_ids
      - Human delay entre cada hop
    """
    date_str    = trade_date.strftime("%Y-%m-%d")
    snapshots   = []
    seen_ids    = set()

    # ── Hop 0: snapshot mais recente do dia ───────────────────────────────────
    snap = await fetch_snapshot(page, trade_date, nonce, run_id=None)
    if snap is None:
        print(f"    [SKIP] Sem dados para {date_str}.")
        return []

    snapshots.append(snap)
    if snap["run_id"]:
        seen_ids.add(snap["run_id"])

    # ── Hops seguintes: remontar a cadeia para trás ───────────────────────────
    for hop in range(1, MAX_HOPS_PER_DAY):
        prev_id = snapshots[-1].get("previous_run_id")

        if not prev_id:
            break                      # chegamos ao primeiro snapshot do dia

        if prev_id in seen_ids:
            print(f"    [WARN] Ciclo detectado em run_id={prev_id}. Abortando cadeia.")
            break

        await asyncio.sleep(human_delay())

        snap = await fetch_snapshot(page, trade_date, nonce, run_id=prev_id)
        if snap is None:
            print(f"    [WARN] Hop {hop}: run_id={prev_id} retornou vazio.")
            break

        snapshots.append(snap)
        if snap["run_id"]:
            seen_ids.add(snap["run_id"])

    # Inverter: queremos ordem cronológica (mais antigo primeiro) no CSV
    snapshots.reverse()
    return snapshots


# ─────────────────────────────────────────────────────────────────────────────
# FORMATAÇÃO INLINE (terminal)
# ─────────────────────────────────────────────────────────────────────────────

def fmt_gex(v: float | None) -> str:
    if v is None:
        return "N/A"
    sign = "-" if v < 0 else "+"
    av   = abs(v)
    if av >= 1e9: return f"{sign}{av/1e9:.2f}B"
    if av >= 1e6: return f"{sign}{av/1e6:.1f}M"
    return f"{sign}{av:.0f}"


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

async def main() -> None:
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    done_dates   = load_done_dates(OUTPUT_CSV)
    all_days     = business_days(DATE_START, DATE_END)
    pending_days = [d for d in all_days if d.strftime("%Y-%m-%d") not in done_dates]

    print("\n" + "=" * 64)
    print("  MenthorQ Historical Levels Scraper — Data Lake Edition")
    print(f"  Prop Desk Quant | {DATE_START} → {DATE_END} | Granularidade Intraday")
    print("=" * 64)
    print(f"  Dias úteis no range : {len(all_days)}")
    print(f"  Já extraídos (skip) : {len(done_dates)}")
    print(f"  A extrair           : {len(pending_days)}")
    print(f"  Max hops/dia        : {MAX_HOPS_PER_DAY}")
    print(f"  Output              : {OUTPUT_CSV}\n")

    if not pending_days:
        print("[OK] Data Lake completo. Nenhum dia pendente.")
        return

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        page = await context.new_page()

        # ── Passo 1: login manual ─────────────────────────────────────────────
        await page.goto(MENTHORQ_BASE, wait_until="domcontentloaded")
        print("─" * 64)
        print("  PASSO 1 — Faça login na conta Premium e pressione ENTER.")
        print("─" * 64)
        input("  >>> ENTER quando logado: ")
        print()

        # ── Passo 2: captura do nonce ─────────────────────────────────────────
        nonce = await wait_for_nonce(page)
        print(f"  Nonce ativo: {nonce}\n")

        # ── Passo 3: loop principal ───────────────────────────────────────────
        print(f"  EXTRAÇÃO — {len(pending_days)} dias pendentes\n")

        total_rows = 0
        days_ok    = 0
        days_skip  = 0

        for i, trade_date in enumerate(pending_days, 1):
            date_str = trade_date.strftime("%Y-%m-%d")
            print(f"  [{i:>3}/{len(pending_days)}] {date_str}", flush=True)

            snapshots = await fetch_all_snapshots_for_day(page, trade_date, nonce)

            if not snapshots:
                days_skip += 1
                print()
                continue

            print(f"    {len(snapshots)} snapshot(s) encontrado(s):")

            for snap in snapshots:
                levels = extract_levels(snap["text_data"])

                # Log compacto por linha
                ts_short = str(snap["timestamp"] or "")[:19]
                print(
                    f"    {ts_short}  "
                    f"Call={str(levels['call_res'] or 'N/A'):>7}  "
                    f"Put={str(levels['put_sup'] or 'N/A'):>7}  "
                    f"HVL={str(levels['hvl'] or 'N/A'):>7}  "
                    f"GEX={fmt_gex(levels['net_gex']):>9}  "
                    f"({levels['gamma_condition'] or '?'})"
                )

                append_row(OUTPUT_CSV, {
                    "date":            date_str,
                    "timestamp":       snap["timestamp"],
                    "run_id":          snap["run_id"],
                    "call_res":        levels["call_res"],
                    "call_res_0dte":   levels["call_res_0dte"],
                    "put_sup":         levels["put_sup"],
                    "put_sup_0dte":    levels["put_sup_0dte"],
                    "hvl":             levels["hvl"],
                    "hvl_0dte":        levels["hvl_0dte"],
                    "net_gex":         levels["net_gex"],
                    "gamma_condition": levels["gamma_condition"],
                })
                total_rows += 1

            days_ok += 1
            print()

            # Delay entre dias (não entre hops — já tem delay interno)
            if i < len(pending_days):
                await asyncio.sleep(human_delay())

        # ── Relatório ─────────────────────────────────────────────────────────
        w = 64
        print(f"+{'=' * w}+")
        print(f"|{'DATA LAKE — EXTRAÇÃO CONCLUÍDA':^{w}}|")
        print(f"+{'=' * w}+")
        print(f"|  Dias extraídos  : {days_ok:<{w-20}}|")
        print(f"|  Dias sem dados  : {days_skip:<{w-20}}|")
        print(f"|  Total de linhas : {total_rows:<{w-20}}|")
        print(f"|  Output          : {OUTPUT_CSV.name:<{w-20}}|")
        print(f"+{'=' * w}+\n")

        await browser.close()


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    asyncio.run(main())
