/* ═══════════════════════════════════════════════════════════════════════════════
   HAMMERTIME — charts.js
   Analytics charts: Lap times, Tyre heatmap, DNF gauges, Radar, Predictions
   ═══════════════════════════════════════════════════════════════════════════════ */

'use strict';

let lapTimeChart = null;
let radarChart = null;

const COMPOUND_COLORS = {
  SOFT: '#FF3333',
  MEDIUM: '#FFC906',
  HARD: '#EEEEEE',
  INTERMEDIATE: '#39B54A',
  WET: '#00AEEF',
  UNKNOWN: '#888888',
};

/* ─── Init ───────────────────────────────────────────────────────────────────── */
async function initCharts() {
  populateChartFilters();
  setupLapTimeChart();
  setupTyreHeatmap();
  setupRadarChart();
  setupPredictions();
  loadDNFGauges();

  // Load initial charts/predictions if possible
  const ltCirc = document.getElementById('lt-circuit');
  const ltDriv = document.getElementById('lt-driver');
  if (ltCirc && ltDriv && ltCirc.value && ltDriv.value) {
    loadLapTimes();
  }
  const thCirc = document.getElementById('th-circuit');
  if (thCirc && thCirc.value) {
    loadTyreHeatmap();
  }
  const predCirc = document.getElementById('pred-circuit');
  if (predCirc && predCirc.value) {
    loadPrediction(predCirc.value);
  }
}

/* ─── Populate Filter Dropdowns ──────────────────────────────────────────────── */
function populateChartFilters() {
  // Populate driver dropdowns
  const driverSelects = ['lt-driver', 'radar-driver'];
  driverSelects.forEach(id => {
    const el = document.getElementById(id);
    if (!el || !allDrivers.length) return;
    el.innerHTML = '';
    allDrivers.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.code;
      opt.textContent = `${d.code} — ${d.name}`;
      el.appendChild(opt);
    });
  });

  // Populate circuit dropdowns
  const circuitSelects = ['lt-circuit', 'th-circuit', 'pred-circuit', 'dnf-circuit'];
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

/* ═══════════════════════════════════════════════════════════════════════════════
   LAP TIME CHART
   ═══════════════════════════════════════════════════════════════════════════════ */
function setupLapTimeChart() {
  const btn = document.getElementById('lt-load');
  if (!btn) return;

  btn.addEventListener('click', loadLapTimes);
}

async function loadLapTimes() {
  const driverCode = document.getElementById('lt-driver')?.value;
  const circuitId = document.getElementById('lt-circuit')?.value;
  const emptyEl = document.getElementById('laptimes-empty');
  const canvas = document.getElementById('laptimes-chart');

  if (!driverCode || !circuitId) {
    return;
  }

  if (emptyEl) emptyEl.style.display = 'none';

  try {
    const data = await api.get(`/api/analytics/laptimes?driver=${driverCode}&circuit=${circuitId}`);
    renderLapTimeChart(data, driverCode);
  } catch (err) {
    console.error('Failed to load lap times:', err);
    if (emptyEl) {
      emptyEl.style.display = '';
      const emptyText = emptyEl.querySelector('.empty-state-text') || emptyEl;
      emptyText.textContent = 'Failed to load lap time data.';
    }
  }
}

function renderLapTimeChart(data, driverCode) {
  const canvas = document.getElementById('laptimes-chart');
  if (!canvas || typeof Chart === 'undefined') return;

  if (lapTimeChart) {
    lapTimeChart.destroy();
    lapTimeChart = null;
  }

  const laps = data.laps || [];
  if (laps.length === 0) {
    const emptyEl = document.getElementById('laptimes-empty');
    if (emptyEl) {
      emptyEl.style.display = '';
      emptyEl.querySelector('.empty-state-text').textContent = 'No lap time data available for this selection.';
    }
    return;
  }

  const lapNumbers = laps.map(l => l.lap);
  const lapTimes = laps.map(l => l.time);
  const compounds = laps.map(l => l.compound || 'UNKNOWN');

  // Color each point by tyre compound
  const pointColors = compounds.map(c => COMPOUND_COLORS[c] || COMPOUND_COLORS.UNKNOWN);

  const driver = allDrivers.find(d => d.code === driverCode);
  const color = driver ? utils.getTeamColor(driver.team) : '#e10600';

  const ctx = canvas.getContext('2d');

  lapTimeChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: lapNumbers,
      datasets: [{
        label: `${driverCode} Lap Time`,
        data: lapTimes,
        borderColor: color,
        backgroundColor: `${color}22`,
        pointBackgroundColor: pointColors,
        pointBorderColor: pointColors,
        pointRadius: 3,
        pointHoverRadius: 6,
        borderWidth: 2,
        fill: true,
        tension: 0.3,
      }]
    },
    options: {
      animation: { duration: 1200, easing: 'easeOutQuart' },
      plugins: {
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const lap = laps[ctx.dataIndex];
              return [
                `Time: ${utils.formatLapTime(lap.time)}`,
                `Tyre: ${lap.compound || 'Unknown'}`,
                `Tyre Age: ${lap.tyre_age || '?'} laps`,
              ];
            }
          }
        }
      },
      scales: {
        x: {
          title: { display: true, text: 'Lap' },
          grid: { color: 'rgba(255,255,255,0.04)' },
        },
        y: {
          title: { display: true, text: 'Lap Time (s)' },
          grid: { color: 'rgba(255,255,255,0.04)' },
        }
      }
    }
  });
}

/* ═══════════════════════════════════════════════════════════════════════════════
   TYRE STRATEGY HEATMAP (Custom Canvas)
   ═══════════════════════════════════════════════════════════════════════════════ */
function setupTyreHeatmap() {
  const btn = document.getElementById('th-load');
  if (!btn) return;

  btn.addEventListener('click', loadTyreHeatmap);
}

async function loadTyreHeatmap() {
  const circuitId = document.getElementById('th-circuit')?.value;
  const emptyEl = document.getElementById('tyres-empty');

  if (!circuitId) {
    return;
  }

  if (emptyEl) emptyEl.style.display = 'none';

  try {
    const data = await api.get(`/api/analytics/tyres?circuit=${circuitId}`);
    renderTyreHeatmap(data);
  } catch (err) {
    console.error('Failed to load tyre strategy:', err);
    if (emptyEl) {
      emptyEl.style.display = '';
      const emptyText = emptyEl.querySelector('.empty-state-text') || emptyEl;
      emptyText.textContent = 'Failed to load tyre data.';
    }
  }
}

function renderTyreHeatmap(data) {
  const canvas = document.getElementById('tyres-heatmap');
  if (!canvas) return;

  const strategies = data.strategies || [];
  if (strategies.length === 0) {
    const emptyEl = document.getElementById('tyres-empty');
    if (emptyEl) {
      emptyEl.style.display = '';
      emptyEl.querySelector('.empty-state-text').textContent = 'No tyre strategy data available.';
    }
    return;
  }

  // Compute start_lap and end_lap for each stint (API gives {stint, compound, laps})
  let maxLap = 0;
  strategies.forEach(s => {
    let cumLap = 0;
    s.stints.forEach(stint => {
      stint.start_lap = cumLap + 1;
      stint.end_lap = cumLap + (stint.laps || 1);
      cumLap = stint.end_lap;
      if (cumLap > maxLap) maxLap = cumLap;
    });
  });

  if (maxLap === 0) maxLap = 60; // fallback

  const rowHeight = 28;
  const labelWidth = 60;
  const lapWidth = 16;
  const headerHeight = 24;
  const totalWidth = labelWidth + maxLap * lapWidth + 10;
  const totalHeight = headerHeight + strategies.length * rowHeight + 10;

  // Set canvas size
  const dpr = window.devicePixelRatio || 1;
  canvas.width = totalWidth * dpr;
  canvas.height = totalHeight * dpr;
  canvas.style.width = `${totalWidth}px`;
  canvas.style.height = `${totalHeight}px`;

  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  // Clear
  ctx.clearRect(0, 0, totalWidth, totalHeight);

  // Header
  ctx.fillStyle = '#606070';
  ctx.font = '10px Inter, sans-serif';
  ctx.textAlign = 'center';
  for (let lap = 1; lap <= maxLap; lap += 5) {
    ctx.fillText(lap.toString(), labelWidth + (lap - 0.5) * lapWidth, headerHeight - 6);
  }

  // Rows
  strategies.forEach((strategy, i) => {
    const y = headerHeight + i * rowHeight;

    // Driver label
    ctx.fillStyle = '#a0a0b0';
    ctx.font = '11px Outfit, sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText(strategy.driver || `D${i + 1}`, labelWidth - 8, y + rowHeight / 2 + 4);

    // Stints
    strategy.stints.forEach(stint => {
      const x = labelWidth + (stint.start_lap - 1) * lapWidth;
      const w = (stint.end_lap - stint.start_lap + 1) * lapWidth;
      const compound = (stint.compound || 'UNKNOWN').toUpperCase();
      const color = COMPOUND_COLORS[compound] || COMPOUND_COLORS.UNKNOWN;

      ctx.fillStyle = color;
      ctx.globalAlpha = 0.85;

      // Rounded rect
      const r = 3;
      const h = rowHeight - 4;
      const ry = y + 2;
      ctx.beginPath();
      ctx.moveTo(x + r, ry);
      ctx.lineTo(x + w - r, ry);
      ctx.quadraticCurveTo(x + w, ry, x + w, ry + r);
      ctx.lineTo(x + w, ry + h - r);
      ctx.quadraticCurveTo(x + w, ry + h, x + w - r, ry + h);
      ctx.lineTo(x + r, ry + h);
      ctx.quadraticCurveTo(x, ry + h, x, ry + h - r);
      ctx.lineTo(x, ry + r);
      ctx.quadraticCurveTo(x, ry, x + r, ry);
      ctx.closePath();
      ctx.fill();

      ctx.globalAlpha = 1;

      // Label inside
      if (w > 30) {
        ctx.fillStyle = compound === 'HARD' ? '#222' : '#fff';
        ctx.font = 'bold 9px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(compound.substring(0, 1), x + w / 2, y + rowHeight / 2 + 3);
      }
    });
  });
}

/* ═══════════════════════════════════════════════════════════════════════════════
   DNF RISK GAUGES (Custom Canvas)
   ═══════════════════════════════════════════════════════════════════════════════ */
async function loadDNFGauges() {
  const container = document.getElementById('dnf-gauges');
  if (!container) return;

  try {
    const data = await api.get('/api/analytics/reliability');
    renderDNFGauges(data);
  } catch {
    container.innerHTML = '<p style="color:var(--text-muted);text-align:center;grid-column:1/-1;">Unable to load reliability data.</p>';
  }
}

function renderDNFGauges(data) {
  const container = document.getElementById('dnf-gauges');
  if (!container) return;

  // API returns a flat array of {code, name, team, team_color, dnf_rate_per_race, dnf_pct, reliability_rating}
  const drivers = Array.isArray(data) ? data : (data.drivers ? Object.entries(data.drivers).map(([code, info]) => ({code, ...info})) : []);
  if (drivers.length === 0) {
    container.innerHTML = '<p style="color:var(--text-muted);text-align:center;grid-column:1/-1;">No reliability data available.</p>';
    return;
  }
  container.innerHTML = '';

  drivers.forEach(d => {
    const rate = d.dnf_rate_per_race || d.dnf_rate || 0;
    const item = document.createElement('div');
    item.className = 'dnf-gauge';

    const canvasEl = document.createElement('canvas');
    canvasEl.width = 80;
    canvasEl.height = 50;
    item.appendChild(canvasEl);

    const label = document.createElement('div');
    label.className = 'dnf-gauge-label';
    label.textContent = d.code || d.name || '';
    item.appendChild(label);

    const value = document.createElement('div');
    value.className = 'dnf-gauge-value';
    value.textContent = `${(rate * 100).toFixed(0)}%`;
    value.style.color = d.team_color || utils.getTeamColor(d.team);
    item.appendChild(value);

    container.appendChild(item);

    // Draw gauge with requestAnimationFrame
    requestAnimationFrame(() => drawGauge(canvasEl, rate));
  });
}

function drawGauge(canvas, value) {
  const ctx = canvas.getContext('2d');
  const cx = canvas.width / 2;
  const cy = canvas.height - 4;
  const r = 32;
  const lineWidth = 6;

  // Background arc
  ctx.beginPath();
  ctx.arc(cx, cy, r, Math.PI, 0, false);
  ctx.strokeStyle = 'rgba(255,255,255,0.08)';
  ctx.lineWidth = lineWidth;
  ctx.lineCap = 'round';
  ctx.stroke();

  // Value arc
  const clampedValue = Math.min(1, Math.max(0, value));
  const endAngle = Math.PI + clampedValue * Math.PI;

  // Color gradient: green -> yellow -> red
  let color;
  if (clampedValue < 0.3) color = '#00e676';
  else if (clampedValue < 0.6) color = '#ffab00';
  else color = '#ff1744';

  ctx.beginPath();
  ctx.arc(cx, cy, r, Math.PI, endAngle, false);
  ctx.strokeStyle = color;
  ctx.lineWidth = lineWidth;
  ctx.lineCap = 'round';
  ctx.stroke();
}

/* ═══════════════════════════════════════════════════════════════════════════════
   DRIVER PERFORMANCE RADAR CHART
   ═══════════════════════════════════════════════════════════════════════════════ */
function setupRadarChart() {
  const select = document.getElementById('radar-driver');
  if (!select) return;

  select.addEventListener('change', () => {
    const code = select.value;
    if (code) renderRadarForDriver(code);
  });
}

function renderRadarForDriver(code) {
  const canvas = document.getElementById('radar-chart');
  if (!canvas || typeof Chart === 'undefined') return;

  if (radarChart) {
    radarChart.destroy();
    radarChart = null;
  }

  const driver = allDrivers.find(d => d.code === code);
  if (!driver) return;

  const stats = driver.stats || {};
  const color = utils.getTeamColor(driver.team);

  // Generate radar data from available stats (normalize to 0-100 scale)
  const maxWins = 15, maxPodiums = 25, maxPoints = 500;
  const labels = ['Race Pace', 'Qualifying', 'Consistency', 'Wet Performance', 'Reliability'];
  const values = [
    Math.min(100, ((stats.wins || 0) / maxWins) * 100 + 30),
    Math.min(100, 100 - (stats.avg_position || 10) * 5),
    Math.min(100, ((stats.podiums || 0) / maxPodiums) * 100 + 20),
    Math.min(100, Math.random() * 30 + 55), // Placeholder — real data from API
    Math.min(100, 100 - (stats.dnfs || 0) * 15),
  ];

  const ctx = canvas.getContext('2d');

  radarChart = new Chart(ctx, {
    type: 'radar',
    data: {
      labels,
      datasets: [{
        label: driver.name,
        data: values,
        backgroundColor: `${color}33`,
        borderColor: color,
        borderWidth: 2,
        pointBackgroundColor: color,
        pointRadius: 4,
        pointHoverRadius: 6,
      }]
    },
    options: {
      animation: { duration: 800 },
      scales: {
        r: {
          beginAtZero: true,
          max: 100,
          grid: { color: 'rgba(255,255,255,0.06)' },
          angleLines: { color: 'rgba(255,255,255,0.06)' },
          pointLabels: {
            font: { family: "'Outfit', sans-serif", size: 11, weight: '500' },
            color: '#a0a0b0',
          },
          ticks: { display: false },
        }
      },
      plugins: {
        legend: { display: false },
      }
    }
  });
}

/* ═══════════════════════════════════════════════════════════════════════════════
   PRE-RACE PREDICTIONS
   ═══════════════════════════════════════════════════════════════════════════════ */
function setupPredictions() {
  const select = document.getElementById('pred-circuit');
  const exportBtn = document.getElementById('prediction-export');

  if (select) {
    select.addEventListener('change', () => {
      if (select.value) loadPrediction(select.value);
    });
  }

  if (exportBtn) {
    exportBtn.addEventListener('click', exportPredictionPNG);
  }
}

async function loadPrediction(circuitId) {
  const subtitleEl = document.querySelector('#predictions .section-subtitle');

  try {
    const data = await api.get(`/api/predictions/${circuitId}`);
    renderPrediction(data);
  } catch (err) {
    console.error('Failed to load predictions:', err);
    if (subtitleEl) subtitleEl.textContent = 'Prediction unavailable';
  }
}

function renderPrediction(data) {
  const subtitleEl = document.querySelector('#predictions .section-subtitle');
  const winner = document.getElementById('pred-winner');
  const podium = document.getElementById('pred-podium');
  const fastest = document.getElementById('pred-fastest');
  const sc = document.getElementById('pred-sc');
  const pits = document.getElementById('pred-pits');
  const confBar = document.getElementById('pred-confidence-fill');
  const confValue = document.getElementById('pred-confidence-val');

  if (subtitleEl && data.circuit_name) {
    subtitleEl.textContent = `AI-powered outcome forecast for ${data.circuit_name}`;
  }

  // Extract predictions from the array
  const preds = data.predictions || [];
  const top1 = preds[0] || {};
  const top3 = preds.slice(0, 3);

  if (winner) {
    const winnerName = top1.driver_name || top1.code || '—';
    const winPct = top1.win_prob != null ? ` (${top1.win_prob}%)` : '';
    winner.textContent = winnerName + winPct;
  }

  if (podium && top3.length > 0) {
    podium.textContent = top3.map(p => p.code || p.driver_name).join(' → ');
  } else if (podium) {
    podium.textContent = '—';
  }

  // Fastest lap — use the driver with best avg position
  if (fastest) {
    const fastestDriver = preds.length > 0 ? (preds[0].code || preds[0].driver_name || '—') : '—';
    fastest.textContent = fastestDriver;
  }

  if (sc) sc.textContent = data.safety_car_predicted || 'Medium Probability';
  if (pits) pits.textContent = data.avg_pit_stops_predicted || '1.8 stops';

  // Confidence from winner's win probability
  const confidence = top1.win_prob != null ? top1.win_prob / 100 : 0.45;
  if (confBar) confBar.style.width = `${(confidence * 100).toFixed(0)}%`;
  if (confValue) confValue.textContent = `${(confidence * 100).toFixed(0)}%`;
}

/* ─── Export Prediction as PNG ────────────────────────────────────────────────── */
function exportPredictionPNG() {
  const card = document.getElementById('prediction-card');
  if (!card) return;

  // Simple canvas-based export
  try {
    const canvas = document.createElement('canvas');
    const width = 800;
    const height = 500;
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');

    // Background
    ctx.fillStyle = '#111118';
    ctx.fillRect(0, 0, width, height);

    // Border gradient
    const grad = ctx.createLinearGradient(0, 0, width, height);
    grad.addColorStop(0, '#e10600');
    grad.addColorStop(0.5, '#FF8000');
    grad.addColorStop(1, '#27F4D2');
    ctx.strokeStyle = grad;
    ctx.lineWidth = 3;
    ctx.strokeRect(2, 2, width - 4, height - 4);

    // Title
    ctx.fillStyle = '#f0f0f5';
    ctx.font = 'bold 28px Outfit, sans-serif';
    ctx.textAlign = 'center';
    const raceTitle = document.getElementById('prediction-race-name')?.textContent || 'Pre-Race Prediction';
    ctx.fillText(raceTitle, width / 2, 60);

    // Badge
    ctx.fillStyle = '#e10600';
    const badgeText = 'AI PREDICTION';
    ctx.font = 'bold 12px Inter, sans-serif';
    const badgeWidth = ctx.measureText(badgeText).width + 20;
    const bx = (width - badgeWidth) / 2;
    roundRect(ctx, bx, 75, badgeWidth, 22, 11);
    ctx.fill();
    ctx.fillStyle = '#fff';
    ctx.fillText(badgeText, width / 2, 91);

    // Data items
    const items = [
      ['PREDICTED WINNER', document.getElementById('pred-winner')?.textContent || '—'],
      ['PODIUM', document.getElementById('pred-podium')?.textContent || '—'],
      ['FASTEST LAP', document.getElementById('pred-fastest')?.textContent || '—'],
      ['SAFETY CARS', document.getElementById('pred-sc')?.textContent || '—'],
      ['PIT STOPS (AVG)', document.getElementById('pred-pits')?.textContent || '—'],
    ];

    const startY = 140;
    const itemSpacing = 65;

    items.forEach((item, i) => {
      const y = startY + i * itemSpacing;

      ctx.fillStyle = '#606070';
      ctx.font = '11px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(item[0], width / 2, y);

      ctx.fillStyle = '#f0f0f5';
      ctx.font = 'bold 22px Outfit, sans-serif';
      ctx.fillText(item[1], width / 2, y + 28);
    });

    // Confidence bar
    const confPct = document.getElementById('pred-confidence-value')?.textContent || '—';
    const barY = startY + items.length * itemSpacing + 20;
    ctx.fillStyle = '#606070';
    ctx.font = '11px Inter, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText('MODEL CONFIDENCE', 100, barY);
    ctx.textAlign = 'right';
    ctx.fillStyle = '#e10600';
    ctx.font = 'bold 14px Inter, sans-serif';
    ctx.fillText(confPct, width - 100, barY);

    // Footer
    ctx.fillStyle = '#404050';
    ctx.font = '10px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('HAMMERTIME — F1 Race Outcome Simulator', width / 2, height - 20);

    // Download
    const link = document.createElement('a');
    link.download = `hammertime-prediction-${Date.now()}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();

  } catch (err) {
    console.error('Export failed:', err);
  }
}

/* Helper: rounded rectangle */
function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

/* ═══════════════════════════════════════════════════════════════════════════════
   RACE DEBRIEFS LOGS
   ═══════════════════════════════════════════════════════════════════════════════ */
const PRECALCULATED_CIRCUITS = [
  'bahrain', 'saudi_arabia', 'australia', 'japan', 'emilia_romagna', 
  'miami', 'monaco', 'austria', 'azerbaijan', 'singapore', 
  'united_states', 'mexico', 'las_vegas', 'qatar', 'abu_dhabi'
];

async function initDebriefs() {
  const select = document.getElementById('debrief-circuit');
  const generateBtn = document.getElementById('debrief-generate');
  
  if (!select || !generateBtn) return;
  
  // Populate the select dropdown with only the supported circuits
  select.innerHTML = '<option value="">Select a race to debrief...</option>';
  allCircuits.forEach(c => {
    if (PRECALCULATED_CIRCUITS.includes(c.id.toLowerCase())) {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = c.name;
      select.appendChild(opt);
    }
  });

  generateBtn.addEventListener('click', async () => {
    const circuitId = select.value;
    if (!circuitId) {
      toast.show('Please select a circuit first.', 'warning');
      return;
    }
    
    generateBtn.disabled = true;
    generateBtn.textContent = 'Generating...';
    
    try {
      const reportData = await api.get(`/api/debrief-reports/${circuitId}`);
      if (reportData && !reportData.error) {
        renderDebriefReport(reportData);
        document.getElementById('debrief-report-area').style.display = 'block';
        toast.show('Strategic debrief report generated successfully.', 'success');
      } else {
        toast.show(reportData.error || 'Failed to generate report.', 'error');
      }
    } catch (err) {
      console.error('Failed to load debrief report:', err);
      toast.show('Error generating debrief report.', 'error');
    } finally {
      generateBtn.disabled = false;
      generateBtn.textContent = 'Generate Report';
    }
  });
}

function renderDebriefReport(data) {
  // Render Narrative
  const narrativeEl = document.getElementById('debrief-narrative');
  if (narrativeEl) {
    narrativeEl.textContent = data.narrative || 'No narrative available.';
  }

  // Render Pit Stop Performance Table
  const pitBody = document.getElementById('debrief-pit-body');
  if (pitBody) {
    pitBody.innerHTML = '';
    if (data.pit_performance && data.pit_performance.length > 0) {
      data.pit_performance.forEach(p => {
        const teamColor = utils.getTeamColor(p.team);
        const tr = document.createElement('tr');
        tr.style.setProperty('--team-color', teamColor);
        
        // Calculate pit laps
        let sum = 0;
        let pitLaps = [];
        for (let i = 0; i < p.stint_lengths.length - 1; i++) {
          sum += p.stint_lengths[i];
          pitLaps.push(sum);
        }
        const pitLapsStr = pitLaps.join(', ') || '—';
        
        tr.innerHTML = `
          <td><span class="team-color-bar" style="background:${teamColor}"></span>${utils.escapeHtml(p.driver_name)} <span style="font-size:0.75rem;color:var(--text-muted)">(${utils.escapeHtml(p.team)})</span></td>
          <td>${p.n_stops}</td>
          <td>${pitLapsStr}</td>
          <td>—</td>
          <td>${utils.escapeHtml(p.strategy)}</td>
        `;
        pitBody.appendChild(tr);
      });
    } else {
      pitBody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted)">No pit stop data available.</td></tr>';
    }
  }

  // Render Strategy Analysis
  const stratEl = document.getElementById('debrief-strategy');
  if (stratEl) {
    const strat = data.strategy_analysis;
    let distHtml = '';
    if (strat.strategy_distribution) {
      distHtml = '<ul style="margin: 10px 0 0 20px; color: var(--text-secondary); line-height: 1.6;">';
      for (const [key, count] of Object.entries(strat.strategy_distribution)) {
        distHtml += `<li><strong>${utils.escapeHtml(key)}</strong>: used by ${count} driver(s)</li>`;
      }
      distHtml += '</ul>';
    }
    
    stratEl.innerHTML = `
      <p>The most popular strategy was <strong style="color:var(--accent-cyan)">${utils.escapeHtml(strat.most_popular_strategy)}</strong>.</p>
      <p>Average pit stops per driver: <strong style="color:var(--text-primary)">${strat.avg_pit_stops}</strong></p>
      <p>Number of unique strategies deployed: <strong style="color:var(--text-primary)">${strat.unique_strategies}</strong></p>
      ${distHtml}
    `;
  }

  // Render Safety Car Impact
  const scEl = document.getElementById('debrief-sc-impact');
  if (scEl) {
    const sc = data.safety_car_impact;
    let lapsHtml = '';
    if (sc.affected_laps && sc.affected_laps.length > 0) {
      lapsHtml = '<table class="data-table" style="margin-top:12px;"><thead><tr><th>Lap</th><th>Avg Lap Time</th><th>Type</th></tr></thead><tbody>';
      sc.affected_laps.forEach(l => {
        lapsHtml += `<tr><td>Lap ${l.lap}</td><td>${l.avg_time}s</td><td><span class="schedule-status next" style="animation:none; background:rgba(0, 240, 255, 0.15); color:var(--accent-cyan); border:1px solid rgba(0, 240, 255, 0.3); padding:2px 8px; border-radius:4px;">${utils.escapeHtml(l.likely_event)}</span></td></tr>`;
      });
      lapsHtml += '</tbody></table>';
    }
    scEl.innerHTML = `
      <p>${utils.escapeHtml(sc.impact_summary)}</p>
      ${lapsHtml}
    `;
  }

  // Render Overtakes
  const overtakesEl = document.getElementById('debrief-overtakes');
  if (overtakesEl) {
    const ov = data.overtakes_summary;
    overtakesEl.innerHTML = `
      <p>Estimated total overtakes: <strong style="color:var(--accent-green)">${ov.estimated_total}</strong></p>
      <p>Overtake Difficulty Index: <strong style="color:var(--accent-cyan)">${ov.circuit_overtake_index}</strong> (${utils.escapeHtml(ov.difficulty)})</p>
    `;
  }

  // Render Team Execution Scores (Consistency + Progress Bar)
  const scoresEl = document.getElementById('debrief-team-scores');
  if (scoresEl) {
    scoresEl.innerHTML = '';
    if (data.team_execution_scores && data.team_execution_scores.length > 0) {
      data.team_execution_scores.forEach(t => {
        const div = document.createElement('div');
        div.className = 'execution-bar-wrap';
        
        let ratingClass = 'poor';
        if (t.execution_rating === 'Excellent') ratingClass = 'excellent';
        else if (t.execution_rating === 'Good') ratingClass = 'good';
        else if (t.execution_rating === 'Average') ratingClass = 'average';
        
        div.innerHTML = `
          <div class="execution-bar-label">
            <span style="color:${t.team_color}; font-weight:600;">${utils.escapeHtml(t.team)}</span>
            <span>${t.execution_rating} (${t.consistency_score}%)</span>
          </div>
          <div class="execution-bar">
            <div class="execution-bar-fill ${ratingClass}" style="width:${t.consistency_score}%;"></div>
          </div>
        `;
        scoresEl.appendChild(div);
      });
    } else {
      scoresEl.innerHTML = '<p style="color:var(--text-muted)">No team execution scores available.</p>';
    }
  }
}
