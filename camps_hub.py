"""Summer Camps hub (/summer-camps/) for NYC Events.

Synced with the Boston Summer Camps hub:
- Left-sidebar `<select>` filters (Format, Borough/Area, Child's Age, Type of Camp, Cost, Status)
- "Sort by Distance" (Near Me) with NYC starting points
- List / Leaflet Map toggle
- Next sign-up dates panel with Google Calendar & iCal export
- Save / bookmark camps in localStorage
- Google Maps links for every camp location
"""

import json
from datetime import datetime, timedelta
from html import escape
from urllib.parse import quote, quote_plus

from camps import AREAS, KINDS, load_camps
from scrapers import EASTERN

CARD_LIMIT = 200

_CAMPS_HERO_ART = """<svg class="camps-hero-art" viewBox="0 0 900 200" aria-hidden="true" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="camps-sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#bae6fd"/>
      <stop offset="60%" stop-color="#e0f2fe"/>
      <stop offset="100%" stop-color="#fef3c7"/>
    </linearGradient>
    <linearGradient id="camps-lake" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#0284c7"/>
    </linearGradient>
    <linearGradient id="camps-sun" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#fde047"/>
      <stop offset="100%" stop-color="#f59e0b"/>
    </linearGradient>
  </defs>
  <rect width="900" height="200" fill="url(#camps-sky)"/>
  <circle cx="450" cy="90" r="46" fill="url(#camps-sun)" opacity="0.95"/>
  <circle cx="450" cy="90" r="65" fill="#fde047" opacity="0.25"/>
  <polygon points="0,150 90,105 210,145 320,95 450,135 560,90 690,140 780,100 900,150 900,200 0,200" fill="#93c5fd" opacity="0.5"/>
  <polygon points="0,165 140,120 280,160 410,115 540,155 670,110 820,160 900,135 900,200 0,200" fill="#60a5fa" opacity="0.4"/>
  <rect x="0" y="150" width="900" height="50" fill="url(#camps-lake)"/>
  <polygon points="20,165 35,115 50,165" fill="#14532d"/>
  <polygon points="40,165 58,105 76,165" fill="#166534"/>
  <polygon points="65,170 82,120 100,170" fill="#15803d"/>
  <polygon points="90,172 105,130 120,172" fill="#166534"/>
  <polygon points="110,175 125,135 140,175" fill="#14532d"/>
  <polygon points="760,175 775,135 790,175" fill="#14532d"/>
  <polygon points="780,172 795,125 810,172" fill="#166534"/>
  <polygon points="800,170 818,115 836,170" fill="#15803d"/>
  <polygon points="825,165 842,105 860,165" fill="#166534"/>
  <polygon points="850,165 865,118 880,165" fill="#14532d"/>
  <g transform="translate(420, 165)">
    <path d="M 0,12 C 15,18 45,18 60,12 C 55,20 20,20 0,12 Z" fill="#dc2626"/>
    <polygon points="24,10 26,1 28,10" fill="#fef08a"/>
    <polygon points="34,10 36,1 38,10" fill="#fef08a"/>
    <line x1="20" y1="8" x2="42" y2="18" stroke="#78350f" stroke-width="2"/>
  </g>
  <polygon points="145,178 165,145 185,178" fill="#ea580c"/>
  <polygon points="165,145 185,178 178,178 165,152" fill="#c2410c"/>
  <polygon points="158,162 165,152 172,162 165,178" fill="#431407"/>
  <g transform="translate(200, 172)">
    <line x1="-6" y1="4" x2="6" y2="-2" stroke="#78350f" stroke-width="2.5"/>
    <line x1="-6" y1="-2" x2="6" y2="4" stroke="#78350f" stroke-width="2.5"/>
    <polygon points="-4,2 0,-8 4,2" fill="#ef4444"/>
    <polygon points="-2,2 0,-5 2,2" fill="#facc15"/>
  </g>
  <g transform="translate(450, 26)">
    <rect x="-120" y="-12" width="240" height="24" rx="12" fill="#ffffff" stroke="#15803d" stroke-width="1.5" opacity="0.95"/>
    <text x="0" y="4" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="11" font-weight="800" fill="#15803d" letter-spacing="1.5">SUMMER CAMPS</text>
  </g>
</svg>"""

_CAMPS_CSS = """
  .camps-hub {
    --bg: #f6f8f5; --card: #ffffff; --card-hover: #ffffff; --fg: #17261b; --muted: #4a5a4f;
    --accent: #166534; --border: #d5dfd6; --amber-bg: #fdf3d7; --amber-fg: #6b4b00;
    background: var(--bg) !important; color: var(--fg) !important;
  }
  .camps-hub header {
    background: #f6f8f5 !important;
    border-bottom: 1px solid var(--border) !important;
    position: static;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px 16px;
    padding: 14px 20px;
  }
  .camps-hub .logo { color: #14532d !important; font-weight: 800; white-space: nowrap; font-size: 16px; text-decoration: none; }
  .camps-hub .logo span { color: #c2410c !important; }
  .camps-hub .hub-nav a {
    box-sizing: border-box;
    color: var(--muted);
    text-decoration: none;
    padding: 6px 12px;
    border-radius: 999px;
    font-weight: 600;
    transition: all 0.15s ease;
    display: inline-flex;
    align-items: center;
    border: 1px solid transparent;
    white-space: nowrap;
  }
  .camps-hub .hub-nav a:hover {
    color: var(--accent);
    background: rgba(22, 101, 52, 0.08);
    border-color: var(--border);
  }
  .camps-hub .hub-nav a.active {
    color: #fff;
    background: var(--accent);
    font-weight: 700;
  }
  .camps-hub main { max-width: 1120px; padding-top: 20px; font-size: 16px; line-height: 1.5; }
  .camps-hub .hero { border: 1px solid var(--border); background: #fff; border-radius: 16px; overflow: hidden; margin-bottom: 20px; padding: 0; text-align: left; }
  .camps-hero-art { display: block; width: 100%; height: 120px; }
  .camps-hero-copy { padding: 18px 22px 22px; }
  .camps-hub .hero h1 { font-size: clamp(28px, 6vw, 40px); font-weight: 800; margin: 0 0 6px; color: #14532d; letter-spacing: -0.01em; }
  .camps-hub .hero h1 small { display: block; font-size: 0.45em; font-weight: 700; color: #3f6f52; letter-spacing: 0; margin-top: 4px; }
  .camps-hub .hero p { color: var(--muted); font-size: 17px; margin: 0 0 10px; max-width: 720px; }
  .camps-stats { margin: 0; font-size: 15px; font-weight: 600; color: var(--fg); }
  .camps-layout {
    display: grid;
    grid-template-columns: 260px minmax(0, 1fr);
    gap: 26px;
    align-items: start;
    margin-bottom: 24px;
  }
  .camps-sidebar {
    position: sticky;
    top: 16px;
    background: #fff;
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 16px 14px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.03);
  }
  .camps-filter-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }
  .camps-sidebar-title {
    font-size: 14px;
    font-weight: 800;
    color: #14532d;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin: 0;
  }
  .camp-reset-btn {
    font-size: 12.5px;
    font-weight: 700;
    color: #c2410c;
  }
  .camps-filters {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .camp-filter-group {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .camp-filter-label {
    font-size: 11.5px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: var(--muted);
  }
  .camps-sidebar .camp-select {
    width: 100%;
    box-sizing: border-box;
  }
  .camp-near-btn {
    appearance: none;
    background: #eaf5ed;
    border: 1px solid #86efac;
    color: #14532d;
    font: inherit;
    font-size: 13px;
    font-weight: 700;
    padding: 7px 12px;
    border-radius: 8px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    transition: all 0.15s ease;
    width: 100%;
  }
  .camp-near-btn:hover {
    background: #166534;
    color: #fff;
    border-color: #166534;
  }
  .camp-near-info {
    font-size: 11.5px;
    color: #15803d;
    font-weight: 600;
    margin-top: 4px;
    line-height: 1.3;
  }
  .camp-origin-select {
    margin-top: 4px;
    font-size: 12px;
  }
  .camps-main-col { min-width: 0; }
  .camp-panel { background: #fff; border: 1px solid var(--border); border-radius: 16px; padding: 18px 20px; margin-bottom: 20px; }
  .camp-panel h2 { font-size: 22px; margin: 0 0 4px; color: #14532d; }
  .camp-panel > p { margin: 0 0 12px; color: var(--muted); }
  .camp-date-list { list-style: none; margin: 0; padding: 0; }
  .camp-date-list li { display: grid; grid-template-columns: 190px minmax(0, 1fr) auto; gap: 4px 14px; padding: 12px 0; border-top: 1px solid #e7ede7; align-items: baseline; }
  .camp-date-list li[hidden] { display: none; }
  .camp-date-when { font-weight: 800; color: #14532d; }
  .camp-date-what a { font-weight: 700; color: var(--fg); }
  .camp-date-what span { display: block; color: var(--muted); }
  .camp-date-cal { white-space: nowrap; font-size: 15px; }
  .camp-linkish { background: none; border: 0; padding: 0; font: inherit; font-weight: 600; color: var(--accent); text-decoration: underline; cursor: pointer; }
  .camp-date-cal a { font-weight: 600; color: var(--accent); margin-right: 10px; }
  .camp-more { margin-top: 10px; }
  .camp-panel details { margin-top: 12px; border-top: 1px solid #e7ede7; padding-top: 12px; }
  .camp-panel summary { font-weight: 700; cursor: pointer; color: var(--accent); }
  .camp-panel details ul { margin: 8px 0 0; padding-left: 20px; }
  .camp-select, .camp-age-select {
    appearance: none;
    -webkit-appearance: none;
    background: #ffffff url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath fill='%234a5a4f' d='M1.4 0L6 4.6 10.6 0 12 1.4l-6 6-6-6z'/%3E%3C/svg%3E") no-repeat right 10px center;
    color: var(--fg, #17261b);
    font-family: inherit;
    font-size: 13.5px;
    font-weight: 700;
    padding: 6px 28px 6px 12px;
    border: 1px solid var(--border);
    border-radius: 8px;
    cursor: pointer;
    outline: none;
    transition: all 0.15s ease;
    white-space: nowrap;
  }
  .camp-select:hover, .camp-age-select:hover {
    border-color: #166534;
    background-color: #f6f8f5;
  }
  .camp-chip { font: inherit; font-size: 13.5px; font-weight: 600; }
  .camps-count-bar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; font-size: 15px; font-weight: 700; margin: 0 2px 14px; }
  .camps-hub .hub-grid { display: flex; flex-direction: column; gap: 6px; margin: 0; }
  .camps-hub #hub-none { text-align: center; background: #fff; border: 1px solid var(--border); border-radius: 14px; padding: 28px 20px; color: var(--muted); }
  .camp-card {
    background: #ffffff;
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
    margin-bottom: 6px;
    transition: all 0.15s ease;
  }
  .camp-card:hover {
    border-color: #9ab8a0;
    box-shadow: 0 3px 10px rgba(20, 83, 45, 0.06);
  }
  .camp-card[hidden] { display: none !important; }
  .camp-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
  .camp-card h3 { margin: 0; font-size: 16.5px; line-height: 1.3; font-weight: 800; }
  .camp-card h3 a { color: var(--fg); text-decoration: none; }
  .camp-card h3 a:hover { color: var(--accent); text-decoration: underline; }
  .camp-where { margin: 2px 0 0; color: var(--muted); font-size: 13.5px; }
  .camp-where a { color: #2f5239; font-weight: 600; text-decoration: none; border-bottom: 1px dotted #8fa996; }
  .camp-where a:hover { color: var(--accent); border-bottom-color: var(--accent); }
  .camp-save { flex: none; font: inherit; font-size: 13px; font-weight: 700; color: var(--accent); background: #fff; border: 1px solid #b9c6bb; border-radius: 6px; padding: 3px 9px; cursor: pointer; }
  .camp-save[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: #fff; }
  .camp-facts { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 14px; margin: 2px 0 0; font-size: 13.5px; }
  .camp-facts dt { font-weight: 700; color: var(--muted); }
  .camp-facts dd { margin: 0; overflow-wrap: anywhere; word-break: break-word; }
  .camp-facts ul { margin: 0; padding: 0; list-style: none; display: inline-flex; gap: 8px; flex-wrap: wrap; }
  .camp-facts li.next { font-weight: 700; }
  .camp-facts li.past { color: var(--muted); }
  .camp-unknown { color: var(--muted); font-style: italic; }
  .camp-note { margin: 0; color: var(--muted); font-size: 13px; }
  .camp-foot { margin-top: 2px; padding-top: 6px; border-top: 1px solid #e7ede7; display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
  .camp-season { font-size: 12px; font-weight: 700; padding: 2px 7px; border-radius: 6px; }
  .camp-season.y2027 { background: #e2f3e6; color: #14532d; }
  .camp-season.y2026 { background: var(--amber-bg); color: var(--amber-fg); }
  .camp-site { font-weight: 700; color: var(--accent); font-size: 13px; }
  .camp-sources { font-size: 12px; color: var(--muted); width: 100%; }
  .camp-top-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .camp-badge { font-size: 11px; font-weight: 700; padding: 1px 7px; border-radius: 999px; white-space: nowrap; }
  .camp-badge-day { background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }
  .camp-badge-overnight { background: #ede9fe; color: #5b21b6; border: 1px solid #ddd6fe; }
  .camp-dist-badge {
    font-size: 11.5px; font-weight: 700; padding: 1px 8px; border-radius: 999px;
    background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; white-space: nowrap;
  }
  .camp-loc-header {
    margin: 24px 0 6px; font-size: 16.5px; font-weight: 800; color: #14532d;
    display: flex; align-items: center; gap: 8px; padding-bottom: 4px; border-bottom: 2px solid #e2ece3;
  }
  .camp-loc-header:first-of-type { margin-top: 0; }
  .camp-loc-header .count {
    font-size: 12px; font-weight: 700; color: #4a5a4f; background: #e2ece3; padding: 1px 7px; border-radius: 999px;
  }
  .camp-saved-bar { background: #e2f3e6; border-radius: 10px; padding: 8px 12px; margin-top: 12px; font-weight: 600; font-size: 13px; display: flex; flex-direction: column; gap: 6px; }
  .camp-saved-bar[hidden] { display: none; }
  .camp-view-toggle {
    display: inline-flex; align-items: center; background: #e2ece3; border: 1px solid var(--border);
    border-radius: 999px; padding: 2px; gap: 2px;
  }
  .camp-view-btn {
    background: transparent; border: none; padding: 4px 10px; border-radius: 999px;
    font: inherit; font-size: 12px; font-weight: 600; color: var(--muted); cursor: pointer; transition: all 0.15s ease;
  }
  .camp-view-btn.active { background: var(--accent); color: #ffffff; font-weight: 700; }
  .camp-map-wrap {
    margin: 0 0 16px; background: #ffffff; border: 1px solid var(--border); border-radius: 14px;
    overflow: hidden; box-shadow: 0 4px 18px rgba(20, 83, 45, 0.08);
  }
  .camp-map-toolbar {
    display: flex; align-items: center; justify-content: space-between; padding: 8px 14px;
    background: #f6faf6; border-bottom: 1px solid var(--border); font-size: 12.5px; font-weight: 600; color: var(--fg);
  }
  .camp-map-close-btn {
    background: none; border: 1px solid var(--border); border-radius: 999px; padding: 2px 8px;
    font: inherit; font-size: 11px; cursor: pointer; color: var(--muted);
  }
  .camps-hub .leaflet-map, .camps-hub .camp-leaflet-map { width: 100%; height: 440px; }
  .camp-after { margin-top: 24px; }
  .camp-after ul { margin: 8px 0 0; padding-left: 20px; }
  @media (max-width: 860px) {
    .camps-layout { grid-template-columns: 1fr; gap: 16px; }
    .camps-sidebar { position: static; padding: 12px; margin-bottom: 12px; }
    .camps-filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(135px, 1fr)); gap: 8px; }
  }
"""

_CAMPS_FILTER_JS = """<script>
(function () {
  var selects = document.querySelectorAll('.camp-select');
  var chips = document.querySelectorAll('.camp-chip');
  if (!selects.length && !chips.length) return;
  var cards = document.querySelectorAll('.camp-card');
  var countEl = document.getElementById('camp-results-count');
  var resetBtn = document.getElementById('camp-reset-btn');
  var nearBtn = document.getElementById('camp-near-btn');
  var originSelect = document.getElementById('camp-origin');
  var nearInfo = document.getElementById('camp-near-info');
  var grid = document.querySelector('.hub-grid');
  var initialNodes = grid ? Array.prototype.slice.call(grid.children) : [];

  var viewListBtn = document.getElementById('camp-view-list');
  var viewMapBtn = document.getElementById('camp-view-map');
  var mapWrap = document.getElementById('camp-map-wrap');
  var mapCloseBtn = document.getElementById('camp-map-close');
  var mapStatus = document.getElementById('camp-map-status');
  var leafletMap = null;
  var markersLayer = null;

  var state = { area: 'all', camp_type: 'all', kind: 'all', cost: 'all', info: 'all', age: 'all' };
  var sorting_dist = false;
  var lastCoords = null;
  var KEY = 'nyc-saved-camps', saved = {};
  try { (JSON.parse(localStorage.getItem(KEY)) || []).forEach(function (i) { saved[i] = 1; }); } catch (e) {}
  function keep() { try { localStorage.setItem(KEY, JSON.stringify(Object.keys(saved))); } catch (e) {} }
  function num(v) { return v === '' || v === undefined ? null : Number(v); }

  function haversineMiles(lat1, lon1, lat2, lon2) {
    var R = 3958.8;
    var dLat = (lat2 - lat1) * Math.PI / 180;
    var dLon = (lon2 - lon1) * Math.PI / 180;
    var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  function formatDist(m) {
    if (m < 10) return m.toFixed(1) + ' mi';
    return Math.round(m) + ' mi';
  }

  function costOk(d) {
    var lo = num(d.lo);
    if (state.cost === 'free') return lo === 0;
    if (state.cost === 'u500') return lo !== null && lo < 500;
    if (state.cost === 'u800') return lo !== null && lo < 800;
    if (state.cost === 'help') return d.help === '1';
    return true;
  }

  function matches(c) {
    var d = c.dataset;
    if (state.camp_type === 'day' && d.type === 'Overnight') return false;
    if (state.camp_type === 'overnight' && d.type !== 'Overnight') return false;
    if (state.area !== 'all' && d.area !== state.area) return false;
    if (state.kind === 'overnight') { if (d.type !== 'Overnight') return false; }
    else if (state.kind !== 'all' && d.kind !== state.kind) return false;
    if (state.info === 'y2027' && d.season !== '2027') return false;
    if (state.info === 'saved' && !saved[d.id]) return false;
    if (!costOk(d)) return false;
    if (state.age !== 'all') {
      var a = Number(state.age), lo = num(d.min), hi = num(d.max);
      if ((lo !== null && a < lo) || (hi !== null && a > hi)) return false;
    }
    return true;
  }

  function loadLeaflet(callback) {
    if (window.L && window.L.map) { callback(); return; }
    if (!document.querySelector('link[href*="leaflet"]')) {
      var css = document.createElement('link');
      css.rel = 'stylesheet';
      css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
      document.head.appendChild(css);
    }
    if (window._leafletLoading) {
      var interval = setInterval(function () {
        if (window.L && window.L.map) { clearInterval(interval); callback(); }
      }, 50);
      return;
    }
    window._leafletLoading = true;
    var script = document.createElement('script');
    script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    script.onload = function () { window._leafletLoading = false; callback(); };
    document.head.appendChild(script);
  }

  function updateCampMapMarkers() {
    if (!leafletMap || !markersLayer) return;
    markersLayer.clearLayers();
    var bounds = [];
    var count = 0;
    cards.forEach(function (c) {
      if (c.hidden) return;
      var lat = parseFloat(c.dataset.lat), lng = parseFloat(c.dataset.lng);
      if (isNaN(lat) || isNaN(lng)) return;
      var title = c.querySelector('h3 a') ? c.querySelector('h3 a').textContent : 'Camp';
      var url = c.querySelector('h3 a') ? c.querySelector('h3 a').href : '#';
      var where = c.querySelector('.camp-where') ? c.querySelector('.camp-where').textContent : '';
      var gmaps = c.dataset.gmaps || '#';

      var marker = L.marker([lat, lng]);
      var popupHtml = '<div style="font-family:sans-serif;font-size:13px;line-height:1.4;">' +
                      '<strong style="font-size:14px;"><a href="' + url + '" target="_blank" rel="noopener" style="color:#166534;text-decoration:none;">' + title + '</a></strong><br>' +
                      (where ? '<a href="' + gmaps + '" target="_blank" rel="noopener" style="color:#4a5a4f;text-decoration:underline;">' + where + '</a><br>' : '') +
                      '<a href="' + url + '" target="_blank" rel="noopener" style="display:inline-block;margin-top:4px;color:#166534;font-size:12px;font-weight:700;">Camp Website →</a>' +
                      '</div>';
      marker.bindPopup(popupHtml);
      markersLayer.addLayer(marker);
      bounds.push([lat, lng]);
      count++;
    });
    if (mapStatus) mapStatus.textContent = '📍 Showing ' + count + ' camps on map';
    if (bounds.length) {
      leafletMap.fitBounds(bounds, { padding: [30, 30], maxZoom: 13 });
    }
  }

  function initCampMap() {
    if (leafletMap) {
      updateCampMapMarkers();
      leafletMap.invalidateSize();
      return;
    }
    var mapEl = document.getElementById('camp-leaflet-map');
    if (!mapEl) return;
    leafletMap = L.map(mapEl, { center: [40.7536, -73.9832], zoom: 11 });
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
      maxZoom: 19
    }).addTo(leafletMap);
    markersLayer = L.layerGroup().addTo(leafletMap);
    updateCampMapMarkers();
  }

  function sortByDistance(userLat, userLng, originLabel) {
    cards.forEach(function (c) {
      var lat = parseFloat(c.dataset.lat), lng = parseFloat(c.dataset.lng);
      var badge = c.querySelector('.camp-dist-badge');
      if (!isNaN(lat) && !isNaN(lng)) {
        var d = haversineMiles(userLat, userLng, lat, lng);
        c._dist = d;
        if (badge) { badge.textContent = '📍 ' + formatDist(d); badge.hidden = false; }
      } else {
        c._dist = 999999;
        if (badge) badge.hidden = true;
      }
    });
    var cardArr = Array.prototype.slice.call(cards);
    cardArr.sort(function (a, b) { return (a._dist || 0) - (b._dist || 0); });
    if (grid) { cardArr.forEach(function (c) { grid.appendChild(c); }); }
    if (nearInfo) {
      nearInfo.textContent = '📍 Sorted from ' + originLabel;
      nearInfo.hidden = false;
    }
  }

  function restoreInitialOrder() {
    if (grid && initialNodes.length) {
      initialNodes.forEach(function (node) { grid.appendChild(node); });
    }
    cards.forEach(function (c) {
      var badge = c.querySelector('.camp-dist-badge');
      if (badge) badge.hidden = true;
    });
    if (nearInfo) { nearInfo.textContent = ''; nearInfo.hidden = true; }
  }

  function activateNear(val) {
    if (originSelect) originSelect.hidden = false;
    if (val === 'here') {
      if (navigator.geolocation) {
        if (nearInfo) { nearInfo.textContent = '📍 Getting location...'; nearInfo.hidden = false; }
        navigator.geolocation.getCurrentPosition(
          function (pos) {
            lastCoords = { lat: pos.coords.latitude, lng: pos.coords.longitude };
            sorting_dist = true;
            if (originSelect) originSelect.value = 'here';
            sortByDistance(lastCoords.lat, lastCoords.lng, 'Your Location');
            render(false);
          },
          function () {
            lastCoords = { lat: 40.7536, lng: -73.9832 };
            sorting_dist = true;
            if (originSelect) originSelect.value = '40.7536,-73.9832';
            sortByDistance(lastCoords.lat, lastCoords.lng, 'Midtown Manhattan');
            render(false);
          },
          { timeout: 7000 }
        );
        return;
      }
      val = '40.7536,-73.9832';
    }
    var parts = val.split(',');
    var lat = parseFloat(parts[0]), lng = parseFloat(parts[1]);
    var label = 'New York City';
    if (originSelect && originSelect.selectedIndex >= 0) {
      label = originSelect.options[originSelect.selectedIndex].text;
    }
    sorting_dist = true;
    lastCoords = { lat: lat, lng: lng };
    sortByDistance(lat, lng, label);
    render(false);
  }

  function render(write) {
    var n = 0;
    cards.forEach(function (c) { var on = matches(c); c.hidden = !on; if (on) n++; });
    selects.forEach(function (sel) {
      if (state[sel.dataset.group] !== undefined) sel.value = state[sel.dataset.group];
    });
    chips.forEach(function (b) { b.classList.toggle('active', state[b.dataset.group] === b.dataset.val); });
    if (countEl) countEl.textContent = n;
    var none = document.getElementById('hub-none');
    if (none) none.hidden = n > 0;

    var locHeaders = document.querySelectorAll('.camp-loc-header');
    if (sorting_dist) {
      locHeaders.forEach(function (h) { h.hidden = true; });
    } else {
      locHeaders.forEach(function (h) {
        var a = h.dataset.area;
        var hasVisible = false;
        cards.forEach(function (c) { if (c.dataset.area === a && !c.hidden) hasVisible = true; });
        h.hidden = !hasVisible;
      });
    }

    var isFiltered = Object.keys(state).some(function (k) { return state[k] !== 'all'; }) || sorting_dist;
    if (resetBtn) resetBtn.hidden = !isFiltered;

    var ids = Object.keys(saved).filter(function (i) { return document.querySelector('.camp-card[data-id="' + i + '"]'); });
    document.querySelectorAll('.camp-save').forEach(function (b) {
      var on = !!saved[b.dataset.id];
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      b.textContent = on ? '★ Saved' : '☆ Save';
    });
    var bar = document.getElementById('camp-saved-bar');
    if (bar) { bar.hidden = !ids.length; var ct = document.getElementById('camp-saved-n'); if (ct) ct.textContent = ids.length; }
    if (write) {
      var parts = Object.keys(state).filter(function (k) { return state[k] !== 'all'; }).map(function (k) { return k + '=' + state[k]; });
      history.replaceState(null, '', parts.length ? '#' + parts.join('&') : location.pathname);
    }

    if (leafletMap && mapWrap && mapWrap.style.display !== 'none') {
      updateCampMapMarkers();
    }
  }

  if (nearBtn) nearBtn.addEventListener('click', function () { activateNear('here'); });
  if (originSelect) originSelect.addEventListener('change', function () { activateNear(originSelect.value); });

  if (viewMapBtn) {
    viewMapBtn.addEventListener('click', function () {
      if (mapWrap) mapWrap.style.display = 'block';
      viewMapBtn.classList.add('active');
      viewMapBtn.setAttribute('aria-pressed', 'true');
      if (viewListBtn) { viewListBtn.classList.remove('active'); viewListBtn.setAttribute('aria-pressed', 'false'); }
      loadLeaflet(function () { initCampMap(); });
    });
  }

  function hideCampMap() {
    if (mapWrap) mapWrap.style.display = 'none';
    if (viewListBtn) { viewListBtn.classList.add('active'); viewListBtn.setAttribute('aria-pressed', 'true'); }
    if (viewMapBtn) { viewMapBtn.classList.remove('active'); viewMapBtn.setAttribute('aria-pressed', 'false'); }
  }
  if (viewListBtn) viewListBtn.addEventListener('click', hideCampMap);
  if (mapCloseBtn) mapCloseBtn.addEventListener('click', hideCampMap);

  if (resetBtn) {
    resetBtn.addEventListener('click', function () {
      state = { area: 'all', camp_type: 'all', kind: 'all', cost: 'all', info: 'all', age: 'all' };
      sorting_dist = false;
      if (originSelect) { originSelect.hidden = true; originSelect.selectedIndex = 0; }
      restoreInitialOrder();
      render(true);
    });
  }

  document.querySelectorAll('.camp-save').forEach(function (b) {
    b.addEventListener('click', function () {
      if (saved[b.dataset.id]) delete saved[b.dataset.id]; else saved[b.dataset.id] = 1;
      keep(); render(false);
    });
  });
  var showSaved = document.getElementById('camp-saved-show');
  if (showSaved) showSaved.addEventListener('click', function () { state.info = 'saved'; render(true); });
  selects.forEach(function (sel) {
    sel.addEventListener('change', function () { state[sel.dataset.group] = sel.value; render(true); });
  });
  chips.forEach(function (b) {
    b.addEventListener('click', function () { state[b.dataset.group] = b.dataset.val; render(true); });
  });
  location.hash.replace(/^#/, '').split('&').forEach(function (p) {
    var kv = p.split('=');
    if (kv.length !== 2 || !state.hasOwnProperty(kv[0])) return;
    state[kv[0]] = kv[1];
  });
  render(false);
})();
</script>"""

_CAMP_TYPE_WORDS = {
    "city": "City or Parks program",
    "ymca": "YMCA / JCC",
    "nature": "Nature & botanic camp",
    "nonprofit": "Nonprofit",
    "museum": "Museum or zoo",
    "private": "Private & specialty camp",
}


def _camp_when(ev, year=False):
    d = datetime.strptime(ev["date"], "%Y-%m-%d")
    text = f"{d.strftime('%a, %b')} {d.day}" + (f", {d.year}" if year else "")
    if ev.get("time"):
        t = datetime.strptime(ev["time"], "%H:%M")
        text += f" at {t.hour % 12 or 12}{t.strftime(':%M') if t.minute else ''} {'AM' if t.hour < 12 else 'PM'}"
    return text


def _camp_gcal(title, ev, url):
    day = ev["date"].replace("-", "")
    if ev.get("time"):
        start = datetime.strptime(ev["date"] + ev["time"], "%Y-%m-%d%H:%M")
        dates = f"{start:%Y%m%dT%H%M%S}/{start + timedelta(minutes=30):%Y%m%dT%H%M%S}"
    else:
        end = datetime.strptime(ev["date"], "%Y-%m-%d") + timedelta(days=1)
        dates = f"{day}/{end:%Y%m%d}"
    return (
        "https://calendar.google.com/calendar/render?action=TEMPLATE&text=" + quote(title)
        + "&dates=" + dates + "&ctz=America/New_York&details=" + quote("Check the camp site to confirm: " + url)
    )


def _camp_fact(label, value):
    shown = escape(value) if value else '<span class="camp-unknown">Not published</span>'
    return f"<dt>{label}</dt><dd>{shown}</dd>"


def _camp_signup(c, today_iso):
    lines = []
    for e in c.get("events") or []:
        if e.get("date"):
            if e["date"] >= today_iso:
                lines.append(f'<li class="next">{escape(_camp_when(e))}: {escape(e["label"])}</li>')
        elif e.get("season") == 2026:
            lines.append(f'<li class="past">Last year: {escape(e["label"])}, {escape(e["when"])}</li>')
        else:
            prefix = "" if e["when"] == "Not posted yet" else f'{escape(e["when"])}: '
            lines.append(f'<li>{prefix}{escape(e["label"])}</li>')
    how = f"<div>{escape(c['signup'])}</div>" if c.get("signup") else ""
    if not how and not lines:
        return '<span class="camp-unknown">Not published</span>'
    return how + (f"<ul>{''.join(lines)}</ul>" if lines else "")


def _camp_card(c):
    today_iso = datetime.now(EASTERN).date().isoformat()
    name, url = escape(c["name"]), escape(c["url"])
    is_overnight = c.get("type") == "Overnight"
    type_badge = (
        '<span class="camp-badge camp-badge-overnight">⛺ Overnight Camp</span>'
        if is_overnight else '<span class="camp-badge camp-badge-day">☀️ Day Camp</span>'
    )
    gmaps_q = f"{c['name']}, {c['town']}, NY"
    gmaps_url = escape(f"https://www.google.com/maps/search/?api=1&query={quote_plus(gmaps_q)}")
    where_suffix = " · ".join(["Overnight" if is_overnight else "Day camp", _CAMP_TYPE_WORDS[c["kind"]]])
    upcoming = [
        {"title": f"{c['name']}: {e['label']}", "date": e["date"], "time": e.get("time"), "url": c["url"]}
        for e in c.get("events") or [] if e.get("date") and e["date"] >= today_iso
    ]
    facts = [
        _camp_fact("Ages", c.get("ages")),
        _camp_fact("Cost", c.get("price")),
        _camp_fact("Dates", c.get("dates")),
        _camp_fact("Hours", c.get("hours")),
        f"<dt>Sign-up</dt><dd>{_camp_signup(c, today_iso)}</dd>",
    ]
    if c.get("residents"):
        facts.append(_camp_fact("Who", c["residents"]))
    if c.get("aid"):
        facts.append(_camp_fact("Help", c["aid"]))
    note = f'<p class="camp-note">{escape(c["note"])}</p>' if c.get("note") else ""
    season = (
        '<span class="camp-season y2027">2027 info</span>'
        if c["season"] == 2027
        else '<span class="camp-season y2026">2026 info, 2027 not posted</span>'
    )
    checked = datetime.strptime(c["checked"], "%Y-%m-%d")
    sources = " · ".join(
        f'<a href="{escape(u)}" target="_blank" rel="noopener">source {i + 1}</a>'
        for i, u in enumerate(c["sources"])
    )
    attrs = {
        "id": c["id"],
        "area": c["area"],
        "kind": c["kind"],
        "type": c["type"],
        "season": c["season"],
        "min": "" if c.get("age_min") is None else c["age_min"],
        "max": "" if c.get("age_max") is None else c["age_max"],
        "lo": "" if c.get("week_low") is None else c["week_low"],
        "help": 1 if c.get("sliding") or c.get("aid") else 0,
        "lat": c.get("lat", ""),
        "lng": c.get("lng", ""),
        "town": c.get("town", ""),
        "gmaps": gmaps_url,
    }
    data = " ".join(f'data-{k}="{escape(str(v))}"' for k, v in attrs.items())
    return f"""<article class="camp-card" {data} data-events="{escape(json.dumps(upcoming))}">
  <div class="camp-head">
    <div>
      <div class="camp-top-row">
        <h3><a href="{url}" target="_blank" rel="noopener">{name}</a></h3>
        {type_badge}
        <span class="camp-dist-badge" hidden></span>
      </div>
      <p class="camp-where"><a href="{gmaps_url}" target="_blank" rel="noopener" title="Open in Google Maps">📍 {escape(c['town'])}</a> · {escape(where_suffix)}</p>
    </div>
    <button type="button" class="camp-save" data-id="{escape(c['id'])}" aria-pressed="false" aria-label="Save {name}">☆ Save</button>
  </div>
  <dl class="camp-facts">{''.join(facts)}</dl>
  {note}
  <div class="camp-foot">{season}<a class="camp-site" href="{url}" target="_blank" rel="noopener">Camp site →</a>
    <span class="camp-sources">Checked {checked.strftime('%b')} {checked.day}, {checked.year}: {sources}</span></div>
</article>"""


def _camp_date_rows(camps, today_iso):
    groups, later, seen_later = {}, [], set()
    for c in camps:
        for e in c.get("events") or []:
            who = e.get("group") or c["name"]
            url = c["url"]
            if e.get("date"):
                if e["date"] >= today_iso:
                    groups.setdefault((e["date"], e.get("time") or "", who, e["label"]), (e, url))
            elif e.get("season") == 2027 and e["when"] != "Not posted yet" and (who, e["label"]) not in seen_later:
                seen_later.add((who, e["label"]))
                later.append((who, e))
    rows = []
    for (_d, _t, who, label), (e, url) in sorted(groups.items()):
        title = f"{who}: {label}"
        rows.append(
            f"""<li data-date="{escape(e['date'])}"><div class="camp-date-when">{escape(_camp_when(e))}</div>
    <div class="camp-date-what"><a href="{escape(url)}" target="_blank" rel="noopener">{escape(who)}</a><span>{escape(label)}</span></div>
    <div class="camp-date-cal"><a href="{escape(_camp_gcal(title, e, url))}" target="_blank" rel="noopener">Google Calendar</a></div></li>"""
        )
    return rows, later


def _camp_summer_year(today=None):
    today = today or datetime.now(EASTERN).date()
    return today.year + 1 if today.month >= 9 else today.year


def render_body(today=None):
    """Return (hero_html, filters_html, body_html) for /summer-camps/."""
    data = load_camps()
    camps = data["camps"][:CARD_LIMIT]
    today_obj = today or datetime.now(EASTERN).date()
    today_iso = today_obj.isoformat()
    rows, later = _camp_date_rows(camps, today_iso)

    def chip(group, val, label):
        return f'<option class="camp-chip" data-group="{group}" data-val="{val}" value="{val}">{escape(label)}</option>'

    present = {c["area"] for c in camps}
    kinds = {c["kind"] for c in camps}
    areas = chip("area", "all", "All Boroughs & Areas") + "".join(chip("area", k, v) for k, v in AREAS if k in present)
    types = chip("kind", "all", "All types") + "".join(chip("kind", k, v) for k, v in KINDS if k in kinds) + chip("kind", "overnight", "Overnight")
    costs = (
        chip("cost", "all", "Any cost")
        + chip("cost", "free", "Free ($0)")
        + chip("cost", "u500", "Under $500/wk")
        + chip("cost", "u800", "Under $800/wk")
        + chip("cost", "help", "Sliding scale / scholarships")
    )
    info = chip("info", "all", "All camps") + chip("info", "y2027", "2027 info posted") + chip("info", "saved", "Saved")
    ages = '<option value="all">Any age</option>' + "".join(f'<option value="{a}">{a} years old</option>' for a in range(2, 18))

    hero_html = f"""<div class="hero">
    {_CAMPS_HERO_ART}
    <div class="camps-hero-copy">
      <h1>Summer Camps in NYC {_camp_summer_year(today_obj)}<small>Manhattan · Brooklyn · Queens · The Bronx · Staten Island &amp; Sleepaway</small></h1>
      <p>Prices, ages, hours, and registration dates for day and sleepaway camps across New York City, checked directly against each camp's official site.</p>
      <p class="camps-stats">{len(camps)} camps across all 5 boroughs &amp; nearby · {len(rows)} upcoming sign-up dates</p>
    </div>
  </div>"""

    later_html = ""
    if later:
        items = "".join(f"<li><strong>{escape(e['when'])}:</strong> {escape(who)}, {escape(e['label'])}</li>" for who, e in later)
        later_html = f"<details><summary>Expected soon, exact day TBA</summary><ul>{items}</ul></details>"

    dates_html = f"""<section class="camp-panel" aria-labelledby="camp-dates-h">
    <h2 id="camp-dates-h">Next sign-up &amp; lottery dates</h2>
    <p>NYC Parks lotteries, Summer Rising, and popular museum/botanic garden camps fill quickly — add these to your calendar.</p>
    <ol class="camp-date-list">{''.join(rows)}</ol>
    {later_html}
  </section>"""

    sidebar_html = f"""<aside class="camps-sidebar" aria-label="Camp filters">
    <div class="camps-filter-header">
      <h2 class="camps-sidebar-title">Filters</h2>
      <button type="button" id="camp-reset-btn" class="camp-linkish camp-reset-btn" hidden>Reset</button>
    </div>
    <div class="camps-filters" role="group" aria-label="Filter summer camps">
      <div class="camp-filter-group camp-near-group">
        <label class="camp-filter-label" for="camp-near-btn">Distance</label>
        <button type="button" id="camp-near-btn" class="camp-near-btn">📍 Sort by Distance</button>
        <select id="camp-origin" class="camp-select camp-origin-select" aria-label="Starting location" hidden>
          <option value="here">📍 Current Location</option>
          <option value="40.7536,-73.9832">Midtown Manhattan</option>
          <option value="40.7812,-73.9745">Upper West Side / Upper East Side</option>
          <option value="40.6782,-73.9772">Park Slope / Downtown Brooklyn</option>
          <option value="40.7181,-73.9571">Williamsburg / Greenpoint</option>
          <option value="40.7510,-73.8294">Astoria / Flushing (Queens)</option>
          <option value="40.8506,-73.8770">Fordham / Riverdale (Bronx)</option>
          <option value="40.6433,-74.1025">St. George / Snug Harbor (Staten Island)</option>
        </select>
        <div id="camp-near-info" class="camp-near-info" hidden></div>
      </div>
      <div class="camp-filter-group">
        <label class="camp-filter-label" for="camp-type">Camp Format</label>
        <select id="camp-type" class="camp-select" data-group="camp_type" aria-label="Day or Overnight camp">
          <option class="camp-chip" data-group="camp_type" data-val="all" value="all">☀️ &amp; ⛺ All Formats</option>
          <option class="camp-chip" data-group="camp_type" data-val="day" value="day">☀️ Day Camps Only</option>
          <option class="camp-chip" data-group="camp_type" data-val="overnight" value="overnight">⛺ Overnight Camps Only</option>
        </select>
      </div>
      <div class="camp-filter-group">
        <label class="camp-filter-label" for="camp-area">Borough / Area</label>
        <select id="camp-area" class="camp-select" data-group="area" aria-label="Camp Area">{areas}</select>
      </div>
      <div class="camp-filter-group">
        <label class="camp-filter-label" for="camp-age">Child's age</label>
        <select id="camp-age" class="camp-select camp-age-select" data-group="age" aria-label="Child's age">{ages}</select>
      </div>
      <div class="camp-filter-group">
        <label class="camp-filter-label" for="camp-kind">Type of Camp</label>
        <select id="camp-kind" class="camp-select" data-group="kind" aria-label="Camp Type">{types}</select>
      </div>
      <div class="camp-filter-group">
        <label class="camp-filter-label" for="camp-cost">Cost</label>
        <select id="camp-cost" class="camp-select" data-group="cost" aria-label="Camp Cost">{costs}</select>
      </div>
      <div class="camp-filter-group">
        <label class="camp-filter-label" for="camp-info">Status</label>
        <select id="camp-info" class="camp-select" data-group="info" aria-label="Camp Info">{info}</select>
      </div>
    </div>
    <div id="camp-saved-bar" class="camp-saved-bar" hidden>
      <span><span id="camp-saved-n">0</span> saved</span>
      <button type="button" id="camp-saved-show" class="camp-linkish">Show saved</button>
    </div>
  </aside>"""

    area_labels = {
        "manhattan": "📍 Manhattan",
        "brooklyn": "📍 Brooklyn",
        "queens": "📍 Queens",
        "bronx": "📍 The Bronx",
        "staten_island": "📍 Staten Island",
        "away": "⛺ Sleepaway & Hudson Valley / Catskills",
    }
    area_order = ["manhattan", "brooklyn", "queens", "bronx", "staten_island", "away"]
    by_area = {}
    for c in camps:
        by_area.setdefault(c["area"], []).append(c)

    cards_html = []
    for a_key in area_order:
        if a_key in by_area:
            c_list = by_area[a_key]
            lbl = area_labels.get(a_key, a_key.title())
            cards_html.append(
                f'<div class="camp-loc-header" data-area="{a_key}">'
                f"<span>{lbl}</span>"
                f'<span class="count">{len(c_list)}</span>'
                f"</div>"
            )
            for c in c_list:
                cards_html.append(_camp_card(c))

    def link(name, url):
        return f'<a href="{escape(url)}" target="_blank" rel="noopener">{escape(name)}</a>' if url else escape(name)

    leads = "".join(f"<li>{link(l['name'], l['url'])} ({escape(l['town'])})</li>" for l in data["leads"])
    towns_html = "".join(f"<li>{link(t['town'], t.get('url'))}: {escape(t['note'])}</li>" for t in data["towns"])
    not_camps = "".join(f"<li>{link(n['name'], n['url'])}: {escape(n['note'])}</li>" for n in data["not_camps"])

    body_html = f"""<div class="camps-layout">
  {sidebar_html}
  <div class="camps-main-col">
    {dates_html}
    <div class="camps-count-bar">
      <span><span id="camp-results-count">{len(camps)}</span> camps</span>
      <div class="camp-view-toggle" role="group" aria-label="View mode">
        <button type="button" id="camp-view-list" class="camp-view-btn active" aria-pressed="true">📋 List</button>
        <button type="button" id="camp-view-map" class="camp-view-btn" aria-pressed="false">🗺️ Map</button>
      </div>
    </div>
    <div id="camp-map-wrap" class="camp-map-wrap" style="display:none;">
      <div class="camp-map-toolbar">
        <span id="camp-map-status" class="camp-map-status">📍 Loading summer camps map...</span>
        <button type="button" id="camp-map-close" class="camp-map-close-btn" aria-label="Close Map">✕ Close Map</button>
      </div>
      <div id="camp-leaflet-map" class="camp-leaflet-map" style="height:440px; width:100%;"></div>
    </div>
    <div class="hub-grid">
      {"".join(cards_html)}
    </div>
    <p id="hub-none" hidden>No camps match those filters.</p>
  </div>
</div>
<div class="camp-after">
  <section class="camp-panel"><h2>More NYC Camps &amp; Free City Programs</h2>
    <p>Additional museum camps, zoo camps, and free citywide summer programs to explore directly:</p>
    <details open><summary>More museum &amp; zoo camps</summary><ul>{leads}</ul></details>
    <details><summary>Free NYC citywide summer programs</summary><ul>{towns_html}</ul></details>
    <details><summary>Drop-in summer reading &amp; library programs</summary><ul>{not_camps}</ul></details>
  </section>
  <p><a href="../kids-family-events-nyc/">See year-round NYC kids and family events →</a></p>
</div>"""

    return hero_html, "", body_html
