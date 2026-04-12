# WAVEMIND 🎵

A gesture-controlled music player that runs entirely in your browser. Control volume, pitch, speed, and track navigation using your hands — no downloads, no installs.

![WAVEMIND screenshot](https://via.placeholder.com/800x450/050810/00ffe7?text=WAVEMIND)

## Features

- 🎵 **Free music streaming** via [Internet Archive](https://archive.org) — millions of legal tracks
- 🤚 **Hand gesture controls** powered by [MediaPipe Hands](https://google.github.io/mediapipe/solutions/hands)
- 🎛️ **Real-time audio controls** — volume, playback speed, pitch shift
- 🔒 **State locking** — freeze your settings and let the music play
- 📷 **Single camera permission** — asked once, used throughout

## Quick Start

No build step needed. Just open `index.html` in a modern browser:

```bash
git clone https://github.com/YOUR_USERNAME/wavemind.git
cd wavemind
# Option 1: open directly
open index.html

# Option 2: serve locally (recommended — avoids some browser restrictions)
npx serve .
# or
python3 -m http.server 8080
```

Then visit `http://localhost:8080` in Chrome or Edge.

> **Note:** Use Chrome or Edge for best MediaPipe performance. Firefox works but may be slower.

## Gesture Controls

| Gesture | Action |
|---|---|
| **Right hand** — thumb+index span | Volume (wide = loud) |
| **Left hand** — thumb+index span | Pitch (wide = higher) |
| **Both hands** — distance between span midpoints | Speed |
| **Right index finger only** | Pause / Play toggle |
| **Right hand swipe →** | Next track |
| **Left hand swipe ←** | Previous track |
| **Open palm (hold ~2s)** | Lock / Unlock current settings |

## How to Use

1. Open the app and click **ENABLE CAMERA**
2. Allow camera access (asked **once**)
3. Search for any song, artist, or genre in the right panel
4. **Click a track** to start playing
5. Use hand gestures to control playback

## Music Source

Tracks are streamed from [Internet Archive](https://archive.org), a non-profit digital library. The catalogue includes:

- Jazz, blues, classical, folk, world music
- Bollywood and Indian classical music
- Old pop, rock, and country recordings
- Live concert recordings
- Independent and CC-licensed music

Good search terms: `jazz`, `beethoven`, `blues`, `bollywood`, `coltrane`, `mozart`, `grateful dead`, `folk`, `lofi`, `carnatic`

## File Structure

```
wavemind/
├── index.html      # App shell and layout
├── style.css       # All styles
├── app.js          # All logic: gestures, audio, search
├── favicon.svg     # App icon
├── .gitignore
└── README.md
```

## Browser Requirements

| Browser | Support |
|---|---|
| Chrome 90+ | ✅ Full |
| Edge 90+ | ✅ Full |
| Firefox 90+ | ⚠️ Works, slower MediaPipe |
| Safari | ❌ MediaPipe not supported |

## Running Locally vs GitHub Pages

The app works as a static site. To deploy on GitHub Pages:

1. Push to a GitHub repo
2. Go to **Settings → Pages**
3. Set source to `main` branch, root folder
4. Visit `https://YOUR_USERNAME.github.io/wavemind`

## Privacy

- Camera feed is processed **locally in your browser** — no video is sent anywhere
- Music is streamed directly from Internet Archive's CDN
- No analytics, no tracking, no accounts

## License

MIT — see [LICENSE](LICENSE)