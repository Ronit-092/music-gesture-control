# WAVEMIND 🎵

A gesture-controlled music player that runs entirely in your browser. Control volume, pitch, and speed using your hands — no downloads, no installs.

🌐 **Live:** [wave-mind.netlify.app](https://wave-mind.netlify.app)

## Features

- 🎵 **Free music streaming** via [Internet Archive](https://archive.org) — millions of legal tracks
- 🤚 **Hand gesture controls** powered by [MediaPipe Hands](https://google.github.io/mediapipe/solutions/hands)
- 🎛️ **Real-time audio controls** — volume, playback speed, pitch shift
- 🔒 **State locking** — freeze your settings and let the music play
- 📷 **Single camera permission** — asked once, used throughout

## Gesture Controls

| Gesture | Action |
|---|---|
| **Right hand** — thumb+index span | Volume (wide open = loud) |
| **Left hand** — thumb+index span | Pitch (wide open = higher) |
| **Both hands** — distance between span midpoints | Speed |
| **Right index finger only** | Pause / Play toggle |
| **Open palm (hold ~2s)** | Lock / Unlock current settings |

## How to Use

1. Open [wave-mind.netlify.app](https://wave-mind.netlify.app) and click **ENABLE CAMERA**
2. Allow camera access when prompted (asked **once**)
3. Search for any song, artist, or genre in the right panel
4. **Click a track** to start playing
5. Use hand gestures to control playback in real time

## Running Locally

No build step needed:

```bash
git clone https://github.com/YOUR_USERNAME/wavemind.git
cd wavemind

# Option 1: open directly
open index.html

# Option 2: serve locally (recommended)
npx serve .
# or
python3 -m http.server 8080
```

Then visit `http://localhost:8080`.

> **Note:** Use Chrome or Edge for best MediaPipe performance. Firefox works but may be slower. Safari is not supported.

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
├── app.js          # All logic: gestures, audio engine, search
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
| Safari | ❌ Not supported |

## Deploying Updates

The site is hosted on Netlify. To deploy changes:

**Via drag-and-drop:** Go to [netlify.com](https://netlify.com) → your site → Deploys → drag the updated folder.

**Via GitHub (auto-deploy):**
```bash
git add .
git commit -m "your changes"
git push
```
Netlify will automatically redeploy on every push.

## Privacy

- Camera feed is processed **entirely in your browser** — no video is ever sent anywhere
- Music is streamed directly from Internet Archive's CDN
- No analytics, no tracking, no accounts required

## License

MIT — see [LICENSE](LICENSE)