/* ═══════════════════════════════════════════════════════════════════════════════
   HAMMERTIME — simulator.js
   Race simulation + Strategy Lab + What-If Engine
   ═══════════════════════════════════════════════════════════════════════════════ */

'use strict';

let simChart = null;
let posDistChart = null;
let circuitsData = [];

/* ═══════════════════════════════════════════════════════════════════════════════
   RACE SIMULATOR
   ═══════════════════════════════════════════════════════════════════════════════ */

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
    const valueEl = document.getElementById(`${id}-val`);
    if (!slider || !valueEl) return;

    slider.addEventListener('input', () => {
      valueEl.textContent = `${slider.value}%`;
    });
  });
}

function setSlider(id, value) {
  const slider = document.getElementById(id);
  const valueEl = document.getElementById(`${id}-val`);
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
  const posDistWrap = document.getElementById('sim-pos-dist-wrap');
  const confidenceEl = document.getElementById('sim-confidence');
  const statsEl = document.getElementById('sim-stats');

  // Show loading
  btn.disabled = true;
  btn.textContent = '⏳ Simulating…';
  if (emptyState) emptyState.style.display = 'none';
  if (loadingEl) {
    loadingEl.style.display = 'block';
    loadingEl.classList.add('active');
  }
  if (podiumEl) podiumEl.style.display = 'none';
  if (chartWrap) chartWrap.style.display = 'none';
  if (posDistWrap) posDistWrap.style.display = 'none';
  if (confidenceEl) confidenceEl.style.display = 'none';
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
  } catch (err) {
    console.error('Simulation run failed:', err);
    if (emptyState) {
      emptyState.style.display = '';
      const emptyText = emptyState.querySelector('p') || emptyState;
      emptyText.textContent = 'Simulation failed. Please try again.';
    }
  } finally {
    if (loadingEl) {
      loadingEl.style.display = 'none';
      loadingEl.classList.remove('active');
    }
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
      top5_prob: r.top5_prob || 0,
      top10_prob: r.top10_prob || 0,
      avg_position: r.avg_position || 20,
      median_position: r.median_position || 20,
      dnf_prob: r.dnf_prob || 0,
      position_distribution: r.position_distribution || {},
      confidence_interval_95: r.confidence_interval_95 || null,
    }))
    .sort((a, b) => b.win_prob - a.win_prob);

  const getDriverData = (code) => {
    if (typeof allDrivers !== 'undefined') {
      const local = allDrivers.find(d => d.code === code);
      if (local) return local;
    }
    const simD = sorted.find(d => d.code === code);
    return simD ? { name: simD.driver_name, team: simD.team, team_color: simD.team_color } : {};
  };

  // Render Podium
  renderPodium(sorted.slice(0, 3), getDriverData);

  // Render Bar Chart
  renderSimChart(sorted, getDriverData);

  // Render Position Distribution
  if (sorted.some(d => Object.keys(d.position_distribution).length > 0)) {
    renderPositionDistChart(sorted.slice(0, 10), getDriverData);
  }

  // Render Confidence Intervals
  renderConfidenceIntervals(sorted.slice(0, 10), getDriverData);

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
      animation: { duration: 1500, easing: 'easeOutQuart' },
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

/* ─── Position Distribution Chart (Stacked Horizontal Bar) ───────────────────── */
function renderPositionDistChart(top10, getDriverData) {
  const wrap = document.getElementById('sim-pos-dist-wrap');
  const canvas = document.getElementById('sim-pos-dist');
  if (!wrap || !canvas || typeof Chart === 'undefined') return;

  if (posDistChart) {
    posDistChart.destroy();
    posDistChart = null;
  }

  const labels = top10.map(d => d.code);
  const posColors = [
    '#FFD700', '#C0C0C0', '#CD7F32', '#00f0ff', '#00c4cc',
    '#0099aa', '#006e88', '#004466', '#223344', '#111a22',
    '#333', '#444', '#555', '#666', '#777',
    '#888', '#999', '#aaa', '#bbb', '#ccc'
  ];

  const datasets = [];
  for (let pos = 1; pos <= 20; pos++) {
    datasets.push({
      label: `P${pos}`,
      data: top10.map(d => {
        const pct = d.position_distribution[String(pos)];
        return pct != null ? +(pct * 100).toFixed(1) : 0;
      }),
      backgroundColor: posColors[pos - 1] + 'cc',
      borderWidth: 0,
      barThickness: 18,
    });
  }

  wrap.style.display = '';
  const ctx = canvas.getContext('2d');

  posDistChart = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets },
    options: {
      indexAxis: 'y',
      animation: { duration: 1200 },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `P${ctx.datasetIndex + 1}: ${ctx.raw}%`,
          }
        }
      },
      scales: {
        x: {
          stacked: true,
          title: { display: true, text: 'Probability (%)' },
          grid: { color: 'rgba(255,255,255,0.04)' },
          max: 100,
        },
        y: {
          stacked: true,
          grid: { display: false },
          ticks: { font: { family: "'Outfit', sans-serif", weight: '600' } }
        }
      }
    }
  });
}

/* ─── Confidence Intervals ───────────────────────────────────────────────────── */
function renderConfidenceIntervals(top10, getDriverData) {
  const wrap = document.getElementById('sim-confidence');
  const content = document.getElementById('sim-confidence-content');
  if (!wrap || !content) return;

  const hasCI = top10.some(d => d.confidence_interval_95);
  if (!hasCI) { wrap.style.display = 'none'; return; }

  content.innerHTML = top10.map(d => {
    const driver = getDriverData(d.code);
    const ci = d.confidence_interval_95;
    const ciText = ci ? `${utils.formatLapTime(ci.lower)} — ${utils.formatLapTime(ci.upper)}` : '—';
    return `
      <div class="sim-confidence-item">
        <span class="sim-confidence-driver" style="color:${utils.getTeamColor(driver.team)}">${d.code}</span>
        <span class="sim-confidence-range">${ciText}</span>
      </div>`;
  }).join('');

  wrap.style.display = '';
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

/* ═══════════════════════════════════════════════════════════════════════════════
   STRATEGY LAB
   ═══════════════════════════════════════════════════════════════════════════════ */

function initStrategyLab() {
  populateStrategyDropdowns();
  setupStintBuilder();
  setupStrategySimButton();
  setupWhatIfEngine();
}

/* ─── Populate Dropdowns ─────────────────────────────────────────────────────── */
function populateStrategyDropdowns() {
  // Driver dropdowns
  const driverSelects = ['strat-driver', 'whatif-gs-driver'];
  driverSelects.forEach(id => {
    const el = document.getElementById(id);
    if (!el || typeof allDrivers === 'undefined' || !allDrivers.length) return;
    el.innerHTML = '';
    allDrivers.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.code;
      opt.textContent = `${d.code} — ${d.name}`;
      el.appendChild(opt);
    });
  });

  // Circuit dropdowns
  const circuitSelects = ['strat-circuit', 'whatif-nsc-circuit', 'whatif-gs-circuit', 'whatif-wc-circuit'];
  circuitSelects.forEach(id => {
    const el = document.getElementById(id);
    if (!el || !circuitsData.length) return;
    el.innerHTML = '';
    circuitsData.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = c.name;
      el.appendChild(opt);
    });
  });
}

/* ─── Stint Builder ──────────────────────────────────────────────────────────── */
function setupStintBuilder() {
  const addBtn = document.getElementById('strat-add-stint');
  const stintContainer = document.getElementById('strat-stints-container');

  function addStintRow(compound = 'HARD', laps = 15) {
    if (!stintContainer) return;
    const stints = stintContainer.querySelectorAll('.stint-row');
    if (stints.length >= 4) {
      toast.show('Maximum 4 stints allowed.', 'warning');
      return;
    }
    const num = stints.length + 1;
    const row = document.createElement('div');
    row.className = 'stint-row';
    row.style = 'display: flex; align-items: center; gap: 8px; margin-bottom: 8px;';
    row.innerHTML = `
      <span class="stint-num" style="color:var(--text-secondary);font-weight:600;min-width:24px;">S${num}</span>
      <select class="stint-compound form-select" style="flex: 1;">
        <option value="SOFT" ${compound === 'SOFT' ? 'selected' : ''}>🔴 SOFT</option>
        <option value="MEDIUM" ${compound === 'MEDIUM' ? 'selected' : ''}>🟡 MEDIUM</option>
        <option value="HARD" ${compound === 'HARD' ? 'selected' : ''}>⚪ HARD</option>
        <option value="INTER" ${compound === 'INTER' ? 'selected' : ''}>🟢 INTER</option>
        <option value="WET" ${compound === 'WET' ? 'selected' : ''}>🔵 WET</option>
      </select>
      <input type="number" class="stint-laps" value="${laps}" min="1" max="70" class="form-input" style="width: 80px;" placeholder="Laps">
      <button type="button" class="btn-remove-stint" style="background:none;border:none;color:var(--accent-red);cursor:pointer;font-size:1.5rem;padding:0 4px;">&times;</button>
    `;

    // Bind remove action
    row.querySelector('.btn-remove-stint').addEventListener('click', () => {
      row.remove();
      // Renumber remaining stints
      stintContainer.querySelectorAll('.stint-row').forEach((r, idx) => {
        r.querySelector('.stint-num').textContent = `S${idx + 1}`;
      });
    });

    stintContainer.appendChild(row);
  }

  // Populate first stint by default if empty
  if (stintContainer && stintContainer.children.length === 0) {
    addStintRow('MEDIUM', 18);
  }

  if (addBtn) {
    addBtn.addEventListener('click', () => {
      addStintRow('HARD', 20);
    });
  }
}

/* ─── Strategy Simulation Button ─────────────────────────────────────────────── */
function setupStrategySimButton() {
  const btn = document.getElementById('strat-run');
  if (!btn) return;

  btn.disabled = false;

  btn.addEventListener('click', async () => {
    const driver = document.getElementById('strat-driver')?.value;
    const circuit = document.getElementById('strat-circuit')?.value;
    const weather = document.getElementById('strat-weather')?.value || 'dry';
    const position = parseInt(document.getElementById('strat-position')?.value || 1);

    if (!driver || !circuit) {
      toast.show('Select a driver and circuit.', 'warning');
      return;
    }

    // Build tyre strategy from stint rows
    const stintRows = document.querySelectorAll('#strat-stints-container .stint-row');
    const tyre_strategy = [];
    stintRows.forEach(row => {
      const compound = row.querySelector('.stint-compound')?.value || 'MEDIUM';
      const laps = parseInt(row.querySelector('.stint-laps')?.value || 20);
      tyre_strategy.push({ compound, laps });
    });

    if (tyre_strategy.length === 0) {
      toast.show('Add at least one stint to the strategy.', 'warning');
      return;
    }

    btn.disabled = true;
    btn.textContent = '⏳ Running…';

    try {
      const data = await api.post('/api/simulate-advanced', {
        circuit_id: circuit,
        driver_code: driver,
        starting_position: position,
        weather,
        tyre_strategy,
        n_simulations: 2000,
      });

      renderStrategyResults(data);
      toast.show('Strategy simulation complete!', 'success');
    } catch (err) {
      console.error('Strategy simulation failed:', err);
      toast.show('Strategy simulation failed. Try again.', 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = '🎯 Run Strategy Analysis';
    }
  });
}

/* ─── Render Strategy Results ────────────────────────────────────────────────── */
function renderStrategyResults(data) {
  const resultsEl = document.getElementById('strat-results');
  const winEl = document.getElementById('strat-win-pct');
  const podiumEl = document.getElementById('strat-podium-pct');
  const top10El = document.getElementById('strat-top10-pct');
  const expEl = document.getElementById('strat-exp-pos');

  if (winEl) winEl.textContent = data.win_prob != null ? (data.win_prob * 100).toFixed(1) + '%' : '—';
  if (podiumEl) podiumEl.textContent = data.podium_prob != null ? (data.podium_prob * 100).toFixed(1) + '%' : '—';
  if (top10El) top10El.textContent = data.top10_prob != null ? (data.top10_prob * 100).toFixed(1) + '%' : '—';
  if (expEl) expEl.textContent = data.expected_position != null ? 'P' + data.expected_position.toFixed(1) : '—';

  if (resultsEl) resultsEl.style.display = 'block';

  // Recommended strategy
  const recommended = document.getElementById('strat-recommended');
  const recContent = document.getElementById('strat-recommended-content');
  if (data.recommended_strategy && recommended && recContent) {
    const rec = data.recommended_strategy;
    recContent.innerHTML = `
      <div style="font-family: var(--font-mono); font-size: 0.9rem; line-height: 1.6; color: var(--text-primary);">
        <p><strong>Stops:</strong> <span style="color:var(--accent-cyan);">${rec.stops || '—'}</span></p>
        <p><strong>Compounds:</strong> <span style="color:var(--accent-green);">${Array.isArray(rec.compounds) ? rec.compounds.join(' → ') : (rec.compounds || '—')}</span></p>
        <p style="margin-top: 0.5rem; color: var(--text-secondary); font-family: var(--font-sans);">${utils.escapeHtml(rec.reasoning || '—')}</p>
      </div>
    `;
    recommended.style.display = 'block';
  }
}

/* ═══════════════════════════════════════════════════════════════════════════════
   WHAT-IF ENGINE
   ═══════════════════════════════════════════════════════════════════════════════ */

function setupWhatIfEngine() {
  const scenarios = [
    {
      type: 'no_safety_car',
      btnId: 'whatif-nsc-run',
      getParams: () => ({}),
      getCircuit: () => document.getElementById('whatif-nsc-circuit')?.value
    },
    {
      type: 'grid_change',
      btnId: 'whatif-gs-run',
      getParams: () => ({
        driver_code: document.getElementById('whatif-gs-driver')?.value,
        new_position: parseInt(document.getElementById('whatif-gs-position')?.value || 1)
      }),
      getCircuit: () => document.getElementById('whatif-gs-circuit')?.value
    },
    {
      type: 'weather_change',
      btnId: 'whatif-wc-run',
      getParams: () => ({
        rain_lap: parseInt(document.getElementById('whatif-wc-lap')?.value || 15)
      }),
      getCircuit: () => document.getElementById('whatif-wc-circuit')?.value
    }
  ];

  scenarios.forEach(sc => {
    const btn = document.getElementById(sc.btnId);
    if (!btn) return;

    btn.addEventListener('click', async () => {
      const circuitId = sc.getCircuit();
      if (!circuitId) {
        toast.show('Select a circuit first.', 'warning');
        return;
      }

      const params = sc.getParams();
      if (sc.type === 'grid_change' && !params.driver_code) {
        toast.show('Select a driver for the grid swap.', 'warning');
        return;
      }

      const originalText = btn.textContent;
      btn.disabled = true;
      btn.textContent = '⏳ Analyzing…';

      // Show temporary loading indicator in results table
      const resultsEl = document.getElementById('whatif-results');
      const tableEl = document.getElementById('whatif-results-table');
      if (resultsEl && tableEl) {
        tableEl.innerHTML = '<div style="text-align:center;padding:2rem;"><div class="spinner"></div><p style="margin-top:1rem;color:var(--accent-cyan);font-family:var(--font-mono);">COMPUTING ALTERNATE QUANTUM REALITY...</p></div>';
        resultsEl.style.display = 'block';
      }

      try {
        const data = await api.post('/api/whatif', {
          circuit_id: circuitId,
          scenario_type: sc.type,
          params
        });

        renderWhatIfResults(data);
        toast.show('What-If analysis complete!', 'success');
      } catch (err) {
        console.error('What-if simulation failed:', err);
        toast.show('What-If analysis failed. Try again.', 'error');
        if (tableEl) {
          tableEl.innerHTML = '<p style="color:var(--accent-red);text-align:center;padding:2rem;">Simulation failed.</p>';
        }
      } finally {
        btn.disabled = false;
        btn.textContent = originalText;
      }
    });
  });
}

/* ─── Render What-If Results ─────────────────────────────────────────────────── */
function renderWhatIfResults(data) {
  const resultsEl = document.getElementById('whatif-results');
  const tableEl = document.getElementById('whatif-results-table');
  if (!resultsEl || !tableEl) return;

  const baselineMap = {};
  if (Array.isArray(data.baseline)) {
    data.baseline.forEach(d => { baselineMap[d.code] = d; });
  }

  const alternateMap = {};
  if (Array.isArray(data.alternate)) {
    data.alternate.forEach(d => { alternateMap[d.code] = d; });
  }

  // Build comparison table using deltas
  const deltas = data.deltas || [];

  let tableHtml = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Driver</th>
          <th>Team</th>
          <th>Baseline Win %</th>
          <th>Alternate Win %</th>
          <th>Delta</th>
        </tr>
      </thead>
      <tbody>
  `;

  if (deltas.length > 0) {
    deltas.forEach(d => {
      const base = baselineMap[d.code] || {};
      const alt = alternateMap[d.code] || {};
      const delta = d.win_prob_delta || 0;
      let deltaClass = 'delta-neutral';
      let deltaText = '0.0%';

      if (delta > 0) {
        deltaClass = 'delta-positive';
        deltaText = `▲ +${delta.toFixed(1)}%`;
      } else if (delta < 0) {
        deltaClass = 'delta-negative';
        deltaText = `▼ ${delta.toFixed(1)}%`;
      }

      tableHtml += `
        <tr>
          <td style="font-weight:600; color: var(--text-primary);">${utils.escapeHtml(d.driver_name)} (${d.code})</td>
          <td style="color: ${utils.getTeamColor(d.team)};">${utils.escapeHtml(d.team)}</td>
          <td>${base.win_prob != null ? base.win_prob.toFixed(1) + '%' : '—'}</td>
          <td>${alt.win_prob != null ? alt.win_prob.toFixed(1) + '%' : '—'}</td>
          <td class="${deltaClass}">${deltaText}</td>
        </tr>
      `;
    });
  } else {
    tableHtml += `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);">No deltas available.</td></tr>`;
  }

  tableHtml += '</tbody></table>';
  tableEl.innerHTML = tableHtml;
  resultsEl.style.display = 'block';
}
