/* ═══════════════════════════════════════════════════════════════════════════════
   HAMMERTIME — schedule.js
   Season schedule: next race countdown, recent winners, full calendar table
   ═══════════════════════════════════════════════════════════════════════════════ */

'use strict';

let countdownTimer = null;

/* ─── Init ───────────────────────────────────────────────────────────────────── */
async function initSchedule() {
  await Promise.allSettled([
    loadNextRace(),
    loadRecentWinners(),
    loadSeasonSchedule(),
  ]);
}

/* ═══════════════════════════════════════════════════════════════════════════════
   NEXT RACE COUNTDOWN
   ═══════════════════════════════════════════════════════════════════════════════ */
async function loadNextRace() {
  try {
    const data = await api.get('/api/calendar');
    const next = data.next_race;

    if (!next) {
      renderSeasonComplete();
      return;
    }

    renderNextRaceInfo(next);
    startCountdown(next.countdown_ms);
    setupSimulateButton(next.circuit_id);
  } catch {
    renderNextRaceError();
  }
}

/* ─── Render Next Race Info ──────────────────────────────────────────────────── */
function renderNextRaceInfo(race) {
  const nameEl    = document.getElementById('next-race-name');
  const circuitEl = document.getElementById('next-race-circuit');
  const dateEl    = document.getElementById('next-race-date');
  const roundEl   = document.getElementById('next-race-round');

  if (nameEl)    nameEl.textContent = race.race_name || '—';
  if (circuitEl) circuitEl.textContent = `${race.circuit_name} — ${race.locality}, ${race.country}`;
  if (dateEl)    dateEl.textContent = formatRaceDate(race.date);
  if (roundEl)   roundEl.textContent = `Round ${race.round}`;
}

/* ─── Season Complete State ──────────────────────────────────────────────────── */
function renderSeasonComplete() {
  const nameEl = document.getElementById('next-race-name');
  if (nameEl) nameEl.textContent = 'Season Complete';

  const circuitEl = document.getElementById('next-race-circuit');
  if (circuitEl) circuitEl.textContent = 'See you next year!';

  const dateEl = document.getElementById('next-race-date');
  if (dateEl) dateEl.textContent = '';

  const roundEl = document.getElementById('next-race-round');
  if (roundEl) roundEl.textContent = '';

  setCountdownDigits(0, 0, 0, 0);
}

/* ─── Error State ────────────────────────────────────────────────────────────── */
function renderNextRaceError() {
  const nameEl = document.getElementById('next-race-name');
  if (nameEl) nameEl.textContent = 'Unable to load';
  console.error('Failed to load race calendar.');
}

/* ─── Countdown Timer ────────────────────────────────────────────────────────── */
function startCountdown(countdownMs) {
  // Clear any existing timer
  if (countdownTimer) {
    clearInterval(countdownTimer);
    countdownTimer = null;
  }

  let remaining = countdownMs;

  // Immediate first render
  updateCountdownDisplay(remaining);

  countdownTimer = setInterval(() => {
    remaining -= 1000;

    if (remaining <= 0) {
      clearInterval(countdownTimer);
      countdownTimer = null;
      setCountdownDigits(0, 0, 0, 0);
      return;
    }

    updateCountdownDisplay(remaining);
  }, 1000);
}

function updateCountdownDisplay(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const days  = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const mins  = Math.floor((totalSeconds % 3600) / 60);
  const secs  = totalSeconds % 60;

  setCountdownDigits(days, hours, mins, secs);
}

function setCountdownDigits(days, hours, mins, secs) {
  const daysEl  = document.getElementById('countdown-days');
  const hoursEl = document.getElementById('countdown-hours');
  const minsEl  = document.getElementById('countdown-mins');
  const secsEl  = document.getElementById('countdown-secs');

  if (daysEl)  daysEl.textContent  = String(days).padStart(2, '0');
  if (hoursEl) hoursEl.textContent = String(hours).padStart(2, '0');
  if (minsEl)  minsEl.textContent  = String(mins).padStart(2, '0');
  if (secsEl)  secsEl.textContent  = String(secs).padStart(2, '0');
}

/* ─── Simulate Button ────────────────────────────────────────────────────────── */
function setupSimulateButton(circuitId) {
  const btn = document.getElementById('next-race-simulate-btn');
  if (!btn) return;

  btn.addEventListener('click', () => {
    const simSection = document.getElementById('simulator');
    if (simSection) {
      simSection.scrollIntoView({ behavior: 'smooth' });
    }

    // Pre-select the circuit in the simulator dropdown
    const simCircuit = document.getElementById('sim-circuit');
    if (simCircuit && circuitId) {
      simCircuit.value = circuitId;
      // Trigger change event so sliders update
      simCircuit.dispatchEvent(new Event('change'));
    }
  });
}

/* ═══════════════════════════════════════════════════════════════════════════════
   RECENT WINNERS
   ═══════════════════════════════════════════════════════════════════════════════ */
async function loadRecentWinners() {
  const grid = document.getElementById('winners-grid');
  if (!grid) return;

  try {
    const data = await api.get('/api/recent-results');
    const results = data.results || [];
    renderWinnerCards(results.slice(0, 5));
  } catch {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1;">
        <div class="empty-state-icon">🏆</div>
        <p class="empty-state-text">Unable to load recent results.</p>
      </div>`;
    console.error('Failed to load recent results.');
  }
}

/* ─── Render Winner Cards ────────────────────────────────────────────────────── */
function renderWinnerCards(results) {
  const grid = document.getElementById('winners-grid');
  if (!grid) return;

  if (results.length === 0) {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1;">
        <div class="empty-state-icon">🏁</div>
        <p class="empty-state-text">No race results yet this season.</p>
      </div>`;
    return;
  }

  grid.innerHTML = results.map((r, i) => {
    const winner = r.winner || {};
    const color = winner.team_color || utils.getTeamColor(winner.team);
    return `
      <div class="winner-card" style="--team-color:${color}; animation-delay:${i * 0.12}s">
        <div class="winner-card-header">
          <span class="winner-trophy">🏆</span>
          <span class="winner-race-name">${utils.escapeHtml(r.race_name)}</span>
        </div>
        <div class="winner-country">${utils.escapeHtml(r.country)}</div>
        <div class="winner-driver" style="color:${color}">
          ${utils.escapeHtml(winner.name || winner.code || '—')}
        </div>
        <div class="winner-team">${utils.escapeHtml(winner.team || '—')}</div>
        <div class="winner-podium">
          ${renderMiniPodium(r.podium)}
        </div>
      </div>`;
  }).join('');

  // Animate cards in with staggered delay
  requestAnimationFrame(() => {
    grid.querySelectorAll('.winner-card').forEach((card, i) => {
      setTimeout(() => card.classList.add('animate-in'), i * 120);
    });
  });
}

/* ─── Mini Podium for Winner Card ────────────────────────────────────────────── */
function renderMiniPodium(podium) {
  if (!Array.isArray(podium) || podium.length === 0) return '';

  return podium.map(p => {
    const color = p.team_color || utils.getTeamColor(p.team);
    const medal = p.position === 1 ? '🥇' : p.position === 2 ? '🥈' : '🥉';
    return `<span class="mini-podium-entry" style="color:${color}" title="${utils.escapeHtml(p.name)}">${medal} ${utils.escapeHtml(p.code)}</span>`;
  }).join('');
}

/* ═══════════════════════════════════════════════════════════════════════════════
   SEASON SCHEDULE TABLE
   ═══════════════════════════════════════════════════════════════════════════════ */
async function loadSeasonSchedule() {
  const tbody = document.getElementById('schedule-body');
  if (!tbody) return;

  try {
    const data = await api.get('/api/calendar');
    const calendar = data.calendar || [];
    renderScheduleTable(calendar);
  } catch {
    tbody.innerHTML =
      '<tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--text-muted)">Unable to load season schedule.</td></tr>';
    console.error('Failed to load season schedule.');
  }
}

/* ─── Render Schedule Table ──────────────────────────────────────────────────── */
function renderScheduleTable(calendar) {
  const tbody = document.getElementById('schedule-body');
  if (!tbody) return;

  if (calendar.length === 0) {
    tbody.innerHTML =
      '<tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--text-muted)">No races scheduled.</td></tr>';
    return;
  }

  tbody.innerHTML = calendar.map(race => {
    const isNext      = race.status === 'next';
    const isCompleted = race.status === 'completed';
    const rowClass    = isNext ? ' class="schedule-row-next"' : isCompleted ? ' class="schedule-row-completed"' : '';

    let statusHtml;
    if (isCompleted) {
      statusHtml = '<span class="schedule-status completed">✅ Completed</span>';
    } else if (isNext) {
      statusHtml = '<span class="schedule-status live">🔴 NEXT</span>';
    } else {
      statusHtml = '<span class="schedule-status upcoming">📅 Upcoming</span>';
    }

    return `
      <tr${rowClass}>
        <td>${race.round}</td>
        <td>${utils.escapeHtml(race.race_name)}</td>
        <td>${utils.escapeHtml(race.locality)}, ${utils.escapeHtml(race.country)}</td>
        <td>${formatRaceDate(race.date)}</td>
        <td>${statusHtml}</td>
      </tr>`;
  }).join('');
}

/* ─── Date Formatting Helper ─────────────────────────────────────────────────── */
function formatRaceDate(dateStr) {
  if (!dateStr) return '—';
  try {
    const date = new Date(dateStr + 'T00:00:00');
    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      month:   'short',
      day:     'numeric',
      year:    'numeric',
    });
  } catch {
    return dateStr;
  }
}
