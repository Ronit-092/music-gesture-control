import cv2
import mediapipe as mp
import numpy as np
import sounddevice as sd
from scipy.io.wavfile import read

# Load audio file (use any .wav file)
fs, data = read("test1.wav")

# If stereo, convert to mono
if len(data.shape) > 1:
    data = data.mean(axis=1)

data = data.astype(np.float32)
data = data / np.max(np.abs(data))

# Globals
volume = 0.5
speed = 1.0
pitch = 1.0

# Audio callback
def audio_callback(outdata, frames, time, status):
    global idx, volume, speed

    chunk = int(frames * speed)

    if idx + chunk >= len(data):
        idx = 0

    samples = data[idx:idx+chunk]

    # Resample for speed control
    samples = np.interp(
        np.linspace(0, len(samples), frames),
        np.arange(len(samples)),
        samples
    )

    outdata[:] = (samples * volume).reshape(-1, 1)
    idx += chunk

idx = 0

# Start audio stream
stream = sd.OutputStream(callback=audio_callback, samplerate=fs, channels=1)
stream.start()

mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils
# MediaPipe setup
hands = mp_hands.Hands(
    max_num_hands=2,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
)

cap = cv2.VideoCapture(0)

def get_distance(p1, p2):
    return int(np.hypot(p2[0] - p1[0], p2[1] - p1[1]))

def map_value(val, in_min, in_max, out_min, out_max):
    val = np.clip(val, in_min, in_max)
    return (val - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame = cv2.flip(frame, 1)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    result = hands.process(rgb)

    h, w, _ = frame.shape
    hand_positions = []

    if result.multi_hand_landmarks:
        for handLms in result.multi_hand_landmarks:
            lm = handLms.landmark

            thumb = (int(lm[4].x * w), int(lm[4].y * h))
            index = (int(lm[8].x * w), int(lm[8].y * h))

            dist = get_distance(thumb, index)
            hand_positions.append((thumb, index, dist))

            # Draw
            cv2.circle(frame, thumb, 10, (255, 0, 0), -1)
            cv2.circle(frame, index, 10, (0, 255, 0), -1)
            cv2.line(frame, thumb, index, (0, 255, 255), 3)

    # Controls
    if len(hand_positions) == 1:
        # One hand → volume
        _, _, dist = hand_positions[0]
        volume = map_value(dist, 20, 200, 0.0, 1.0)

    elif len(hand_positions) == 2:
        # Two hands
        (t1, i1, d1), (t2, i2, d2) = hand_positions

        # Volume (right hand approx)
        volume = map_value(d1, 20, 200, 0.0, 1.0)

        # Speed (distance between hands)
        center1 = ((t1[0] + i1[0]) // 2, (t1[1] + i1[1]) // 2)
        center2 = ((t2[0] + i2[0]) // 2, (t2[1] + i2[1]) // 2)

        hand_dist = get_distance(center1, center2)
        speed = map_value(hand_dist, 50, 400, 0.5, 2.0)

        # Draw line between hands
        cv2.line(frame, center1, center2, (255, 0, 255), 3)

    # Display info
    cv2.putText(frame, f"Volume: {volume:.2f}", (10, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    cv2.putText(frame, f"Speed: {speed:.2f}", (10, 80),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    cv2.imshow("Gesture Music Controller", frame)

    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()
stream.stop()
