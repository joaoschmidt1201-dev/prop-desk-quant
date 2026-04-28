#!/usr/bin/env python3
"""
Print compact Google Drive OAuth env vars for Render/Railway.

Run locally only. The output contains secrets and should be pasted into the
hosting provider's encrypted environment variable UI, never committed.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CREDENTIALS = ROOT / ".credentials" / "gdrive_credentials.json"
TOKEN = ROOT / ".credentials" / "gdrive_token.json"


def compact_json(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    return json.dumps(data, separators=(",", ":"))


def main() -> None:
    missing = [path for path in (CREDENTIALS, TOKEN) if not path.exists()]
    if missing:
        for path in missing:
            print(f"missing: {path}")
        raise SystemExit(1)

    print(f"GDRIVE_CREDENTIALS_JSON={compact_json(CREDENTIALS)}")
    print(f"GDRIVE_TOKEN_JSON={compact_json(TOKEN)}")


if __name__ == "__main__":
    main()
