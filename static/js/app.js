/* ═══════════════════════════════════════════════════════════════════════════════
   HAMMERTIME — app.js
   Main application controller: API wrapper, navigation, utilities, init
   ═══════════════════════════════════════════════════════════════════════════════ */

'use strict';

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
  DK: '🇩🇰', MX: '🇲🇽', US: '🇺🇸',
};

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
      toast.show(`Failed to load data: ${err.message}`, 'error');
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
      toast.show(`Simulation failed: ${err.message}`, 'error');
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
    el.className = `toast ${type}`;
    el.innerHTML = `<span class="toast-icon">${icons[type] || icons.info}</span><span>${message}</span>`;
    this.container.appendChild(el);

    setTimeout(() => {
      el.classList.add('removing');
      el.addEventListener('animationend', () => el.remove());
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
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }
};

/* ─── Navigation ─────────────────────────────────────────────────────────────── */
const nav = {
  links: null,
  sections: null,
  hamburger: null,
  linksContainer: null,

  init() {
    this.links = document.querySelectorAll('.nav-links a');
    this.sections = document.querySelectorAll('.section');
    this.hamburger = document.getElementById('nav-hamburger');
    this.linksContainer = document.getElementById('nav-links');

    // Smooth scroll
    this.links.forEach(link => {
      link.addEventListener('click', (e) => {
        e.preventDefault();
        const sectionId = link.getAttribute('data-section');
        const target = document.getElementById(sectionId);
        if (target) {
          target.scrollIntoView({ behavior: 'smooth' });
          this.setActive(link);
          // Close mobile menu
          if (this.linksContainer) this.linksContainer.classList.remove('open');
        }
      });
    });

    // Hamburger toggle
    if (this.hamburger) {
      this.hamburger.addEventListener('click', () => {
        this.linksContainer.classList.toggle('open');
      });
    }

    // Active link tracking on scroll
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const id = entry.target.id;
          const link = document.querySelector(`.nav-links a[data-section="${id}"]`);
          if (link) this.setActive(link);
        }
      });
    }, { rootMargin: '-30% 0px -60% 0px' });

    this.sections.forEach(section => observer.observe(section));
  },

  setActive(activeLink) {
    this.links.forEach(l => l.classList.remove('active'));
    activeLink.classList.add('active');
  }
};

/* ─── Section Visibility Animation ───────────────────────────────────────────── */
const sectionAnimator = {
  init() {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
        }
      });
    }, { threshold: 0.08 });

    document.querySelectorAll('.section').forEach(section => {
      observer.observe(section);
    });
  }
};

/* ─── Status Check ───────────────────────────────────────────────────────────── */
const status = {
  async check() {
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');
    try {
      const data = await api.get('/api/status');
      if (dot) dot.classList.add('online');
      if (text) text.textContent = data.data_loaded ? 'Data Ready' : 'Loading Data…';
      return data;
    } catch {
      if (dot) dot.classList.remove('online');
      if (text) text.textContent = 'Offline';
      return null;
    }
  }
};

/* ─── Chart.js Defaults ──────────────────────────────────────────────────────── */
const configureChartDefaults = () => {
  if (typeof Chart === 'undefined') return;

  Chart.defaults.color = '#a0a0b0';
  Chart.defaults.borderColor = 'rgba(255,255,255,0.06)';
  Chart.defaults.font.family = "'Inter', sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.padding = 16;
  Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(17,17,24,0.95)';
  Chart.defaults.plugins.tooltip.borderColor = 'rgba(255,255,255,0.1)';
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
  sectionAnimator.init();
  configureChartDefaults();
  setupChartResize();

  // Check API status
  const apiStatus = await status.check();

  // Initialize modules (they each check for their own dependencies)
  try {
    if (typeof initDriverGrid === 'function') await initDriverGrid();
  } catch (err) {
    console.error('Driver grid init failed:', err);
  }

  try {
    if (typeof initSimulator === 'function') await initSimulator();
  } catch (err) {
    console.error('Simulator init failed:', err);
  }

  try {
    if (typeof initStandings === 'function') await initStandings();
  } catch (err) {
    console.error('Standings init failed:', err);
  }

  try {
    if (typeof initCharts === 'function') await initCharts();
  } catch (err) {
    console.error('Charts init failed:', err);
  }

  try {
    if (typeof initSchedule === 'function') await initSchedule();
  } catch (err) {
    console.error('Schedule init failed:', err);
  }

  // Hide loading overlay
  loading.hide();

  // Handle hash navigation on load
  if (window.location.hash) {
    const target = document.querySelector(window.location.hash);
    if (target) {
      setTimeout(() => target.scrollIntoView({ behavior: 'smooth' }), 500);
    }
  }
});
