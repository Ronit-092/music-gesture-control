import cv2
import mediapipe as mp
import numpy as np
import sounddevice as sd
from scipy.io.wavfile import read as wav_read
from scipy.signal import stft, istft
import time, os, glob, threading, queue

# ══════════════════════════════════════════════════════════
#  PITCH SHIFT — Phase Vocoder (runs ONLY in background thread)
# ══════════════════════════════════════════════════════════
def phase_vocoder(audio, sr, semitones):
    if abs(semitones) < 0.2:
        return audio
    factor  = 2.0 ** (semitones / 12.0)
    n_fft, hop = 1024, 256          # smaller fft = much faster
    win     = np.hanning(n_fft)
    _, _, Z = stft(audio, fs=sr, window=win, nperseg=n_fft, noverlap=n_fft-hop)
    phase_adv   = 2.0 * np.pi * hop * np.arange(Z.shape[0]) / n_fft
    stretch     = 1.0 / factor
    n_out       = int(np.ceil(Z.shape[1] * stretch))
    Z_out       = np.zeros((Z.shape[0], n_out), dtype=complex)
    phase_acc   = np.angle(Z[:, 0])
    for i in range(n_out):
        src = i / stretch
        lo  = min(int(src), Z.shape[1]-1)
        hi  = min(lo+1,     Z.shape[1]-1)
        t   = src - int(src)
        mag = (1-t)*np.abs(Z[:,lo]) + t*np.abs(Z[:,hi])
        if i > 0:
            dp         = np.angle(Z[:,min(lo+1,Z.shape[1]-1)]) - np.angle(Z[:,lo]) - phase_adv
            dp        -= 2*np.pi * np.round(dp/(2*np.pi))
            phase_acc += phase_adv + dp
        Z_out[:,i] = mag * np.exp(1j * phase_acc)
    _, stretched = istft(Z_out, fs=sr, window=win, nperseg=n_fft, noverlap=n_fft-hop)
    idx    = np.linspace(0, len(stretched)-1, len(audio))
    return np.interp(idx, np.arange(len(stretched)), stretched).astype(np.float32)


# ══════════════════════════════════════════════════════════
#  AUDIO MANAGER
# ══════════════════════════════════════════════════════════
class AudioManager:
    def __init__(self):
        self.tracks    = sorted(glob.glob("music/*.wav"))
        if not self.tracks:
            raise FileNotFoundError("No .wav files found in music/")
        self.track_idx = 0
        self._raw      = {}
        self._fs_map   = {}
        self._cache    = {}          # (track_idx, semitones_q) -> pitched array
        self._lock     = threading.Lock()
        self._pitch_q  = queue.Queue(maxsize=1)  # pending pitch job
        self._pending_st = None      # semitones we're computing right now

        self.semitones = 0.0
        self.volume    = 0.5
        self.speed     = 1.0
        self.paused    = False
        self.locked    = False
        self.play_idx  = 0

        self._load_raw(0)
        self.data = self._raw[0]
        self.fs   = self._fs_map[0]

        # single background worker
        threading.Thread(target=self._worker, daemon=True).start()

    # ── raw load (fast, no processing) ─────────────────────
    def _load_raw(self, idx):
        if idx in self._raw:
            return
        fs, d = wav_read(self.tracks[idx])
        if len(d.shape) > 1:
            d = d.mean(axis=1)
        d = d.astype(np.float32)
        d /= np.max(np.abs(d)) + 1e-9
        self._fs_map[idx] = fs
        self._raw[idx]    = d

    # ── background worker: processes ONE pitch job at a time ─
    def _worker(self):
        while True:
            idx, st = self._pitch_q.get()
            key = (idx, st)
            if key not in self._cache:
                result = phase_vocoder(self._raw[idx], self._fs_map[idx], st)
                with self._lock:
                    self._cache[key] = result
            self._pitch_q.task_done()

    # ── request a pitch shift (non-blocking) ────────────────
    def request_pitch(self, semitones):
        st = round(semitones)   # quantise to whole semitones — avoids flood of jobs
        if st == round(self.semitones):
            return
        self.semitones = float(st)
        key = (self.track_idx, st)
        with self._lock:
            if key in self._cache:
                self.data = self._cache[key]
                return
        # enqueue job (drop if queue full — stale request)
        try:
            self._pitch_q.put_nowait((self.track_idx, st))
        except queue.Full:
            pass

    # ── poll: apply pitched data if ready ───────────────────
    def poll_pitch(self):
        key = (self.track_idx, round(self.semitones))
        with self._lock:
            if key in self._cache and self.data is not self._cache[key]:
                self.data = self._cache[key]

    # ── switch track ────────────────────────────────────────
    def switch_track(self, delta):
        new_idx = (self.track_idx + delta) % len(self.tracks)
        self._load_raw(new_idx)
        with self._lock:
            self.track_idx = new_idx
            self.data      = self._raw[new_idx]   # use raw immediately
            self.fs        = self._fs_map[new_idx]
            self.play_idx  = 0
            self.semitones = 0.0                   # reset pitch on track change

    # ── audio callback (called from sounddevice thread) ─────
    def audio_callback(self, outdata, frames, time_info, status):
        if self.paused:
            outdata[:] = 0
            return
        speed = max(0.25, min(self.speed, 2.5))
        chunk = int(frames * speed)
        with self._lock:
            i    = self.play_idx
            data = self.data
            if i + chunk >= len(data):
                i = 0
            self.play_idx = i + chunk
            samples = data[i: i+chunk]
        samples = np.interp(np.linspace(0, len(samples), frames),
                            np.arange(len(samples)), samples)
        outdata[:] = (samples * self.volume).reshape(-1, 1)

    @property
    def track_name(self):
        return os.path.splitext(os.path.basename(self.tracks[self.track_idx]))[0]

    @property
    def progress(self):
        return self.play_idx / max(1, len(self.data))


# ══════════════════════════════════════════════════════════
#  SWIPE TRACKER
# ══════════════════════════════════════════════════════════
class SwipeTracker:
    def __init__(self, min_dist=160, max_time=0.5, cooldown=1.0):
        self.min_dist = min_dist
        self.max_time = max_time
        self.cooldown = cooldown
        self._sx = self._st = None
        self._last = 0.0

    def update(self, x, active):
        now = time.time()
        if not active or now - self._last < self.cooldown:
            self._sx = None
            return 0
        if self._sx is None:
            self._sx, self._st = x, now
            return 0
        dx, dt = x - self._sx, now - self._st
        if dt > self.max_time:
            self._sx, self._st = x, now
            return 0
        if abs(dx) >= self.min_dist:
            d = 1 if dx > 0 else -1
            self._sx = None
            self._last = now
            return d
        return 0


# ══════════════════════════════════════════════════════════
#  FINGER HELPERS
# ══════════════════════════════════════════════════════════
def lm_pt(lm, i, w, h):
    return (int(lm[i].x * w), int(lm[i].y * h))

def dist(p1, p2):
    return float(np.hypot(p2[0]-p1[0], p2[1]-p1[1]))

def map_val(v, a, b, c, d):
    return float(np.clip((v-a)/(b-a)*(d-c)+c, c, d))

def finger_states(lm):
    tips = [4, 8, 12, 16, 20]
    pip  = [3, 6, 10, 14, 18]
    thumb  = lm[4].x < lm[3].x
    others = [lm[tips[i]].y < lm[pip[i]].y for i in range(1,5)]
    return {"thumb": thumb, "index": others[0], "middle": others[1],
            "ring": others[2], "pinky": others[3]}

def only_index_up(fs):
    return fs["index"] and not fs["middle"] and not fs["ring"] \
           and not fs["pinky"] and not fs["thumb"]

def all_up(fs):
    return all(fs[k] for k in fs)


# ══════════════════════════════════════════════════════════
#  LIGHTWEIGHT DRAW UTILS  (no per-element img.copy())
# ══════════════════════════════════════════════════════════
NC  = (0,  255, 255)   # cyan
NP  = (255, 50, 200)   # pink
NG  = (50, 255, 100)   # green
NO  = (0,  165, 255)   # orange
NY  = (0,  220, 255)   # yellow
NPU = (200, 60, 255)   # purple
PBG = (18,  18,  38)   # panel bg

# Pre-built dark overlay panel — drawn once, blended each frame
_panel_cache = {}
def panel(img, x, y, w, h, alpha=0.6):
    key = (w, h)
    if key not in _panel_cache:
        p = np.full((h, w, 3), PBG, dtype=np.uint8)
        _panel_cache[key] = p
    roi = img[y:y+h, x:x+w]
    cv2.addWeighted(_panel_cache[key], alpha, roi, 1-alpha, 0, roi)
    img[y:y+h, x:x+w] = roi
    cv2.rectangle(img, (x,y), (x+w,y+h), (0,100,100), 1)

def nt(img, text, pos, scale, color, t=1):
    cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, color, t, cv2.LINE_AA)

def arc_meter(img, cx, cy, r, val, color, label, vstr):
    val = max(0.0, min(1.0, val))
    cv2.ellipse(img,(cx,cy),(r,r),0,230,510,(50,50,70),4)
    filled = int(280*val)
    if filled > 1:
        cv2.ellipse(img,(cx,cy),(r,r),0,230,230+filled,color,4)
    (tw,th),_ = cv2.getTextSize(vstr, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
    nt(img, vstr, (cx-tw//2, cy+th//2), 0.48, color)
    (lw,_),_  = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.33, 1)
    nt(img, label, (cx-lw//2, cy+r+4), 0.33, (160,160,190), 1)

def lock_ring(img, cx, cy, prog, locked):
    color = NY if not locked else NG
    cv2.ellipse(img,(cx,cy),(44,44),-90,0,360,(50,50,70),4)
    sweep = int(360*prog)
    if sweep > 1:
        cv2.ellipse(img,(cx,cy),(44,44),-90,0,sweep,color,4)
    lbl = "LOCK" if not locked else "UNLOCK"
    (tw,th),_ = cv2.getTextSize(lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
    nt(img, lbl, (cx-tw//2, cy+th//2), 0.4, color, 1)

def swipe_arrow(img, direction, cx, cy):
    color = NC
    if direction > 0:
        cv2.arrowedLine(img,(cx-50,cy),(cx+50,cy),color,3,tipLength=0.3)
    else:
        cv2.arrowedLine(img,(cx+50,cy),(cx-50,cy),color,3,tipLength=0.3)


# ══════════════════════════════════════════════════════════
#  INIT
# ══════════════════════════════════════════════════════════
am = AudioManager()
stream = sd.OutputStream(callback=am.audio_callback,
                         samplerate=am.fs, channels=1, blocksize=2048)
stream.start()

mp_hands = mp.solutions.hands
mp_draw  = mp.solutions.drawing_utils
hands_det = mp_hands.Hands(
    max_num_hands=2,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7,
    model_complexity=0,          # ← LITE model, much faster
)

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
W, H = 1280, 720
MP_W, MP_H = 640, 360   # MediaPipe runs on half-res — big speedup

right_sw = SwipeTracker()
left_sw  = SwipeTracker()

LOCK_DELAY    = 1.8
open_since    = None
lock_cd       = 0.0
pause_cd      = 0.0
flash         = {"text": "", "color": NC, "until": 0.0}
swipe_anim    = {"dir": 0, "until": 0.0}
frame_count   = 0

def show_flash(text, color=NC, dur=2.0):
    flash["text"]  = text
    flash["color"] = color
    flash["until"] = time.time() + dur

# ── Pre-build static guide panel (never changes) ──────────
GUIDE_LINES = [
    ("R thumb-index",  "Volume",  NC),
    ("L thumb-index",  "Pitch",   NP),
    ("Both hands",     "Speed",   NPU),
    ("R index only",   "Pause",   NO),
    ("R swipe right",  "Next",    NC),
    ("L swipe left",   "Prev",    NP),
    ("Open palm hold", "Lock",    NY),
]
GUIDE_X, GUIDE_Y = W-220, 50
GUIDE_W, GUIDE_H = 210, len(GUIDE_LINES)*24+40
guide_panel = np.full((GUIDE_H, GUIDE_W, 3), PBG, dtype=np.uint8)
cv2.rectangle(guide_panel,(0,0),(GUIDE_W-1,GUIDE_H-1),(0,100,100),1)
cv2.putText(guide_panel,"CONTROLS",(8,20),cv2.FONT_HERSHEY_SIMPLEX,0.45,NC,1,cv2.LINE_AA)
for i,(gest,action,col) in enumerate(GUIDE_LINES):
    y = 38 + i*24
    cv2.putText(guide_panel,gest,   (6,  y),cv2.FONT_HERSHEY_SIMPLEX,0.32,(190,190,210),1,cv2.LINE_AA)
    cv2.putText(guide_panel,f"->{action}",(114,y),cv2.FONT_HERSHEY_SIMPLEX,0.32,col,1,cv2.LINE_AA)


# ══════════════════════════════════════════════════════════
#  MAIN LOOP
# ══════════════════════════════════════════════════════════
while True:
    ret, frame = cap.read()
    if not ret:
        break
    frame = cv2.flip(frame, 1)
    # Don't resize to W,H yet — work at native cap resolution first
    now = time.time()
    frame_count += 1

    # ── MediaPipe on HALF-res ────────────────────────────
    small = cv2.resize(frame, (MP_W, MP_H))
    rgb   = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    result = hands_det.process(rgb)

    # Scale factors back to full frame size
    fh, fw = frame.shape[:2]
    sx, sy = fw / MP_W, fh / MP_H

    detected = []
    if result.multi_hand_landmarks and result.multi_handedness:
        for handLms, handedness in zip(result.multi_hand_landmarks,
                                       result.multi_handedness):
            lm    = handLms.landmark
            label = handedness.classification[0].label

            # Scale landmarks to full-frame coordinates
            def pt(i):
                return (int(lm[i].x * fw), int(lm[i].y * fh))

            thumb  = pt(4)
            index  = pt(8)
            wrist  = pt(0)
            span   = dist(thumb, index)
            center = ((thumb[0]+index[0])//2, (thumb[1]+index[1])//2)
            fs     = finger_states(lm)

            detected.append({"label": label, "lm": lm, "handLms": handLms,
                              "thumb": thumb, "index": index, "wrist": wrist,
                              "span": span, "center": center, "fs": fs,
                              "all_up": all_up(fs), "only_idx": only_index_up(fs)})

            # Draw — simple lines only, no glow
            hc = NC if label == "Right" else NP
            mp_draw.draw_landmarks(
                frame, handLms, mp_hands.HAND_CONNECTIONS,
                mp_draw.DrawingSpec(color=hc, thickness=1, circle_radius=2),
                mp_draw.DrawingSpec(color=(120,120,140), thickness=1),
            )
            cv2.circle(frame, thumb, 7, hc, -1)
            cv2.circle(frame, index, 7, NG, -1)
            cv2.line(frame, thumb, index, NY, 2)

    right = next((d for d in detected if d["label"]=="Right"), None)
    left  = next((d for d in detected if d["label"]=="Left"),  None)

    # ── PAUSE — right index only ─────────────────────────
    if right and right["only_idx"] and now - pause_cd > 1.2:
        am.paused  = not am.paused
        pause_cd   = now
        show_flash("PAUSED" if am.paused else "PLAYING",
                   NO if am.paused else NG)

    # ── SWIPE ─────────────────────────────────────────────
    if right:
        rs = right_sw.update(right["wrist"][0],
                             not right["only_idx"] and not right["all_up"])
        if rs == 1:
            am.switch_track(+1)
            show_flash(f">> {am.track_name}", NC)
            swipe_anim["dir"]   = 1
            swipe_anim["until"] = now + 0.5
    else:
        right_sw.update(0, False)

    if left:
        ls = left_sw.update(left["wrist"][0],
                            not left["only_idx"] and not left["all_up"])
        if ls == -1:
            am.switch_track(-1)
            show_flash(f"<< {am.track_name}", NP)
            swipe_anim["dir"]   = -1
            swipe_anim["until"] = now + 0.5
    else:
        left_sw.update(0, False)

    # ── LOCK — open palm hold ─────────────────────────────
    is_open = any(d["all_up"] for d in detected)
    if is_open:
        if open_since is None:
            open_since = now
        elif now - open_since >= LOCK_DELAY and now - lock_cd > LOCK_DELAY + 0.5:
            am.locked  = not am.locked
            lock_cd    = now
            open_since = None
            show_flash("LOCKED" if am.locked else "UNLOCKED",
                       NY if am.locked else NG)
    else:
        open_since = None

    # ── CONTROLS (unlocked, no special gesture active) ────
    if not am.locked and not am.paused:
        r_ctrl = right and not right["all_up"] and not right["only_idx"]
        l_ctrl = left  and not left["all_up"]  and not left["only_idx"]

        if r_ctrl:
            am.volume = map_val(right["span"], 20, 230, 0.0, 1.0)

        if l_ctrl:
            new_st = map_val(left["span"], 20, 230, -12.0, 12.0)
            am.request_pitch(new_st)   # non-blocking

        if r_ctrl and l_ctrl:
            hd = dist(right["center"], left["center"])
            am.speed = map_val(hd, 60, 600, 0.3, 2.5)
            cv2.line(frame, right["center"], left["center"], NPU, 2)

    # Poll whether background pitch job finished
    am.poll_pitch()

    # ══ DRAW HUD ══════════════════════════════════════════

    # resize frame to display size now
    if frame.shape[1] != W or frame.shape[0] != H:
        frame = cv2.resize(frame, (W, H))

    # ── Top bar ───────────────────────────────────────────
    panel(frame, 0, 0, W, 42, 0.75)
    nt(frame, f"  {am.track_name}", (10, 27), 0.55, NC)
    tc = f"{am.track_idx+1}/{len(am.tracks)}"
    (tcw,_),_ = cv2.getTextSize(tc, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
    nt(frame, tc, (W//2-tcw//2, 27), 0.42, (160,160,190), 1)
    mode_c = NG if not am.locked else NY
    mode_s = ("LOCKED" if am.locked else "CONTROL") + ("  |  PAUSED" if am.paused else "")
    nt(frame, mode_s, (W-240, 27), 0.5, mode_c)

    # ── Progress bar ──────────────────────────────────────
    cv2.rectangle(frame, (0,42), (W,46), (40,40,60), -1)
    cv2.rectangle(frame, (0,42), (int(W*am.progress),46), NC, -1)

    # ── Arc meters ────────────────────────────────────────
    panel(frame, 0, H-120, 430, 120, 0.65)
    arc_meter(frame,  60, H-55, 42, am.volume, NC, "VOL", f"{int(am.volume*100)}%")
    arc_meter(frame, 180, H-55, 42, (am.speed-0.3)/2.2, NO, "SPEED", f"{am.speed:.1f}x")
    st = round(am.semitones)
    arc_meter(frame, 300, H-55, 42, (am.semitones+12)/24, NP, "PITCH",
              f"{st:+d}st" if st != 0 else "0st")
    # Pitch computing indicator
    key = (am.track_idx, round(am.semitones))
    with am._lock:
        cached = key in am._cache
    if not cached and abs(am.semitones) > 0.5:
        nt(frame, "computing...", (340, H-10), 0.3, (150,150,80), 1)

    # ── Static guide panel (blit directly) ────────────────
    frame[GUIDE_Y:GUIDE_Y+GUIDE_H, GUIDE_X:GUIDE_X+GUIDE_W] = \
        cv2.addWeighted(guide_panel, 0.75,
                        frame[GUIDE_Y:GUIDE_Y+GUIDE_H, GUIDE_X:GUIDE_X+GUIDE_W], 0.25, 0)

    # ── Waveform — downsampled to 120 points ──────────────
    if not am.paused:
        wv_chunk = min(4800, len(am.data) - am.play_idx)
        if wv_chunk > 1:
            wave = am.data[am.play_idx: am.play_idx + wv_chunk]
            wave_n = np.interp(
                np.linspace(0, len(wave)-1, 120),
                np.arange(len(wave)), wave
            )
            wave_n = np.interp(wave_n, (-1.0,1.0), (0.0,1.0))
            xs = np.linspace(440, GUIDE_X-10, 120).astype(int)
            ys = (H - 60 - wave_n * 48).astype(int)
            pts = np.column_stack([xs, ys])
            cv2.polylines(frame, [pts], False, (0,180,255), 1)

    # ── Lock ring ─────────────────────────────────────────
    if open_since is not None:
        lock_ring(frame, W//2, H//2, min(1.0,(now-open_since)/LOCK_DELAY), am.locked)

    # ── Swipe arrow ───────────────────────────────────────
    if now < swipe_anim["until"]:
        swipe_arrow(frame, swipe_anim["dir"], W//2, H//2-50)

    # ── Flash ─────────────────────────────────────────────
    if now < flash["until"]:
        (tw,th),_ = cv2.getTextSize(flash["text"], cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)
        fx, fy = W//2-tw//2, H//2+70
        panel(frame, fx-12, fy-th-8, tw+24, th+18, 0.80)
        nt(frame, flash["text"], (fx, fy), 1.0, flash["color"], 2)

    # ── Locked / paused badges ────────────────────────────
    if am.locked:
        nt(frame, "[ LOCKED ]", (W//2-55, H-158), 0.5, NY, 1)
    if am.paused:
        nt(frame, "II", (W//2-14, 110), 2.0, NO, 4)

    cv2.imshow("Gesture Music Controller", frame)
    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()
stream.stop()