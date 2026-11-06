"""DJ Nights, Techno & Dance Parties hub: a dark, neon page with vibe, borough, date and cost filters.

Ported from boston_events, with Latin and hip-hop filters since those make up much of NYC's club
listings, and the boroughs as areas.
"""
import re
from datetime import datetime
from html import escape

from scrapers import EASTERN

_EDM_NON_WORDS = re.compile(
    r'(?i)\b(workshop|lesson|class|watch party|bake off|drag brunch|trivia|board game|book club|storytime|puppet|for littles|lego build)\b'
)
_EDM_TITLE_EXCLUSIONS = re.compile(
    r'(?i)\b(open mic|comedy|podcast|tribute band|karaoke|jazz night|blues jam|acoustic session|open jam)\b'
)

_EDM_SUBGENRE_PATTERNS = [
    ('techno', '⚡ Techno', '⚡', re.compile(r'(?i)\b(techno|acid\s+techno|hard\s+techno|industrial(\s+dance|\s+techno)?|ebm\b|dark\s+techno|minimal\s+techno)\b')),
    ('house', '🎛️ House', '🎛️', re.compile(r'(?i)\b(house\s+music|tech\s+house|deep\s+house|afro\s+house|acid\s+house|disco\s+house|prog(ressive)?\s+house|chicago\s+house|house\s+party)\b')),
    ('bass', '🔊 Bass & D&B', '🔊', re.compile(r'(?i)\b(drum\s*(&|and)\s*bass|\bdnb\b|\bd&b\b|dubstep|riddim|breakbeat|bass\s+music|jungle|bass\s+house)\b')),
    ('synth', '🌌 Synth & Darkwave', '🌌', re.compile(r'(?i)\b(synthwave|darkwave|electro|electropop|modular\s+synth|synthesizer|vaporwave|ebm|cyberpunk)\b')),
    ('latin', '🌴 Latin & Reggaeton', '🌴', re.compile(r'(?i)\b(reggaeton|perreo|latin|salsa|bachata|dembow|cumbia|afrobeats?|amapiano|soca)\b')),
    ('hiphop', '🎤 Hip-Hop & R&B', '🎤', re.compile(r'(?i)\b(hip[- ]?hop|r&b|rnb|trap|drill)\b')),
    ('club', '🪩 DJ Sets & Dance', '🪩', re.compile(r'(?i)\b(dj\s+(set|night|party|session|lineup|residency)|dance\s+party|club\s+night|all-night\s+dance|rave\b|boiler\s+room|turntablism|guest\s+dj|resident\s+dj)\b')),
]


_EDM_FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
              '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
              '<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@700;800;900&family=Syne:wght@700;800;900&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">')

_EDM_HERO_ART = """<svg class="edm-hero-art" viewBox="0 0 900 200" aria-hidden="true" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="edm-sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#04050a"/>
      <stop offset="60%" stop-color="#0a0d1c"/>
      <stop offset="100%" stop-color="#12182e"/>
    </linearGradient>
    <linearGradient id="edm-neon" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#00f0ff"/>
      <stop offset="50%" stop-color="#a855f7"/>
      <stop offset="100%" stop-color="#ff007f"/>
    </linearGradient>
    <linearGradient id="bar-grad" x1="0" y1="1" x2="0" y2="0">
      <stop offset="0%" stop-color="#00f0ff" stop-opacity="0.2"/>
      <stop offset="60%" stop-color="#00f0ff" stop-opacity="0.8"/>
      <stop offset="100%" stop-color="#ff007f"/>
    </linearGradient>
    <filter id="neon-glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="5" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>
  <rect width="900" height="200" fill="url(#edm-sky)"/>
  <g opacity="0.35" stroke="#00f0ff" stroke-width="1">
    <line x1="450" y1="40" x2="0" y2="200"/>
    <line x1="450" y1="40" x2="120" y2="200"/>
    <line x1="450" y1="40" x2="240" y2="200"/>
    <line x1="450" y1="40" x2="350" y2="200"/>
    <line x1="450" y1="40" x2="450" y2="200"/>
    <line x1="450" y1="40" x2="550" y2="200"/>
    <line x1="450" y1="40" x2="660" y2="200"/>
    <line x1="450" y1="40" x2="780" y2="200"/>
    <line x1="450" y1="40" x2="900" y2="200"/>
    <line x1="200" y1="130" x2="700" y2="130" opacity="0.5"/>
    <line x1="120" y1="160" x2="780" y2="160" opacity="0.7"/>
    <line x1="0" y1="200" x2="900" y2="200" stroke-width="2" opacity="0.9"/>
  </g>
  <g fill="url(#bar-grad)">
    <rect x="40" y="110" width="8" height="70" rx="3"/>
    <rect x="54" y="90" width="8" height="90" rx="3"/>
    <rect x="68" y="130" width="8" height="50" rx="3"/>
    <rect x="82" y="75" width="8" height="105" rx="3"/>
    <rect x="96" y="105" width="8" height="75" rx="3"/>
    <rect x="110" y="60" width="8" height="120" rx="3"/>
    <rect x="124" y="95" width="8" height="85" rx="3"/>
    <rect x="138" y="125" width="8" height="55" rx="3"/>
    <rect x="152" y="80" width="8" height="100" rx="3"/>
    <rect x="166" y="115" width="8" height="65" rx="3"/>
    <rect x="180" y="70" width="8" height="110" rx="3"/>
    <rect x="194" y="135" width="8" height="45" rx="3"/>
  </g>
  <g fill="url(#bar-grad)">
    <rect x="698" y="135" width="8" height="45" rx="3"/>
    <rect x="712" y="70" width="8" height="110" rx="3"/>
    <rect x="726" y="115" width="8" height="65" rx="3"/>
    <rect x="740" y="80" width="8" height="100" rx="3"/>
    <rect x="754" y="125" width="8" height="55" rx="3"/>
    <rect x="768" y="95" width="8" height="85" rx="3"/>
    <rect x="782" y="60" width="8" height="120" rx="3"/>
    <rect x="796" y="105" width="8" height="75" rx="3"/>
    <rect x="810" y="75" width="8" height="105" rx="3"/>
    <rect x="824" y="130" width="8" height="50" rx="3"/>
    <rect x="838" y="90" width="8" height="90" rx="3"/>
    <rect x="852" y="110" width="8" height="70" rx="3"/>
  </g>
  <g transform="translate(450, 95)" filter="url(#neon-glow)">
    <ellipse rx="130" ry="42" fill="none" stroke="#00f0ff" stroke-width="2.5" opacity="0.8"/>
    <ellipse rx="100" ry="32" fill="none" stroke="#a855f7" stroke-width="2" opacity="0.9"/>
    <ellipse rx="70" ry="22" fill="none" stroke="#ff007f" stroke-width="2" opacity="0.85"/>
    <ellipse rx="35" ry="11" fill="none" stroke="#00f0ff" stroke-width="3" opacity="0.95"/>
    <circle r="6" fill="#00f0ff"/>
    <line x1="-120" y1="0" x2="-260" y2="-60" stroke="#ff007f" stroke-width="2" opacity="0.6"/>
    <line x1="120" y1="0" x2="260" y2="-60" stroke="#00f0ff" stroke-width="2" opacity="0.6"/>
  </g>
  <g transform="translate(450, 26)">
    <rect x="-95" y="-12" width="190" height="24" rx="12" fill="#000" stroke="#00f0ff" stroke-width="1.5" opacity="0.85"/>
    <text x="0" y="4" text-anchor="middle" font-family="'Orbitron', monospace" font-size="10.5" font-weight="800" fill="#00f0ff" letter-spacing="3">NYC RAVE FREQ</text>
  </g>
</svg>"""

_EDM_CSS = """
  .hub-card[hidden], .hub-day[hidden], .edm-city-section[hidden] { display: none; }
  .edm-hub .cta-btn { display: inline-block; text-decoration: none; }
  .edm-hub .badge { padding: 1px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; white-space: nowrap; }
  .edm-hub .badge-free { background: rgba(0, 255, 136, 0.15); color: #00ff88; border: 1px solid rgba(0, 255, 136, 0.4); }
  .edm-hub .badge-price { background: rgba(255, 255, 255, 0.08); color: var(--fg); }
  .edm-hub {
    --bg: #07080f;
    --card: #0d101d;
    --card-hover: #13172b;
    --fg: #eef2fb;
    --muted: #8893a7;
    --cyan: #00f0ff;
    --pink: #ff007f;
    --purple: #a855f7;
    --lime: #00ff88;
    --yellow: #fcee0a;
    --border: rgba(0, 240, 255, 0.16);
    background: var(--bg) !important;
    color: var(--fg) !important;
  }
  .edm-hub h1, .edm-hub h2, .edm-hub h3, .edm-hub .logo, .edm-hub .edm-chip, .edm-hub .cta-btn, .edm-hub .edm-card-subgenre {
    font-family: "Syne", "Orbitron", -apple-system, sans-serif;
  }
  .edm-hub header {
    background: rgba(7, 8, 15, 0.9) !important;
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border) !important;
  }
  .edm-hub .logo { color: #fff !important; font-weight: 800; }
  .edm-hub .logo span {
    color: var(--cyan) !important;
    text-shadow: 0 0 10px rgba(0, 240, 255, 0.6);
  }
  .edm-hub .hub-nav a { color: var(--muted); }
  .edm-hub .hub-nav a.active, .edm-hub .hub-nav a:hover { color: var(--cyan); text-shadow: 0 0 8px rgba(0,240,255,0.4); }
  .edm-hub main { max-width: 980px; padding-top: 22px; }
  .edm-hub .hero {
    border: 1px solid var(--border);
    background: #090b16;
    border-radius: 24px;
    overflow: hidden;
    box-shadow: 0 0 30px rgba(0, 240, 255, 0.08), 0 12px 40px rgba(0,0,0,0.6);
    margin-bottom: 22px;
  }
  .edm-hero-art { display: block; width: 100%; height: 190px; }
  .edm-hero-copy { padding: 20px 24px 26px; text-align: center; }
  .edm-hub .hero h1 {
    font-size: clamp(28px, 5.5vw, 44px);
    font-weight: 900;
    margin: 0 0 8px;
    letter-spacing: -0.02em;
    background: linear-gradient(135deg, #fff 30%, var(--cyan) 75%, var(--pink) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .edm-hub .hero h1 small {
    display: block;
    font-size: 0.42em;
    color: var(--cyan);
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-top: 6px;
    -webkit-text-fill-color: var(--cyan);
    text-shadow: 0 0 8px rgba(0, 240, 255, 0.4);
  }
  .edm-hub .hero p {
    color: var(--muted);
    font-size: 15px;
    max-width: 680px;
    margin: 0 auto 18px;
    line-height: 1.5;
  }
  .edm-stats { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; margin: 0 0 18px; }
  .edm-stat {
    background: rgba(0, 240, 255, 0.08);
    border: 1px solid rgba(0, 240, 255, 0.25);
    color: #d8f8ff;
    border-radius: 999px;
    padding: 4px 14px;
    font-weight: 700;
    font-size: 13px;
    box-shadow: 0 0 12px rgba(0, 240, 255, 0.15);
  }
  .edm-hub .cta-btn {
    background: linear-gradient(135deg, var(--cyan), #0077ff);
    color: #04050a;
    font-weight: 800;
    font-size: 15px;
    padding: 8px 22px;
    border-radius: 8px;
    box-shadow: 0 0 16px rgba(0, 240, 255, 0.4);
    text-decoration: none;
    display: inline-block;
  }
  .edm-hub .cta-btn:hover { filter: brightness(1.15); transform: translateY(-1px); }
  .edm-filters {
    background: #090c18;
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 16px 18px 8px;
    margin-bottom: 22px;
    box-shadow: 0 0 20px rgba(0, 240, 255, 0.05);
  }
  .edm-filter-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
  .edm-filter-label {
    font-family: "Orbitron", monospace;
    font-weight: 800;
    color: var(--cyan);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    min-width: 65px;
  }
  .edm-chip {
    font-size: 13.5px;
    font-weight: 700;
    padding: 5px 14px 4px;
    border-radius: 999px;
    cursor: pointer;
    border: 1px solid rgba(255, 255, 255, 0.12);
    background: #0d1122;
    color: var(--fg);
    transition: transform 0.15s ease, background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
  }
  .edm-chip:hover {
    transform: translateY(-1px);
    border-color: var(--cyan);
    box-shadow: 0 0 10px rgba(0, 240, 255, 0.3);
  }
  .edm-chip.active {
    background: linear-gradient(135deg, rgba(0, 240, 255, 0.2), rgba(168, 85, 247, 0.25));
    border-color: var(--cyan);
    color: #fff;
    box-shadow: 0 0 14px rgba(0, 240, 255, 0.45);
  }
  .edm-hub .hub-day {
    margin: 32px 0 14px;
    font-size: 20px;
    font-weight: 800;
    letter-spacing: -0.01em;
    color: #fff;
    display: flex;
    align-items: center;
    gap: 12px;
    border: 0;
    padding: 0;
  }
  .edm-hub .hub-day::before {
    content: "⚡";
    font-size: 16px;
    filter: drop-shadow(0 0 6px var(--cyan));
  }
  .edm-hub .hub-day::after {
    content: "";
    flex: 1;
    height: 1px;
    background: linear-gradient(90deg, var(--cyan), rgba(168, 85, 247, 0.3) 60%, transparent);
  }
  .edm-city-section {
    background: rgba(13, 16, 29, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 16px;
    padding: 14px;
    margin-bottom: 16px;
  }
  .edm-city-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
    padding: 0 4px;
  }
  .edm-city-pill {
    font-size: 11.5px;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 3px 10px;
    border-radius: 999px;
  }
  .edm-city-pill.city-manhattan { color: #00f0ff; border-color: rgba(0, 240, 255, 0.4); background: rgba(0, 240, 255, 0.1); }
  .edm-city-pill.city-brooklyn { color: #ff007f; border-color: rgba(255, 0, 127, 0.4); background: rgba(255, 0, 127, 0.1); }
  .edm-city-pill.city-queens { color: #ffb020; border-color: rgba(255, 176, 32, 0.4); background: rgba(255, 176, 32, 0.1); }
  .edm-city-pill.city-bronx { color: #00ff88; border-color: rgba(0, 255, 136, 0.4); background: rgba(0, 255, 136, 0.1); }
  .edm-city-pill.city-staten_island,
  .edm-city-pill.city-citywide { color: #a855f7; border-color: rgba(168, 85, 247, 0.4); background: rgba(168, 85, 247, 0.1); }
  .edm-city-head .count {
    font-size: 11.5px;
    font-weight: 700;
    color: var(--muted);
    background: rgba(255, 255, 255, 0.06);
    padding: 2px 8px;
    border-radius: 999px;
  }
  .edm-city-cards {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 14px;
  }
  @media (min-width: 640px) {
    .edm-city-cards {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
  .hub-card.edm-card {
    background: #0d1020;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
    overflow: hidden;
    position: relative;
    display: flex;
    flex-direction: column;
    transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
  }
  .hub-card.edm-card:hover {
    transform: translateY(-2px);
    border-color: var(--edm-band);
    box-shadow: 0 0 18px rgba(0, 240, 255, 0.18), 0 8px 24px rgba(0,0,0,0.4);
  }
  .edm-card-band {
    height: 3px;
    background: var(--edm-band);
    box-shadow: 0 0 8px var(--edm-band);
  }
  .edm-k-techno { --edm-band: var(--cyan); }
  .edm-k-house { --edm-band: var(--pink); }
  .edm-k-bass { --edm-band: var(--lime); }
  .edm-k-synth { --edm-band: var(--purple); }
  .edm-k-club { --edm-band: var(--yellow); }
  .edm-card-body {
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    flex: 1;
  }
  .edm-card-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  .edm-card-subgenre {
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--edm-band);
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .edm-card-title {
    margin: 0;
    font-size: 17px;
    font-weight: 700;
    line-height: 1.25;
  }
  .edm-card-title a {
    color: #fff;
    text-decoration: none;
  }
  .edm-card-title a:hover {
    color: var(--cyan);
    text-decoration: underline;
  }
  .edm-card-venue {
    font-size: 13px;
    color: #a4b3c9;
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }
  .edm-card-neigh {
    font-size: 11px;
    color: var(--muted);
    background: rgba(255,255,255,0.06);
    padding: 1px 6px;
    border-radius: 4px;
  }
  .edm-card-desc {
    font-size: 12.5px;
    color: var(--muted);
    line-height: 1.45;
    margin: 2px 0 6px;
    overflow-wrap: anywhere;
  }
  .edm-card-footer {
    margin-top: auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-top: 10px;
    border-top: 1px solid rgba(255,255,255,0.06);
  }
  .edm-ticket-btn {
    background: linear-gradient(135deg, rgba(0, 240, 255, 0.15), rgba(168, 85, 247, 0.2));
    border: 1px solid rgba(0, 240, 255, 0.4);
    color: #fff;
    font-size: 12px;
    font-weight: 700;
    padding: 5px 12px;
    border-radius: 6px;
    text-decoration: none;
    transition: all 0.15s ease;
  }
  .edm-ticket-btn:hover {
    background: var(--cyan);
    color: #07080f;
    box-shadow: 0 0 12px rgba(0, 240, 255, 0.5);
    text-decoration: none;
  }
  @media (max-width: 640px) {
    .edm-hero-art { height: 130px; }
    .edm-filter-label { min-width: 100%; }
    .edm-hub .hub-nav { font-size: 12px; gap: 8px 10px; }
  }
"""

_EDM_FILTER_JS = """<script>
(function () {
  var chips = document.querySelectorAll('.edm-chip');
  if (!chips.length) return;
  var cards = document.querySelectorAll('.hub-card.edm-card');
  var heads = document.querySelectorAll('.hub-day');
  var citySecs = document.querySelectorAll('.edm-city-section');
  var state = { genre: 'all', area: 'all', when: 'all', cost: 'all' };

  function matches(c) {
    if (state.genre !== 'all' && c.dataset.genre !== state.genre) return false;
    if (state.area !== 'all' && c.dataset.area !== state.area) return false;
    if (state.when === 'tonight' && c.dataset.when !== 'tonight') return false;
    if (state.when === 'weekend' && c.dataset.when !== 'weekend' && c.dataset.when !== 'tonight') return false;
    if (state.cost === 'free' && c.dataset.free !== '1') return false;
    return true;
  }

  function render(save) {
    var days = {}, n = 0;
    cards.forEach(function (c) {
      var on = matches(c);
      c.hidden = !on;
      if (on) { days[c.dataset.day] = 1; n++; }
    });
    heads.forEach(function (h) { h.hidden = !days[h.dataset.day]; });
    citySecs.forEach(function (sec) {
      var visible = sec.querySelectorAll('.hub-card.edm-card:not([hidden])').length;
      sec.hidden = (visible === 0);
      var cCount = sec.querySelector('.edm-city-head .count');
      if (cCount) cCount.textContent = visible;
    });
    chips.forEach(function (b) {
      var g = b.dataset.group, v = b.dataset.val;
      b.classList.toggle('active', state[g] === v);
    });
    var none = document.getElementById('hub-none');
    if (none) none.hidden = n > 0;
    if (save) {
      var parts = Object.keys(state).filter(function (k) { return state[k] !== 'all'; }).map(function (k) { return k + '=' + state[k]; });
      history.replaceState(null, '', parts.length ? '#' + parts.join('&') : location.pathname);
    }
  }

  chips.forEach(function (b) {
    b.addEventListener('click', function () {
      var g = b.dataset.group, v = b.dataset.val;
      if (g === 'cost' && state[g] === v && v !== 'all') {
        state[g] = 'all';
      } else {
        state[g] = v;
      }
      render(true);
    });
  });

  location.hash.replace(/^#/, '').split('&').forEach(function (p) {
    var kv = p.split('=');
    if (kv.length === 2 && state.hasOwnProperty(kv[0])) {
      var btn = document.querySelector('.edm-chip[data-group="' + kv[0] + '"][data-val="' + kv[1] + '"]');
      if (btn) state[kv[0]] = kv[1];
    }
  });
  render(false);
})();
</script>"""


# Rooms that only book this kind of night
_EDM_VENUES = ("nowadays", "elsewhere", "knockdown center", "bossa nova civic club", "good room", "h0l0", "public records",
               "basement", "mirage", "signal", "paragon", "le bain", "marquee")
_NOT_EDM_CATEGORIES = ("comedy", "family", "theater", "sports", "books", "art", "markets", "services", "tech", "deals")
_NOT_EDM_GENRES = ("jazz_blues", "folk_trad", "classical")
CARD_LIMIT = 1500  # about three weeks of the 35-day calendar
_CITY_ORDER = ("manhattan", "brooklyn", "queens", "bronx", "staten_island", "citywide")
_AREA_CHIPS = (("manhattan", "Manhattan"), ("brooklyn", "Brooklyn"), ("queens", "Queens"), ("bronx", "The Bronx"),
               ("staten_island", "Staten Island"), ("citywide", "Citywide"))


def is_edm_event(e):
    title = (e.get("name") or "").strip()
    venue = (e.get("venue") or e.get("_source_venue") or "").lower()
    cat = (e.get("category") or "").lower()
    if cat in _NOT_EDM_CATEGORIES or _EDM_NON_WORDS.search(title) or _EDM_TITLE_EXCLUSIONS.search(title):
        return False
    if e.get("genre") in _NOT_EDM_GENRES:
        return False
    if e.get("genre") == "electronic" or cat == "clubbing":
        return True
    text = f"{title} {e.get('description') or ''}"
    return any(rx.search(text) for k, _l, _e, rx in _EDM_SUBGENRE_PATTERNS if k not in ("latin", "hiphop")) or any(v in venue for v in _EDM_VENUES)


def _vibe(e):
    text = f"{e.get('name') or ''} {e.get('venue') or ''} {e.get('description') or ''}"
    for key, label, emoji, rx in _EDM_SUBGENRE_PATTERNS:
        if rx.search(text):
            return key, label.split(" ", 1)[1], emoji
    return "club", "DJ Sets & Dance", "🪩"


def _when_tag(t):
    today = datetime.now(EASTERN).date()
    if t.date() == today:
        return "tonight"
    if t.weekday() in (4, 5, 6) and 0 <= (t.date() - today).days < 7:
        return "weekend"
    return "upcoming"


def _chips(group, rows):
    return "".join(f'<button type="button" class="edm-chip{" active" if v == "all" else ""}" data-group="{group}" data-val="{v}">{lbl}</button>'
                   for v, lbl in rows)


def render_body(events, city_of, is_free, query, title, subtitle, city_labels):
    """(hero html, filters html, sections html) for date-sorted events. city_of(e) gives a borough."""
    vibes, free, places, by_day = {}, 0, set(), {}

    def card(e, city):
        nonlocal free
        key, label, emoji = _vibe(e)
        vibes[key] = vibes.get(key, 0) + 1
        places.add(e.get("venue") or "")
        t = e["_time"]
        paid = not is_free(e)
        free += 0 if paid else 1
        when = "Time TBA" if e.get("_time_unknown") else ("All day" if (t.hour, t.minute) == (0, 0) and e.get("_all_day") else t.strftime("%-I:%M %p"))
        if not paid:
            badge = '<span class="badge badge-free">Free</span>'
        elif e.get("price"):
            badge = f'<span class="badge badge-price">{escape(str(e["price"]))[:24]}</span>'
        else:
            badge = ""
        desc = re.sub(r"\s+", " ", str(e.get("description") or "")).strip()
        desc_html = f'<p class="edm-card-desc">{escape(desc[:160] + ("…" if len(desc) > 160 else ""))}</p>' if desc else ""
        url = escape(e.get("url") or "../")
        return f"""<article class="hub-card edm-card edm-k-{key}" data-city="{city}" data-day="{t.date().isoformat()}" data-genre="{key}" data-area="{city}" data-when="{_when_tag(t)}" data-free="{0 if paid else 1}">
  <div class="edm-card-band"></div>
  <div class="edm-card-body">
    <div class="edm-card-top">
      <div class="edm-card-subgenre"><span aria-hidden="true">{emoji}</span> {escape(label)}</div>
      <div class="hub-badges">{badge}</div>
    </div>
    <h3 class="edm-card-title"><a href="{url}" target="_blank" rel="noopener">{escape(e.get('name') or 'Event')}</a></h3>
    <div class="edm-card-venue"><span>📍 {escape(e.get('venue') or e.get('_source_venue') or '')}</span></div>
    {desc_html}
    <div class="edm-card-footer">
      <time class="hub-date">{when}</time>
      <a href="{url}" target="_blank" rel="noopener" class="edm-ticket-btn">Tickets / Info →</a>
    </div>
  </div>
</article>"""

    for e in events[:CARD_LIMIT]:
        by_day.setdefault(e["_time"].date(), []).append(e)

    sections, present = [], set()
    for day, day_events in by_day.items():
        iso = day.isoformat()
        sections.append(f'<h2 class="hub-day" id="{iso}" data-day="{iso}">{day.strftime("%A, %B")} {day.day}</h2>')
        by_city = {}
        for e in day_events:
            by_city.setdefault(city_of(e), []).append(e)
        for city in _CITY_ORDER:
            city_events = by_city.get(city)
            if not city_events:
                continue
            present.add(city)
            cards = "".join(card(e, city) for e in city_events)
            sections.append(f"""<div class="edm-city-section" data-city="{city}" data-day="{iso}">
  <div class="edm-city-head">
    <span class="edm-city-pill city-{city}">{escape(city_labels.get(city, city.title()))}</span>
    <span class="count">{len(city_events)}</span>
  </div>
  <div class="edm-city-cards">{cards}</div>
</div>""")

    vibe_chips = _chips("genre", [("all", "All Vibes")] + [(k, lbl) for k, lbl, _e, _r in _EDM_SUBGENRE_PATTERNS if vibes.get(k)])
    area_chips = _chips("area", [("all", "All Boroughs")] + [(k, lbl) for k, lbl in _AREA_CHIPS if k in present])
    when_chips = _chips("when", [("all", "All Dates"), ("tonight", "🔥 Tonight"), ("weekend", "🎉 This Weekend")])
    cost_chips = _chips("cost", [("all", "All Prices"), ("free", "💛 Free / No Cover")])
    filters = f"""<div class="edm-filters" role="group" aria-label="Filter DJ nights and dance parties">
    <div class="edm-filter-row"><span class="edm-filter-label">Vibes</span>{vibe_chips}</div>
    <div class="edm-filter-row"><span class="edm-filter-label">Area</span>{area_chips}</div>
    <div class="edm-filter-row"><span class="edm-filter-label">When</span>{when_chips}</div>
    <div class="edm-filter-row"><span class="edm-filter-label">Cost</span>{cost_chips}</div>
  </div>"""
    n_cards = sum(vibes.values())
    hero = f"""<div class="hero">
    {_EDM_HERO_ART}
    <div class="edm-hero-copy">
      <h1>{escape(title)}<small>Warehouses, rooftops &amp; basements across the five boroughs</small></h1>
      <p>{escape(subtitle)}</p>
      <div class="edm-stats"><span class="edm-stat">⚡ {n_cards} shows &amp; club nights</span><span class="edm-stat">💛 {free} free / no cover</span><span class="edm-stat">📍 {len(places)} venues</span></div>
      <a href="../{query}" class="cta-btn">View on interactive calendar →</a>
    </div>
  </div>"""
    body = "\n".join(sections) or '<p class="no-hub-events">No club nights are listed right now.</p>'
    none = '<p id="hub-none" class="no-hub-events" hidden>Nothing matches those filters.</p>'
    return hero, filters, f"{body}\n{none}"
