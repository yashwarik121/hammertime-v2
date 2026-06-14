/* ═══════════════════════════════════════════════════════════════════════════════
   HAMMERTIME — app.js
   Main application controller: API wrapper, SPA navigation, utilities, init
   ═══════════════════════════════════════════════════════════════════════════════ */

'use strict';

/* ─── Global State ───────────────────────────────────────────────────────────── */
var allDrivers = [];
var allCircuits = [];

async function loadSharedData() {
  try {
    allDrivers = await api.get('/api/drivers');
  } catch (err) {
    console.error('Failed to load global drivers:', err);
    allDrivers = [];
  }
  try {
    allCircuits = await api.get('/api/circuits');
  } catch (err) {
    console.error('Failed to load global circuits:', err);
    allCircuits = [];
  }
}

/* ─── Team Color Map ─────────────────────────────────────────────────────────── */
const TEAM_COLORS = {
  'Red Bull Racing':  '#3671C6',
  'Red Bull':         '#3671C6',
  'Ferrari':          '#E8002D',
  'Mercedes':         '#27F4D2',
  'McLaren':          '#FF8000',
  'Aston Martin':     '#229971',
  'Alpine':           '#FF87BC',
  'Haas F1 Team':     '#B6BABD',
  'Haas':             '#B6BABD',
  'RB':               '#6692FF',
  'Racing Bulls':     '#6692FF',
  'Williams':         '#64C4FF',
  'Kick Sauber':      '#52E252',
  'Sauber':           '#52E252',
};

const COUNTRY_FLAGS = {
  NL: '🇳🇱', NZ: '🇳🇿', MC: '🇲🇨', GB: '🇬🇧', IT: '🇮🇹',
  AU: '🇦🇺', ES: '🇪🇸', CA: '🇨🇦', FR: '🇫🇷', JP: '🇯🇵',
  TH: '🇹🇭', DE: '🇩🇪', BR: '🇧🇷', FI: '🇫🇮', CN: '🇨🇳',
  DK: '🇩🇰', MX: '🇲🇽', US: '🇺🇸', AR: '🇦🇷',
};

/* ─── Section IDs (navigation order) ────────────────────────────────────────── */
const SECTION_IDS = [
  'command-center',
  'drivers',
  'strategy-lab',
  'simulator',
  'standings',
  'schedule',
  'analytics',
  'predictions',
  'debriefs',
];

/* ─── API Wrapper ────────────────────────────────────────────────────────────── */
const api = {
  baseUrl: '',

  async get(url) {
    try {
      const res = await fetch(`${this.baseUrl}${url}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      return await res.json();
    } catch (err) {
      console.error(`[API GET] ${url}`, err);
      throw err;
    }
  },

  async post(url, body) {
    try {
      const res = await fetch(`${this.baseUrl}${url}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      return await res.json();
    } catch (err) {
      console.error(`[API POST] ${url}`, err);
      throw err;
    }
  }
};

/* ─── Toast Notifications ────────────────────────────────────────────────────── */
const toast = {
  container: null,

  init() {
    this.container = document.getElementById('toast-container');
  },

  show(message, type = 'info', duration = 4000) {
    if (!this.container) this.init();
    const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.innerHTML = `<span class="toast-icon">${icons[type] || icons.info}</span><span>${message}</span>`;
    this.container.appendChild(el);

    setTimeout(() => {
      el.classList.add('toast-hide');
      el.addEventListener('animationend', () => el.remove());
      // Fallback removal if animation fails
      setTimeout(() => el.remove(), 500);
    }, duration);
  }
};

/* ─── Loading Overlay ────────────────────────────────────────────────────────── */
const loading = {
  el: null,

  init() {
    this.el = document.getElementById('loading-overlay');
  },

  show() {
    if (this.el) this.el.classList.remove('hidden');
  },

  hide() {
    if (this.el) this.el.classList.add('hidden');
  }
};

/* ─── Skeleton Loader Utility ────────────────────────────────────────────────── */
const skeleton = {
  cards(container, count = 20) {
    const el = document.getElementById(container);
    if (!el) return;
    el.innerHTML = Array.from({ length: count }, () =>
      '<div class="skeleton skeleton-card"></div>'
    ).join('');
  },

  clear(container) {
    const el = document.getElementById(container);
    if (el) el.innerHTML = '';
  }
};

/* ─── Utilities ──────────────────────────────────────────────────────────────── */
const utils = {
  formatNumber(n) {
    if (n == null) return '—';
    return Number(n).toLocaleString('en-US');
  },

  formatPercentage(n, decimals = 1) {
    if (n == null) return '—';
    return `${(Number(n)).toFixed(decimals)}%`;
  },

  formatLapTime(seconds) {
    if (seconds == null || seconds <= 0) return '—';
    const mins = Math.floor(seconds / 60);
    const secs = (seconds % 60).toFixed(3);
    return mins > 0 ? `${mins}:${secs.padStart(6, '0')}` : `${secs}s`;
  },

  getTeamColor(team) {
    if (!team) return '#ffffff';
    return TEAM_COLORS[team] || '#ffffff';
  },

  getFlag(nationality) {
    return COUNTRY_FLAGS[nationality] || '🏴';
  },

  debounce(fn, ms = 300) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), ms);
    };
  },

  escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }
};

/* ─── SPA Navigation ─────────────────────────────────────────────────────────── */
const nav = {
  links: null,
  hamburger: null,
  linksContainer: null,

  init() {
    this.links = document.querySelectorAll('.nav-tab');
    this.hamburger = document.getElementById('hamburger-btn');
    this.linksContainer = document.getElementById('nav-tabs');

    // Tab click handler — show/hide sections
    this.links.forEach(link => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        const sectionId = link.getAttribute('data-section');
        this.switchSection(sectionId);
        this.setActive(link);
        // Close mobile menu
        if (this.linksContainer) this.linksContainer.classList.remove('open');
        if (this.hamburger) this.hamburger.classList.remove('active');
        // Update URL hash
        window.location.hash = sectionId;
      });
    });

    // Hamburger toggle
    if (this.hamburger) {
      this.hamburger.addEventListener('click', () => {
        this.linksContainer.classList.toggle('open');
        this.hamburger.classList.toggle('active');
      });
    }

    // Interactive Logo engine rev synthesizer
    const logoEl = document.getElementById('nav-interactive-logo');
    if (logoEl) {
      logoEl.addEventListener('click', () => {
        try {
          const ctx = new (window.AudioContext || window.webkitAudioContext)();
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          
          osc.type = 'sawtooth';
          osc.frequency.setValueAtTime(85, ctx.currentTime);
          osc.frequency.exponentialRampToValueAtTime(820, ctx.currentTime + 0.12);
          osc.frequency.exponentialRampToValueAtTime(160, ctx.currentTime + 0.45);
          
          gain.gain.setValueAtTime(0.25, ctx.currentTime);
          gain.gain.linearRampToValueAtTime(0.01, ctx.currentTime + 0.5);
          
          osc.connect(gain);
          gain.connect(ctx.destination);
          
          osc.start();
          osc.stop(ctx.currentTime + 0.5);
        } catch (e) {
          console.warn('Audio Context not allowed or failed:', e);
        }
      });
    }

    // Handle initial hash
    const hash = window.location.hash.replace('#', '');
    if (hash && SECTION_IDS.includes(hash)) {
      this.switchSection(hash);
      const link = document.querySelector(`.nav-tab[data-section="${hash}"]`);
      if (link) this.setActive(link);
    }
  },

  switchSection(sectionId) {
    // Hide all sections
    SECTION_IDS.forEach(id => {
      const section = document.getElementById(id);
      if (section) {
        section.classList.remove('active');
        section.style.display = 'none';
      }
    });

    // Show the target section
    const target = document.getElementById(sectionId);
    if (target) {
      target.classList.add('active');
      target.style.display = 'block';
      // Scroll to top smoothly
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  },

  setActive(activeLink) {
    this.links.forEach(l => l.classList.remove('active'));
    activeLink.classList.add('active');
  }
};

/* ─── Status Check ───────────────────────────────────────────────────────────── */
const status = {
  async check() {
    const dot = document.getElementById('nav-status-dot') || document.getElementById('status-dot');
    const text = document.getElementById('status-text');
    try {
      const data = await api.get('/api/status');
      if (dot) {
        dot.classList.add('online');
        dot.classList.add('connected');
      }
      if (text) text.textContent = data.data_loaded ? 'Systems Online' : 'Loading Data…';
      return data;
    } catch {
      if (dot) {
        dot.classList.remove('online');
        dot.classList.remove('connected');
      }
      if (text) text.textContent = 'Offline';
      return null;
    }
  }
};

/* ─── Chart.js Defaults ──────────────────────────────────────────────────────── */
const configureChartDefaults = () => {
  if (typeof Chart === 'undefined') return;

  Chart.defaults.color = '#8b8b9e';
  Chart.defaults.borderColor = 'rgba(255,255,255,0.06)';
  Chart.defaults.font.family = "'Inter', sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.padding = 16;
  Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(12,12,20,0.95)';
  Chart.defaults.plugins.tooltip.borderColor = 'rgba(0,240,255,0.15)';
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.plugins.tooltip.padding = 12;
  Chart.defaults.plugins.tooltip.titleFont = { family: "'Outfit', sans-serif", weight: '600' };
  Chart.defaults.animation.duration = 1000;
  Chart.defaults.responsive = true;
  Chart.defaults.maintainAspectRatio = false;
};

/* ─── Global Chart Resize Handler ────────────────────────────────────────────── */
const setupChartResize = () => {
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      Object.values(Chart.instances || {}).forEach(chart => {
        try { chart.resize(); } catch {}
      });
    }, 250);
  });
};

/* ─── App Init ───────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', async () => {
  loading.init();
  toast.init();
  nav.init();
  configureChartDefaults();
  setupChartResize();

  // Check API status
  const apiStatus = await status.check();

  // Load global shared data
  await loadSharedData();

  // Initialize all modules
  const modules = [
    { name: 'Weekend Intel', fn: typeof initWeekendIntel === 'function' ? initWeekendIntel : null },
    { name: 'Driver Grid', fn: typeof initDriverGrid === 'function' ? initDriverGrid : null },
    { name: 'Simulator', fn: typeof initSimulator === 'function' ? initSimulator : null },
    { name: 'Standings', fn: typeof initStandings === 'function' ? initStandings : null },
    { name: 'Charts', fn: typeof initCharts === 'function' ? initCharts : null },
    { name: 'Schedule', fn: typeof initSchedule === 'function' ? initSchedule : null },
    { name: 'Strategy Lab', fn: typeof initStrategyLab === 'function' ? initStrategyLab : null },
    { name: 'Debriefs', fn: typeof initDebriefs === 'function' ? initDebriefs : null },
  ];

  for (const mod of modules) {
    if (mod.fn) {
      try {
        await mod.fn();
      } catch (err) {
        console.error(`${mod.name} init failed:`, err);
      }
    }
  }

  // Hide loading overlay
  loading.hide();

  // Initialize custom F1 cursor
  initCustomCursor();

  // Show Command Center as default
  if (!window.location.hash || !SECTION_IDS.includes(window.location.hash.replace('#', ''))) {
    nav.switchSection('command-center');
  }

  // Ensure we cleanup any leftover theme state and enforce dark HUD theme
  localStorage.removeItem('theme');
  document.body.classList.remove('light-theme');
});

/* ─── Custom F1 HUD Cursor Controller ─── */
function initCustomCursor() {
  const cursor = document.getElementById('custom-f1-cursor');
  if (!cursor) return;

  // Check if coarse pointer (touch device) - if so, hide custom cursor
  if (window.matchMedia('(pointer: coarse)').matches) {
    cursor.style.display = 'none';
    return;
  }

  let mouseX = -100;
  let mouseY = -100;
  let currentX = -100;
  let currentY = -100;
  let angle = 0;
  let isMoving = false;
  let moveTimeout;

  // Track mouse coordinates
  window.addEventListener('mousemove', (e) => {
    mouseX = e.clientX;
    mouseY = e.clientY;
    
    if (!cursor.classList.contains('active')) {
      cursor.classList.add('active');
      currentX = mouseX;
      currentY = mouseY;
    }

    isMoving = true;
    clearTimeout(moveTimeout);
    moveTimeout = setTimeout(() => {
      isMoving = false;
    }, 200);
  });

  // Handle click animations
  window.addEventListener('mousedown', () => {
    cursor.classList.add('clicking');
  });

  window.addEventListener('mouseup', () => {
    cursor.classList.remove('clicking');
  });

  // Track hovering over clickable items
  const clickableSelectors = 'a, button, select, input, textarea, .nav-tab, .driver-card, .standings-tab, .whatif-scenario, .nav-interactive-logo, .detail-close, .btn, .btn-remove-stint';
  
  document.addEventListener('mouseover', (e) => {
    if (e.target.closest(clickableSelectors)) {
      cursor.classList.add('hovering');
    }
  });

  document.addEventListener('mouseout', (e) => {
    if (!e.target.closest(clickableSelectors)) {
      cursor.classList.remove('hovering');
    }
  });

  // Smooth animation loop using requestAnimationFrame
  function animateCursor() {
    // Distance from target
    const dx = mouseX - currentX;
    const dy = mouseY - currentY;

    // Smooth interpolation (easing)
    currentX += dx * 0.16;
    currentY += dy * 0.16;

    // Calculate rotation angle based on movement delta
    if (isMoving && Math.sqrt(dx*dx + dy*dy) > 1.5) {
      const targetAngle = Math.atan2(dy, dx) * 180 / Math.PI + 90;
      
      // Interpolate rotation angle to avoid sudden flips
      let angleDiff = targetAngle - angle;
      // Normalize angle difference to -180 to 180
      while (angleDiff < -180) angleDiff += 360;
      while (angleDiff > 180) angleDiff -= 360;
      
      angle += angleDiff * 0.25;
    }

    // Apply transformation
    cursor.style.transform = `translate3d(${currentX - 18}px, ${currentY - 18}px, 0) rotate(${angle}deg)`;

    requestAnimationFrame(animateCursor);
  }

  requestAnimationFrame(animateCursor);
}
