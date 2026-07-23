/**
 * app/static/admin.js — Admin dashboard logic.
 *
 * - Guards page to admin-only
 * - Loads platform stats
 * - Lists all users with search, enable/disable, delete
 * - Shows user conversation history on row click
 */

'use strict';

if (!requireAuth('/login') || !requireAdmin('/')) throw new Error('Admin required');

const $statsGrid    = document.getElementById('stats-grid');
const $usersTbody   = document.getElementById('users-tbody');
const $userSearch   = document.getElementById('user-search');
const $detailPanel  = document.getElementById('user-detail-panel');
const $detailTitle  = document.getElementById('user-detail-title');
const $detailInfo   = document.getElementById('user-detail-info');
const $detailConvs  = document.getElementById('user-conv-list');

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
  const user = getStoredUser();
  if (user) {
    document.getElementById('admin-name').textContent = user.name;
    document.getElementById('admin-avatar').textContent = user.name.charAt(0).toUpperCase();
  }
  await Promise.all([loadStats(), loadUsers()]);
})();

// ── Stats ─────────────────────────────────────────────────────────────────────
async function loadStats() {
  try {
    const res = await authFetch('/api/v1/admin/stats');
    const d = await res.json();
    $statsGrid.innerHTML = [
      { icon: '👥', value: d.total_users, label: 'Total Users', sub: `${d.active_users} active` },
      { icon: '💬', value: d.total_sessions, label: 'Conversations', sub: `${d.sessions_today} today` },
      { icon: '🎙️', value: d.total_messages, label: 'Messages', sub: 'transcribed turns' },
      { icon: '⚡', value: d.avg_latency_ms ? `${Math.round(d.avg_latency_ms)}ms` : '—', label: 'Avg Latency', sub: 'per message' },
      { icon: '🔵', value: d.active_voice_sessions, label: 'Live Sessions', sub: 'right now' },
    ].map(s => `
      <div class="stat-card">
        <div class="stat-icon">${s.icon}</div>
        <div class="stat-value">${s.value}</div>
        <div class="stat-label">${s.label}</div>
        <div style="font-size:11px;color:var(--text-muted)">${s.sub}</div>
      </div>`).join('');
  } catch {
    $statsGrid.innerHTML = '<p style="color:var(--error);font-size:13px;padding:8px">Failed to load stats.</p>';
  }
}

// ── Users table ───────────────────────────────────────────────────────────────
async function loadUsers(search = '') {
  try {
    const url = `/api/v1/admin/users?limit=100${search ? `&search=${encodeURIComponent(search)}` : ''}`;
    const res = await authFetch(url);
    const data = await res.json();
    renderUsers(data.users || []);
  } catch {
    $usersTbody.innerHTML = '<tr><td colspan="7" style="color:var(--error);text-align:center;padding:16px">Failed to load users.</td></tr>';
  }
}

function renderUsers(users) {
  if (users.length === 0) {
    $usersTbody.innerHTML = '<tr><td colspan="7" style="color:var(--text-muted);text-align:center;padding:var(--space-xl)">No users found.</td></tr>';
    return;
  }
  $usersTbody.innerHTML = users.map(u => `
    <tr style="cursor:pointer" onclick="showUserDetail(${u.id})" title="View conversations">
      <td>
        <div style="display:flex;align-items:center;gap:10px">
          <div class="user-avatar" style="width:32px;height:32px;font-size:13px">${u.name.charAt(0).toUpperCase()}</div>
          <span style="font-weight:600;color:var(--text-primary)">${escHtml(u.name)}</span>
        </div>
      </td>
      <td>${escHtml(u.email)}</td>
      <td><span class="badge ${u.role === 'admin' ? 'badge-orange' : 'badge-blue'}">${u.role}</span></td>
      <td><span class="badge ${u.is_active ? 'badge-green' : 'badge-red'}">${u.is_active ? 'Active' : 'Disabled'}</span></td>
      <td>${formatDate(u.created_at)}</td>
      <td>${u.last_login ? formatDate(u.last_login) : '<span style="color:var(--text-muted)">Never</span>'}</td>
      <td onclick="event.stopPropagation()">
        <div style="display:flex;gap:6px">
          <button class="icon-btn" onclick="toggleStatus(${u.id},${u.is_active})" title="${u.is_active ? 'Disable' : 'Enable'} user">
            ${u.is_active ? '🚫' : '✅'}
          </button>
          <button class="icon-btn danger" onclick="deleteUser(${u.id},'${escHtml(u.name)}')" title="Delete user">🗑️</button>
        </div>
      </td>
    </tr>`).join('');
}

// ── User detail ───────────────────────────────────────────────────────────────
async function showUserDetail(userId) {
  $detailPanel.style.display = 'block';
  $detailTitle.textContent = 'Loading…';
  $detailInfo.innerHTML = '';
  $detailConvs.innerHTML = '<div class="skeleton" style="height:56px;margin-bottom:8px"></div><div class="skeleton" style="height:56px"></div>';
  $detailPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });

  try {
    const res = await authFetch(`/api/v1/admin/users/${userId}`);
    const data = await res.json();
    const u = data.user;

    $detailTitle.textContent = `${u.name} · Conversation History`;

    $detailInfo.innerHTML = [
      { label: 'Email', value: u.email },
      { label: 'Role', value: `<span class="badge ${u.role === 'admin' ? 'badge-orange' : 'badge-blue'}">${u.role}</span>` },
      { label: 'Status', value: `<span class="badge ${u.is_active ? 'badge-green' : 'badge-red'}">${u.is_active ? 'Active' : 'Disabled'}</span>` },
      { label: 'Joined', value: formatDate(u.created_at) },
      { label: 'Last login', value: u.last_login ? formatDate(u.last_login) : 'Never' },
    ].map(x => `
      <div>
        <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.4px;margin-bottom:4px">${x.label}</div>
        <div style="font-size:14px;color:var(--text-primary)">${x.value}</div>
      </div>`).join('');

    const convs = data.conversations || [];
    if (convs.length === 0) {
      $detailConvs.innerHTML = '<div class="empty-state" style="padding:var(--space-lg)"><div class="empty-state-icon">💬</div><p>No conversations yet.</p></div>';
    } else {
      $detailConvs.innerHTML = convs.map(c => `
        <div class="conv-item">
          <div class="conv-icon">💬</div>
          <div class="conv-info">
            <div class="conv-title">${escHtml(c.title)}</div>
            <div class="conv-meta">${formatDate(c.updated_at)} · ${c.message_count} messages · ${formatDuration(c.duration_seconds)}</div>
          </div>
          <span class="badge badge-muted">${c.token_usage ? c.token_usage + ' tok' : '—'}</span>
        </div>`).join('');
    }
  } catch {
    $detailTitle.textContent = 'Error loading user';
    $detailConvs.innerHTML = '<p style="color:var(--error);padding:8px">Failed to load user detail.</p>';
  }
}

function closeUserDetail() {
  $detailPanel.style.display = 'none';
}

// ── Actions ───────────────────────────────────────────────────────────────────
async function toggleStatus(userId, currentlyActive) {
  const action = currentlyActive ? 'disable' : 'enable';
  if (!confirm(`${action.charAt(0).toUpperCase() + action.slice(1)} this user?`)) return;
  try {
    await authFetch(`/api/v1/admin/users/${userId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ is_active: !currentlyActive }),
    });
    await loadUsers($userSearch.value.trim());
  } catch { alert('Failed to update status.'); }
}

async function deleteUser(userId, name) {
  if (!confirm(`Permanently delete "${name}" and all their data? This cannot be undone.`)) return;
  try {
    await authFetch(`/api/v1/admin/users/${userId}`, { method: 'DELETE' });
    await loadUsers($userSearch.value.trim());
    $detailPanel.style.display = 'none';
  } catch (err) {
    alert(err.message || 'Failed to delete user.');
  }
}

// ── Search ────────────────────────────────────────────────────────────────────
$userSearch.addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadUsers($userSearch.value.trim()), 350);
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function formatDate(ts) {
  if (!ts) return '—';
  try { return new Date(ts).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }); }
  catch { return ts; }
}

function formatDuration(secs) {
  if (!secs) return '—';
  if (secs < 60) return `${Math.round(secs)}s`;
  return `${Math.floor(secs/60)}m ${Math.round(secs%60)}s`;
}

function escHtml(str) {
  const d = document.createElement('div'); d.textContent = str; return d.innerHTML;
}
