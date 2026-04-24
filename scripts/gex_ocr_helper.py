#!/usr/bin/env python3
"""
gex_ocr_helper.py
─────────────────
Extrai níveis de GEX de um screenshot do TradingLitt (YouTube Weekly Outlook)
e gera strings no formato  label:preço  prontas para colar no indicador TradingView.

FLUXO SEGUNDA-FEIRA:
  1. Assistir Weekly Outlook do TradingLitt no YouTube
  2. Pausar no frame do gráfico SPY 15m (frame com melhor visibilidade dos labels)
  3. Print: Win+Shift+S → salvar como PNG em scripts/gex_screenshots/YYYY-MM-DD.png
  4. Verificar fator: SPX_spot ÷ SPY_spot  (ex: 6588 ÷ 656 = 10.04)
  5. Rodar: python scripts/gex_ocr_helper.py scripts/gex_screenshots/2026-04-14.png --factor 10.04
  6. Copiar cada linha do output → colar no campo correspondente do indicador TradingView

DEPENDÊNCIAS:
  pip install pytesseract opencv-python Pillow
  + Instalar Tesseract OCR: winget install UB-Mannheim.TesseractOCR
"""

import sys
import re
import argparse
from collections import defaultdict, Counter
from pathlib import Path
from datetime import date

try:
    import cv2
    import numpy as np
    import pytesseract
except ImportError as e:
    print(f"[ERRO] Dependência não instalada: {e}")
    print("Execute: pip install pytesseract opencv-python Pillow")
    sys.exit(1)

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ─── PADRÃO DE LABEL DO TRADINGLITT ──────────────────────────────────────────
# Captura: "p1 + ag2 + col ($660)" → label="p1 + ag2 + col", price="660"
# Captura: "g-flip ($660)"          → label="g-flip",          price="660"
# Captura: "pos gex starts ($653)"  → label="pos gex starts",  price="653"
LEVEL_RE = re.compile(
    r"([a-z][a-z0-9 +\-]*?)\s*\(\s*\$\s*(\d{2,4}(?:\.\d+)?)\s*\)",
    re.IGNORECASE
)

# ─── CORREÇÃO DE ERROS COMUNS DO OCR ─────────────────────────────────────────
OCR_FIXES = [
    (r"\bS(\d{3})\b",           r"$\1"),       # S660 → $660
    (r"\(S\s*(\d+)",            r"($\1"),       # (S660) → ($660)
    (r"\(5\s*(\d{2,4})\)",      r"($\1)"),      # (5660) → ($660)
    (r"g[—–\s]+flip",           "g-flip"),      # g flip / g—flip → g-flip
    (r"\bgflip\b",              "g-flip"),      # gflip → g-flip
    (r"\bflip\b",               "g-flip"),      # flip → g-flip
    (r"\bpos\s+gex\s+start\b",  "pos gex starts"),
    (r"\bneg\s+gex\s+start\b",  "neg gex starts"),
    (r"\bposigex\b",            "pos gex starts"),
    (r"\bnegigex\b",            "neg gex starts"),
    (r"\bl\b(?=\s+\()",         "n"),           # OCR confunde 'l' com 'n' ou 'i'
    (r"\bagi(\d)\b",            r"ag\1"),       # agi4 → ag4
]

def fix_ocr(text: str) -> str:
    for pattern, replacement in OCR_FIXES:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


# ─── PRÉ-PROCESSAMENTO ────────────────────────────────────────────────────────

def find_last_separator(img: np.ndarray, debug: bool = False) -> int:
    """
    Detecta a posição X da última linha vertical separadora de semana no chart.
    TradingLitt desenha linhas verticais cinzas tracejadas a cada segunda-feira.
    Retornamos o X da mais recente (mais à direita) para cropar só a semana atual.
    """
    h, w = img.shape[:2]
    gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Detecta bordas
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges   = cv2.Canny(blurred, 30, 100)

    # Hough probabilístico: procura linhas longas e quase verticais
    lines = cv2.HoughLinesP(
        edges,
        rho=1, theta=np.pi / 180,
        threshold=40,
        minLineLength=int(h * 0.35),   # linha deve ter pelo menos 35% da altura
        maxLineGap=int(h * 0.30),      # gap máximo de 30% (linha tracejada)
    )

    if lines is None:
        fallback = int(w * 0.72)
        if debug:
            print(f"  [separator] Nenhuma linha encontrada, usando fallback x={fallback}")
        return fallback

    # Filtra linhas verticais (ângulo > 75°) dentro da área interna do chart
    vertical_xs = []
    for seg in lines:
        x1, y1, x2, y2 = seg[0]
        if x2 == x1:
            angle = 90.0
        else:
            angle = abs(np.degrees(np.arctan2(abs(y2 - y1), abs(x2 - x1))))
        is_vertical  = angle > 75
        is_inner     = w * 0.10 < x1 < w * 0.93   # ignora bordas do chart
        if is_vertical and is_inner:
            vertical_xs.append(x1)

    if not vertical_xs:
        fallback = int(w * 0.72)
        if debug:
            print(f"  [separator] Sem linhas verticais internas, fallback x={fallback}")
        return fallback

    # Agrupa xs próximos (tolerância 10px) para eliminar detecções duplicadas
    vertical_xs.sort()
    groups = []
    group  = [vertical_xs[0]]
    for x in vertical_xs[1:]:
        if x - group[-1] <= 10:
            group.append(x)
        else:
            groups.append(int(np.mean(group)))
            group = [x]
    groups.append(int(np.mean(group)))

    # Pega o separador mais à direita (semana mais recente)
    last_sep = max(groups)

    if debug:
        print(f"  [separator] Separadores detectados em x={groups}")
        print(f"  [separator] Usando último separador: x={last_sep} ({last_sep/w*100:.0f}% da largura)")

    return last_sep


def crop_regions(img: np.ndarray, debug: bool = False) -> dict[str, np.ndarray]:
    """
    Retorna regiões de interesse para OCR.
    Estratégia principal: cropar à direita do último separador semanal,
    capturando apenas os labels da semana atual e evitando semanas anteriores.
    """
    h, w = img.shape[:2]

    # Posição do último separador semanal
    sep_x = find_last_separator(img, debug=debug)

    # Região primária: tudo à direita do separador (semana atual)
    current_week = img[:, sep_x:]

    # Fallbacks caso a detecção falhe
    regions = {
        "current_week":  current_week,                  # PRINCIPAL — só semana atual
        "right_quarter": img[:, int(w * 0.78):],        # fallback: último 22%
        "right_half":    img[:, int(w * 0.55):],        # fallback mais amplo
    }

    if debug:
        print(f"  [crop] current_week: x={sep_x} → {w} ({current_week.shape[1]}px de largura)")

    return regions


def preprocess_variants(img: np.ndarray) -> list[np.ndarray]:
    """
    Gera múltiplas variações pré-processadas para maximizar o acerto do OCR.
    TradingLitt usa tema escuro (fundo ~#131722, labels claros).
    """
    variants = []
    h, w = img.shape[:2]
    scale = 2

    # ── Variante 1: inversão + threshold clássico (para texto branco/claro)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    inv = cv2.bitwise_not(gray)
    _, t1 = cv2.threshold(inv, 100, 255, cv2.THRESH_BINARY)
    variants.append(cv2.resize(t1, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC))

    # ── Variante 2: CLAHE + inversão (melhora contraste local)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    eq = clahe.apply(gray)
    inv2 = cv2.bitwise_not(eq)
    _, t2 = cv2.threshold(inv2, 90, 255, cv2.THRESH_BINARY)
    variants.append(cv2.resize(t2, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC))

    # ── Variante 3: isolar texto verde (positive GEX — #00C853)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (35, 40, 40), (90, 255, 255))
    green_inv = cv2.bitwise_not(green)
    variants.append(cv2.resize(green_inv, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC))

    # ── Variante 4: isolar texto vermelho (negative GEX — #FF1744)
    red1 = cv2.inRange(hsv, (0, 50, 50),   (12, 255, 255))
    red2 = cv2.inRange(hsv, (155, 50, 50), (180, 255, 255))
    red  = cv2.bitwise_or(red1, red2)
    red_inv = cv2.bitwise_not(red)
    variants.append(cv2.resize(red_inv, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC))

    # ── Variante 5: isolar texto branco (g-flip)
    _, white = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
    white_inv = cv2.bitwise_not(white)
    variants.append(cv2.resize(white_inv, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC))

    # ── Variante 6: isolar texto roxo (aggregate — #AA00FF)
    purple = cv2.inRange(hsv, (125, 40, 40), (165, 255, 255))
    purple_inv = cv2.bitwise_not(purple)
    variants.append(cv2.resize(purple_inv, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC))

    return variants


# ─── OCR ──────────────────────────────────────────────────────────────────────

def run_ocr_on_image(img: np.ndarray) -> str:
    """Roda Tesseract com múltiplas configurações de PSM."""
    configs = [
        "--oem 3 --psm 11",   # sparse text (melhor para labels espalhados)
        "--oem 3 --psm 6",    # bloco uniforme
        "--oem 3 --psm 12",   # sparse text + OSD
    ]
    texts = []
    for cfg in configs:
        try:
            t = pytesseract.image_to_string(img, config=cfg)
            if t.strip():
                texts.append(t)
        except Exception:
            pass
    return "\n".join(texts)


def extract_all_text(img: np.ndarray, debug: bool = False) -> str:
    """Processa todas as regiões e variantes, consolida o texto bruto."""
    all_text = []
    regions = crop_regions(img, debug=debug)

    for region_name, region_img in regions.items():
        if region_img.shape[1] < 50:   # ignora crops muito estreitos
            continue
        variants = preprocess_variants(region_img)
        for variant in variants:
            text = run_ocr_on_image(variant)
            if text.strip():
                all_text.append(text)

    return "\n".join(all_text)


# ─── EXTRAÇÃO E CATEGORIZAÇÃO ─────────────────────────────────────────────────

def extract_levels(raw_text: str) -> list[tuple[str, float]]:
    """Extrai pares (label, preço) do texto bruto do OCR."""
    text = fix_ocr(raw_text)
    found = []
    seen = set()

    for m in LEVEL_RE.finditer(text):
        lbl   = m.group(1).strip()
        price = float(m.group(2))

        # Normaliza espaços no label
        lbl = re.sub(r"\s+", " ", lbl).strip().lower()

        # Filtro de sanidade: SPY entre $400 e $900
        if not (400 <= price <= 900):
            continue

        # Deduplica (mesmo label + preço)
        key = (lbl, round(price))
        if key in seen:
            continue
        seen.add(key)

        found.append((lbl, price))

    return found


def categorize(label: str) -> str:
    """Classifica o label na categoria GEX."""
    t = label.lower().strip()
    if "g-flip" in t or "gflip" in t:
        return "gflip"
    if "pos gex" in t:
        return "pos_zone"
    if "neg gex" in t:
        return "neg_zone"
    if re.match(r"^p[\d +]|^p$", t):
        return "positive"
    if re.match(r"^n[\d +\-]|^n$|^r[\d]?", t):
        return "negative"
    if re.match(r"^ag[\d ]|^agg", t):
        return "aggregate"
    return "unknown"


def normalize_label(lbl: str) -> str:
    """Normaliza o label para o formato do Pine Script: sem espaços ao redor do +."""
    # "p1 + ag2 + col" → "p1+ag2+col"
    lbl = re.sub(r"\s*\+\s*", "+", lbl.strip())
    return lbl


# ─── FORMATAÇÃO DO OUTPUT ─────────────────────────────────────────────────────

def format_output(grouped: dict, today: str, factor: float = 1.0) -> str:
    """
    Formata o output no formato  label:preço  pronto para colar no TradingView.
    Se factor > 1, mostra o equivalente SPX para conferência visual.
    """
    show_spx = factor > 1.0
    sep = "═" * 62
    header_spx = f"  fator SPY→SPX: {factor:.2f}" if show_spx else ""
    lines = [
        sep,
        f"  GEX WEEKLY LEVELS — {today}   {header_spx}",
        f"  Copie cada linha para o campo correspondente no TradingView:",
        sep,
    ]

    fields = [
        ("gflip",    "Gamma Flip          "),
        ("positive", "Positive GEX        "),
        ("negative", "Negative GEX        "),
        ("aggregate","Aggregate           "),
        ("pos_zone", "Pos GEX Zone Start  "),
        ("neg_zone", "Neg GEX Zone Start  "),
    ]

    for cat, field_label in fields:
        levels = grouped.get(cat, [])

        if not levels:
            lines.append(f"  {field_label}→  (não encontrado — preencher manualmente)")
            continue

        # Ordena por preço decrescente, deduplica
        seen_prices = set()
        unique = []
        for lbl, price in sorted(levels, key=lambda x: -x[1]):
            p_round = round(price)
            if p_round not in seen_prices:
                seen_prices.add(p_round)
                unique.append((lbl, p_round))

        if cat in ("pos_zone", "neg_zone"):
            lbl, price = unique[0]
            spx_str = f"   ← SPX: {round(price * factor):,}" if show_spx else ""
            lines.append(f"  {field_label}→  {normalize_label(lbl)}:{price}{spx_str}")
        else:
            pairs    = ", ".join(f"{normalize_label(lbl)}:{price}" for lbl, price in unique)
            lines.append(f"  {field_label}→  {pairs}")
            if show_spx:
                spx_vals = ", ".join(str(round(p * factor)) for _, p in unique)
                lines.append(f"  {'':22}   ← SPX: {spx_vals}")

    if grouped.get("unknown"):
        unknown = grouped["unknown"]
        unknown_str = ", ".join(f"{normalize_label(lbl)}:{round(p)}" for lbl, p in unknown)
        lines.append(f"\n  (Não classificados — revisar manualmente):")
        lines.append(f"  {unknown_str}")

    lines.append(sep)
    return "\n".join(lines)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extrai níveis GEX de screenshot do TradingLitt",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exemplo: python gex_ocr_helper.py screenshot.png --factor 10.04"
    )
    parser.add_argument("screenshot",
        help="Caminho para o screenshot PNG ou JPG")
    parser.add_argument("--factor", type=float, default=1.0,
        help="Fator SPY→SPX (ex: 10.04). Calcule: SPX_spot ÷ SPY_spot. "
             "Quando informado, exibe coluna SPX equivalente.")
    parser.add_argument("--debug", action="store_true",
        help="Mostra texto bruto do OCR para diagnóstico")
    args = parser.parse_args()

    img_path = Path(args.screenshot)
    if not img_path.exists():
        print(f"[ERRO] Arquivo não encontrado: {img_path}")
        sys.exit(1)

    print(f"Processando: {img_path.name} ...")

    img = cv2.imread(str(img_path))
    if img is None:
        print("[ERRO] Não foi possível carregar a imagem. Use PNG ou JPG.")
        sys.exit(1)

    h, w = img.shape[:2]
    print(f"Dimensões: {w}×{h}px")

    raw_text = extract_all_text(img, debug=args.debug)

    if args.debug:
        print("\n── TEXTO BRUTO DO OCR ──────────────────────────────────")
        print(raw_text[:3000])
        print("────────────────────────────────────────────────────────\n")

    levels = extract_levels(raw_text)

    if not levels:
        print("\n[AVISO] Nenhum nível encontrado.")
        print("Dicas:")
        print("  • Use PNG (melhor que JPG para OCR)")
        print("  • Pause o vídeo no frame com os labels mais visíveis (lado direito do chart)")
        print("  • Use --debug para ver o texto bruto extraído")
        sys.exit(0)

    grouped = defaultdict(list)
    for lbl, price in levels:
        cat = categorize(lbl)
        grouped[cat].append((lbl, price))

    total = sum(len(v) for v in grouped.values())
    cats  = sum(1 for k, v in grouped.items() if k != "unknown" and v)
    print(f"Níveis extraídos: {total} em {cats} categorias\n")

    today = date.today().strftime("%d/%m/%Y")
    print(format_output(dict(grouped), today, factor=args.factor))
    print()


if __name__ == "__main__":
    main()
