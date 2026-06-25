#!/usr/bin/env python3
"""
Re-autentica o Google Drive do dashboard (OAuth browser flow) e salva um token novo.

PROBLEMA QUE RESOLVE: o app OAuth em modo *Testing* revoga o refresh token a cada ~7 dias,
o snapshot do dashboard para de atualizar e o "hard refresh" no Render falha com
`invalid_grant: Token has been expired or revoked`. Este script mina um token novo.

USO (rodar LOCALMENTE, abre o navegador — precisa do desktop do Joao):
    python scripts/gdrive_reauth.py
Depois:
    python scripts/print_gdrive_env_vars.py   # copia o GDRIVE_TOKEN_JSON -> Render env -> redeploy

FIX PERMANENTE (para de quebrar toda semana): publicar o app OAuth de Testing -> Production
no Google Cloud Console (APIs & Services > OAuth consent screen > PUBLISH APP). Em Production
o refresh token nao expira em 7 dias.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CREDS_DIR = ROOT / ".credentials"
GDRIVE_CREDS = CREDS_DIR / "gdrive_credentials.json"
GDRIVE_TOKEN = CREDS_DIR / "gdrive_token.json"
GDRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def main() -> None:
    if not GDRIVE_CREDS.exists():
        print(f"[ERRO] OAuth client ausente: {GDRIVE_CREDS}")
        print("       Baixe o JSON do cliente OAuth (Desktop app) do GCP e salve nesse caminho.")
        raise SystemExit(1)

    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google.auth.exceptions import RefreshError
    from google_auth_oauthlib.flow import InstalledAppFlow

    # 1) tenta refresh do token atual (se so expirou o access token, evita re-login)
    if GDRIVE_TOKEN.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(GDRIVE_TOKEN), GDRIVE_SCOPES)
            if creds and creds.valid:
                print("[ok] token atual ainda valido — nada a fazer.")
                return
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                GDRIVE_TOKEN.write_text(creds.to_json(), encoding="utf-8")
                print("[ok] refresh do token funcionou (sem precisar de navegador).")
                return
        except RefreshError as e:
            print(f"[i] refresh falhou ({str(e)[:80]}...) -> re-login no navegador.")
        except Exception as e:
            print(f"[i] token atual ilegivel ({str(e)[:80]}...) -> re-login no navegador.")

    # 2) arquiva o token velho e roda o browser flow
    if GDRIVE_TOKEN.exists():
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        archived = CREDS_DIR / f"gdrive_token.expired_{stamp}.json"
        GDRIVE_TOKEN.rename(archived)
        print(f"[i] token velho arquivado em {archived.name}")

    print("[i] abrindo o navegador para login no Google (use a conta dona do arquivo no Drive)...")
    flow = InstalledAppFlow.from_client_secrets_file(str(GDRIVE_CREDS), GDRIVE_SCOPES)
    creds = flow.run_local_server(port=0)
    GDRIVE_TOKEN.write_text(creds.to_json(), encoding="utf-8")
    print(f"[ok] token novo salvo em {GDRIVE_TOKEN}")
    print("\nProximo passo:")
    print("  python scripts/print_gdrive_env_vars.py   # cole o GDRIVE_TOKEN_JSON no Render -> redeploy")
    print("\nFix permanente (para nao quebrar toda semana): publicar o OAuth app Testing -> Production no GCP.")


if __name__ == "__main__":
    main()
