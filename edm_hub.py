"""DJ Nights, Techno & Dance Parties hub: a dark, neon page with vibe, borough, date and cost filters.

Ported from boston_events, with Latin and hip-hop filters since those make up much of NYC's club
listings, the five boroughs as areas, left-sidebar dropdown filters, and Google Maps venue links.
"""
import re
from datetime import datetime
from html import escape
from urllib.parse import quote_plus

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

_EDM_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@700;800;900&family=Syne:wght@700;800;900&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">'
)

_EDM_HERO_ART = """<svg class="edm-hero-art" viewBox="0 0 900 200" aria-hidden="true" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="edm-sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#02040a"/>
      <stop offset="40%" stop-color="#070b1f"/>
      <stop offset="80%" stop-color="#111638"/>
      <stop offset="100%" stop-color="#1b1033"/>
    </linearGradient>
    <linearGradient id="beam-cyan" x1="0" y1="1" x2="0.5" y2="0">
      <stop offset="0%" stop-color="#00f0ff" stop-opacity="0.75"/>
      <stop offset="60%" stop-color="#00f0ff" stop-opacity="0.2"/>
      <stop offset="100%" stop-color="#00f0ff" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="beam-pink" x1="1" y1="1" x2="0.3" y2="0">
      <stop offset="0%" stop-color="#ff007f" stop-opacity="0.7"/>
      <stop offset="60%" stop-color="#ff007f" stop-opacity="0.2"/>
      <stop offset="100%" stop-color="#ff007f" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="beam-lime" x1="0" y1="1" x2="0.7" y2="0">
      <stop offset="0%" stop-color="#00ff88" stop-opacity="0.55"/>
      <stop offset="60%" stop-color="#00ff88" stop-opacity="0.15"/>
      <stop offset="100%" stop-color="#00ff88" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="beam-purple" x1="0.5" y1="1" x2="0.5" y2="0">
      <stop offset="0%" stop-color="#b026ff" stop-opacity="0.65"/>
      <stop offset="60%" stop-color="#b026ff" stop-opacity="0.2"/>
      <stop offset="100%" stop-color="#b026ff" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="bar-grad" x1="0" y1="1" x2="0" y2="0">
      <stop offset="0%" stop-color="#00f0ff" stop-opacity="0.25"/>
      <stop offset="40%" stop-color="#00f0ff" stop-opacity="0.8"/>
      <stop offset="75%" stop-color="#b026ff"/>
      <stop offset="100%" stop-color="#ff007f"/>
    </linearGradient>
    <radialGradient id="nebula-center" cx="50%" cy="60%" r="45%">
      <stop offset="0%" stop-color="#b026ff" stop-opacity="0.35"/>
      <stop offset="50%" stop-color="#00f0ff" stop-opacity="0.12"/>
      <stop offset="100%" stop-color="#02040a" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="water-grad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#060815" stop-opacity="0.95"/>
      <stop offset="100%" stop-color="#030409"/>
    </linearGradient>
    <filter id="glow-neon" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="4" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>
  <rect width="900" height="200" fill="url(#edm-sky)"/>
  <rect width="900" height="200" fill="url(#nebula-center)"/>
  <g opacity="0.85">
    <polygon points="450,165 40,0 85,0" fill="url(#beam-cyan)"/>
    <polygon points="450,165 815,0 860,0" fill="url(#beam-pink)"/>
    <polygon points="450,165 240,0 275,0" fill="url(#beam-lime)"/>
    <polygon points="450,165 625,0 660,0" fill="url(#beam-purple)"/>
    <polygon points="450,165 435,0 465,0" fill="url(#beam-cyan)" opacity="0.6"/>
  </g>
  <g stroke-linecap="round" opacity="0.75" filter="url(#glow-neon)">
    <line x1="450" y1="165" x2="60" y2="0" stroke="#00f0ff" stroke-width="1.5"/>
    <line x1="450" y1="165" x2="840" y2="0" stroke="#ff007f" stroke-width="1.5"/>
    <line x1="450" y1="165" x2="255" y2="0" stroke="#00ff88" stroke-width="1"/>
    <line x1="450" y1="165" x2="645" y2="0" stroke="#b026ff" stroke-width="1"/>
  </g>
  <g fill="url(#bar-grad)">
    <rect x="30" y="118" width="6" height="36" rx="2"/><rect x="40" y="98" width="6" height="56" rx="2"/>
    <rect x="50" y="128" width="6" height="26" rx="2"/><rect x="60" y="78" width="6" height="76" rx="2"/>
    <rect x="70" y="106" width="6" height="48" rx="2"/><rect x="80" y="62" width="6" height="92" rx="2"/>
    <rect x="90" y="88" width="6" height="66" rx="2"/><rect x="100" y="116" width="6" height="38" rx="2"/>
    <rect x="110" y="74" width="6" height="80" rx="2"/><rect x="120" y="102" width="6" height="52" rx="2"/>
    <rect x="130" y="58" width="6" height="96" rx="2"/><rect x="140" y="92" width="6" height="62" rx="2"/>
    <rect x="734" y="82" width="6" height="72" rx="2"/><rect x="744" y="124" width="6" height="30" rx="2"/>
    <rect x="754" y="92" width="6" height="62" rx="2"/><rect x="764" y="58" width="6" height="96" rx="2"/>
    <rect x="774" y="102" width="6" height="52" rx="2"/><rect x="784" y="74" width="6" height="80" rx="2"/>
    <rect x="794" y="116" width="6" height="38" rx="2"/><rect x="804" y="88" width="6" height="66" rx="2"/>
    <rect x="814" y="62" width="6" height="92" rx="2"/><rect x="824" y="106" width="6" height="48" rx="2"/>
    <rect x="834" y="78" width="6" height="76" rx="2"/><rect x="844" y="128" width="6" height="26" rx="2"/>
  </g>
  <rect x="0" y="154" width="900" height="46" fill="url(#water-grad)"/>
  <g transform="translate(450, 24)">
    <rect x="-135" y="-12" width="270" height="24" rx="12" fill="#04060e" stroke="#00f0ff" stroke-width="1.4" opacity="0.95"/>
    <circle cx="-118" cy="0" r="4" fill="#00f0ff" filter="url(#glow-neon)"/>
    <circle cx="118" cy="0" r="4" fill="#ff007f" filter="url(#glow-neon)"/>
    <text x="0" y="4" text-anchor="middle" font-family="'Orbitron', -apple-system, sans-serif" font-size="10" font-weight="800" fill="#00f0ff" letter-spacing="1.4">⚡ NYC UNDERGROUND &amp; CLUBS</text>
  </g>
</svg>"""

_EDM_CSS = """
  .hub-card[hidden], .hub-day[hidden], .edm-city-section[hidden] { display: none !important; }
  .edm-hub .cta-btn { display: inline-block; text-decoration: none; }
  .edm-hub .badge { padding: 2px 9px; border-radius: 999px; font-size: 11px; font-weight: 800; white-space: nowrap; }
  .edm-hub .badge-free { background: rgba(0, 255, 136, 0.15); color: #00ff88; border: 1.5px solid #00ff88; border-radius: 999px; }
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
  .edm-hub h1, .edm-hub h2, .edm-hub h3, .edm-hub .logo, .edm-hub .edm-chip, .edm-hub .cta-btn, .edm-hub .edm-card-subgenre, .edm-filter-label {
    font-family: "Syne", "Orbitron", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  .edm-hub header {
    background: rgba(7, 8, 15, 0.92) !important;
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border) !important;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px 16px;
    padding: 12px 20px;
  }
  .edm-hub .logo { color: #fff !important; font-weight: 800; font-size: 18px; text-decoration: none; }
  .edm-hub .logo span {
    color: var(--cyan) !important;
    text-shadow: 0 0 10px rgba(0, 240, 255, 0.6);
  }
  .edm-hub .hub-nav a {
    color: var(--muted);
    padding: 5px 12px;
    border-radius: 999px;
    transition: all 0.15s ease;
    text-decoration: none;
    border: 1px solid transparent;
    white-space: nowrap;
    font-weight: 600;
  }
  .edm-hub .hub-nav a:hover {
    color: var(--cyan);
    background: rgba(0, 240, 255, 0.08);
    border-color: rgba(0, 240, 255, 0.25);
  }
  .edm-hub .hub-nav a.active {
    color: #04060f;
    background: var(--cyan);
    border-color: var(--cyan);
    box-shadow: 0 0 14px rgba(0, 240, 255, 0.5);
    font-weight: 800;
  }
  .edm-hub main { max-width: 1120px; padding-top: 22px; }
  .edm-hub .hero {
    border: 1px solid var(--border);
    background: #090b16;
    border-radius: 24px;
    overflow: hidden;
    box-shadow: 0 0 30px rgba(0, 240, 255, 0.08), 0 12px 40px rgba(0,0,0,0.6);
    margin-bottom: 22px;
  }
  .edm-hero-art { display: block; width: 100%; height: 190px; }
  .edm-hero-copy { padding: 20px 24px 26px; text-align: left; }
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
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-top: 6px;
    -webkit-text-fill-color: var(--cyan);
    text-shadow: 0 0 8px rgba(0, 240, 255, 0.4);
  }
  .edm-hub .hero p {
    color: var(--muted);
    font-size: 15px;
    max-width: 720px;
    margin: 0 0 16px;
    line-height: 1.5;
  }
  .edm-hero-bar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin: 0; }
  .edm-stats { display: flex; gap: 10px; flex-wrap: wrap; margin: 0; }
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
    margin-left: auto;
    white-space: nowrap;
  }
  .edm-hub .cta-btn:hover { filter: brightness(1.15); transform: translateY(-1px); }
  .edm-layout {
    display: grid;
    grid-template-columns: 260px minmax(0, 1fr);
    gap: 26px;
    align-items: start;
    margin-bottom: 24px;
  }
  .edm-sidebar {
    position: sticky;
    top: 80px;
    background: #090c18;
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 18px 16px;
    box-shadow: 0 0 24px rgba(0, 240, 255, 0.06);
  }
  .edm-filter-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 14px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }
  .edm-sidebar-title {
    font-size: 14px;
    font-weight: 800;
    color: #fff;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin: 0;
  }
  .edm-reset-btn {
    background: none;
    border: none;
    color: var(--cyan);
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
    padding: 2px 6px;
  }
  .edm-reset-btn:hover {
    text-shadow: 0 0 8px rgba(0, 240, 255, 0.6);
    text-decoration: underline;
  }
  .edm-filters {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .edm-filter-group {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .edm-filter-label {
    font-size: 11px;
    font-weight: 700;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .edm-select {
    appearance: none;
    -webkit-appearance: none;
    background: #0d1122 url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' fill='none' stroke='%2300f0ff' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M1 1l4 4 4-4'/%3E%3C/svg%3E") no-repeat right 10px center;
    border: 1px solid rgba(0, 240, 255, 0.25);
    border-radius: 8px;
    color: #fff;
    font-size: 13px;
    font-weight: 600;
    padding: 7px 28px 7px 12px;
    cursor: pointer;
    width: 100%;
    box-sizing: border-box;
    transition: all 0.15s ease;
  }
  .edm-select:hover, .edm-select:focus {
    border-color: var(--cyan);
    box-shadow: 0 0 10px rgba(0, 240, 255, 0.3);
    outline: none;
  }
  .edm-chip { font-size: 13px; font-weight: 600; }
  .edm-main-col { min-width: 0; }
  .edm-hub .hub-day {
    margin: 28px 0 14px;
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
  .edm-hub .hub-day:first-child { margin-top: 4px; }
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
    border: 1px solid transparent;
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
  .edm-k-latin { --edm-band: #ff8c00; }
  .edm-k-hiphop { --edm-band: #a855f7; }
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
  .edm-venue-link {
    color: #b8c7dd;
    text-decoration: none;
    border-bottom: 1px dotted rgba(0, 240, 255, 0.35);
    font-weight: 600;
  }
  .edm-venue-link:hover {
    color: var(--cyan);
    border-bottom-color: var(--cyan);
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
  @media (max-width: 860px) {
    .edm-layout { grid-template-columns: 1fr; gap: 16px; }
    .edm-sidebar { position: static; padding: 12px 14px; margin-bottom: 12px; }
    .edm-filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(135px, 1fr)); gap: 8px; }
  }
  @media (max-width: 640px) {
    .edm-hero-art { height: 130px; }
    .edm-hub .hub-nav { font-size: 12px; gap: 6px 8px; }
  }
"""

_EDM_FILTER_JS = """<script>
(function () {
  var selects = document.querySelectorAll('.edm-select');
  var chips = document.querySelectorAll('.edm-chip');
  if (!selects.length && !chips.length) return;
  var cards = document.querySelectorAll('.hub-card.edm-card');
  var heads = document.querySelectorAll('.hub-day');
  var citySecs = document.querySelectorAll('.edm-city-section');
  var resetBtn = document.getElementById('edm-reset-btn');
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
    selects.forEach(function (sel) {
      if (state[sel.dataset.group] !== undefined) {
        sel.value = state[sel.dataset.group];
      }
    });
    chips.forEach(function (b) {
      var g = b.dataset.group, v = b.dataset.val;
      b.classList.toggle('active', state[g] === v);
    });
    var none = document.getElementById('hub-none');
    if (none) none.hidden = n > 0;
    if (resetBtn) {
      var hasFilters = Object.keys(state).some(function (k) { return state[k] !== 'all'; });
      resetBtn.hidden = !hasFilters;
    }
    if (save) {
      var parts = Object.keys(state).filter(function (k) { return state[k] !== 'all'; }).map(function (k) { return k + '=' + state[k]; });
      history.replaceState(null, '', parts.length ? '#' + parts.join('&') : location.pathname);
    }
  }

  selects.forEach(function (sel) {
    sel.addEventListener('change', function () {
      state[sel.dataset.group] = sel.value;
      render(true);
    });
  });

  chips.forEach(function (b) {
    if (b.tagName !== 'OPTION') {
      b.addEventListener('click', function () {
        var g = b.dataset.group, v = b.dataset.val;
        if (g === 'cost' && state[g] === v && v !== 'all') {
          state[g] = 'all';
        } else {
          state[g] = v;
        }
        render(true);
      });
    }
  });

  if (resetBtn) {
    resetBtn.addEventListener('click', function () {
      Object.keys(state).forEach(function (k) { state[k] = 'all'; });
      render(true);
    });
  }

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
_EDM_VENUES = (
    "nowadays", "elsewhere", "knockdown center", "bossa nova civic club", "good room",
    "h0l0", "public records", "basement", "mirage", "avant gardner", "brooklyn storehouse",
    "signal", "paragon", "le bain", "marquee", "superior ingredients", "silo brooklyn",
    "gabriela", "musica", "market hotel", "trans-pecos", "jupiter disco", "c'mon everybody",
    "the sultan room", "mood ring",
)
_NOT_EDM_CATEGORIES = ("comedy", "family", "theater", "sports", "books", "art", "markets", "services", "tech", "deals")
_NOT_EDM_GENRES = ("jazz_blues", "folk_trad", "classical")
CARD_LIMIT = 1500  # about three weeks of the 35-day calendar
_CITY_ORDER = ("manhattan", "brooklyn", "queens", "bronx", "staten_island", "citywide")
_AREA_CHIPS = (
    ("manhattan", "Manhattan"),
    ("brooklyn", "Brooklyn"),
    ("queens", "Queens"),
    ("bronx", "The Bronx"),
    ("staten_island", "Staten Island"),
    ("citywide", "Citywide"),
)


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


def _opt(group, val, label, is_active=False):
    cls = "edm-chip active" if is_active else "edm-chip"
    return f'<option class="{cls}" data-group="{group}" data-val="{val}" value="{val}">{label}</option>'


def render_body(events, city_of, is_free, query, title, subtitle, city_labels):
    """(hero html, filters html, sections html) for date-sorted events. city_of(e) gives a borough."""
    vibes, free, places, by_day = {}, 0, set(), {}

    def card(e, city):
        nonlocal free
        key, label, emoji = _vibe(e)
        vibes[key] = vibes.get(key, 0) + 1
        raw_venue = (e.get("venue") or e.get("_source_venue") or "NYC Club").strip()
        if raw_venue.lower() in ("nyc / the skint", "the skint", "nyc / secret nyc", "secret nyc"):
            raw_venue = city_labels.get(city, "New York City")
        places.add(raw_venue)
        gmaps_url = escape(f"https://www.google.com/maps/search/?api=1&query={quote_plus(raw_venue + ', ' + city_labels.get(city, 'New York') + ', NY')}")
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
    <div class="edm-card-venue"><a class="edm-venue-link" href="{gmaps_url}" target="_blank" rel="noopener" title="Open {escape(raw_venue)} in Google Maps">📍 {escape(raw_venue)}</a></div>
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

    vibe_opts = _opt("genre", "all", "⚡ All Vibes", is_active=True) + "".join(
        _opt("genre", k, lbl) for k, lbl, _e, _r in _EDM_SUBGENRE_PATTERNS if vibes.get(k)
    )
    area_opts = _opt("area", "all", "📍 All Boroughs", is_active=True) + "".join(
        _opt("area", k, lbl) for k, lbl in _AREA_CHIPS if k in present
    )
    when_opts = (
        _opt("when", "all", "📅 All Dates", is_active=True)
        + _opt("when", "tonight", "🔥 Tonight")
        + _opt("when", "weekend", "🎉 This Weekend")
    )
    cost_opts = (
        _opt("cost", "all", "💵 All Prices", is_active=True)
        + _opt("cost", "free", "💛 Free / No Cover")
    )

    edm_sidebar = f"""<aside class="edm-sidebar" aria-label="Electronic &amp; EDM filters">
    <div class="edm-filter-header">
      <h2 class="edm-sidebar-title">Filters</h2>
      <button type="button" id="edm-reset-btn" class="edm-reset-btn" hidden>Reset</button>
    </div>
    <div class="edm-filters" role="group" aria-label="Filter DJ nights and dance parties">
      <div class="edm-filter-group">
        <label class="edm-filter-label" for="edm-genre">Music Style</label>
        <select id="edm-genre" class="edm-select" data-group="genre" aria-label="Vibes">{vibe_opts}</select>
      </div>
      <div class="edm-filter-group">
        <label class="edm-filter-label" for="edm-area">Borough</label>
        <select id="edm-area" class="edm-select" data-group="area" aria-label="Area">{area_opts}</select>
      </div>
      <div class="edm-filter-group">
        <label class="edm-filter-label" for="edm-when">When</label>
        <select id="edm-when" class="edm-select" data-group="when" aria-label="When">{when_opts}</select>
      </div>
      <div class="edm-filter-group">
        <label class="edm-filter-label" for="edm-cost">Cover / Price</label>
        <select id="edm-cost" class="edm-select" data-group="cost" aria-label="Cost">{cost_opts}</select>
      </div>
    </div>
  </aside>"""

    n_cards = sum(vibes.values())
    hero = f"""<div class="hero">
    {_EDM_HERO_ART}
    <div class="edm-hero-copy">
      <h1>{escape(title)}<small>Warehouses, rooftops &amp; basements across the five boroughs</small></h1>
      <p>{escape(subtitle)}</p>
      <div class="edm-hero-bar">
        <div class="edm-stats"><span class="edm-stat">⚡ {n_cards} shows &amp; club nights</span><span class="edm-stat">💛 {free} free / no cover</span><span class="edm-stat">📍 {len(places)} venues</span></div>
        <a href="../{query}" class="cta-btn">Full calendar →</a>
      </div>
    </div>
  </div>"""
    body_list = "\n".join(sections) or '<p class="no-hub-events">No club nights are listed right now.</p>'
    none = '<p id="hub-none" class="no-hub-events" hidden>Nothing matches those filters.</p>'
    full_body = f"""<div class="edm-layout">
  {edm_sidebar}
  <div class="edm-main-col">
    {body_list}
    {none}
  </div>
</div>"""
    return hero, "", full_body
