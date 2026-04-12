// ═══════════════════════════════════════════════════════════════════
//  WAVEMIND — app.js
//  Gesture-controlled music player using MediaPipe Hands +
//  Internet Archive audio streaming.
// ═══════════════════════════════════════════════════════════════════

// ─────────────────────────────────────────────────────────────────
//  COORDINATE SYSTEM
//
//  MediaPipe gives landmarks in 0..1 space where x=0 is camera-left.
//  The VIDEO has CSS transform:scaleX(-1) — mirror selfie view.
//  The CANVAS has NO CSS transform.
//
//  To align skeleton with mirrored video, one rule handles everything:
//    canvasX = (1 - lm.x) * canvasWidth    ← mirror flip
//    canvasY =       lm.y * canvasHeight
//
//  This keeps canvas text readable and Left/Right labels correct.
// ─────────────────────────────────────────────────────────────────

// ── Internet Archive search ────────────────────────────────────────
async function searchIA(query) {
  const url =
    'https://archive.org/advancedsearch.php?' +
    'q=' + encodeURIComponent(query + ' AND mediatype:audio AND format:mp3') +
    '&fl[]=identifier,title,creator,year,downloads' +
    '&sort[]=downloads+desc&rows=25&page=1&output=json';

  setSt('Searching Internet Archive…');
  const r = await fetch(url);
  if (!r.ok) throw new Error('HTTP ' + r.status);
  const data = await r.json();
  const items = (data.response?.docs || []).filter(d => d.identifier);
  if (!items.length) return [];

  setSt('Loading track details…');
  const tracks = [];

  await Promise.all(items.slice(0, 8).map(async (item, rank) => {
    try {
      const m  = await fetch('https://archive.org/metadata/' + item.identifier);
      if (!m.ok) return;
      const md = await m.json();
      const mp3s = (md.files || []).filter(f =>
        f.name?.toLowerCase().endsWith('.mp3') && parseInt(f.size || 0) > 100000
      );
      if (!mp3s.length) return;
      const f = mp3s.find(f => !f.name.includes('sample')) || mp3s[0];
      tracks.push({
        rank,
        id:       item.identifier,
        title:    md.metadata?.title   || item.title   || item.identifier,
        creator:  md.metadata?.creator || item.creator || 'Unknown',
        year:     md.metadata?.year    || item.year    || '',
        audioUrl: 'https://archive.org/download/' + item.identifier + '/' + encodeURIComponent(f.name),
      });
    } catch (_) {}
  }));

  tracks.sort((a, b) => a.rank - b.rank);
  return tracks;
}

// ── Audio engine (HTMLAudioElement — no proxy needed) ─────────────
const audioEl = new Audio();
audioEl.crossOrigin = 'anonymous';

let actx, analyser, aData, mediaSrc, ctxConnected = false;

function initAudio() {
  if (ctxConnected) return;
  actx      = new (window.AudioContext || window.webkitAudioContext)();
  analyser  = actx.createAnalyser();
  analyser.fftSize = 256;
  aData     = new Uint8Array(analyser.frequencyBinCount);
  mediaSrc  = actx.createMediaElementSource(audioEl);
  mediaSrc.connect(analyser);
  analyser.connect(actx.destination);
  ctxConnected = true;
}

// ── App state ──────────────────────────────────────────────────────
const ST = {
  tracks: [], idx: 0,
  vol: .6, spd: 1.0, pit: 0,
  paused: false, locked: false,
  lVol: .6, lSpd: 1.0, lPit: 0,
};

const eVol = () => ST.locked ? ST.lVol : ST.vol;
const eSpd = () => ST.locked ? ST.lSpd : ST.spd;
const ePit = () => ST.locked ? ST.lPit : ST.pit;
const rate  = () => Math.max(0.25, Math.min(4, eSpd() * Math.pow(2, ePit() / 12)));

function applyAudio() {
  audioEl.volume          = Math.max(0, Math.min(1, eVol()));
  audioEl.playbackRate    = rate();
  audioEl.preservesPitch  = false;
}

// loadTrack is called ONLY when user explicitly clicks a track
async function loadTrack(t) {
  setSt('Loading "' + t.title + '"…');
  document.getElementById('ttitle').textContent  = t.title;
  document.getElementById('tartist').textContent = t.creator + (t.year ? ' · ' + t.year : '');

  // Initialise Web Audio on first user gesture (browser autoplay policy)
  initAudio();
  if (actx.state === 'suspended') await actx.resume();

  audioEl.src = t.audioUrl;
  applyAudio();

  try {
    await audioEl.play();
    ST.paused = false;
    document.getElementById('pauseicon').style.opacity = '0';
    updateBadge();
    setSt('');
    toast(t.title.length > 28 ? t.title.slice(0, 28) + '…' : t.title, '#00ffe7');
  } catch (e) {
    setSt('⚠ Playback blocked — click the page first, then try again');
    console.error('Play error:', e);
  }
}

// playAt is triggered by clicking a track row — the ONLY way audio starts
function playAt(i) {
  ST.idx = i;
  loadTrack(ST.tracks[i]);
  renderList();
}

// ── Search UI ──────────────────────────────────────────────────────
async function doSearch() {
  const q = document.getElementById('sq').value.trim();
  if (!q) return;

  const btn = document.getElementById('sbtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spin"></span>';

  try {
    const res  = await searchIA(q);
    ST.tracks  = res;
    ST.idx     = 0;

    if (res.length) {
      setSt(res.length + ' tracks found — click one to play');
      renderList();
      // ← NO auto-play here: user must click a track
    } else {
      setSt('No results — try: jazz, beethoven, blues, folk');
      document.getElementById('tl').innerHTML =
        '<div id="empty">No results.<br>Try: jazz · blues · classical<br>folk · bollywood · lofi</div>';
    }
  } catch (e) {
    setSt('Error: ' + e.message);
    toast('Search error', '#ff2d9e');
    console.error(e);
  }

  btn.disabled  = false;
  btn.textContent = 'SEARCH';
}

document.getElementById('sq').addEventListener('keydown', e => {
  if (e.key === 'Enter') doSearch();
});

function renderList() {
  document.getElementById('tl').innerHTML = ST.tracks.map((t, i) => `
    <div class="ti ${i === ST.idx ? 'on' : ''}" onclick="playAt(${i})">
      <div class="tn">${i + 1}</div>
      <div class="tmeta">
        <div class="tname">${esc(t.title)}</div>
        <div class="tartist2">${esc(t.creator)}${t.year ? ' · ' + esc(t.year) : ''}</div>
      </div>
      <div class="tplay">▶</div>
    </div>`).join('');
}

const esc = s => String(s)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;');

function setSt(m) { document.getElementById('ss').textContent = m; }

// ═══════════════════════════════════════════════════════════════════
//  MEDIAPIPE HAND TRACKING
// ═══════════════════════════════════════════════════════════════════
const vid = document.getElementById('webcam');
const ovC = document.getElementById('ov');   const ovX = ovC.getContext('2d');
const lkC = document.getElementById('lkc'); const lkX = lkC.getContext('2d');
const wvC = document.getElementById('wvc'); const wvX = wvC.getContext('2d');

function resize() {
  const a   = document.getElementById('ca');
  ovC.width = wvC.width = a.offsetWidth;
  ovC.height            = a.offsetHeight;
  wvC.height            = 56;
}
window.addEventListener('resize', resize);

// Convert landmark → canvas pixel (with X mirror)
let CW = 1, CH = 1;
const mx = x => (1 - x) * CW;
const my = y =>      y  * CH;

// ── Finger detection ───────────────────────────────────────────────
// label here is already the VISUAL label (after swap), so:
//   visual 'Right' hand  → in raw MP coords this was 'Left'
//   → thumb extends to the RIGHT in raw coords → tip.x > base.x
//   visual 'Left'  hand  → in raw MP coords this was 'Right'
//   → thumb extends to the LEFT  in raw coords → tip.x < base.x
function fUp(lm, visualLabel) {
  const thumbUp = visualLabel === 'Right'
    ? lm[4].x > lm[3].x   // raw Left hand, thumb goes right
    : lm[4].x < lm[3].x;  // raw Right hand, thumb goes left
  return {
    thumb:  thumbUp,
    index:  lm[8].y  < lm[6].y,
    middle: lm[12].y < lm[10].y,
    ring:   lm[16].y < lm[14].y,
    pinky:  lm[20].y < lm[18].y,
  };
}
const allUp   = fs => Object.values(fs).every(Boolean);
const idxOnly = fs => fs.index && !fs.middle && !fs.ring && !fs.pinky && !fs.thumb;

// ── Helpers ────────────────────────────────────────────────────────
const d2n    = (a, b) => Math.hypot(b.x - a.x, b.y - a.y);
const clamp  = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const mapV   = (v, a, b, c, d) => clamp((v - a) / (b - a) * (d - c) + c, c, d);

let openAt = null, lockAt = 0, pauseAt = 0;
const LOCK_T = 1.8;

// ── Draw utilities ─────────────────────────────────────────────────
function dot(x, y, r, col) {
  ovX.shadowColor = col; ovX.shadowBlur = 10;
  ovX.fillStyle   = col;
  ovX.beginPath(); ovX.arc(x, y, r, 0, Math.PI * 2); ovX.fill();
  ovX.shadowBlur  = 0;
}
function seg(x1, y1, x2, y2, col, w = 2) {
  ovX.strokeStyle = col; ovX.lineWidth = w;
  ovX.beginPath(); ovX.moveTo(x1, y1); ovX.lineTo(x2, y2); ovX.stroke();
}
function lbl(txt, x, y, col, size = 11, align = 'center') {
  ovX.fillStyle   = col;
  ovX.font        = `bold ${size}px "Share Tech Mono",monospace`;
  ovX.textAlign   = align;
  ovX.fillText(txt, x, y);
}

function drawLock(prog, locked) {
  lkX.clearRect(0, 0, 110, 110);
  const col = locked ? '#39ff7a' : '#ffe100';
  lkX.strokeStyle = 'rgba(255,255,255,.08)'; lkX.lineWidth = 5;
  lkX.beginPath(); lkX.arc(55, 55, 40, 0, Math.PI * 2); lkX.stroke();
  lkX.strokeStyle = col; lkX.shadowColor = col; lkX.shadowBlur = 10;
  lkX.beginPath();
  lkX.arc(55, 55, 40, -Math.PI / 2, -Math.PI / 2 + prog * Math.PI * 2);
  lkX.stroke();
  lkX.shadowBlur = 0; lkX.fillStyle = col;
  lkX.font = 'bold 10px "Share Tech Mono",monospace';
  lkX.textAlign = 'center'; lkX.textBaseline = 'middle';
  lkX.fillText(locked ? 'UNLOCK' : 'LOCK', 55, 55);
}

// ─────────────────────────────────────────────────────────────────
//  GESTURE CALLBACK
// ─────────────────────────────────────────────────────────────────
function onHands(res) {
  CW = ovC.width; CH = ovC.height;
  ovX.clearRect(0, 0, CW, CH);
  const now   = Date.now() / 1000;
  const hands = {};

  if (res.multiHandLandmarks && res.multiHandedness) {
    res.multiHandLandmarks.forEach((lm, i) => {
      // MediaPipe labels from camera POV. Since the video is CSS-mirrored,
      // MP 'Right' appears on the LEFT of the screen → swap to get visual label.
      const mpLabel  = res.multiHandedness[i].label;
      const labelStr = mpLabel === 'Right' ? 'Left' : 'Right'; // visual label
      const fs = fUp(lm, labelStr);

      // Draw skeleton using mirrored coords
      if (typeof HAND_CONNECTIONS !== 'undefined') {
        ovX.strokeStyle = 'rgba(180,200,220,.3)'; ovX.lineWidth = 1;
        for (const [a, b] of HAND_CONNECTIONS) {
          ovX.beginPath();
          ovX.moveTo(mx(lm[a].x), my(lm[a].y));
          ovX.lineTo(mx(lm[b].x), my(lm[b].y));
          ovX.stroke();
        }
      }

      // Key points in canvas coords
      const tx = mx(lm[4].x), ty = my(lm[4].y); // thumb tip
      const ix = mx(lm[8].x), iy = my(lm[8].y); // index tip
      const wx = mx(lm[0].x), wy = my(lm[0].y); // wrist
      const midX = (tx + ix) / 2, midY = (ty + iy) / 2;

      const hcol = labelStr === 'Right' ? '#00ffe7' : '#ff2d9e';

      // Thumb-index span line
      seg(tx, ty, ix, iy, 'rgba(255,225,0,.7)', 2);
      // Key dots
      dot(tx, ty, 7, hcol);
      dot(ix, iy, 7, '#39ff7a');
      // Span label
      const spanPx = Math.hypot(tx - ix, ty - iy);
      lbl(Math.round(spanPx) + 'px', midX + 4, midY - 8, 'rgba(255,225,0,.85)', 10, 'left');
      // Hand label at wrist
      lbl(labelStr, wx, wy + 22, hcol, 11, 'center');

      hands[labelStr] = {
        lm, fs,
        allUp:   allUp(fs),
        idxOnly: idxOnly(fs),
        spanN:   d2n(lm[4], lm[8]), // normalised span
        tx, ty, ix, iy,
        midX, midY,
      };
    });
  }

  const R = hands['Right'], L = hands['Left'];

  // ── PAUSE: right index only ────────────────────────────────────
  if (R && R.idxOnly && now - pauseAt > 1.2) {
    ST.paused = !ST.paused; pauseAt = now;
    if (ST.paused) {
      audioEl.pause();
      document.getElementById('pauseicon').style.opacity = '1';
    } else {
      audioEl.play();
      document.getElementById('pauseicon').style.opacity = '0';
    }
    toast(ST.paused ? 'PAUSED' : 'PLAYING', ST.paused ? '#ff8c00' : '#39ff7a');
    updateBadge();
  }


  // ── LOCK: open palm hold ───────────────────────────────────────
  const anyOpen = (R && R.allUp) || (L && L.allUp);
  if (anyOpen) {
    if (!openAt) openAt = now;
    const prog = Math.min(1, (now - openAt) / LOCK_T);
    lkC.classList.add('vis'); drawLock(prog, ST.locked);
    if (prog >= 1 && now - lockAt > LOCK_T + 0.5) {
      ST.locked = !ST.locked; lockAt = now; openAt = null;
      if (ST.locked) {
        ST.lVol = ST.vol; ST.lSpd = ST.spd; ST.lPit = ST.pit;
        toast('STATE LOCKED', '#ffe100');
      } else {
        toast('UNLOCKED', '#39ff7a');
      }
      applyAudio(); updateBadge();
    }
  } else {
    openAt = null; lkC.classList.remove('vis');
  }

  // ── CONTINUOUS CONTROLS ────────────────────────────────────────
  if (!ST.locked && !ST.paused) {
    const rc = R && !R.allUp && !R.idxOnly;
    const lc = L && !L.allUp && !L.idxOnly;

    // Volume = right hand thumb-index span
    if (rc) ST.vol = mapV(R.spanN, 0.03, 0.38, 0, 1);

    // Pitch = left hand thumb-index span
    if (lc) ST.pit = mapV(L.spanN, 0.03, 0.38, -12, 12);

    // Speed = distance between midpoints of each hand's thumb-index line
    if (rc && lc) {
      const distPx = Math.hypot(R.midX - L.midX, R.midY - L.midY);
      const distN  = distPx / CW;
      ST.spd = mapV(distN, 0.05, 0.65, 0.25, 2.5);

      // Visual: line between midpoints
      seg(R.midX, R.midY, L.midX, L.midY, 'rgba(191,0,255,.75)', 2);
      dot(R.midX, R.midY, 5, '#bf00ff');
      dot(L.midX, L.midY, 5, '#bf00ff');
      const cx = (R.midX + L.midX) / 2, cy = (R.midY + L.midY) / 2;
      lbl(
        Math.round(distPx) + 'px · ' + ST.spd.toFixed(2) + '×',
        cx, cy - 10, 'rgba(191,0,255,.9)', 11, 'center'
      );
    }

    applyAudio();
  }

  updateMeters();
}

// ── UI helpers ─────────────────────────────────────────────────────
let toastTmr;
function toast(msg, col = '#00ffe7') {
  const el = document.getElementById('toast');
  el.textContent    = msg;
  el.style.color    = col;
  el.style.borderColor = col;
  el.classList.add('on');
  clearTimeout(toastTmr);
  toastTmr = setTimeout(() => el.classList.remove('on'), 1800);
}
function updateBadge() {
  const b = document.getElementById('mbadge');
  b.className = '';
  if      (ST.paused)  { b.textContent = 'PAUSED';       b.className = 'paus'; }
  else if (ST.locked)  { b.textContent = 'LOCKED';       b.className = 'lock'; }
  else                 { b.textContent = 'CONTROL MODE'; b.className = 'ctrl'; }
  b.id = 'mbadge';
}
function updateMeters() {
  const v = eVol(), s = eSpd(), p = ePit();
  document.getElementById('vv').textContent    = Math.round(v * 100) + '%';
  document.getElementById('vf').style.width    = (v * 100) + '%';
  document.getElementById('sv').textContent    = s.toFixed(2) + '×';
  document.getElementById('sf').style.width    = ((s - 0.25) / 2.25 * 100) + '%';
  const st = Math.round(p);
  document.getElementById('pv').textContent    = st === 0 ? '0 st' : (st > 0 ? '+' : '') + st + ' st';
  document.getElementById('pf2').style.width   = ((p + 12) / 24 * 100) + '%';
}
function drawWave() {
  wvX.clearRect(0, 0, wvC.width, wvC.height);
  if (!analyser || audioEl.paused || audioEl.ended) return;
  analyser.getByteTimeDomainData(aData);
  const W = wvC.width, H = wvC.height;
  wvX.beginPath();
  const step = W / aData.length;
  for (let i = 0; i < aData.length; i++) {
    const y = (aData[i] / 128) * H / 2;
    i === 0 ? wvX.moveTo(0, y) : wvX.lineTo(i * step, y);
  }
  const g = wvX.createLinearGradient(0, 0, W, 0);
  g.addColorStop(0,   '#00ffe7');
  g.addColorStop(0.5, '#ff2d9e');
  g.addColorStop(1,   '#00ffe7');
  wvX.strokeStyle = g; wvX.lineWidth = 1.5;
  wvX.shadowColor = '#00ffe7'; wvX.shadowBlur = 5;
  wvX.stroke(); wvX.shadowBlur = 0;
}
function updateProg() {
  if (!audioEl.src || !audioEl.duration || isNaN(audioEl.duration)) return;
  document.getElementById('pf').style.width =
    (audioEl.currentTime / audioEl.duration * 100) + '%';
}

// ═══════════════════════════════════════════════════════════════════
//  APP START — single camera permission call
//
//  The previous bug: MediaPipe's Camera() utility internally calls
//  getUserMedia() again, triggering a second browser permission prompt.
//
//  Fix: call getUserMedia() once ourselves, feed the video element,
//  then drive MediaPipe manually with requestAnimationFrame.
//  Never use new Camera() from camera_utils.js.
// ═══════════════════════════════════════════════════════════════════
async function startApp() {
  document.getElementById('startscreen').style.display = 'none';
  resize();

  // ── Single getUserMedia call ───────────────────────────────────
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { width: 640, height: 360, facingMode: 'user' },
      audio: false,
    });
  } catch (e) {
    alert('Camera access denied. Please allow camera access and reload.');
    return;
  }

  vid.srcObject = stream;
  await new Promise(r => { vid.onloadedmetadata = r; });
  await vid.play();

  // ── MediaPipe Hands setup ──────────────────────────────────────
  const hp = new Hands({
    locateFile: f => `https://cdn.jsdelivr.net/npm/@mediapipe/hands@0.4.1646424915/${f}`,
  });
  hp.setOptions({
    maxNumHands:            2,
    modelComplexity:        0,   // 0 = Lite model (faster)
    minDetectionConfidence: 0.7,
    minTrackingConfidence:  0.65,
  });
  hp.onResults(onHands);

  // ── Drive MediaPipe with rAF — NO Camera() utility ────────────
  // This avoids the second getUserMedia() call that Camera() makes.
  let lastSend = 0;
  async function tick(ts) {
    // Throttle to ~30fps for hand detection (saves CPU)
    if (ts - lastSend > 33 && vid.readyState >= 2) {
      lastSend = ts;
      await hp.send({ image: vid });
    }
    updateProg();
    drawWave();
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);

  toast('Ready! Search and click a track →', '#00ffe7');
}