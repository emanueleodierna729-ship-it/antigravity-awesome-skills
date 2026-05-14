# Hand Gesture Control System ✋

Applicazione Python che trasforma la webcam in un controller gestuale completo:
controllo del mouse, scroll, drag, scorciatoie da tastiera e tastiera virtuale
— tutto senza toccare mouse o tastiera fisica.

---

## Avvio rapido

```bash
python install.py
```

Lo script installa le dipendenze e avvia la dashboard automaticamente.

```bash
python install.py --only        # solo installazione
python hand_gesture_control.py  # avvio diretto (dopo installazione)
```

---

## Requisiti

| Componente | Versione minima |
|---|---|
| Python | 3.8+ |
| Webcam | qualsiasi USB / integrata |
| OS | Windows 10+, macOS 12+, Linux (X11) |

### Note piattaforma

**Linux:** `sudo apt install python3-tk python3-xlib`  
**macOS:** concedere i permessi di *Accessibilità* al Terminale  
**Windows:** avviare come Amministratore se il mouse non risponde  

---

## Gesti supportati

| Gesto | Azione |
|---|---|
| ☝ Solo indice | Muovi cursore |
| 🤏 Pinch (pollice+indice) | Click sinistro |
| 🤏 Pinch + movimento | Drag (trascina) |
| ✌ Due dita (indice+medio) | Scroll su/giù |
| 🤌 3 dita su | Copia `Ctrl+C` |
| ✋ 4 dita su (senza pollice) | Incolla `Ctrl+V` |
| 👍 Solo pollice | Doppio click |
| 🤘 Rock (indice+mignolo) | Annulla `Ctrl+Z` |
| 🤙 Pollice+mignolo | Salva `Ctrl+S` |
| ✊ Pugno | Stop / pausa drag |
| 🖐 Palmo aperto | Reset stato |
| 🤏 Pinch pollice+medio | Click destro |

---

## Architettura

```
hand_gesture_control.py
├── HandTracker        — MediaPipe wrapper (rilevamento landmark)
├── GestureRecogniser  — classifica gesto dai 21 punti landmark
├── GestureProcessor   — mappa gesti → azioni mouse/tastiera
├── SmoothMouse        — controllo mouse con EMA smoothing
├── VirtualKeyboard    — tastiera Tkinter on-screen
├── CameraThread       — cattura webcam in thread separato
└── Dashboard          — GUI principale (Tkinter)
```

---

## Dipendenze Python

```
opencv-python >= 4.8
mediapipe     >= 0.10
pyautogui     >= 0.9.54
numpy         >= 1.24
Pillow        >= 10.0
pynput        >= 1.7.6
```
