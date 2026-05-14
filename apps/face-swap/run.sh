#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║     FaceSwap Studio  v1.0        ║"
echo "  ╚══════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "  [ERROR] Python 3 non trovato. Installa Python 3.10+"
  exit 1
fi

# Virtual env
if [ ! -d ".venv" ]; then
  echo "  Creazione ambiente virtuale..."
  python3 -m venv .venv
fi

source .venv/bin/activate

# Install deps
echo "  Installazione dipendenze..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Check model
if [ ! -f "models/inswapper_128.onnx" ]; then
  echo ""
  echo "  ⚠  ATTENZIONE: modello mancante!"
  echo "  Scarica inswapper_128.onnx e mettilo in: $SCRIPT_DIR/models/"
  echo "  Trovi il modello su HuggingFace cercando 'inswapper_128'"
  echo ""
fi

# Check ffmpeg
if ! command -v ffmpeg &>/dev/null; then
  echo "  ℹ  ffmpeg non trovato — i video saranno salvati in formato raw (mp4v)"
  echo "     Installa ffmpeg per compatibilità browser ottimale"
  echo ""
fi

echo "  Avvio server su http://localhost:8000"
echo "  Premi Ctrl+C per fermare"
echo ""

uvicorn app:app --host 0.0.0.0 --port 8000 --reload
