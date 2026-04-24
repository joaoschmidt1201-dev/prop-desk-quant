#!/usr/bin/env python3
"""
dry_run_briefing.py
-------------------
Roda o morning_briefing completo mas imprime o resultado no terminal
em vez de postar no Discord. Útil para testar mudanças localmente.

Uso:
  python scripts/dry_run_briefing.py

Requer as mesmas env vars do script principal:
  PERPLEXITY_API_KEY
  FINNHUB_API_KEY
  (DISCORD_WEBHOOK_URL não é necessário no dry-run)
"""

import sys
import os
from pathlib import Path

# Adiciona a pasta scripts ao path para importar morning_briefing
sys.path.insert(0, str(Path(__file__).parent))
import morning_briefing as mb

# ─── PATCH: substitui post_to_discord por print ──────────────────────────────

def _dry_run_post(webhook_url: str, briefing: str, today, market_data: dict):
    divider = "─" * 60
    print(f"\n{divider}")
    print("  MORNING BRIEFING — DRY RUN (não postado no Discord)")
    print(f"{divider}\n")
    print(briefing)
    print(f"\n{divider}")
    print(f"  Total: {len(briefing)} chars")
    print(divider)

mb.post_to_discord = _dry_run_post

# ─── Também injeta DISCORD_WEBHOOK_URL fake para não travar a validação ──────
if not os.environ.get("DISCORD_WEBHOOK_URL"):
    os.environ["DISCORD_WEBHOOK_URL"] = "dry-run-no-post"

# ─── Roda ─────────────────────────────────────────────────────────────────────
mb.main()
