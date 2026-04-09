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
HISTORY_FILE = ROOT / "gex_history.json"

# ─── MARKET DATA ─────────────────────────────────────────────────────────────

def fetch_market_data() -> dict:
    """Fetches VIX, ES, NQ, RTY futures and SPX from Yahoo Finance."""
    symbols = {
        "VIX":  "^VIX",
        "ES":   "ES=F",
        "NQ":   "NQ=F",
        "RTY":  "RTY=F",
        "SPX":  "^GSPC",
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

# ─── PERPLEXITY — RESEARCH + BRIEFING ────────────────────────────────────────

def generate_briefing(
    market_data: dict,
    technicals: dict,
    gex_context: str,
    gex_is_current: bool,
    today: date,
    api_key: str,
) -> str:
    """Calls Perplexity sonar-pro to research news and generate the morning briefing."""

    today_str  = today.strftime("%A, %B %d, %Y")

    # Build market summary string
    mkt_lines = []
    for name, d in market_data.items():
        mkt_lines.append(f"  {name}: {d['price']:,.2f} {d['arrow']} {d['change_pct']:+.2f}%")

    # Build technicals summary
    tech_lines = []
    if technicals:
        tech_lines.append(f"  SPX: {technicals['price']:,.2f}")
        for ma, data in technicals.get("mas", {}).items():
            tech_lines.append(
                f"  {ma}: {data['value']:,.2f}  ({data['dist_pct']:+.1f}% — SPX is {data['side']})"
            )

    is_monday = today.weekday() == 0
    if not gex_is_current:
        gex_instruction = (
            "GEX data for this week has NOT yet been released by TradingLIT. "
            "Write exactly: '⚠️ GEX levels not yet available — TradingLIT has not released this week\\'s data. "
            "Levels will be included in tomorrow\\'s briefing once published.' Do not speculate on GEX levels."
        )
    elif is_monday:
        gex_instruction = (
            "Today is MONDAY with NEW GEX levels just released by TradingLIT. "
            "Using the LEVEL TYPE LEGEND provided, introduce each level present in the data and explain "
            "what it means for SPX price action this week: where is the g-flip (bullish/bearish inflection)? "
            "Which p/p1/p2/p3 levels are the key call walls (resistance)? "
            "Which n/n1/n2 levels are the key put walls (support)? "
            "Are there ag (aggregate) or combined labels (e.g. p1 + coi + ag2) indicating especially strong levels? "
            "Reference the actual SPX dollar prices."
        )
    else:
        gex_instruction = (
            "Comment on how SPX is currently positioned relative to this week's GEX levels. "
            "Is price above or below the Gamma Flip? Approaching any call wall (resistance) or put wall (support)? "
            "What does the current positioning suggest for today's session?"
        )

    prompt = f"""You are the senior quantitative analyst for a professional proprietary trading desk.
The desk trades SPX options with a minimum 7DTE horizon. No individual stocks — only macro index ETFs.
Today is {today_str}.

--- PRE-MARKET DATA ---
{chr(10).join(mkt_lines) if mkt_lines else "  (data unavailable)"}

--- SPX MOVING AVERAGES ---
{chr(10).join(tech_lines) if tech_lines else "  (data unavailable)"}

--- GEX LEVELS (Gamma Exposure, 7DTE — Source: TradingLitt) ---
{gex_context}

--- YOUR TASK ---
Write a concise Morning Briefing. Structure:

**1. PRE-MARKET PULSE**
Two or three sentences on the overall tone heading into the open. Reference futures and VIX.

**2. KEY NEWS & MACRO**
Search for and summarize the 3-4 most important news items or macro events relevant to SPX/ES/NQ today ({today_str}). Include any scheduled data releases (CPI, jobs, Fed speakers, FOMC, earnings from major index components). Be specific and cite what you find.

**3. SPX TECHNICAL PICTURE**
Comment on SPX relative to its key moving averages. Which MAs are acting as support/resistance today? Keep it to 3-4 sentences.

**4. GEX ANALYSIS — 7DTE**
{gex_instruction}

**5. SESSION BIAS**
One direct sentence: what is the desk's tactical bias for today's session and why.

--- CONSTRAINTS ---
- Total length: 400-550 words
- Professional, direct tone — no fluff
- No excessive emojis
- Use markdown bold for section headers"""

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
        return response.json()["choices"][0]["message"]["content"]

    except requests.exceptions.Timeout:
        return "⚠️ Morning Briefing could not be generated (Perplexity API timeout)."
    except requests.exceptions.RequestException as e:
        return f"⚠️ Morning Briefing could not be generated: {e}"

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

    if not perplexity_key:
        print("[ERROR] PERPLEXITY_API_KEY not set in environment.")
        sys.exit(1)
    if not discord_webhook:
        print("[ERROR] DISCORD_WEBHOOK_URL not set in environment.")
        sys.exit(1)

    today = datetime.now(ET).date()
    print(f"Morning Briefing — {today.strftime('%A %B %d, %Y')} (ET)")

    print("  Fetching market data (yfinance)...")
    market_data = fetch_market_data()

    print("  Computing SPX moving averages...")
    technicals = fetch_spx_technicals()

    print("  Reading GEX levels...")
    gex_result = get_gex_context(today)

    print("  Generating briefing (Perplexity sonar-pro)...")
    briefing = generate_briefing(
        market_data, technicals,
        gex_result["text"], gex_result["is_current"],
        today, perplexity_key,
    )

    print("  Posting to Discord...")
    post_to_discord(discord_webhook, briefing, today, market_data)

    print("Done.")


if __name__ == "__main__":
    main()
