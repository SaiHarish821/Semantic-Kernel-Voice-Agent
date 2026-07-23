/**
 * app/static/dashboard.js — User dashboard logic.
 *
 * - Authenticates user on page load
 * - Loads conversation history
 * - Allows selecting a session to view its messages
 * - Supports rename and delete
 */

'use strict';

if (!requireAuth('/login')) throw new Error('Not authenticated');

const $convList    = document.getElementById('conv-list');
const $searchInput = document.getElementById('search-input');
const $chatEmpty   = document.getElementById('chat-empty');
const $chatMessages= document.getElementById('chat-messages');
const $chatTitle   = document.getElementById('chat-title');
const $renameModal = document.getElementById('rename-modal');
const $renameInput = document.getElementById('rename-input');

let allSessions = [];
let activeSessionId = null;
let searchTimer = null;

// ── Background canvas ─────────────────────────────────────────────────────────
(function() {
  const c = document.getElementById('bg-canvas');
  if (!c) return;
  const ctx = c.getContext('2d');
  const orbs = Array.from({length:4},(_,i)=>({x:Math.random(),y:Math.random(),r:200+Math.random()*300,vx:(Math.random()-.5)*.0002,vy:(Math.random()-.5)*.0002,hue:i%2===0?24:145,alpha:.04+Math.random()*.04}));
  function resize(){c.width=window.innerWidth;c.height=window.innerHeight;}
  function draw(){const W=c.width,H=c.height;ctx.clearRect(0,0,W,H);orbs.forEach(o=>{o.x=(o.x+o.vx+1)%1;o.y=(o.y+o.vy+1)%1;const g=ctx.createRadialGradient(o.x*W,o.y*H,0,o.x*W,o.y*H,o.r);g.addColorStop(0,`hsla(${o.hue},90%,55%,${o.alpha})`);g.addColorStop(1,'transparent');ctx.fillStyle=g;ctx.fillRect(0,0,W,H);});requestAnimationFrame(draw);}
  window.addEventListener('resize',resize);resize();draw();
})();

// ── Init ──────────────────────────────────────────────────────────────────────
(async function init() {
  // Set user info in header
  const user = getStoredUser();
  if (user) {
    document.getElementById('user-name-display').textContent = user.name;
    document.getElementById('user-avatar-initial').textContent = user.name.charAt(0).toUpperCase();
  }

  await loadConversations();
})();

// ── Load conversations ────────────────────────────────────────────────────────
async function loadConversations(search = '') {
  try {
    const url = `/api/v1/conversations?limit=50${search ? `&search=${encodeURIComponent(search)}` : ''}`;
    const res = await authFetch(url);
    const data = await res.json();
    allSessions = data.sessions || [];
    renderConversationList(allSessions);
  } catch (err) {
    $convList.innerHTML = `<p style="color:var(--error);font-size:13px;padding:var(--space-md)">Failed to load conversations.</p>`;
  }
}

function renderConversationList(sessions) {
  if (sessions.length === 0) {
    $convList.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">🎙️</div>
        <p>No conversations yet. <a href="/" style="color:var(--orange-light)">Start talking to Sam!</a></p>
      </div>`;
    return;
  }

  $convList.innerHTML = sessions.map(s => {
    const date = new Date(s.updated_at || s.created_at);
    const ago = timeAgo(date);
    const msgs = s.message_count || 0;
    const dur = s.duration_seconds ? formatDuration(s.duration_seconds) : '';
    const isActive = s.id === activeSessionId;
    return `
      <div class="conv-item ${isActive ? 'conv-item-active' : ''}" data-id="${s.id}" role="button" tabindex="0" aria-label="Conversation: ${escHtml(s.title)}" onclick="selectSession(${s.id})" onkeydown="if(event.key==='Enter')selectSession(${s.id})">
        <div class="conv-icon">💬</div>
        <div class="conv-info">
          <div class="conv-title" id="conv-title-${s.id}">${escHtml(s.title)}</div>
          <div class="conv-meta">${ago} · ${msgs} message${msgs !== 1 ? 's' : ''}${dur ? ' · ' + dur : ''}</div>
        </div>
        <div class="conv-actions">
          <button class="icon-btn" title="Rename" onclick="event.stopPropagation();openRename(${s.id},'${escHtml(s.title).replace(/'/g,"\\'")}')">✏️</button>
          <button class="icon-btn danger" title="Delete" onclick="event.stopPropagation();deleteSession(${s.id})">🗑️</button>
        </div>
      </div>`;
  }).join('');
}

// ── Session viewer ────────────────────────────────────────────────────────────
async function selectSession(sessionId) {
  activeSessionId = sessionId;
  // Highlight active
  document.querySelectorAll('.conv-item').forEach(el => {
    el.classList.toggle('conv-item-active', parseInt(el.dataset.id) === sessionId);
  });

  $chatEmpty.style.display = 'none';
  $chatMessages.style.display = 'flex';
  $chatMessages.innerHTML = '<div class="skeleton" style="height:40px;margin:8px"></div><div class="skeleton" style="height:60px;margin:8px"></div>';

  try {
    const res = await authFetch(`/api/v1/conversations/${sessionId}`);
    const data = await res.json();
    const sess = allSessions.find(s => s.id === sessionId);
    $chatTitle.textContent = sess ? sess.title : 'Conversation';

    if (!data.messages || data.messages.length === 0) {
      $chatMessages.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🎙️</div><p>This session has no messages yet.</p></div>';
      return;
    }

    $chatMessages.innerHTML = data.messages.map(m => `
      <div class="turn ${m.role}" style="display:flex;gap:8px;animation:turn-slide-in 0.25s ease-out${m.role === 'user' ? ';flex-direction:row-reverse' : ''}">
        <div class="turn-bubble">
          <div style="font-size:11px;color:var(--text-muted);margin-bottom:3px">${m.role === 'user' ? '🎤 You' : '🤖 Sam'} · ${formatTime(m.timestamp)}</div>
          ${escHtml(m.content)}
        </div>
      </div>`).join('');
    $chatMessages.scrollTop = $chatMessages.scrollHeight;
  } catch (err) {
    $chatMessages.innerHTML = `<p style="color:var(--error);font-size:13px;padding:var(--space-md)">Failed to load messages.</p>`;
  }
}

// ── Rename ────────────────────────────────────────────────────────────────────
let renamingId = null;

function openRename(sessionId, currentTitle) {
  renamingId = sessionId;
  $renameInput.value = currentTitle;
  $renameModal.style.display = 'flex';
  setTimeout(() => $renameInput.focus(), 50);
}

document.getElementById('rename-confirm').addEventListener('click', async () => {
  const newTitle = $renameInput.value.trim();
  if (!newTitle || !renamingId) return;
  try {
    await authFetch(`/api/v1/conversations/${renamingId}`, {
      method: 'PATCH',
      body: JSON.stringify({ title: newTitle }),
    });
    // Update in-place
    const el = document.getElementById(`conv-title-${renamingId}`);
    if (el) el.textContent = newTitle;
    const s = allSessions.find(x => x.id === renamingId);
    if (s) s.title = newTitle;
    if (activeSessionId === renamingId) $chatTitle.textContent = newTitle;
  } catch {}
  closeRename();
});

document.getElementById('rename-cancel').addEventListener('click', closeRename);
$renameModal.addEventListener('click', e => { if (e.target === $renameModal) closeRename(); });

function closeRename() {
  $renameModal.style.display = 'none';
  renamingId = null;
}

// ── Delete ────────────────────────────────────────────────────────────────────
async function deleteSession(sessionId) {
  if (!confirm('Delete this conversation? This cannot be undone.')) return;
  try {
    await authFetch(`/api/v1/conversations/${sessionId}`, { method: 'DELETE' });
    allSessions = allSessions.filter(s => s.id !== sessionId);
    renderConversationList(allSessions);
    if (activeSessionId === sessionId) {
      activeSessionId = null;
      $chatMessages.style.display = 'none';
      $chatEmpty.style.display = 'flex';
      $chatTitle.textContent = 'Select a conversation';
    }
  } catch { alert('Failed to delete conversation.'); }
}

// ── Search ────────────────────────────────────────────────────────────────────
$searchInput.addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadConversations($searchInput.value.trim()), 350);
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function timeAgo(date) {
  const diff = (Date.now() - date.getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff/86400)}d ago`;
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

function formatDuration(secs) {
  if (!secs) return '';
  if (secs < 60) return `${Math.round(secs)}s`;
  return `${Math.floor(secs/60)}m ${Math.round(secs%60)}s`;
}

function formatTime(ts) {
  if (!ts) return '';
  try { return new Date(ts).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }); } catch { return ''; }
}

function escHtml(str) {
  const d = document.createElement('div'); d.textContent = str; return d.innerHTML;
}

// Add active conv-item style
const style = document.createElement('style');
style.textContent = `.conv-item-active { border-color: rgba(240,108,0,0.4) !important; background: rgba(240,108,0,0.06) !important; }`;
document.head.appendChild(style);
