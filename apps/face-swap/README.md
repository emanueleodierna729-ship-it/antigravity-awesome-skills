# FaceSwap Studio

App locale per face swap su immagini e video, con interfaccia moderna e supporto GPU.

## Requisiti

- Python 3.10+
- NVIDIA GPU con CUDA (opzionale, funziona anche su CPU)
- ffmpeg (per encoding video compatibile con browser)
- Modello `inswapper_128.onnx`

## Installazione modello

Il modello **non** è incluso per ragioni di licenza.

1. Cerca `inswapper_128.onnx` su HuggingFace (profilo `deepinsight/insightface`)
2. Scaricalo e mettilo nella cartella `models/`

```
apps/face-swap/models/inswapper_128.onnx
```

## Avvio

**Linux / macOS:**
```bash
chmod +x run.sh
./run.sh
```

**Windows:**
```
run.bat
```

Poi apri il browser su: **http://localhost:8000**

## Uso

1. **Foto sorgente** — carica la foto del viso da applicare (frontale, alta risoluzione)
2. **Video / Immagine** — carica il video scaricato da ComfyUI o altro portale
3. Premi **SWAP** e aspetta l'elaborazione
4. Scarica il risultato

## Struttura

```
apps/face-swap/
├── app.py              # Backend FastAPI
├── requirements.txt
├── run.sh / run.bat    # Script di avvio
├── models/             # Metti qui inswapper_128.onnx
├── uploads/            # File caricati (pulizia automatica ogni ora)
├── outputs/            # File risultato
└── static/             # UI (HTML/CSS/JS)
```

## Note GPU

- Con NVIDIA GPU: `onnxruntime-gpu` usa CUDA automaticamente
- Senza GPU: usa `onnxruntime` (CPU, più lento ma funziona)
- Per sostituire: `pip install onnxruntime` invece di `onnxruntime-gpu`
