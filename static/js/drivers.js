/* ═══════════════════════════════════════════════════════════════════════════════
   HAMMERTIME — drivers.js
   Driver grid rendering, search/filter, detail panel with stats & H2H chart
   ═══════════════════════════════════════════════════════════════════════════════ */

'use strict';

let allDrivers = [];
let h2hChart = null;

/* ─── Init ───────────────────────────────────────────────────────────────────── */
async function initDriverGrid() {
  await loadDriverGrid();
  setupDriverSearch();
  setupDetailPanel();
}

/* ─── Load Driver Grid ───────────────────────────────────────────────────────── */
async function loadDriverGrid() {
  const grid = document.getElementById('driver-grid');
  if (!grid) return;

  try {
    allDrivers = await api.get('/api/drivers');
    renderDriverCards(allDrivers);
  } catch {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1;">
        <div class="empty-state-icon">🏁</div>
        <p class="empty-state-text">Unable to load driver data. Check if the API is running.</p>
      </div>`;
  }
}

/* ─── Render Driver Cards ────────────────────────────────────────────────────── */
function renderDriverCards(drivers) {
  const grid = document.getElementById('driver-grid');
  if (!grid) return;

  grid.innerHTML = drivers.map((d, i) => {
    const color = utils.getTeamColor(d.team);
    const flag = utils.getFlag(d.nationality);
    const pts = d.stats?.points ?? '—';
    const headshot = d.headshot_url
      ? `<img class="driver-headshot" src="${utils.escapeHtml(d.headshot_url)}" alt="${utils.escapeHtml(d.name)}" onerror="this.replaceWith(createInitialsAvatar('${utils.escapeHtml(d.name)}','${color}'))">`
      : `<div class="driver-initials" style="background:${color}">${getInitials(d.name)}</div>`;

    return `
      <div class="driver-card" data-code="${d.code}" style="--team-color:${color}; animation-delay:${i * 0.04}s">
        <div class="driver-card-header">
          ${headshot}
          <div class="driver-info">
            <div class="driver-name">${utils.escapeHtml(d.name)}</div>
            <div class="driver-team">
              <span class="team-color-dot" style="background:${color}"></span>
              ${utils.escapeHtml(d.team)}
            </div>
          </div>
        </div>
        <div class="driver-card-footer">
          <span class="driver-number">${d.number || ''}</span>
          <span class="driver-flag">${flag}</span>
          <span class="driver-points">${pts} pts</span>
        </div>
      </div>`;
  }).join('');

  // Click handler via event delegation
  grid.addEventListener('click', (e) => {
    const card = e.target.closest('.driver-card');
    if (card) openDriverDetail(card.dataset.code);
  });
}

/* ─── Helper: Get initials ───────────────────────────────────────────────────── */
function getInitials(name) {
  return name.split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase();
}

/* ─── Helper: Create initials avatar (for onerror) ───────────────────────────── */
function createInitialsAvatar(name, color) {
  const div = document.createElement('div');
  div.className = 'driver-initials';
  div.style.background = color;
  div.textContent = getInitials(name);
  return div;
}
// Make available globally for inline onerror
window.createInitialsAvatar = createInitialsAvatar;

/* ─── Search / Filter ────────────────────────────────────────────────────────── */
function setupDriverSearch() {
  const input = document.getElementById('driver-search');
  if (!input) return;

  input.addEventListener('input', utils.debounce(() => {
    const query = input.value.toLowerCase().trim();
    if (!query) {
      renderDriverCards(allDrivers);
      return;
    }
    const filtered = allDrivers.filter(d =>
      d.name.toLowerCase().includes(query) ||
      d.team.toLowerCase().includes(query) ||
      d.code.toLowerCase().includes(query)
    );
    renderDriverCards(filtered);
  }, 200));
}

/* ─── Detail Panel ───────────────────────────────────────────────────────────── */
function setupDetailPanel() {
  const overlay = document.getElementById('driver-detail-overlay');
  const closeBtn = document.getElementById('detail-close');

  if (closeBtn) {
    closeBtn.addEventListener('click', closeDriverDetail);
  }

  if (overlay) {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeDriverDetail();
    });
  }

  // ESC key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeDriverDetail();
  });

  // Simulate button in detail panel
  const simBtn = document.getElementById('detail-simulate-btn');
  if (simBtn) {
    simBtn.addEventListener('click', () => {
      closeDriverDetail();
      const simSection = document.getElementById('simulator');
      if (simSection) simSection.scrollIntoView({ behavior: 'smooth' });
    });
  }
}

function closeDriverDetail() {
  const overlay = document.getElementById('driver-detail-overlay');
  if (overlay) overlay.classList.remove('open');
  document.body.style.overflow = '';
}

/* ─── Open Driver Detail ─────────────────────────────────────────────────────── */
async function openDriverDetail(code) {
  const overlay = document.getElementById('driver-detail-overlay');
  if (!overlay) return;

  overlay.classList.add('open');
  document.body.style.overflow = 'hidden';

  // Clear previous data
  const hero = document.getElementById('detail-hero');
  const statsGrid = document.getElementById('detail-stats-grid');
  const resultsList = document.getElementById('detail-results-list');

  if (hero) hero.innerHTML = '<div class="skeleton skeleton-text medium"></div>';
  if (statsGrid) statsGrid.innerHTML = '<div class="skeleton skeleton-card"></div>'.repeat(4);
  if (resultsList) resultsList.innerHTML = '<div class="skeleton skeleton-text"></div>'.repeat(5);

  try {
    const d = await api.get(`/api/drivers/${code}`);
    renderDetailPanel(d);
  } catch {
    if (hero) hero.innerHTML = '<p style="color:var(--text-muted)">Failed to load driver data.</p>';
  }
}

/* ─── Render Detail Panel ────────────────────────────────────────────────────── */
function renderDetailPanel(d) {
  const color = utils.getTeamColor(d.team);
  const flag = utils.getFlag(d.nationality);

  // Hero
  const hero = document.getElementById('detail-hero');
  if (hero) {
    const imgHtml = d.headshot_url
      ? `<img src="${utils.escapeHtml(d.headshot_url)}" alt="${utils.escapeHtml(d.name)}" onerror="this.style.display='none'">`
      : '';
    hero.innerHTML = `
      ${imgHtml}
      <div class="detail-hero-info">
        <h2>${flag} ${utils.escapeHtml(d.name)}</h2>
        <p class="detail-team" style="color:${color}">#${d.number} · ${utils.escapeHtml(d.team)}</p>
      </div>`;
  }

  // Stats
  const statsGrid = document.getElementById('detail-stats-grid');
  const s = d.stats || d.season_stats || {};
  if (statsGrid) {
    statsGrid.innerHTML = `
      <div class="detail-stat">
        <div class="detail-stat-value">${s.wins ?? '—'}</div>
        <div class="detail-stat-label">Wins</div>
      </div>
      <div class="detail-stat">
        <div class="detail-stat-value">${s.podiums ?? '—'}</div>
        <div class="detail-stat-label">Podiums</div>
      </div>
      <div class="detail-stat">
        <div class="detail-stat-value">${s.dnfs ?? '—'}</div>
        <div class="detail-stat-label">DNFs</div>
      </div>
      <div class="detail-stat">
        <div class="detail-stat-value">${s.avg_position != null ? Number(s.avg_position).toFixed(1) : '—'}</div>
        <div class="detail-stat-label">Avg Position</div>
      </div>`;
  }

  // Recent Results
  const resultsList = document.getElementById('detail-results-list');
  if (resultsList && d.recent_results) {
    resultsList.innerHTML = d.recent_results.slice(0, 5).map(r => {
      const posClass = r.position <= 3 ? ` p${r.position}` : '';
      return `
        <div class="detail-result-row">
          <span class="position-badge${posClass}">P${r.position}</span>
          <span>${utils.escapeHtml(r.race)}</span>
          <span>Grid ${r.grid}</span>
          <span>${r.points} pts</span>
        </div>`;
    }).join('');
  } else if (resultsList) {
    resultsList.innerHTML = '<p style="color:var(--text-muted);font-size:0.85rem;">No recent results available.</p>';
  }

  // H2H Chart
  renderH2HChart(d);
}

/* ─── H2H Chart ──────────────────────────────────────────────────────────────── */
function renderH2HChart(d) {
  const canvas = document.getElementById('detail-h2h-chart');
  if (!canvas || typeof Chart === 'undefined') return;

  if (h2hChart) {
    h2hChart.destroy();
    h2hChart = null;
  }

  const h2h = d.h2h;
  if (!h2h || !h2h.driver || !h2h.teammate) {
    const wrap = document.getElementById('detail-h2h-wrap');
    if (wrap) wrap.innerHTML = '<p style="color:var(--text-muted);font-size:0.85rem;text-align:center;padding:1rem;">H2H data not available.</p>';
    return;
  }

  // Restore canvas if replaced
  const wrap = document.getElementById('detail-h2h-wrap');
  if (!wrap.querySelector('canvas')) {
    wrap.innerHTML = '<canvas id="detail-h2h-chart"></canvas>';
  }
  const ctx = document.getElementById('detail-h2h-chart').getContext('2d');

  const color = utils.getTeamColor(d.team);
  const driverWins = h2h.wins_ahead || 0;
  const teammateWins = (h2h.total_races || (driverWins + (h2h.teammate_wins_ahead || 0))) - driverWins;

  h2hChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: [h2h.driver, h2h.teammate],
      datasets: [{
        data: [driverWins, teammateWins >= 0 ? teammateWins : 0],
        backgroundColor: [color, `${color}66`],
        borderColor: [color, color],
        borderWidth: 1,
        borderRadius: 6,
        barThickness: 28,
      }]
    },
    options: {
      indexAxis: 'y',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.raw} qualifying wins`
          }
        }
      },
      scales: {
        x: { grid: { display: false }, ticks: { stepSize: 1 } },
        y: { grid: { display: false } }
      }
    }
  });
}

/* ─── Standings ──────────────────────────────────────────────────────────────── */
let driverStandings = [];
let constructorStandings = [];

async function initStandings() {
  setupStandingsTabs();
  await loadDriverStandings();
}

function setupStandingsTabs() {
  const tabContainer = document.getElementById('standings-tabs');
  if (!tabContainer) return;

  tabContainer.addEventListener('click', async (e) => {
    const tab = e.target.closest('.standings-tab');
    if (!tab) return;

    tabContainer.querySelectorAll('.standings-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');

    const tabId = tab.dataset.tab;
    document.getElementById('standings-drivers-wrap').style.display = tabId === 'drivers' ? '' : 'none';
    document.getElementById('standings-constructors-wrap').style.display = tabId === 'constructors' ? '' : 'none';

    if (tabId === 'constructors' && constructorStandings.length === 0) {
      await loadConstructorStandings();
    }
  });

  // Sortable columns
  document.querySelectorAll('.standings-table thead th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const table = th.closest('.standings-table');
      const key = th.dataset.sort;
      const tableId = table.id;

      if (tableId.includes('drivers')) {
        sortAndRenderStandings(driverStandings, key, 'standings-drivers-body', 'driver');
      } else {
        sortAndRenderStandings(constructorStandings, key, 'standings-constructors-body', 'constructor');
      }
    });
  });
}

let standingsSortDir = {};

function sortAndRenderStandings(data, key, bodyId, type) {
  const dir = standingsSortDir[key] === 'asc' ? 'desc' : 'asc';
  standingsSortDir[key] = dir;

  const sorted = [...data].sort((a, b) => {
    let valA = a[key], valB = b[key];
    if (typeof valA === 'string') {
      return dir === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
    }
    return dir === 'asc' ? valA - valB : valB - valA;
  });

  if (type === 'driver') {
    renderDriverStandings(sorted, bodyId);
  } else {
    renderConstructorStandings(sorted, bodyId);
  }
}

async function loadDriverStandings() {
  try {
    const resp = await api.get('/api/standings/drivers');
    driverStandings = resp.standings || resp || [];
    renderDriverStandings(driverStandings, 'standings-drivers-body');
  } catch {
    document.getElementById('standings-drivers-body').innerHTML =
      '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text-muted)">Unable to load standings.</td></tr>';
  }
}

function renderDriverStandings(data, bodyId) {
  const body = document.getElementById(bodyId);
  if (!body || !Array.isArray(data) || data.length === 0) {
    if (body) body.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text-muted)">No standings data available yet.</td></tr>';
    return;
  }

  body.innerHTML = data.map((d, i) => {
    const driverName = d.driver_name || `${d.given_name || ''} ${d.family_name || ''}`.trim() || d.code || d.driver_id || `P${i+1}`;
    const team = d.team || '';
    const color = utils.getTeamColor(team);
    const pos = d.position || i + 1;
    const posClass = pos <= 3 ? ' top3' : '';
    return `
      <tr style="--team-color:${color}">
        <td class="standings-pos${posClass}">${pos}</td>
        <td class="standings-driver">${utils.escapeHtml(driverName)}</td>
        <td class="standings-team" style="color:${color}">${utils.escapeHtml(team)}</td>
        <td class="standings-points">${d.points || 0}</td>
        <td class="standings-wins">${d.wins || 0}</td>
        <td>${d.podiums || 0}</td>
        <td>${d.dnfs || 0}</td>
      </tr>`;
  }).join('');
}

async function loadConstructorStandings() {
  try {
    const resp = await api.get('/api/standings/constructors');
    constructorStandings = resp.standings || resp || [];
    renderConstructorStandings(constructorStandings, 'standings-constructors-body');
  } catch {
    document.getElementById('standings-constructors-body').innerHTML =
      '<tr><td colspan="4" style="text-align:center;padding:2rem;color:var(--text-muted)">Unable to load standings.</td></tr>';
  }
}

function renderConstructorStandings(data, bodyId) {
  const body = document.getElementById(bodyId);
  if (!body) return;

  body.innerHTML = data.map(d => {
    const color = d.color || utils.getTeamColor(d.name);
    return `
      <tr style="--team-color:${color}">
        <td class="standings-pos${d.position <= 3 ? ' top3' : ''}">${d.position}</td>
        <td class="standings-team" style="color:${color}">${utils.escapeHtml(d.name)}</td>
        <td class="standings-points">${d.points}</td>
        <td class="standings-wins">${d.wins || 0}</td>
      </tr>`;
  }).join('');
}
