/**
 * app/static/app.js — Sainsbury's AI Voice Agent frontend
 *
 * Responsibilities:
 *  - Capture microphone audio via Web Audio API
 *  - Stream PCM16 chunks to FastAPI WebSocket as base64
 *  - Receive audio deltas from server and play via AudioContext queue
 *  - Render live transcript, speaking indicators, and function-call events
 *  - Load offers and store hours from REST API
 *  - Animate the background canvas and waveform visualiser
 *  - Handle reconnection with exponential backoff
 */

'use strict';

// ── Constants ──────────────────────────────────────────────────────────────────
const WS_BASE_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/voice`;
const SAMPLE_RATE = 24000;          // Must match backend voice.audio_sample_rate
const CHUNK_MS    = 100;            // Audio chunk interval in ms
const MAX_BACKOFF = 8000;           // Max WS reconnect delay ms

function getWsUrl() {
  const token = getAccessToken ? getAccessToken() : null;
  return token ? `${WS_BASE_URL}?token=${encodeURIComponent(token)}` : WS_BASE_URL;
}

// ── DOM refs ───────────────────────────────────────────────────────────────────
const $micBtn        = document.getElementById('mic-btn');
const $micHint       = document.getElementById('mic-hint');
const $micPulse      = document.getElementById('mic-pulse');
const $statusBadge   = document.getElementById('status-badge');
const $statusDot     = document.getElementById('status-dot');
const $statusLabel   = document.getElementById('status-label');
const $agentAvatar   = document.getElementById('agent-avatar');
const $agentTagline  = document.getElementById('agent-tagline');
const $waveformWrap  = document.getElementById('waveform-container');
const $waveformCanvas= document.getElementById('waveform-canvas');
const $transcriptList= document.getElementById('transcript-list');
const $transcriptEmpty= document.getElementById('transcript-empty');
const $clearBtn      = document.getElementById('clear-btn');
const $offersList    = document.getElementById('offers-list');
const $hoursGrid     = document.getElementById('hours-grid');
const $openBadge     = document.getElementById('open-badge');
const $toastContainer= document.getElementById('toast-container');
const $bgCanvas      = document.getElementById('bg-canvas');
const $chips         = document.querySelectorAll('.chip');

// ── State ──────────────────────────────────────────────────────────────────────
let ws              = null;
let wsBackoff       = 500;
let recording       = false;
let audioCtx        = null;
let micStream       = null;
let scriptProcessor = null;
let analyser        = null;
let playbackQueue   = [];
let playbackTime    = 0;
let agentSpeaking   = false;
let userSpeaking    = false;
let assistantBuffer = '';  // accumulate transcript deltas
let reconnectTimer  = null;

// ── Background canvas ──────────────────────────────────────────────────────────
(function initBgCanvas() {
  const ctx = $bgCanvas.getContext('2d');
  const orbs = Array.from({ length: 5 }, (_, i) => ({
    x: Math.random(),
    y: Math.random(),
    r: 200 + Math.random() * 300,
    vx: (Math.random() - 0.5) * 0.0002,
    vy: (Math.random() - 0.5) * 0.0002,
    hue: i % 2 === 0 ? 24 : 145,   // orange or green
    alpha: 0.06 + Math.random() * 0.06,
  }));

  function resize() {
    $bgCanvas.width  = window.innerWidth;
    $bgCanvas.height = window.innerHeight;
  }

  function draw() {
    const W = $bgCanvas.width, H = $bgCanvas.height;
    ctx.clearRect(0, 0, W, H);
    orbs.forEach(o => {
      o.x = (o.x + o.vx + 1) % 1;
      o.y = (o.y + o.vy + 1) % 1;
      const grd = ctx.createRadialGradient(o.x*W, o.y*H, 0, o.x*W, o.y*H, o.r);
      grd.addColorStop(0, `hsla(${o.hue}, 90%, 55%, ${o.alpha})`);
      grd.addColorStop(1, 'transparent');
      ctx.fillStyle = grd;
      ctx.fillRect(0, 0, W, H);
    });
    requestAnimationFrame(draw);
  }

  window.addEventListener('resize', resize);
  resize();
  draw();
})();

// ── Waveform visualiser ────────────────────────────────────────────────────────
const waveCtx = $waveformCanvas.getContext('2d');
const BARS = 48;
let waveData = new Float32Array(BARS).fill(0);

function drawWaveform() {
  const W = $waveformCanvas.width, H = $waveformCanvas.height;
  waveCtx.clearRect(0, 0, W, H);
  const bw = W / BARS;
  const isAgent = agentSpeaking;
  const color = isAgent ? '#f06c00' : '#00a855';

  waveData.forEach((v, i) => {
    const barH = Math.max(4, v * H * 0.85);
    const x = i * bw + bw * 0.15;
    const y = (H - barH) / 2;
    const grd = waveCtx.createLinearGradient(0, y, 0, y + barH);
    grd.addColorStop(0, color + 'ff');
    grd.addColorStop(1, color + '44');
    waveCtx.fillStyle = grd;
    waveCtx.beginPath();
    waveCtx.roundRect(x, y, bw * 0.7, barH, 3);
    waveCtx.fill();
    // Decay
    waveData[i] *= 0.88;
  });

  requestAnimationFrame(drawWaveform);
}
drawWaveform();

function feedWave(rmsData) {
  // rmsData: Float32Array of RMS values for each bar
  if (!rmsData) {
    // random idle animation
    if (agentSpeaking || userSpeaking) {
      for (let i = 0; i < BARS; i++) {
        waveData[i] = Math.max(waveData[i], 0.1 + Math.random() * 0.5);
      }
    }
    return;
  }
  for (let i = 0; i < BARS; i++) {
    waveData[i] = Math.max(waveData[i], rmsData[i % rmsData.length] || 0);
  }
}

// Idle wave animation
setInterval(() => {
  if (agentSpeaking || userSpeaking) feedWave(null);
}, 60);

// ── Status UI ─────────────────────────────────────────────────────────────────
function setStatus(state, label) {
  $statusBadge.className = `status-badge ${state}`;
  $statusLabel.textContent = label;
}

// ── WebSocket ──────────────────────────────────────────────────────────────────
function connectWS() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;

  setStatus('connecting', 'Connecting…');
  ws = new WebSocket(getWsUrl());

  ws.addEventListener('open', () => {
    setStatus('connected', 'Ready');
    wsBackoff = 500;
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  });

  ws.addEventListener('message', e => handleServerMessage(JSON.parse(e.data)));

  ws.addEventListener('close', () => {
    setStatus('', 'Disconnected');
    stopRecording();
    reconnectTimer = setTimeout(connectWS, wsBackoff);
    wsBackoff = Math.min(wsBackoff * 2, MAX_BACKOFF);
  });

  ws.addEventListener('error', () => {
    setStatus('error', 'Connection error');
  });
}

function sendWS(data) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(data));
  }
}

// ── Server message handler ────────────────────────────────────────────────────
function handleServerMessage(msg) {
  switch (msg.type) {
    case 'status':
      if (msg.state === 'connected') setStatus('connected', 'Connected');
      break;

    case 'session_created':
      setStatus('connected', 'Ready');
      break;

    case 'audio_chunk':
      enqueueAudio(msg.audio);
      break;

    case 'agent_start':
      agentSpeaking = true;
      $agentAvatar.classList.add('speaking');
      $agentAvatar.classList.remove('listening');
      $waveformWrap.classList.add('visible');
      $agentTagline.textContent = 'Speaking…';
      setStatus('active', 'Agent speaking');
      // Add typing indicator while first audio comes in
      showTypingIndicator();
      break;

    case 'agent_stop':
      agentSpeaking = false;
      $agentAvatar.classList.remove('speaking');
      $agentTagline.textContent = 'Your Sainsbury\'s assistant';
      setStatus('connected', 'Ready');
      removeTypingIndicator();
      if (!userSpeaking) $waveformWrap.classList.remove('visible');
      break;

    case 'user_start':
      userSpeaking = true;
      $agentAvatar.classList.add('listening');
      $agentAvatar.classList.remove('speaking');
      $waveformWrap.classList.add('visible');
      $agentTagline.textContent = 'Listening…';
      setStatus('active', 'Listening');
      break;

    case 'user_stop':
      userSpeaking = false;
      if (!agentSpeaking) {
        $agentAvatar.classList.remove('listening');
        $agentTagline.textContent = 'Your Sainsbury\'s assistant';
        setStatus('connected', 'Ready');
        $waveformWrap.classList.remove('visible');
      }
      break;

    case 'transcript':
      removeTypingIndicator();
      appendTranscriptTurn(msg.role, msg.text);
      break;

    case 'transcript_delta':
      handleTranscriptDelta(msg.role, msg.text);
      break;

    case 'function_call':
      if (msg.status === 'running') {
        showFunctionCallIndicator(msg.name);
      } else {
        hideFunctionCallIndicator();
      }
      break;

    case 'error':
      showToast(msg.message || 'An error occurred', 'error');
      setStatus('error', 'Error');
      break;

    case 'pong':
      break;

    default:
      break;
  }
}

// ── Audio playback ────────────────────────────────────────────────────────────
function ensureAudioCtx() {
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: SAMPLE_RATE });
  }
  if (audioCtx.state === 'suspended') audioCtx.resume();
}

function enqueueAudio(base64) {
  ensureAudioCtx();
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

  // PCM16 → Float32
  const samples = new Float32Array(bytes.length / 2);
  const view = new DataView(bytes.buffer);
  for (let i = 0; i < samples.length; i++) {
    samples[i] = view.getInt16(i * 2, true) / 32768.0;
  }

  const buffer = audioCtx.createBuffer(1, samples.length, SAMPLE_RATE);
  buffer.copyToChannel(samples, 0);

  const source = audioCtx.createBufferSource();
  source.buffer = buffer;
  source.connect(audioCtx.destination);

  const now = audioCtx.currentTime;
  if (playbackTime < now) playbackTime = now + 0.05;
  source.start(playbackTime);
  playbackTime += buffer.duration;

  // Feed waveform with amplitude envelope
  const chunkSize = Math.ceil(samples.length / BARS);
  for (let i = 0; i < BARS; i++) {
    let sum = 0;
    for (let j = 0; j < chunkSize; j++) {
      const idx = i * chunkSize + j;
      if (idx < samples.length) sum += Math.abs(samples[idx]);
    }
    waveData[i] = Math.max(waveData[i], (sum / chunkSize) * 3.0);
  }
}

// ── Microphone capture ────────────────────────────────────────────────────────
async function startRecording() {
  if (recording) return;
  try {
    ensureAudioCtx();
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { sampleRate: SAMPLE_RATE, channelCount: 1, echoCancellation: true, noiseSuppression: true }
    });

    const source = audioCtx.createMediaStreamSource(micStream);
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);

    scriptProcessor = audioCtx.createScriptProcessor(4096, 1, 1);
    source.connect(scriptProcessor);
    scriptProcessor.connect(audioCtx.destination);

    scriptProcessor.onaudioprocess = (e) => {
      if (!recording || !ws || ws.readyState !== WebSocket.OPEN) return;

      const input = e.inputBuffer.getChannelData(0);

      // Feed waveform from mic input
      const chunkSize = Math.ceil(input.length / BARS);
      for (let i = 0; i < BARS; i++) {
        let sum = 0;
        for (let j = 0; j < chunkSize; j++) {
          const idx = i * chunkSize + j;
          if (idx < input.length) sum += Math.abs(input[idx]);
        }
        waveData[i] = Math.max(waveData[i], (sum / chunkSize) * 4.0);
      }

      // Convert Float32 → PCM16 → base64
      const pcm16 = new Int16Array(input.length);
      for (let i = 0; i < input.length; i++) {
        pcm16[i] = Math.max(-32768, Math.min(32767, input[i] * 32768));
      }
      const b64 = arrayBufferToBase64(pcm16.buffer);
      sendWS({ type: 'audio_chunk', audio: b64 });
    };

    recording = true;
    updateMicUI(true);
    connectWS();
    showToast('Microphone active — start speaking!', 'success');

  } catch (err) {
    console.error('Microphone error:', err);
    showToast('Could not access microphone. Check browser permissions.', 'error');
  }
}

function stopRecording() {
  if (!recording) return;
  recording = false;

  if (scriptProcessor) { scriptProcessor.disconnect(); scriptProcessor = null; }
  if (analyser)         { analyser.disconnect(); analyser = null; }
  if (micStream)        { micStream.getTracks().forEach(t => t.stop()); micStream = null; }

  updateMicUI(false);
  $waveformWrap.classList.remove('visible');
  $agentTagline.textContent = 'Your Sainsbury\'s assistant';
  $agentAvatar.classList.remove('speaking', 'listening');
}

function updateMicUI(active) {
  $micBtn.classList.toggle('recording', active);
  $micBtn.setAttribute('aria-pressed', active);
  $micBtn.setAttribute('aria-label', active ? 'Stop voice conversation' : 'Start voice conversation');
  $micHint.textContent = active ? 'Click to stop' : 'Click to start talking';
  document.querySelector('.mic-icon svg path:first-child').setAttribute('fill', active ? '#fff' : 'currentColor');
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  bytes.forEach(b => binary += String.fromCharCode(b));
  return btoa(binary);
}

// ── Transcript rendering ───────────────────────────────────────────────────────
let $currentAssistantBubble = null;

function appendTranscriptTurn(role, text) {
  if (!text || !text.trim()) return;
  $transcriptEmpty.style.display = 'none';

  // If we were streaming assistant deltas, finalise that bubble
  if (role === 'assistant' && $currentAssistantBubble) {
    $currentAssistantBubble.textContent = text;
    $currentAssistantBubble = null;
    assistantBuffer = '';
    return;
  }

  const turn = document.createElement('div');
  turn.className = `turn ${role}`;
  const bubble = document.createElement('div');
  bubble.className = 'turn-bubble';
  bubble.textContent = text;
  turn.appendChild(bubble);
  $transcriptList.appendChild(turn);
  $transcriptList.scrollTop = $transcriptList.scrollHeight;
}

function handleTranscriptDelta(role, delta) {
  if (role !== 'assistant') return;
  $transcriptEmpty.style.display = 'none';
  removeTypingIndicator();

  if (!$currentAssistantBubble) {
    const turn = document.createElement('div');
    turn.className = 'turn assistant';
    const bubble = document.createElement('div');
    bubble.className = 'turn-bubble';
    turn.appendChild(bubble);
    $transcriptList.appendChild(turn);
    $currentAssistantBubble = bubble;
    assistantBuffer = '';
  }

  assistantBuffer += delta;
  $currentAssistantBubble.textContent = assistantBuffer;
  $transcriptList.scrollTop = $transcriptList.scrollHeight;
}

// ── Typing indicator ──────────────────────────────────────────────────────────
let $typingEl = null;
function showTypingIndicator() {
  if ($typingEl) return;
  $transcriptEmpty.style.display = 'none';
  $typingEl = document.createElement('div');
  $typingEl.className = 'turn assistant';
  $typingEl.id = 'typing-indicator';
  $typingEl.innerHTML = `
    <div class="turn-bubble typing-indicator">
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
    </div>`;
  $transcriptList.appendChild($typingEl);
  $transcriptList.scrollTop = $transcriptList.scrollHeight;
}

function removeTypingIndicator() {
  if ($typingEl) { $typingEl.remove(); $typingEl = null; }
}

// ── Function call indicator ───────────────────────────────────────────────────
let $fnIndicator = null;
function showFunctionCallIndicator(name) {
  removeTypingIndicator();
  if ($fnIndicator) return;
  const friendlyName = name.replace(/[-_]/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
  $fnIndicator = document.createElement('div');
  $fnIndicator.className = 'turn assistant';
  $fnIndicator.innerHTML = `
    <div class="turn-bubble typing-indicator" style="font-size:11px;color:var(--text-muted);">
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
      <span style="margin-left:6px">Checking ${friendlyName}…</span>
    </div>`;
  $transcriptList.appendChild($fnIndicator);
  $transcriptList.scrollTop = $transcriptList.scrollHeight;
}

function hideFunctionCallIndicator() {
  if ($fnIndicator) { $fnIndicator.remove(); $fnIndicator = null; }
}

// ── Toast notifications ───────────────────────────────────────────────────────
function showToast(message, type = 'info', duration = 4000) {
  const icons = { success: '✓', error: '✕', info: 'ℹ' };
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${icons[type] || 'ℹ'}</span><span>${message}</span>`;
  $toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('hiding');
    toast.addEventListener('animationend', () => toast.remove(), { once: true });
  }, duration);
}

// ── Offers sidebar ────────────────────────────────────────────────────────────
async function loadOffers() {
  try {
    const res = await fetch('/api/v1/offers');
    const data = await res.json();
    $offersList.innerHTML = '';

    if (!data.offers || data.offers.length === 0) {
      $offersList.innerHTML = '<p style="padding:12px;color:var(--text-muted);font-size:13px">No active offers at the moment.</p>';
      return;
    }

    data.offers.slice(0, 6).forEach(offer => {
      const item = document.createElement('div');
      item.className = 'offer-item';

      let badgeClass = 'discount', badgeText = offer.discount_pct ? `${offer.discount_pct}% off` : 'Deal';
      if (offer.is_nectar_deal) { badgeClass = 'nectar'; badgeText = '⭐ Nectar'; }
      if (offer.offer_type === 'multibuy') { badgeClass = 'multibuy'; badgeText = 'Multibuy'; }

      const until = offer.valid_until ? `Until ${offer.valid_until}` : '';

      item.innerHTML = `
        <div class="offer-title">${escapeHtml(offer.title)}</div>
        <div class="offer-meta">
          <span class="offer-badge ${badgeClass}">${badgeText}</span>
          <span class="offer-category">${escapeHtml(offer.category || '')}</span>
          <span class="offer-until">${until}</span>
        </div>`;
      $offersList.appendChild(item);
    });
  } catch (err) {
    $offersList.innerHTML = '<p style="padding:12px;color:var(--text-muted);font-size:13px">Couldn\'t load offers.</p>';
  }
}

// ── Store hours sidebar ───────────────────────────────────────────────────────
async function loadStoreHours() {
  try {
    const res = await fetch('/api/v1/stores');
    const data = await res.json();
    if (!data.stores || data.stores.length === 0) return;

    const store = data.stores[0];
    document.getElementById('store-name-label').textContent = store.name.replace("Sainsbury's ", '');

    const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
    const today = new Date().toLocaleDateString('en-GB', { weekday: 'long' }).toLowerCase();

    const colMap = {
      monday: store.monday_hours, tuesday: store.tuesday_hours,
      wednesday: store.wednesday_hours, thursday: store.thursday_hours,
      friday: store.friday_hours, saturday: store.saturday_hours,
      sunday: store.sunday_hours,
    };

    // Fetch full store with all hours
    const res2 = await fetch(`/api/v1/stores`);
    const allStores = await res2.json();

    $hoursGrid.innerHTML = days.map(d => {
      const isToday = d === today;
      return `
        <div class="hours-row">
          <span class="hours-day ${isToday ? 'today' : ''}">${capitalize(d)}</span>
          <span class="hours-time ${isToday ? 'today' : ''}">${colMap[d] || '—'}</span>
        </div>`;
    }).join('');

    // Is the store open now?
    const hours = colMap[today];
    if (hours) {
      const [open, close] = hours.split('-').map(t => {
        const [h, m] = t.trim().split(':').map(Number);
        return h * 60 + m;
      });
      const now = new Date();
      const nowMins = now.getHours() * 60 + now.getMinutes();
      const isOpen = nowMins >= open && nowMins < close;
      $openBadge.className = `open-badge ${isOpen ? 'open' : 'closed'}`;
      $openBadge.textContent = isOpen ? `Open now · Closes ${colMap[today].split('-')[1]}` : `Closed · Opens ${colMap[today].split('-')[0]}`;
    }
  } catch (err) {
    $hoursGrid.innerHTML = '<p style="padding:12px;color:var(--text-muted);font-size:13px">Couldn\'t load hours.</p>';
  }
}

// ── Quick chips ───────────────────────────────────────────────────────────────
$chips.forEach(chip => {
  chip.addEventListener('click', () => {
    const query = chip.dataset.query;
    if (!query) return;
    // Show as user message in transcript
    appendTranscriptTurn('user', query);
    showToast('Tip: Click the mic to speak your question!', 'info', 3000);
  });
});

// ── Mic button ────────────────────────────────────────────────────────────────
$micBtn.addEventListener('click', async () => {
  if (!recording) {
    await startRecording();
    connectWS();
  } else {
    stopRecording();
    sendWS({ type: 'interrupt' });
  }
});

// ── Clear button ──────────────────────────────────────────────────────────────
$clearBtn.addEventListener('click', () => {
  $transcriptList.innerHTML = '';
  $transcriptList.appendChild($transcriptEmpty);
  $transcriptEmpty.style.display = 'flex';
  $currentAssistantBubble = null;
  assistantBuffer = '';
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ── Ping to keep WS alive ─────────────────────────────────────────────────────
setInterval(() => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    sendWS({ type: 'ping', ts: Date.now() });
  }
}, 15000);

// ── Auth nav state ────────────────────────────────────────────────────────────
function initAuthNav() {
  const loggedIn = typeof isLoggedIn === 'function' && isLoggedIn();
  const navLogin    = document.getElementById('nav-login');
  const navDashboard= document.getElementById('nav-dashboard');
  const navLogout   = document.getElementById('nav-logout');
  if (!navLogin) return;
  navLogin.style.display    = loggedIn ? 'none' : 'inline-flex';
  navDashboard.style.display= loggedIn ? 'inline-flex' : 'none';
  navLogout.style.display   = loggedIn ? 'inline-flex' : 'none';
}

function authLogout() {
  if (typeof logout === 'function') logout();
  else { localStorage.clear(); location.href = '/login'; }
}

// ── Init ──────────────────────────────────────────────────────────────────────
(async function init() {
  setStatus('', 'Disconnected');
  initAuthNav();
  await Promise.all([loadOffers(), loadStoreHours()]);
  connectWS();
})();
