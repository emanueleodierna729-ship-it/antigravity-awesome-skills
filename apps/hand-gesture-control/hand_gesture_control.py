#!/usr/bin/env python3
"""
Hand Gesture Control System
Dashboard + webcam hand tracking + mouse emulation + virtual keyboard
Requires: opencv-python mediapipe pyautogui numpy Pillow pynput
"""

import cv2
import mediapipe as mp
import numpy as np
import pyautogui
import tkinter as tk
from tkinter import ttk
import threading
import time
import math
import sys
from collections import deque
from PIL import Image, ImageTk

try:
    from pynput.mouse import Button, Controller as _MouseCtrl
    from pynput.keyboard import Controller as _KeyboardCtrl
    PYNPUT_OK = True
except ImportError:
    PYNPUT_OK = False


# ─────────────────────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────────────────────
class Cfg:
    CAMERA_IDX      = 0
    CAM_W           = 640
    CAM_H           = 480
    MAX_HANDS       = 1
    DETECT_CONF     = 0.72
    TRACK_CONF      = 0.55

    SMOOTH          = 0.28      # EMA alpha  (lower → smoother, more lag)
    PINCH_THRESH    = 0.042     # normalised distance → click
    DRAG_THRESH     = 0.032     # movement before drag starts
    SCROLL_SENS     = 18        # multiplier for scroll delta
    CLICK_CD        = 0.30      # seconds between clicks
    SHORTCUT_CD     = 0.70      # seconds between shortcut fires
    DWELL_MS        = 30        # update interval (ms) for UI loop

    SCR_W, SCR_H    = pyautogui.size()

    # Webcam-to-screen mapping margins (avoid edges)
    MARGIN_X        = 0.12
    MARGIN_Y        = 0.12

    # ── Tkinter palette ──
    BG_DARK  = "#0d1117"
    BG_MID   = "#161b22"
    BG_CARD  = "#21262d"
    ACCENT   = "#e94560"
    SUCCESS  = "#3fb950"
    WARNING  = "#d29922"
    TEXT     = "#e6edf3"
    TEXT_DIM = "#8b949e"
    BLUE     = "#58a6ff"


# ─────────────────────────────────────────────────────────────
#  HAND TRACKER  (MediaPipe wrapper)
# ─────────────────────────────────────────────────────────────
class HandTracker:
    # landmark indices
    WRIST      = 0
    THUMB_TIP  = 4
    INDEX_MCP  = 5;  INDEX_PIP  = 6;  INDEX_TIP  = 8
    MIDDLE_MCP = 9;  MIDDLE_PIP = 10; MIDDLE_TIP = 12
    RING_MCP   = 13; RING_PIP   = 14; RING_TIP   = 16
    PINKY_MCP  = 17; PINKY_PIP  = 18; PINKY_TIP  = 20

    def __init__(self):
        mh = mp.solutions.hands
        self._hands = mh.Hands(
            static_image_mode=False,
            max_num_hands=Cfg.MAX_HANDS,
            min_detection_confidence=Cfg.DETECT_CONF,
            min_tracking_confidence=Cfg.TRACK_CONF,
        )
        self._draw  = mp.solutions.drawing_utils
        self._style = mp.solutions.drawing_styles
        self._conn  = mh.HAND_CONNECTIONS

    def process(self, frame_bgr):
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        res = self._hands.process(rgb)
        rgb.flags.writeable = True
        return res

    def annotate(self, frame, results):
        if results.multi_hand_landmarks:
            for lm in results.multi_hand_landmarks:
                self._draw.draw_landmarks(
                    frame, lm, self._conn,
                    self._style.get_default_hand_landmarks_style(),
                    self._style.get_default_hand_connections_style(),
                )
        return frame

    def extract(self, results):
        """Return (norm_lm, handedness_str) or (None, None)."""
        if not results.multi_hand_landmarks:
            return None, None
        lm = results.multi_hand_landmarks[0].landmark
        norm = [(p.x, p.y, p.z) for p in lm]
        hand = "Right"
        if results.multi_handedness:
            hand = results.multi_handedness[0].classification[0].label
        return norm, hand

    def close(self):
        self._hands.close()


# ─────────────────────────────────────────────────────────────
#  GESTURE RECOGNISER
# ─────────────────────────────────────────────────────────────
class Gesture:
    NONE         = "NONE"
    CURSOR       = "CURSOR"          # ☝ index only
    PINCH        = "PINCH"           # 🤏 thumb+index close
    PINCH_RIGHT  = "PINCH_RIGHT"     # 🤏 thumb+middle close
    SCROLL       = "SCROLL"          # ✌ index+middle
    COPY         = "COPY"            # 3 fingers up  → Ctrl+C
    PASTE        = "PASTE"           # 4 fingers up  → Ctrl+V
    THUMB_UP     = "THUMB_UP"        # 👍 thumb only  → double-click
    ROCK         = "ROCK"            # 🤘 index+pinky → Ctrl+Z
    FIST         = "FIST"            # ✊ all down    → drag / pause
    OPEN_PALM    = "OPEN_PALM"       # 🖐 all up      → reset
    SAVE         = "SAVE"            # 🤙 thumb+pinky → Ctrl+S
    UNKNOWN      = "UNKNOWN"


class GestureRecogniser:
    T = HandTracker  # alias for indices

    def fingers_up(self, lm):
        """[thumb, index, middle, ring, pinky]  True = extended."""
        # Thumb: horizontal comparison (camera is already flipped)
        thumb = lm[self.T.THUMB_TIP][0] < lm[self.T.THUMB_TIP - 1][0]
        others = [
            lm[tip][1] < lm[pip][1]
            for tip, pip in (
                (self.T.INDEX_TIP,  self.T.INDEX_PIP),
                (self.T.MIDDLE_TIP, self.T.MIDDLE_PIP),
                (self.T.RING_TIP,   self.T.RING_PIP),
                (self.T.PINKY_TIP,  self.T.PINKY_PIP),
            )
        ]
        return [thumb] + others

    def pinch(self, lm, a=HandTracker.THUMB_TIP, b=HandTracker.INDEX_TIP):
        return math.hypot(lm[a][0] - lm[b][0], lm[a][1] - lm[b][1])

    def classify(self, lm):
        if lm is None:
            return Gesture.NONE

        f = self.fingers_up(lm)
        thumb, idx, mid, ring, pinky = f
        count = sum(f)

        d_ti = self.pinch(lm, self.T.THUMB_TIP, self.T.INDEX_TIP)
        d_tm = self.pinch(lm, self.T.THUMB_TIP, self.T.MIDDLE_TIP)
        d_tp = self.pinch(lm, self.T.THUMB_TIP, self.T.PINKY_TIP)

        if d_ti < Cfg.PINCH_THRESH:
            return Gesture.PINCH
        if d_tm < Cfg.PINCH_THRESH * 1.2:
            return Gesture.PINCH_RIGHT
        if d_tp < Cfg.PINCH_THRESH * 1.3 and not idx and not mid and not ring:
            return Gesture.SAVE

        if idx and not mid and not ring and not pinky:
            return Gesture.CURSOR
        if idx and mid and not ring and not pinky:
            return Gesture.SCROLL
        if idx and mid and ring and not pinky and not thumb:
            return Gesture.COPY
        if idx and mid and ring and pinky and not thumb:
            return Gesture.PASTE
        if thumb and not idx and not mid and not ring and not pinky:
            return Gesture.THUMB_UP
        if idx and pinky and not mid and not ring:
            return Gesture.ROCK
        if count == 0:
            return Gesture.FIST
        if count == 5:
            return Gesture.OPEN_PALM

        return Gesture.UNKNOWN


# ─────────────────────────────────────────────────────────────
#  SMOOTH MOUSE CONTROLLER
# ─────────────────────────────────────────────────────────────
class SmoothMouse:
    def __init__(self):
        pyautogui.FAILSAFE = False
        pyautogui.PAUSE = 0.0

        self._mc = _MouseCtrl() if PYNPUT_OK else None
        self._kc = _KeyboardCtrl() if PYNPUT_OK else None

        self.cx = Cfg.SCR_W // 2
        self.cy = Cfg.SCR_H // 2
        self.dragging = False
        self._t_click = 0.0
        self._t_short = 0.0
        self._lock = threading.Lock()

    # ── mapping ──
    def _norm2scr(self, nx, ny):
        mx, my = Cfg.MARGIN_X, Cfg.MARGIN_Y
        sx = (nx - mx) / max(1e-6, 1.0 - 2 * mx)
        sy = (ny - my) / max(1e-6, 1.0 - 2 * my)
        sx = max(0.0, min(1.0, 1.0 - sx))   # mirror-x
        sy = max(0.0, min(1.0, sy))
        return int(sx * Cfg.SCR_W), int(sy * Cfg.SCR_H)

    # ── movement ──
    def move(self, nx, ny):
        tx, ty = self._norm2scr(nx, ny)
        a = Cfg.SMOOTH
        with self._lock:
            self.cx = int(self.cx + a * (tx - self.cx))
            self.cy = int(self.cy + a * (ty - self.cy))
            pyautogui.moveTo(self.cx, self.cy)

    # ── clicks ──
    def _cd_ok(self, attr):
        now = time.time()
        if now - getattr(self, attr) < Cfg.CLICK_CD:
            return False
        setattr(self, attr, now)
        return True

    def left_click(self):
        if not self._cd_ok("_t_click"):
            return
        if PYNPUT_OK:
            from pynput.mouse import Button
            self._mc.click(Button.left)
        else:
            pyautogui.click()

    def right_click(self):
        if not self._cd_ok("_t_click"):
            return
        if PYNPUT_OK:
            from pynput.mouse import Button
            self._mc.click(Button.right)
        else:
            pyautogui.rightClick()

    def double_click(self):
        if not self._cd_ok("_t_click"):
            return
        if PYNPUT_OK:
            from pynput.mouse import Button
            self._mc.click(Button.left, count=2)
        else:
            pyautogui.doubleClick()

    # ── scroll ──
    def scroll(self, dy):
        if PYNPUT_OK:
            self._mc.scroll(0, dy)
        else:
            pyautogui.scroll(int(dy * 3))

    # ── drag ──
    def start_drag(self):
        if self.dragging:
            return
        self.dragging = True
        if PYNPUT_OK:
            from pynput.mouse import Button
            self._mc.press(Button.left)
        else:
            pyautogui.mouseDown()

    def stop_drag(self):
        if not self.dragging:
            return
        self.dragging = False
        if PYNPUT_OK:
            from pynput.mouse import Button
            self._mc.release(Button.left)
        else:
            pyautogui.mouseUp()

    # ── keyboard shortcuts ──
    def hotkey(self, *keys):
        now = time.time()
        if now - self._t_short < Cfg.SHORTCUT_CD:
            return False
        self._t_short = now
        try:
            pyautogui.hotkey(*keys)
        except Exception:
            pass
        return True

    def press_key(self, key):
        try:
            pyautogui.press(key)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
#  GESTURE → ACTION PROCESSOR
# ─────────────────────────────────────────────────────────────
class GestureProcessor:
    def __init__(self, mouse: SmoothMouse):
        self.mouse = mouse
        self.rec = GestureRecogniser()

        self._pinching      = False
        self._pinch_right   = False
        self._drag_started  = False
        self._drag_origin   = (0.0, 0.0)
        self._scroll_ref    = None
        self._t_shortcut    = 0.0

    def process(self, lm) -> tuple:
        """Return (gesture_name, action_label_or_empty)."""
        gesture = self.rec.classify(lm)
        action  = ""

        ix = lm[HandTracker.INDEX_TIP][0] if lm else 0.5
        iy = lm[HandTracker.INDEX_TIP][1] if lm else 0.5

        m = self.mouse

        if gesture == Gesture.CURSOR:
            self._reset_drag()
            m.move(ix, iy)
            self._pinching    = False
            self._pinch_right = False
            self._scroll_ref  = None

        elif gesture == Gesture.PINCH:
            if not self._pinching:
                self._pinching    = True
                self._drag_origin = (ix, iy)
                self._drag_started = False
            else:
                dx = abs(ix - self._drag_origin[0])
                dy = abs(iy - self._drag_origin[1])
                if dx > Cfg.DRAG_THRESH or dy > Cfg.DRAG_THRESH:
                    if not self._drag_started:
                        self._drag_started = True
                        m.start_drag()
                if self._drag_started:
                    m.move(ix, iy)
            self._pinch_right = False
            self._scroll_ref  = None

        elif gesture == Gesture.PINCH_RIGHT:
            if not self._pinch_right:
                self._pinch_right = True
                m.right_click()
                action = "RIGHT CLICK"
            self._reset_pinch()
            self._scroll_ref = None

        elif gesture == Gesture.SCROLL:
            self._reset_drag()
            if self._scroll_ref is None:
                self._scroll_ref = iy
            else:
                delta = (self._scroll_ref - iy) * Cfg.SCROLL_SENS
                if abs(delta) > 0.05:
                    m.scroll(delta)
                    self._scroll_ref = iy
            self._reset_pinch()

        elif gesture == Gesture.THUMB_UP:
            self._reset_drag()
            if m.double_click.__func__(m) is not False:
                action = "DOUBLE CLICK"
            self._reset_pinch()
            self._scroll_ref = None

        elif gesture == Gesture.COPY:
            self._reset_drag()
            if m.hotkey("ctrl", "c"):
                action = "COPY  Ctrl+C"
            self._reset_pinch()

        elif gesture == Gesture.PASTE:
            self._reset_drag()
            if m.hotkey("ctrl", "v"):
                action = "PASTE  Ctrl+V"
            self._reset_pinch()

        elif gesture == Gesture.ROCK:
            self._reset_drag()
            if m.hotkey("ctrl", "z"):
                action = "UNDO  Ctrl+Z"
            self._reset_pinch()

        elif gesture == Gesture.SAVE:
            self._reset_drag()
            if m.hotkey("ctrl", "s"):
                action = "SAVE  Ctrl+S"
            self._reset_pinch()

        elif gesture == Gesture.FIST:
            self._reset_drag()
            self._reset_pinch()
            self._scroll_ref = None

        elif gesture == Gesture.OPEN_PALM:
            self._reset_drag()
            self._reset_pinch()
            self._scroll_ref = None

        else:
            # Gesture ended / unknown → finalise pending click
            if self._pinching and not self._drag_started:
                m.left_click()
                action = "LEFT CLICK"
            self._reset_drag()
            self._reset_pinch()
            self._scroll_ref = None

        return gesture, action

    def _reset_pinch(self):
        self._pinching     = False
        self._pinch_right  = False

    def _reset_drag(self):
        if self._drag_started:
            self.mouse.stop_drag()
            self._drag_started = False
        self._pinching = False


# ─────────────────────────────────────────────────────────────
#  VIRTUAL KEYBOARD
# ─────────────────────────────────────────────────────────────
class VirtualKeyboard(tk.Toplevel):
    _ROWS = [
        ["Esc","F1","F2","F3","F4","F5","F6","F7","F8","F9","F10","F11","F12"],
        ["`","1","2","3","4","5","6","7","8","9","0","-","=","Back"],
        ["Tab","q","w","e","r","t","y","u","i","o","p","[","]","\\"],
        ["Caps","a","s","d","f","g","h","j","k","l",";","'","Enter"],
        ["Shift","z","x","c","v","b","n","m",",",".","/","Shift↑"],
        ["Ctrl","Win","Alt","          Space          ","Alt↗","Ctrl↗"],
    ]
    _MAP = {
        "Esc":"escape","Back":"backspace","Tab":"tab","Caps":"capslock",
        "Enter":"return","Shift":"shift","Shift↑":"shift","Ctrl":"ctrl",
        "Ctrl↗":"ctrl","Alt":"alt","Alt↗":"alt","Win":"super",
        "          Space          ":"space",
        **{f"F{n}":f"f{n}" for n in range(1, 13)},
    }
    _WIDE = {"Back","Tab","Caps","Enter","Shift","Shift↑","Ctrl","Ctrl↗",
             "Alt","Alt↗","Win","          Space          "}

    def __init__(self, parent, mouse: SmoothMouse):
        super().__init__(parent)
        self._mouse   = mouse
        self._shift   = False
        self._ctrl    = False
        self._buttons = {}

        self.title("Virtual Keyboard")
        self.configure(bg=Cfg.BG_DARK)
        self.attributes("-topmost", True)
        self.resizable(False, False)

        sw = parent.winfo_screenwidth()
        sh = parent.winfo_screenheight()
        self.geometry(f"+0+{sh - 240}")

        self._build()
        self.protocol("WM_DELETE_WINDOW", self.withdraw)

    def _build(self):
        for row in self._ROWS:
            fr = tk.Frame(self, bg=Cfg.BG_DARK)
            fr.pack(padx=4, pady=2)
            for key in row:
                w = 7 if key in self._WIDE else 4
                if key == "          Space          ":
                    w = 28
                btn = tk.Button(
                    fr, text=key, width=w,
                    bg=Cfg.BG_CARD, fg=Cfg.TEXT,
                    font=("Consolas", 8, "bold"),
                    relief="flat", bd=0, cursor="hand2",
                    activebackground=Cfg.ACCENT, activeforeground=Cfg.TEXT,
                    command=lambda k=key: self._press(k),
                )
                btn.pack(side="left", padx=1, pady=1, ipady=4)
                self._buttons[key] = btn

    def _press(self, key):
        mapped = self._MAP.get(key, key)
        if mapped in ("shift", "ctrl"):
            if mapped == "shift":
                self._shift = not self._shift
                col = Cfg.ACCENT if self._shift else Cfg.BG_CARD
                for k in ("Shift", "Shift↑"):
                    if k in self._buttons:
                        self._buttons[k].configure(bg=col)
            else:
                self._ctrl = not self._ctrl
                col = Cfg.ACCENT if self._ctrl else Cfg.BG_CARD
                for k in ("Ctrl", "Ctrl↗"):
                    if k in self._buttons:
                        self._buttons[k].configure(bg=col)
            return

        chain = []
        if self._ctrl:
            chain.append("ctrl")
            self._ctrl = False
            for k in ("Ctrl", "Ctrl↗"):
                if k in self._buttons:
                    self._buttons[k].configure(bg=Cfg.BG_CARD)
        if self._shift:
            chain.append("shift")
            self._shift = False
            for k in ("Shift", "Shift↑"):
                if k in self._buttons:
                    self._buttons[k].configure(bg=Cfg.BG_CARD)
        chain.append(mapped)

        try:
            if len(chain) > 1:
                self._mouse.hotkey(*chain)
            else:
                self._mouse.press_key(mapped)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
#  CAMERA PROCESSING THREAD
# ─────────────────────────────────────────────────────────────
class CameraThread(threading.Thread):
    def __init__(self, app):
        super().__init__(daemon=True)
        self.app       = app
        self._running  = False
        self._flock    = threading.Lock()
        self.frame     = None
        self.gesture   = Gesture.NONE
        self.action    = ""
        self.fps       = 0.0

    def start_capture(self):
        self._running = True
        self.start()

    def stop_capture(self):
        self._running = False

    def run(self):
        cap = cv2.VideoCapture(Cfg.CAMERA_IDX)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  Cfg.CAM_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, Cfg.CAM_H)

        tracker   = HandTracker()
        processor = GestureProcessor(self.app.mouse)

        t0, fc = time.time(), 0

        while self._running:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.01)
                continue

            frame = cv2.flip(frame, 1)

            if self.app.hand_active:
                results       = tracker.process(frame)
                frame         = tracker.annotate(frame, results)
                lm, handedness = tracker.extract(results)
                gesture, action = processor.process(lm)
                self.gesture = gesture
                self.action  = action
                self._draw_hud(frame, gesture, action, lm)
            else:
                self.gesture = Gesture.NONE
                self.action  = ""

            # FPS counter
            fc += 1
            elapsed = time.time() - t0
            if elapsed >= 1.0:
                self.fps = fc / elapsed
                fc, t0 = 0, time.time()

            cv2.putText(frame, f"FPS {self.fps:.0f}", (8, 26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (80, 220, 80), 2)

            with self._flock:
                self.frame = frame.copy()

        tracker.close()
        cap.release()

    def get_frame(self):
        with self._flock:
            return None if self.frame is None else self.frame.copy()

    @staticmethod
    def _draw_hud(frame, gesture, action, lm):
        h, w = frame.shape[:2]
        label_color = (80, 220, 80) if gesture not in (Gesture.NONE, Gesture.UNKNOWN) else (120, 120, 120)
        cv2.putText(frame, gesture, (8, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, label_color, 2)

        if action:
            tw, _ = cv2.getTextSize(action, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)[:2]
            cx = (w - tw[0]) // 2 if isinstance(tw, tuple) else w // 4
            cv2.putText(frame, action, (cx, h - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 220, 220), 2)

        if gesture == Gesture.CURSOR and lm:
            ix = int((1 - lm[HandTracker.INDEX_TIP][0]) * w)
            iy = int(lm[HandTracker.INDEX_TIP][1] * h)
            cv2.circle(frame, (ix, iy), 14, (0, 255, 255), 2)
            cv2.circle(frame, (ix, iy), 4,  (0, 255, 255), -1)

        if gesture == Gesture.PINCH:
            cv2.putText(frame, "DRAG/CLICK", (w - 150, 55),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 80, 255), 2)


# ─────────────────────────────────────────────────────────────
#  DASHBOARD  (Tkinter)
# ─────────────────────────────────────────────────────────────
class Dashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.mouse       = SmoothMouse()
        self.hand_active = False
        self._vk         = None
        self._cam        = None

        self._setup_window()
        self._build_ui()
        self._start_camera()
        self._loop()

    # ── window setup ──────────────────────────────────────────
    def _setup_window(self):
        self.title("Hand Gesture Control  ✋")
        self.configure(bg=Cfg.BG_DARK)
        self.geometry("1060x660")
        self.minsize(900, 580)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI construction ───────────────────────────────────────
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=Cfg.BG_DARK)
        hdr.pack(fill="x", padx=12, pady=(10, 4))

        tk.Label(hdr, text="✋  Hand Gesture Control",
                 font=("Segoe UI", 19, "bold"),
                 bg=Cfg.BG_DARK, fg=Cfg.TEXT).pack(side="left")

        self._status_lbl = tk.Label(hdr, text="●  OFFLINE",
                 font=("Segoe UI", 11), bg=Cfg.BG_DARK, fg="#ff4444")
        self._status_lbl.pack(side="right", padx=16)

        sep = tk.Frame(self, bg=Cfg.BG_CARD, height=1)
        sep.pack(fill="x", padx=12)

        # Body
        body = tk.Frame(self, bg=Cfg.BG_DARK)
        body.pack(fill="both", expand=True, padx=12, pady=8)

        # Left – camera
        left = tk.Frame(body, bg=Cfg.BG_MID)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))

        tk.Label(left, text="CAMERA FEED",
                 font=("Segoe UI", 8, "bold"),
                 bg=Cfg.BG_MID, fg=Cfg.TEXT_DIM).pack(pady=(8, 2))

        self._cam_lbl = tk.Label(left, bg="#000000")
        self._cam_lbl.pack(padx=8, pady=(0, 8))

        # Right – controls
        right = tk.Frame(body, bg=Cfg.BG_DARK, width=310)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        self._build_controls(right)

    def _card(self, parent, title):
        f = tk.Frame(parent, bg=Cfg.BG_CARD)
        f.pack(fill="x", padx=4, pady=4)
        tk.Label(f, text=title, font=("Segoe UI", 9, "bold"),
                 bg=Cfg.BG_CARD, fg=Cfg.TEXT_DIM).pack(pady=(10, 4))
        return f

    def _build_controls(self, parent):
        # ─ Hand Control toggle ─
        c1 = self._card(parent, "HAND CONTROL")
        tk.Label(c1, text="Attiva il riconoscimento mani/dita\nper controllare il cursore",
                 font=("Segoe UI", 8), bg=Cfg.BG_CARD, fg=Cfg.TEXT_DIM,
                 justify="center").pack()
        self._hand_btn = tk.Button(
            c1, text="▶  ATTIVA",
            font=("Segoe UI", 11, "bold"),
            bg=Cfg.SUCCESS, fg="#000000",
            relief="flat", bd=0, cursor="hand2",
            padx=16, pady=8,
            command=self._toggle_hand)
        self._hand_btn.pack(pady=10, ipadx=8)

        # ─ Virtual Keyboard toggle ─
        c2 = self._card(parent, "TASTIERA VIRTUALE")
        tk.Label(c2, text="Mostra/nascondi la tastiera\non-screen per scrivere",
                 font=("Segoe UI", 8), bg=Cfg.BG_CARD, fg=Cfg.TEXT_DIM,
                 justify="center").pack()
        self._vk_btn = tk.Button(
            c2, text="⌨  MOSTRA TASTIERA",
            font=("Segoe UI", 10, "bold"),
            bg=Cfg.BLUE, fg="#000000",
            relief="flat", bd=0, cursor="hand2",
            padx=16, pady=8,
            command=self._toggle_vk)
        self._vk_btn.pack(pady=10, ipadx=8)

        # ─ Current gesture ─
        c3 = self._card(parent, "GESTO RILEVATO")
        self._gest_lbl = tk.Label(c3, text="—",
                 font=("Segoe UI", 16, "bold"),
                 bg=Cfg.BG_CARD, fg=Cfg.ACCENT)
        self._gest_lbl.pack(pady=(2, 4))
        self._action_lbl = tk.Label(c3, text="",
                 font=("Segoe UI", 9),
                 bg=Cfg.BG_CARD, fg=Cfg.WARNING)
        self._action_lbl.pack(pady=(0, 8))

        # ─ Smoothing slider ─
        c4 = self._card(parent, "SENSIBILITÀ CURSORE")
        tk.Label(c4, text="Smorzamento movimento mouse",
                 font=("Segoe UI", 8), bg=Cfg.BG_CARD, fg=Cfg.TEXT).pack()
        self._smooth_var = tk.DoubleVar(value=Cfg.SMOOTH)
        ttk.Scale(c4, from_=0.05, to=1.0, orient="horizontal",
                  variable=self._smooth_var,
                  command=lambda v: setattr(Cfg, "SMOOTH", float(v))
                  ).pack(fill="x", padx=16, pady=(4, 10))

        # ─ Gesture guide ─
        c5 = tk.Frame(parent, bg=Cfg.BG_MID)
        c5.pack(fill="both", expand=True, padx=4, pady=4)
        tk.Label(c5, text="GUIDA GESTI",
                 font=("Segoe UI", 9, "bold"),
                 bg=Cfg.BG_MID, fg=Cfg.TEXT_DIM).pack(pady=(8, 4))

        GUIDE = [
            ("☝  Indice solo",      "Muovi cursore"),
            ("🤏  Pinch",           "Click sinistro"),
            ("🤏  Pinch + muovi",   "Drag"),
            ("✌  Due dita",         "Scorri (scroll)"),
            ("🤌  3 dita su",       "Copia  Ctrl+C"),
            ("✋  4 dita su",       "Incolla  Ctrl+V"),
            ("👍  Solo pollice",    "Doppio click"),
            ("🤘  Rock (i+mig)",    "Annulla  Ctrl+Z"),
            ("🤙  Pollice+mignolo", "Salva  Ctrl+S"),
            ("✊  Pugno",           "Pausa / stop drag"),
            ("🖐  Palmo aperto",    "Reset stato"),
        ]
        for g, a in GUIDE:
            row = tk.Frame(c5, bg=Cfg.BG_MID)
            row.pack(fill="x", padx=8, pady=1)
            tk.Label(row, text=g,  font=("Segoe UI", 8),
                     bg=Cfg.BG_MID, fg=Cfg.TEXT, width=20, anchor="w").pack(side="left")
            tk.Label(row, text=a,  font=("Segoe UI", 8),
                     bg=Cfg.BG_MID, fg=Cfg.TEXT_DIM, anchor="w").pack(side="left")

    # ── toggle handlers ───────────────────────────────────────
    def _toggle_hand(self):
        self.hand_active = not self.hand_active
        if self.hand_active:
            self._hand_btn.configure(text="⏹  DISATTIVA", bg=Cfg.ACCENT, fg=Cfg.TEXT)
            self._status_lbl.configure(text="●  ATTIVO", fg=Cfg.SUCCESS)
        else:
            self._hand_btn.configure(text="▶  ATTIVA", bg=Cfg.SUCCESS, fg="#000000")
            self._status_lbl.configure(text="●  OFFLINE", fg="#ff4444")
            self._gest_lbl.configure(text="—")
            self._action_lbl.configure(text="")
            if self._cam and self._cam._drag_started if hasattr(self._cam, '_processor') else False:
                self.mouse.stop_drag()

    def _toggle_vk(self):
        if self._vk is None or not self._vk.winfo_exists():
            self._vk = VirtualKeyboard(self, self.mouse)
            self._vk_btn.configure(text="⌨  NASCONDI TASTIERA", bg=Cfg.ACCENT, fg=Cfg.TEXT)
        else:
            if self._vk.state() == "normal":
                self._vk.withdraw()
                self._vk_btn.configure(text="⌨  MOSTRA TASTIERA", bg=Cfg.BLUE, fg="#000000")
            else:
                self._vk_btn.configure(text="⌨  NASCONDI TASTIERA", bg=Cfg.ACCENT, fg=Cfg.TEXT)
                self._vk.deiconify()

    # ── camera + UI loop ──────────────────────────────────────
    def _start_camera(self):
        self._cam = CameraThread(self)
        self._cam.start_capture()

    def _loop(self):
        if self._cam:
            frame = self._cam.get_frame()
            if frame is not None:
                h, w = frame.shape[:2]
                dw   = 620
                dh   = int(h * dw / w)
                small = cv2.resize(frame, (dw, dh))
                rgb   = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                photo = ImageTk.PhotoImage(Image.fromarray(rgb))
                self._cam_lbl.configure(image=photo)
                self._cam_lbl.image = photo

            if self.hand_active:
                g = self._cam.gesture
                a = self._cam.action
                self._gest_lbl.configure(text=g or "—")
                self._action_lbl.configure(text=a)

        self.after(Cfg.DWELL_MS, self._loop)

    def _on_close(self):
        if self._cam:
            self._cam.stop_capture()
        self.destroy()
        sys.exit(0)


# ─────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = Dashboard()
    app.mainloop()
