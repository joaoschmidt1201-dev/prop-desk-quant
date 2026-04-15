#!/usr/bin/env python3
"""
morning_briefing.py
-------------------
Generates a daily pre-market briefing for the Prop Desk and posts to Discord.
Runs every weekday at 9 AM ET via GitHub Actions.

Required environment variables:
  PERPLEXITY_API_KEY  — from perplexity.ai
  DISCORD_WEBHOOK_URL — from Discord server settings

Data sources:
  - yfinance       : VIX, ES/NQ/RTY futures, SPX price + moving averages
  - gex_history.json : GEX levels from TradingLitt (committed to repo every Monday)
  - Perplexity API : real-time news research + briefing generation
"""

import os
import re
import sys
import json
import requests
import pandas as pd
from datetime import datetime, date, timedelta
from pathlib import Path

try:
    import yfinance as yf
except ImportError:
    print("[ERROR] yfinance not installed.")
    sys.exit(1)

try:
    import pytz
    ET = pytz.timezone("America/New_York")
except ImportError:
    print("[ERROR] pytz not installed.")
    sys.exit(1)

ROOT         = Path(__file__).parent.parent
HISTORY_FILE = ROOT / "gex_history.json"       # legacy (kept for backward compat)
HISTORY_SPX  = ROOT / "gex_history_spx.json"   # new pipeline
HISTORY_NDX  = ROOT / "gex_history_ndx.json"   # new pipeline

# Top S&P 500 tickers by market cap — used to filter earnings calendar
_SP500_MAJORS = {
    "AAPL", "NVDA", "MSFT", "AMZN", "META", "GOOGL", "GOOG", "TSLA",
    "JPM", "V", "UNH", "MA", "XOM", "JNJ", "PG", "HD", "AVGO",
    "LLY", "MRK", "BAC", "ABBV", "KO", "PEP", "WMT", "COST",
    "CRM", "NFLX", "AMD", "ORCL", "TMO",
}

# ─── MARKET DATA ─────────────────────────────────────────────────────────────

def fetch_market_data() -> dict:
    """Fetches VIX, ES, NQ, RTY futures and SPX from Yahoo Finance."""
    symbols = {
        "VIX":  "^VIX",
        "ES":   "ES=F",
        "NQ":   "NQ=F",
        "RTY":  "RTY=F",
        "SPX":  "^GSPC",
        "NDX":  "^NDX",
    }
    result = {}
    for name, ticker in symbols.items():
        try:
            hist = yf.Ticker(ticker).history(period="5d", auto_adjust=True)
            if hist.empty:
                continue
            price = round(float(hist["Close"].iloc[-1]), 2)
            prev  = round(float(hist["Close"].iloc[-2]), 2) if len(hist) >= 2 else price
            chg   = round(price - prev, 2)
            chg_pct = round((chg / prev) * 100, 2) if prev else 0.0
            result[name] = {
                "price":      price,
                "change":     chg,
                "change_pct": chg_pct,
                "arrow":      "▲" if chg >= 0 else "▼",
            }
        except Exception as e:
            print(f"  [WARNING] Could not fetch {name} ({ticker}): {e}")
    return result


def fetch_spx_technicals() -> dict:
    """Fetches SPX history and computes W EMA20, D SMA50, D SMA200."""
    try:
        daily  = yf.Ticker("^GSPC").history(period="2y", auto_adjust=True)
        weekly = yf.Ticker("^GSPC").history(period="2y", interval="1wk", auto_adjust=True)
        if daily.empty or len(daily) < 200 or weekly.empty or len(weekly) < 20:
            return {}
        price    = round(float(daily["Close"].iloc[-1]), 2)
        d_sma50  = round(float(daily["Close"].rolling(50).mean().iloc[-1]), 2)
        d_sma200 = round(float(daily["Close"].rolling(200).mean().iloc[-1]), 2)
        w_ema20  = round(float(weekly["Close"].ewm(span=20, adjust=False).mean().iloc[-1]), 2)

        def ma_info(val):
            dist = round((price - val) / val * 100, 2)
            return {"value": val, "dist_pct": dist, "side": "above" if dist >= 0 else "below"}

        return {
            "price": price,
            "mas": {
                "W EMA20":  ma_info(w_ema20),
                "D SMA50":  ma_info(d_sma50),
                "D SMA200": ma_info(d_sma200),
            },
        }
    except Exception as e:
        print(f"  [WARNING] Could not compute SPX technicals: {e}")
        return {}

# ─── FINNHUB — ECONOMIC & EARNINGS CALENDAR ──────────────────────────────────

def fetch_economic_calendar(today: date, api_key: str) -> str:
    """Fetches high-impact US economic events from Finnhub for today.
    Returns formatted string to inject into Perplexity prompt.
    Returns '' on failure (graceful degradation)."""
    if not api_key:
        return ""
    date_str = today.strftime("%Y-%m-%d")
    try:
        resp = requests.get(
            "https://finnhub.io/api/v1/calendar/economic",
            params={"from": date_str, "to": date_str, "token": api_key},
            timeout=15,
        )
        resp.raise_for_status()
        events = resp.json().get("economicCalendar", [])
    except Exception as e:
        print(f"  [WARNING] Finnhub economic calendar failed: {e}")
        return ""

    # Filter: US + high impact only (medium = too much noise for the desk)
    filtered = [
        e for e in events
        if e.get("country", "").upper() == "US"
        and e.get("impact", "").lower() == "high"
    ]
    if not filtered:
        return "No high-impact US macro releases scheduled."

    filtered.sort(key=lambda e: e.get("time", ""))

    date_label = today.strftime("%A, %B %d")
    lines = [f"--- ECONOMIC CALENDAR — {date_label} (source: Finnhub) ---"]
    for e in filtered:
        name   = e.get("event", "Unknown")
        impact = e.get("impact", "").upper()
        est    = e.get("estimate", "")
        unit   = e.get("unit", "")
        time_str = ""
        raw_time = e.get("time", "")
        if raw_time:
            try:
                from datetime import datetime as _dt
                t_utc = _dt.strptime(raw_time[:16], "%Y-%m-%d %H:%M")
                t_et  = pytz.utc.localize(t_utc).astimezone(ET)
                time_str = t_et.strftime("%H:%M ET") + "  "
            except (ValueError, AttributeError):
                pass
        line = f"• {time_str}{name}  [{impact} IMPACT]"
        if est:
            line += f"  est: {est}{unit}"
        lines.append(line)

    return "\n".join(lines)


def fetch_earnings_calendar(today: date, api_key: str) -> str:
    """Fetches earnings releases for major S&P 500 components from Finnhub.
    Returns formatted string to inject into Perplexity prompt.
    Returns '' on failure (graceful degradation)."""
    if not api_key:
        return ""
    date_str = today.strftime("%Y-%m-%d")
    try:
        resp = requests.get(
            "https://finnhub.io/api/v1/calendar/earnings",
            params={"from": date_str, "to": date_str, "token": api_key},
            timeout=15,
        )
        resp.raise_for_status()
        events = resp.json().get("earningsCalendar", [])
    except Exception as e:
        print(f"  [WARNING] Finnhub earnings calendar failed: {e}")
        return ""

    # Filter: only major S&P 500 tickers
    filtered = [e for e in events if e.get("symbol", "") in _SP500_MAJORS]
    if not filtered:
        return "No major S&P 500 earnings scheduled."

    _HOUR_LABEL = {"bmo": "pre-market", "amc": "after-close", "dmh": "during session"}

    date_label = today.strftime("%A, %B %d")
    lines = [f"--- EARNINGS CALENDAR — {date_label} (source: Finnhub) ---"]
    for e in sorted(filtered, key=lambda x: x.get("symbol", "")):
        sym   = e.get("symbol", "?")
        hour  = _HOUR_LABEL.get(e.get("hour", ""), e.get("hour", ""))
        eps   = e.get("epsEstimate")
        rev   = e.get("revenueEstimate")
        line  = f"• {sym}  ({hour})"
        if eps is not None:
            line += f"  EPS est: {eps:.2f}"
        if rev is not None:
            rev_b = rev / 1e9
            line += f"  Rev est: ${rev_b:.1f}B"
        lines.append(line)

    return "\n".join(lines)


# ─── GEX LEVELS ──────────────────────────────────────────────────────────────

def get_gex_context(today: date) -> dict:
    """Reads gex_history.json. Returns dict with 'text' (str) and 'is_current' (bool)."""
    if not HISTORY_FILE.exists():
        return {"text": "GEX levels not available (gex_history.json not found in repo).", "is_current": False}
    try:
        history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"text": "GEX levels not available (could not parse history file).", "is_current": False}
    if not history:
        return {"text": "No GEX levels recorded yet.", "is_current": False}

    latest    = history[-1]
    week_date = latest.get("week", "")
    factor    = latest.get("factor", 1.0)

    # Detect if data is from the current calendar week
    monday_of_week = today - timedelta(days=today.weekday())
    is_current = False
    try:
        week_dt    = datetime.strptime(week_date, "%Y-%m-%d").date()
        is_current = week_dt >= monday_of_week
    except (ValueError, TypeError):
        pass

    if not is_current:
        return {
            "text": (
                f"GEX DATA NOT YET UPDATED for this week (most recent: week of {week_date}). "
                "TradingLIT has not yet released this week's levels."
            ),
            "is_current": False,
        }

    is_monday = today.weekday() == 0

    # Level type legend — only included on Mondays to educate the LLM
    LEGEND = (
        "LEVEL TYPE LEGEND (source: TradingLIT):\n"
        "  g-flip        : Gamma Flip — where dealer hedging shifts direction. "
                          "Price ABOVE = bullish dealer flow; price BELOW = bearish dealer flow. Critical inflection.\n"
        "  p/p1/p2/p3    : Positive GEX levels ranked by magnitude. Act as RESISTANCE (Call Walls).\n"
        "  n/n1/n2       : Negative GEX levels ranked by magnitude. Act as SUPPORT (Put Walls).\n"
        "  ag            : Aggregate gamma from multiple strikes — strong CONFLUENCE level.\n"
        "  coi/poi/hoi   : Coinciding option interest at that strike — reinforces the level.\n"
        "  r             : Resistance level.\n"
        "  dip           : Short-term support level.\n"
        "  low gex       : Broad low-GEX zone — price can move more freely here.\n"
        "  Combined labels (e.g. p1 + coi + ag2): Multiple signals at the same strike = very strong level."
    )

    lines = []
    intro = (
        f"NEW GEX LEVELS — week of {week_date} (Source: TradingLIT, 7DTE SPY→SPX factor: {factor:.2f})"
        if is_monday else
        f"GEX levels — week of {week_date} (Source: TradingLIT, factor: {factor:.2f})"
    )
    lines.append(intro)
    if is_monday:
        lines.append(LEGEND)

    field_labels = [
        ("gflip",    "Gamma Flip (g-flip)"),
        ("pos",      "Positive GEX / Call Walls (p/p1/p2/p3)"),
        ("neg",      "Negative GEX / Put Walls (n/n1/n2)"),
        ("agg",      "Aggregate GEX (ag)"),
        ("neg_zone", "Low GEX Zone Start"),
    ]
    for key, label in field_labels:
        raw = latest.get(key, "")
        if not raw:
            continue
        spx_vals = []
        for part in raw.split(","):
            part = part.strip()
            if ":" in part:
                lbl, price_str = part.rsplit(":", 1)
                try:
                    spx = round(float(price_str.strip()) * factor)
                    spx_vals.append(f"{lbl.strip()} (${spx:,})")
                except ValueError:
                    pass
        if spx_vals:
            lines.append(f"  • {label}: {', '.join(spx_vals)}")

    return {"text": "\n".join(lines), "is_current": True}


# ─── GEX SECTION (local JSON pipeline) ───────────────────────────────────────

def _gex_regime_analysis_fallback(spot: float | None, gflip: int | None, pos: list, neg: list) -> str:
    """Template fallback used when Perplexity AI analysis call fails."""
    if spot is None or gflip is None:
        return ""

    diff     = round(spot - gflip)
    dist_pct = abs(diff / gflip * 100) if gflip else 0
    flip_below_all_neg = neg and all(v > gflip for v in neg)

    if diff >= 0:
        if dist_pct >= 4.0:
            s1 = (
                f"Gamma cushion is thick ({diff:,} pts above flip) — dealers are net long gamma "
                f"across the entire visible range, buying dips and selling rips, compressing volatility."
            )
            if flip_below_all_neg:
                s1 += " Flip sits below all put walls — entire structure in positive gamma territory."
        elif dist_pct >= 1.5:
            s1 = (
                f"Positive gamma with moderate cushion ({diff:,} pts above flip) — "
                f"dealer flow dampens moves in both directions."
            )
        else:
            s1 = (
                f"Spot hovering just above flip (+{diff} pts) — transition zone. "
                f"Close below ${gflip:,} would shift dealer gamma negative."
            )
        s2 = (
            f"Key risk: break below flip (${gflip:,}) shifts dealers short-gamma, "
            f"amplifying moves — treat as volatility cliff."
        ) if dist_pct >= 1.5 else ""
    else:
        s1 = (
            f"Negative gamma regime ({abs(diff):,} pts below flip) — dealers amplify "
            f"directional moves; expect elevated volatility."
        )
        s2 = f"Recapturing flip at ${gflip:,} would restore stabilizing dealer flow."

    return "-> " + " ".join(s for s in [s1, s2] if s)


def _gex_ai_analysis(
    ticker: str,
    spot: float,
    gflip: int,
    pos: list,
    neg: list,
    agg: int | None,
    conf: set,
    today: date,
    api_key: str,
) -> str:
    """
    Calls Perplexity sonar to generate a focused 2-3 sentence GEX regime analysis
    specific to today's exact data. Falls back to template on any failure.
    """
    if not api_key or spot is None or gflip is None:
        return _gex_regime_analysis_fallback(spot, gflip, pos, neg)

    diff     = round(spot - gflip)
    dist_pct = diff / gflip * 100 if gflip else 0
    regime   = "POSITIVE" if diff >= 0 else "NEGATIVE"
    flip_below_all_neg = neg and all(v > gflip for v in neg)

    # Build structured data block — only numbers, no pre-baked interpretation
    data_lines = [
        f"Ticker: {ticker}",
        f"Date: {today.strftime('%A, %B %d, %Y')}",
        f"Spot: ${spot:,.0f}",
        f"Gamma Flip: ${gflip:,}  ({diff:+,} pts / {dist_pct:+.1f}% from spot)",
        f"Gamma regime: {regime} GAMMA",
    ]

    candidates_above = [(v, f"p{i+1}") for i, v in enumerate(pos) if v > spot]
    if agg is not None and agg > spot:
        candidates_above.append((agg, "agg"))
    if candidates_above:
        res_val, res_lbl = min(candidates_above, key=lambda x: x[0])
        ctag = " [confluence]" if res_val in conf else ""
        data_lines.append(f"Nearest resistance: {res_lbl} ${res_val:,} (+{round(res_val - spot)} pts){ctag}")

    candidates_below = [(v, f"n{i+1}") for i, v in enumerate(neg) if v < spot]
    if agg is not None and agg < spot:
        candidates_below.append((agg, "agg"))
    if candidates_below:
        sup_val, sup_lbl = max(candidates_below, key=lambda x: x[0])
        ctag = " [confluence]" if sup_val in conf else ""
        data_lines.append(f"Nearest support: {sup_lbl} ${sup_val:,} (-{round(spot - sup_val)} pts){ctag}")

    if flip_below_all_neg:
        data_lines.append(
            "Structural note: Gamma Flip is below ALL put walls — "
            "entire visible price range is in positive gamma territory."
        )

    data_block = "\n".join(data_lines)

    prompt = (
        f"Analyze the following GEX (Gamma Exposure) data and write a 2-3 sentence "
        f"interpretation for today's trading session.\n\n"
        f"{data_block}\n\n"
        f"Address: (1) what the current gamma regime means for dealer hedging behavior today, "
        f"(2) the single most important level to watch and why. "
        f"Be specific to the numbers above. No bullet points. No headers. "
        f"No citation markers. Professional, data-driven tone."
    )

    try:
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
            },
            json={
                "model": "sonar",
                "messages": [
                    {
                        "role":    "system",
                        "content": "You are a senior derivatives analyst at a professional proprietary trading desk. Be concise, specific, and data-driven. Never use bullet points or headers.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens":  220,
            },
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        text = re.sub(r'\[\d+\]', '', text)
        text = re.sub(r'\[[^\]]{1,60}\]', '', text)
        text = re.sub(r'  +', ' ', text).strip()
        if text:
            return "-> " + text
        return _gex_regime_analysis_fallback(spot, gflip, pos, neg)
    except Exception as e:
        print(f"  [WARNING] GEX AI analysis failed ({e}) — using template fallback")
        return _gex_regime_analysis_fallback(spot, gflip, pos, neg)


def _gex_ticker_block(
    entry: dict,
    ticker_name: str,
    spot: float | None,
    is_monday: bool,
    today: date | None = None,
    api_key: str = "",
) -> str:
    """Format the GEX block for one ticker (SPX or NDX)."""
    expiry = entry.get("expiry", "?")
    try:
        exp_fmt = datetime.strptime(expiry, "%Y-%m-%d").strftime("%b %d")
    except (ValueError, TypeError):
        exp_fmt = expiry

    gflip    = entry.get("gflip")
    pos      = entry.get("pos", [])    # [p1, p2, p3] ints
    neg      = entry.get("neg", [])    # [n1, n2, n3] ints
    coi      = entry.get("coi", [])
    poi      = entry.get("poi", [])
    agg      = entry.get("agg")
    conf     = set(entry.get("conf") or [])

    def star(v):
        return " ★" if v in conf else ""

    lines = [f"**{ticker_name}** (7DTE, expires {exp_fmt})"]

    if is_monday:
        if gflip is not None:
            lines.append(f"• Gamma Flip:  ${gflip:,}{star(gflip)}")
        if pos:
            pos_str = " | ".join(f"p{i+1} ${v:,}{star(v)}" for i, v in enumerate(pos))
            lines.append(f"• Pos GEX:     {pos_str}")
        if neg:
            neg_str = " | ".join(f"n{i+1} ${v:,}{star(v)}" for i, v in enumerate(neg))
            lines.append(f"• Neg GEX:     {neg_str}")
        if coi:
            lines.append(f"• Call OI:     " + " / ".join(f"${v:,}{star(v)}" for v in coi))
        if poi:
            lines.append(f"• Put OI:      " + " / ".join(f"${v:,}{star(v)}" for v in poi))
        if agg is not None:
            lines.append(f"• Agg GEX:     ${agg:,}{star(agg)}")
        if conf:
            lines.append(f"• Confluences: " + " | ".join(f"${v:,}" for v in sorted(conf)))
        if spot is not None and gflip is not None:
            analysis = _gex_ai_analysis(ticker_name, spot, gflip, pos, neg, agg, conf, today or date.today(), api_key)
            if analysis:
                lines.append(analysis)
    else:
        # Tue–Fri: spot vs levels
        if spot is not None and gflip is not None:
            diff = round(spot - gflip)
            if diff >= 0:
                cond = f"ABOVE Gamma Flip (${gflip:,}) by {diff} pts [POSITIVE GAMMA]"
            else:
                cond = f"BELOW Gamma Flip (${gflip:,}) by {abs(diff)} pts [NEGATIVE GAMMA]"
            lines.append(f"• Spot ${spot:,.0f} -> {cond}")

        if spot is not None:
            # Nearest resistance above spot
            candidates_above = [(v, f"p{i+1}") for i, v in enumerate(pos) if v > spot]
            if agg is not None and agg > spot:
                candidates_above.append((agg, "agg"))
            if candidates_above:
                res_val, res_lbl = min(candidates_above, key=lambda x: x[0])
                ctag = " [confluence]" if res_val in conf else ""
                lines.append(f"• Nearest resistance: {res_lbl} ${res_val:,} (+{round(res_val - spot)} pts){ctag}")

            # Nearest support below spot
            candidates_below = [(v, f"n{i+1}") for i, v in enumerate(neg) if v < spot]
            if agg is not None and agg < spot:
                candidates_below.append((agg, "agg"))
            if candidates_below:
                sup_val, sup_lbl = max(candidates_below, key=lambda x: x[0])
                ctag = " [confluence]" if sup_val in conf else ""
                lines.append(f"• Nearest support:    {sup_lbl} ${sup_val:,} (-{round(spot - sup_val)} pts){ctag}")

        if spot is not None and gflip is not None:
            analysis = _gex_ai_analysis(ticker_name, spot, gflip, pos, neg, agg, conf, today or date.today(), api_key)
            if analysis:
                lines.append(analysis)

    return "\n".join(lines)


def build_gex_section(today: date, market_data: dict, perplexity_key: str = "") -> str:
    """
    Build the §4§ GEX content from local JSON files.
    Monday: full level listing. Tue–Fri: spot vs levels distances.
    perplexity_key: if provided, generates AI analysis for each ticker block.
    Returns a plain text string to be injected into the briefing.
    """
    monday    = today - timedelta(days=today.weekday())
    is_monday = today.weekday() == 0

    spot_spx = market_data.get("SPX", {}).get("price")
    spot_ndx = market_data.get("NDX", {}).get("price")

    blocks = []
    for ticker_name, hist_file, spot in [
        ("SPX", HISTORY_SPX, spot_spx),
        ("NDX", HISTORY_NDX, spot_ndx),
    ]:
        if not hist_file.exists():
            blocks.append(f"**{ticker_name} GEX:** file not found — run gex_csv_parser.py and push to repo")
            continue
        try:
            history = json.loads(hist_file.read_text(encoding="utf-8"))
        except Exception as e:
            blocks.append(f"**{ticker_name} GEX:** could not parse data file ({e})")
            continue
        if not history:
            blocks.append(f"**{ticker_name} GEX:** history file is empty")
            continue

        latest    = history[-1]
        week_str  = latest.get("week", "")
        is_current = False
        try:
            week_dt    = datetime.strptime(week_str, "%Y-%m-%d").date()
            is_current = week_dt >= monday
        except (ValueError, TypeError):
            pass

        if not is_current:
            blocks.append(
                f"**{ticker_name} GEX:** data outdated (last update: {week_str}) — "
                "run gex_csv_parser.py and push to repo"
            )
            continue

        blocks.append(_gex_ticker_block(latest, ticker_name, spot, is_monday, today=today, api_key=perplexity_key))

    return "\n\n".join(blocks) if blocks else "GEX data unavailable."


# ─── PERPLEXITY — RESEARCH + BRIEFING ────────────────────────────────────────

def generate_briefing(
    market_data: dict,
    technicals: dict,
    today: date,
    api_key: str,
    gex_section: str = "",
    calendar_data: dict = None,
) -> str:
    """Calls Perplexity sonar-pro to research news and generate the morning briefing.
    §4§ (GEX levels) is built locally and injected — Perplexity handles §1§–§3§ and §5§ only.
    calendar_data: dict with 'economic' and 'earnings' strings (from Finnhub)."""

    today_str = today.strftime("%A, %B %d, %Y")

    # Build market summary string
    mkt_lines = []
    for name, d in market_data.items():
        mkt_lines.append(f"  {name}: {d['price']:,.2f} {d['arrow']} {d['change_pct']:+.2f}%")

    # Build technicals summary
    tech_lines = []
    if technicals:
        tech_lines.append(f"  SPX: {round(technicals['price'])}")
        for ma, data in technicals.get("mas", {}).items():
            tech_lines.append(
                f"  {ma}: {round(data['value'])}  ({data['dist_pct']:+.1f}% — SPX is {data['side']})"
            )

    # Build calendar block (from Finnhub — authoritative structured data)
    cal = calendar_data or {}
    econ_block     = cal.get("economic", "") or ""
    earnings_block = cal.get("earnings", "") or ""
    calendar_block = ""
    if econ_block or earnings_block:
        calendar_block = (
            f"\n--- ECONOMIC CALENDAR (authoritative, from Finnhub) ---\n"
            f"{econ_block or 'No high-impact US macro releases scheduled.'}\n"
            f"\n--- EARNINGS CALENDAR (authoritative, from Finnhub) ---\n"
            f"{earnings_block or 'No major S&P 500 earnings scheduled.'}"
        )

    prompt = f"""You are the senior quantitative analyst for a professional proprietary trading desk.
The desk trades SPX options with a minimum 7DTE horizon. No individual stocks — only macro index ETFs.
Today is {today_str}.

--- PRE-MARKET DATA (from yfinance) ---
{chr(10).join(mkt_lines) if mkt_lines else "  (data unavailable)"}

--- SPX MOVING AVERAGES (from yfinance) ---
{chr(10).join(tech_lines) if tech_lines else "  (data unavailable)"}
{calendar_block}

--- YOUR TASK ---
Write a Morning Briefing with exactly four sections.
CRITICAL: Begin each section with its delimiter token on its own line — NOTHING before it.
The four delimiter tokens are: §1§  §2§  §3§  §5§
Do NOT write any text before §1§. Do NOT number or title the sections yourself.
Do NOT write a §4§ section — it will be filled in separately.

§1§
2-3 sentences on pre-market tone. State VIX (level and % change direction), then ES, NQ and RTY (price and % change). Punchy, direct.

§2§
CRITICAL — SELECT ONLY GENUINE MARKET MOVERS: Use the ECONOMIC CALENDAR and EARNINGS CALENDAR above as your primary source. From these, pick ONLY the 2-3 events that are true market catalysts — e.g. Fed decisions/speeches, CPI/PPI/PCE, NFP/jobless claims, GDP prints, major index-weight earnings (AAPL, NVDA, MSFT, etc.). Ignore routine low-impact releases (mortgage rates, housing surveys, minor regional indices). Then search the web for 1-2 additional urgent macro developments not already covered (geopolitical risks, Fed commentary, policy shifts). Write each item on its own line starting with a dash (-). Include ET times when known. Maximum 5 items total — quality and relevance over completeness.

§3§
3-4 sentences using the moving averages in the data above. State where SPX is relative to W EMA20, D SMA50, and D SMA200. Which MA is nearest support, which is nearest resistance. What does the MA structure imply for near-term direction?

§5§
One direct sentence: the desk's tactical bias for today and the single most important reason.

--- OUTPUT RULES ---
- The ONLY special characters allowed are the four delimiters §1§ §2§ §3§ §5§ and dashes (-) for bullet lines.
- Do NOT write section titles or headers.
- Do NOT include any citation markers like [1], [2], [provided data], or anything in square brackets.
- Total content: 280-420 words (excluding delimiters).
- Professional, data-driven tone."""

    try:
        response = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
            },
            json={
                "model":       "sonar-pro",
                "messages": [
                    {
                        "role":    "system",
                        "content": "You are a senior quant analyst for a professional trading desk. You have access to real-time financial news and market data. Be factual, concise and data-driven.",
                    },
                    {
                        "role":    "user",
                        "content": prompt,
                    },
                ],
                "temperature": 0.2,
                "max_tokens":  1800,
            },
            timeout=90,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        # Strip Perplexity's auto-injected citation markers at the source
        content = re.sub(r'\[\d+\]', '', content)
        content = re.sub(r'\[[^\]]{1,60}\]', '', content)
        content = re.sub(r'  +', ' ', content).strip()

        # Inject local GEX data as §4§ before §5§
        if gex_section:
            if '§5§' in content:
                content = content.replace('§5§', f'\n§4§\n{gex_section}\n\n§5§', 1)
            else:
                # §5§ not found — append §4§ at the end
                content = content.rstrip() + f'\n§4§\n{gex_section}'

        print(f"  [DEBUG] Raw response (first 300 chars): {repr(content[:300])}")
        return content

    except requests.exceptions.Timeout:
        return "⚠️ Morning Briefing could not be generated (Perplexity API timeout)."
    except requests.exceptions.RequestException as e:
        return f"⚠️ Morning Briefing could not be generated: {e}"

# ─── POST-PROCESSING ─────────────────────────────────────────────────────────

_DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
_SECTIONS = {
    "1": ("📊", "PRE-MARKET PULSE"),
    "2": ("📰", "KEY NEWS & MACRO"),
    "3": ("📈", "SPX TECHNICAL PICTURE"),
    "4": ("⚡", "GAMMA LEVELS — 7DTE"),
    "5": ("🎯", "SESSION BIAS"),
}

def post_process(raw: str) -> str:
    """Parse §N§ delimiters, strip citations, build Discord-formatted output."""
    # Strip ALL bracket citation patterns aggressively
    text = re.sub(r'\[\d+\]', '', raw)
    text = re.sub(r'\[[^\]]{1,60}\]', '', text)
    text = re.sub(r'  +', ' ', text)

    # Split on §1§ ... §5§ delimiters
    parts = re.split(r'§(\d)§', text)
    # parts = [anything_before_first, "1", content1, "2", content2, ...]

    output = []
    i = 1
    while i + 1 < len(parts):
        num     = parts[i].strip()
        content = parts[i + 1].strip()
        # Convert dash bullets to •
        content = re.sub(r'(?m)^-\s+', '• ', content)
        # Strip stray bold headers Perplexity may add (e.g. "**Pre-Market Pulse**")
        # Only strip lines where ** wraps the ENTIRE line (nothing after closing **)
        content = re.sub(r'^\*\*[^*\n]+\*\*\s*$', '', content, flags=re.MULTILINE).strip()
        if num in _SECTIONS:
            emoji, title = _SECTIONS[num]
            output.append(f"{_DIVIDER}\n**{emoji}  {title}**\n\n{content}")
        i += 2

    if not output:
        # Delimiter parsing failed — return raw text with citations stripped at minimum
        return text.strip()

    return "\n\n".join(output)

# ─── DISCORD ─────────────────────────────────────────────────────────────────

def post_to_discord(webhook_url: str, briefing: str, today: date, market_data: dict):
    """Posts the briefing to Discord as an embed."""

    today_str = today.strftime("%A, %B %d, %Y")

    # Compact market line for footer
    parts = []
    for name in ("VIX", "ES", "NQ", "RTY"):
        d = market_data.get(name)
        if d:
            parts.append(f"{name} {d['price']:,.0f} {d['arrow']}{abs(d['change_pct']):.1f}%")
    footer_text = "  ·  ".join(parts) + "  |  Prop Desk Quant"

    # Discord embed description limit: 4096 chars
    # Split if needed
    max_len = 4000
    segments = []
    text = briefing
    while len(text) > max_len:
        cut = text[:max_len].rfind("\n\n")
        if cut == -1:
            cut = max_len
        segments.append(text[:cut])
        text = text[cut:].lstrip()
    segments.append(text)

    # First embed
    payload = {
        "embeds": [{
            "title":       f"📊  Morning Briefing  —  {today_str}",
            "description": segments[0],
            "color":       0x1A1A2E,
            "footer":      {"text": footer_text},
        }]
    }
    try:
        r = requests.post(webhook_url, json=payload, timeout=15)
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Discord post failed: {e}")
        sys.exit(1)

    # Overflow segments
    for seg in segments[1:]:
        try:
            requests.post(webhook_url, json={"content": seg}, timeout=15).raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"[WARNING] Could not post overflow segment: {e}")

    print(f"  Posted to Discord ({len(briefing)} chars, {len(segments)} message(s)).")

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    perplexity_key  = os.environ.get("PERPLEXITY_API_KEY", "").strip()
    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    finnhub_key     = os.environ.get("FINNHUB_API_KEY", "").strip()

    if not perplexity_key:
        print("[ERROR] PERPLEXITY_API_KEY not set in environment.")
        sys.exit(1)
    if not discord_webhook:
        print("[ERROR] DISCORD_WEBHOOK_URL not set in environment.")
        sys.exit(1)
    if not finnhub_key:
        print("  [WARNING] FINNHUB_API_KEY not set — calendar data unavailable, Perplexity will search instead.")

    today = datetime.now(ET).date()
    print(f"Morning Briefing — {today.strftime('%A %B %d, %Y')} (ET)")

    print("  Fetching market data (yfinance)...")
    market_data = fetch_market_data()

    print("  Computing SPX moving averages...")
    technicals = fetch_spx_technicals()

    print("  Fetching economic & earnings calendar (Finnhub)...")
    calendar_data = {
        "economic": fetch_economic_calendar(today, finnhub_key),
        "earnings": fetch_earnings_calendar(today, finnhub_key),
    }
    if calendar_data["economic"]:
        print(f"  [CALENDAR] Economic: {calendar_data['economic'][:120]}...")
    if calendar_data["earnings"]:
        print(f"  [CALENDAR] Earnings: {calendar_data['earnings'][:120]}...")

    print("  Building GEX section (local data + Perplexity AI analysis)...")
    gex_section = build_gex_section(today, market_data, perplexity_key)

    print("  Generating briefing (Perplexity sonar-pro)...")
    briefing = post_process(
        generate_briefing(market_data, technicals, today, perplexity_key, gex_section, calendar_data)
    )

    print("  Posting to Discord...")
    post_to_discord(discord_webhook, briefing, today, market_data)

    print("Done.")


if __name__ == "__main__":
    main()
