/* ═══════════════════════════════════════════════════════════════════════════════
   HAMMERTIME — simulator.js
   Race simulation interface: circuit selection, parameter sliders, results
   ═══════════════════════════════════════════════════════════════════════════════ */

'use strict';

let simChart = null;
let circuitsData = [];

/* ─── Init ───────────────────────────────────────────────────────────────────── */
async function initSimulator() {
  await loadCircuits();
  setupSliders();
  setupSimButton();
}

/* ─── Load Circuits ──────────────────────────────────────────────────────────── */
async function loadCircuits() {
  const select = document.getElementById('sim-circuit');
  if (!select) return;

  try {
    circuitsData = await api.get('/api/circuits');
    circuitsData.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = `${c.name} — ${c.location}, ${c.country}`;
      opt.dataset.sc = c.sc_probability != null ? Math.round(c.sc_probability * 100) : 35;
      opt.dataset.rain = c.rain_probability != null ? Math.round(c.rain_probability * 100) : 10;
      select.appendChild(opt);
    });

    // Update sliders when circuit changes
    select.addEventListener('change', () => {
      const opt = select.options[select.selectedIndex];
      if (opt && opt.value) {
        setSlider('sim-sc', opt.dataset.sc || 35);
        setSlider('sim-rain', opt.dataset.rain || 10);
        document.getElementById('btn-simulate').disabled = false;
      } else {
        document.getElementById('btn-simulate').disabled = true;
      }
    });
  } catch {
    select.innerHTML = '<option value="">Failed to load circuits</option>';
  }
}

/* ─── Sliders ────────────────────────────────────────────────────────────────── */
function setupSliders() {
  ['sim-sc', 'sim-vsc', 'sim-rain'].forEach(id => {
    const slider = document.getElementById(id);
    const valueEl = document.getElementById(`${id}-value`);
    if (!slider || !valueEl) return;

    slider.addEventListener('input', () => {
      valueEl.textContent = `${slider.value}%`;
    });
  });
}

function setSlider(id, value) {
  const slider = document.getElementById(id);
  const valueEl = document.getElementById(`${id}-value`);
  if (slider) slider.value = value;
  if (valueEl) valueEl.textContent = `${value}%`;
}

/* ─── Simulate Button ────────────────────────────────────────────────────────── */
function setupSimButton() {
  const btn = document.getElementById('btn-simulate');
  if (!btn) return;

  btn.addEventListener('click', runSimulation);
}

async function runSimulation() {
  const circuitId = document.getElementById('sim-circuit')?.value;
  if (!circuitId) return;

  const btn = document.getElementById('btn-simulate');
  const emptyState = document.getElementById('sim-empty');
  const loadingEl = document.getElementById('sim-loading');
  const podiumEl = document.getElementById('sim-podium');
  const chartWrap = document.getElementById('sim-chart-wrap');
  const statsEl = document.getElementById('sim-stats');

  // Show loading
  btn.disabled = true;
  btn.textContent = '⏳ Simulating…';
  if (emptyState) emptyState.style.display = 'none';
  if (loadingEl) loadingEl.classList.add('active');
  if (podiumEl) podiumEl.style.display = 'none';
  if (chartWrap) chartWrap.style.display = 'none';
  if (statsEl) statsEl.style.display = 'none';

  const body = {
    circuit_id: circuitId,
    sc_prob: parseInt(document.getElementById('sim-sc')?.value || 35) / 100,
    vsc_prob: parseInt(document.getElementById('sim-vsc')?.value || 25) / 100,
    rain_prob: parseInt(document.getElementById('sim-rain')?.value || 10) / 100,
  };

  try {
    const data = await api.post('/api/simulate', body);
    renderSimResults(data);
    toast.show('Simulation complete!', 'success');
  } catch {
    if (emptyState) {
      emptyState.style.display = '';
      emptyState.querySelector('.empty-state-text').textContent = 'Simulation failed. Please try again.';
    }
  } finally {
    if (loadingEl) loadingEl.classList.remove('active');
    btn.disabled = false;
    btn.textContent = '🏁 Run Simulation';
  }
}

/* ─── Render Simulation Results ──────────────────────────────────────────────── */
function renderSimResults(data) {
  const results = data.drivers || {};

  // Sort drivers by win probability
  const sorted = Object.entries(results)
    .map(([code, r]) => ({
      code,
      driver_name: r.driver_name || code,
      team: r.team || '',
      team_color: r.team_color || '#fff',
      win_prob: r.win_prob || 0,
      podium_prob: r.podium_prob || 0,
      avg_position: r.avg_position || 20,
      dnf_prob: r.dnf_prob || 0,
    }))
    .sort((a, b) => b.win_prob - a.win_prob);

  // Find driver data for team colors
  const getDriverData = (code) => {
    const local = allDrivers.find(d => d.code === code);
    if (local) return local;
    // Fallback to simulation data
    const simD = sorted.find(d => d.code === code);
    return simD ? { name: simD.driver_name, team: simD.team, team_color: simD.team_color } : {};
  };

  // Render Podium
  renderPodium(sorted.slice(0, 3), getDriverData);

  // Render Bar Chart
  renderSimChart(sorted, getDriverData);

  // Render Stats
  renderSimStats(data);
}

/* ─── Podium ─────────────────────────────────────────────────────────────────── */
function renderPodium(top3, getDriverData) {
  const podiumEl = document.getElementById('sim-podium');
  if (!podiumEl) return;

  const trophies = ['🏆', '🥈', '🥉'];
  const posClasses = ['p1', 'p2', 'p3'];

  podiumEl.innerHTML = top3.map((d, i) => {
    const driver = getDriverData(d.code);
    const color = utils.getTeamColor(driver.team);
    return `
      <div class="podium-card ${posClasses[i]}" style="--team-color:${color}">
        <div class="podium-trophy">${trophies[i]}</div>
        <div class="podium-position">P${i + 1}</div>
        <div class="podium-driver-name">${utils.escapeHtml(driver.name || d.code)}</div>
        <div class="podium-team">${utils.escapeHtml(driver.team || '—')}</div>
        <div class="podium-prob">${(d.win_prob * 100).toFixed(1)}%</div>
      </div>`;
  }).join('');

  podiumEl.style.display = '';

  // Animate in
  setTimeout(() => {
    podiumEl.querySelectorAll('.podium-card').forEach((card, i) => {
      setTimeout(() => card.classList.add('animate-in'), i * 200);
    });
  }, 100);
}

/* ─── Simulation Bar Chart ───────────────────────────────────────────────────── */
function renderSimChart(sorted, getDriverData) {
  const chartWrap = document.getElementById('sim-chart-wrap');
  const canvas = document.getElementById('sim-chart');
  if (!chartWrap || !canvas || typeof Chart === 'undefined') return;

  if (simChart) {
    simChart.destroy();
    simChart = null;
  }

  const labels = sorted.map(d => d.code);
  const winProbs = sorted.map(d => +(d.win_prob * 100).toFixed(1));
  const colors = sorted.map(d => {
    const driver = getDriverData(d.code);
    return utils.getTeamColor(driver.team);
  });

  chartWrap.style.display = '';
  const ctx = canvas.getContext('2d');

  simChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Win Probability (%)',
        data: winProbs,
        backgroundColor: colors.map(c => `${c}cc`),
        borderColor: colors,
        borderWidth: 1,
        borderRadius: 6,
        barThickness: 20,
      }]
    },
    options: {
      indexAxis: 'y',
      animation: {
        duration: 1500,
        easing: 'easeOutQuart',
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const d = sorted[ctx.dataIndex];
              return [
                `Win: ${(d.win_prob * 100).toFixed(1)}%`,
                `Podium: ${(d.podium_prob * 100).toFixed(1)}%`,
                `Avg Pos: ${d.avg_position.toFixed(1)}`,
                `DNF: ${(d.dnf_prob * 100).toFixed(1)}%`,
              ];
            }
          }
        }
      },
      scales: {
        x: {
          title: { display: true, text: 'Win Probability (%)' },
          grid: { color: 'rgba(255,255,255,0.04)' },
          beginAtZero: true,
        },
        y: {
          grid: { display: false },
          ticks: {
            font: { family: "'Outfit', sans-serif", weight: '600' },
          }
        }
      }
    }
  });
}

/* ─── Sim Stats Summary ──────────────────────────────────────────────────────── */
function renderSimStats(data) {
  const statsEl = document.getElementById('sim-stats');
  if (!statsEl) return;

  const scPct = data.sc_probability != null ? (data.sc_probability * 100).toFixed(0) + '%' : '—';
  const rainPct = data.rain_probability != null ? (data.rain_probability * 100).toFixed(0) + '%' : '—';

  statsEl.innerHTML = `
    <div class="sim-stat-card">
      <div class="sim-stat-value">${utils.formatNumber(data.n_simulations)}</div>
      <div class="sim-stat-label">Simulations</div>
    </div>
    <div class="sim-stat-card">
      <div class="sim-stat-value">${data.total_laps || '—'}</div>
      <div class="sim-stat-label">Race Laps</div>
    </div>
    <div class="sim-stat-card">
      <div class="sim-stat-value">${scPct}</div>
      <div class="sim-stat-label">SC Probability</div>
    </div>
    <div class="sim-stat-card">
      <div class="sim-stat-value">${rainPct}</div>
      <div class="sim-stat-label">Rain Probability</div>
    </div>`;

  statsEl.style.display = '';
}
