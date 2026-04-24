"""
===============================================================================
 WHISPER TRANSCRIBER — Transcrição automática de áudios do CZ
 Prop Desk Quant | Senior Quant Developer
===============================================================================
 Monitora a pasta context/cz_intel/inbox/ por novos áudios,
 transcreve usando Whisper (OpenAI, open source, roda local),
 e salva o texto em context/cz_intel/ com data e timestamp.

 Instalação (uma vez só):
     pip install openai-whisper
     pip install soundfile    # suporte a formatos extras

 Formatos suportados: .m4a, .mp3, .ogg, .opus, .wav, .mp4

 Uso:
     python scripts/whisper_transcriber.py
===============================================================================
"""

import whisper
import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

ROOT        = Path(__file__).resolve().parent.parent
INBOX_DIR   = ROOT / "context" / "cz_intel" / "inbox"
OUTPUT_DIR  = ROOT / "context" / "cz_intel"

# Modelo Whisper: "tiny" (rápido) → "base" → "small" → "medium" → "large" (preciso)
# Para PT-BR: "small" já é muito bom. "medium" é excelente.
WHISPER_MODEL   = "small"
AUDIO_FORMATS   = {".m4a", ".mp3", ".ogg", ".opus", ".wav", ".mp4", ".webm"}

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def transcribe_inbox():
    audio_files = [f for f in INBOX_DIR.iterdir() if f.suffix.lower() in AUDIO_FORMATS]

    if not audio_files:
        print("Nenhum áudio encontrado em inbox/. Adicione arquivos e rode novamente.")
        return

    print(f"Carregando modelo Whisper ({WHISPER_MODEL})...")
    model = whisper.load_model(WHISPER_MODEL)

    for audio_path in sorted(audio_files):
        print(f"\nTranscrevendo: {audio_path.name}")

        result = model.transcribe(str(audio_path), language="pt", fp16=False)
        text   = result["text"].strip()

        # Nome do arquivo de saída: YYYY-MM-DD_HH-MM_<nome_original>.md
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        stem      = audio_path.stem.replace(" ", "_")
        out_path  = OUTPUT_DIR / f"{timestamp}_{stem}.txt"

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"Data: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"Arquivo original: {audio_path.name}\n")
            f.write("-" * 60 + "\n\n")
            f.write(text)

        print(f"Salvo em: {out_path.name}")

        # Move o áudio processado para subpasta /processed
        processed_dir = INBOX_DIR / "processed"
        processed_dir.mkdir(exist_ok=True)
        audio_path.rename(processed_dir / audio_path.name)
        print(f"Áudio movido para inbox/processed/")

    print(f"\nConcluído. {len(audio_files)} áudio(s) processado(s).")


if __name__ == "__main__":
    transcribe_inbox()
