/* ═══════════════════════════════════════════════════════════════════════════════
   HAMMERTIME — weekend_intel.js
   Real-time race weekend intelligence & command center UI controller
   ═══════════════════════════════════════════════════════════════════════════════ */

'use strict';

let ccCountdownTimer = null;

async function initWeekendIntel() {
  await loadWeekendIntelligence();
}

async function loadWeekendIntelligence() {
  try {
    const data = await api.get('/api/weekend-intelligence');
    if (data && data.current_weekend) {
      renderCommandCenter(data);
    } else {
      await loadFallbackIntel();
    }
  } catch (err) {
    console.error('Failed to load weekend intelligence:', err);
    await loadFallbackIntel();
  }
}

async function loadFallbackIntel() {
  try {
    // Try to get next race from calendar
    const calendarData = await api.get('/api/calendar');
    const nextRace = calendarData.next_race;
    if (nextRace) {
      const fallbackData = {
        current_weekend: {
          round: nextRace.round,
          race_name: nextRace.race_name,
          circuit_id: nextRace.circuit_id,
          circuit_name: nextRace.circuit_name,
          locality: nextRace.locality,
          country: nextRace.country,
          date: nextRace.date,
          countdown_seconds: Math.floor(nextRace.countdown_ms / 1000)
        },
        sessions: [
          { session: 'Qualifying', status: 'upcoming', countdown_seconds: Math.floor(nextRace.countdown_ms / 1000) - 86400, time_utc: '14:00' },
          { session: 'Race', status: 'upcoming', countdown_seconds: Math.floor(nextRace.countdown_ms / 1000), time_utc: '14:00' }
        ],
        previous_race: null
      };
      renderCommandCenter(fallbackData);
    } else {
      renderNoWeekendIntel();
    }
  } catch (err) {
    console.error('Fallback calendar load failed:', err);
    renderNoWeekendIntel();
  }
}

function renderCommandCenter(data) {
  const cw = data.current_weekend;
  
  // Update elements
  document.getElementById('cc-race-name').textContent = cw.race_name || 'Loading...';
  document.getElementById('cc-circuit').textContent = `${cw.circuit_name || ''} — ${cw.locality || ''}, ${cw.country || ''}`;
  document.getElementById('cc-date').textContent = cw.date ? new Date(cw.date).toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }) : '—';
  document.getElementById('cc-round').textContent = cw.round ? `ROUND ${cw.round}` : '—';

  // Wire Simulate Button
  const simBtn = document.getElementById('cc-simulate-btn');
  if (simBtn) {
    simBtn.onclick = () => {
      // Auto-select circuit in Simulator tab
      const simSelect = document.getElementById('sim-circuit');
      if (simSelect && cw.circuit_id) {
        simSelect.value = cw.circuit_id;
        // Trigger select change if needed
        simSelect.dispatchEvent(new Event('change'));
      }
      
      // Navigate to Simulator tab
      const simTab = document.querySelector('.nav-tab[data-section="simulator"]');
      if (simTab) {
        simTab.click();
      }
    };
  }

  // Start countdown
  if (cw.countdown_seconds !== undefined) {
    startCcCountdown(cw.countdown_seconds);
  }

  // Render sessions
  renderCcSessions(data.sessions);

  // Render previous race results
  renderCcPreviousRace(data.previous_race);
}

function startCcCountdown(totalSeconds) {
  if (ccCountdownTimer) {
    clearInterval(ccCountdownTimer);
  }
  
  let remaining = totalSeconds;
  
  function updateTimerDisplay() {
    if (remaining <= 0) {
      clearInterval(ccCountdownTimer);
      ccCountdownTimer = null;
      updateCcCountdownDigits(0, 0, 0, 0);
      return;
    }

    const days = Math.floor(remaining / (3600 * 24));
    const hours = Math.floor((remaining % (3600 * 24)) / 3600);
    const mins = Math.floor((remaining % 3600) / 60);
    const secs = remaining % 60;
    
    updateCcCountdownDigits(days, hours, mins, secs);
    remaining--;
  }

  updateTimerDisplay();
  ccCountdownTimer = setInterval(updateTimerDisplay, 1000);
}

function updateCcCountdownDigits(d, h, m, s) {
  const daysEl = document.getElementById('cc-countdown-days');
  const hoursEl = document.getElementById('cc-countdown-hours');
  const minsEl = document.getElementById('cc-countdown-mins');
  const secsEl = document.getElementById('cc-countdown-secs');
  
  if (daysEl) daysEl.textContent = String(d).padStart(2, '0');
  if (hoursEl) hoursEl.textContent = String(h).padStart(2, '0');
  if (minsEl) minsEl.textContent = String(m).padStart(2, '0');
  if (secsEl) secsEl.textContent = String(s).padStart(2, '0');
}

function renderCcSessions(sessions) {
  const container = document.getElementById('cc-sessions');
  if (!container || !sessions || sessions.length === 0) return;
  
  container.innerHTML = sessions.map(s => {
    let statusClass = 'upcoming';
    let statusLabel = 'UPCOMING';
    if (s.status === 'completed') {
      statusClass = 'completed';
      statusLabel = 'COMPLETED';
    } else if (s.status === 'live') {
      statusClass = 'live';
      statusLabel = 'LIVE';
    }
    
    return `
      <div class="session-item" data-session="${s.session.toLowerCase()}">
        <span class="session-dot ${statusClass}"></span>
        <span class="session-label">${utils.escapeHtml(s.session)}</span>
        <span class="session-status ${statusClass}">${statusLabel} (${s.time_utc} UTC)</span>
      </div>
    `;
  }).join('');
}

function renderCcPreviousRace(prevRace) {
  const card = document.getElementById('cc-previous-race');
  if (!card) return;
  
  if (!prevRace) {
    card.style.display = 'none';
    return;
  }
  
  card.style.display = '';
  
  // Set winner
  const winnerEl = document.getElementById('cc-prev-winner');
  if (winnerEl && prevRace.winner) {
    const color = utils.getTeamColor(prevRace.winner.team);
    winnerEl.innerHTML = `<span style="color:${color}">${utils.escapeHtml(prevRace.winner.name)}</span> <small style="color:var(--text-muted)">(${utils.escapeHtml(prevRace.winner.team)})</small>`;
  } else if (winnerEl) {
    winnerEl.textContent = '—';
  }
  
  // Set pole
  const poleEl = document.getElementById('cc-prev-pole');
  if (poleEl && prevRace.pole_sitter) {
    const color = utils.getTeamColor(prevRace.pole_sitter.team);
    poleEl.innerHTML = `<span style="color:${color}">${utils.escapeHtml(prevRace.pole_sitter.name)}</span>`;
  } else if (poleEl) {
    poleEl.textContent = '—';
  }
  
  // Set fastest lap
  const fastestEl = document.getElementById('cc-prev-fastest');
  if (fastestEl && prevRace.fastest_lap) {
    const color = utils.getTeamColor(prevRace.fastest_lap.team);
    fastestEl.innerHTML = `<span style="color:${color}">${utils.escapeHtml(prevRace.fastest_lap.name)}</span>`;
  } else if (fastestEl) {
    fastestEl.textContent = '—';
  }
  
  // Set podium
  const podiumEl = document.getElementById('cc-prev-podium');
  if (podiumEl && prevRace.podium && prevRace.podium.length > 0) {
    const podiumNames = prevRace.podium.slice(0, 3).map(p => {
      const color = utils.getTeamColor(p.team);
      return `<span style="color:${color}">${utils.escapeHtml(p.code || p.name)}</span>`;
    }).join(' · ');
    podiumEl.innerHTML = podiumNames;
  } else if (podiumEl) {
    podiumEl.textContent = '—';
  }
  
  // Set constructor winner
  const constructorEl = document.getElementById('cc-prev-constructor');
  if (constructorEl && prevRace.constructor_winner) {
    const color = utils.getTeamColor(prevRace.constructor_winner);
    constructorEl.innerHTML = `<span style="color:${color}">${utils.escapeHtml(prevRace.constructor_winner)}</span>`;
  } else if (constructorEl) {
    constructorEl.textContent = '—';
  }
}

function renderNoWeekendIntel() {
  document.getElementById('cc-race-name').textContent = 'No Active Race Weekend';
  document.getElementById('cc-circuit').textContent = 'The season has either completed or not started yet.';
  document.getElementById('cc-date').textContent = '—';
  document.getElementById('cc-round').textContent = '—';
  
  updateCcCountdownDigits(0, 0, 0, 0);
  
  const sessionsContainer = document.getElementById('cc-sessions');
  if (sessionsContainer) {
    sessionsContainer.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted)">No sessions scheduled</div>';
  }
  
  const prevRaceCard = document.getElementById('cc-previous-race');
  if (prevRaceCard) {
    prevRaceCard.style.display = 'none';
  }
}
