"""Kids & Family hub: a light, playful page with borough, age, activity and cost filters.

Ages and activities are read from each listing's title, then its description: "Toddler Tales
(ages 1.5-3)", "0-18 months", "Grades 3-5". Ported from boston_events.
"""
import re
from html import escape

_KID_AGE_BUCKETS = (  # key, label, (lo, hi) years
    ("baby", "👶 Babies (0–1)", (0, 1.5)),
    ("toddler", "🧸 Toddlers (1–3)", (1, 3)),
    ("preschool", "🖍️ Preschool (3–5)", (3, 5)),
    ("bigkid", "🎒 Kids (5–12)", (5, 12)),
)
_KID_AGE_WORDS = (
    ("baby", r"\b(?:bab(?:y|ies)|newborns?|infants?|pre-?walkers?|lap ?(?:sit|time)|wee ones|0\s*[-–]\s*18 months)\b"),
    ("toddler", r"\b(?:toddlers?|walkers|twos|tots?|little ones)\b"),
    ("preschool", r"\b(?:pre-?school(?:ers)?|pre-?k)\b"),
    ("bigkid", r"\b(?:school[- ]age|elementary|tweens?|kids club|grades? k\b)"),
)
_KID_FAMILY_RE = re.compile(r"(?i)\b(?:famil(?:y|ies)|all ages|caregivers|kids & adults|for everyone)\b")
_KID_RANGE_RES = (
    (re.compile(r"(?i)\bages?\s*(\d{1,2}(?:\.\d)?)\s*(?:-|–|—|to)\s*(\d{1,2}(?:\.\d)?)\b"), 1.0),
    (re.compile(r"(?i)\b(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})\s*(?:months?|mos)\b"), 1 / 12),
    (re.compile(r"(?i)\(\s*(\d{1,2}(?:\.\d)?)\s*(?:-|–|—)\s*(\d{1,2}(?:\.\d)?)\s*\)"), 1.0),
)
_KID_GRADE_RE = re.compile(r"(?i)\bgrades?\s*(k|pre-?k|\d{1,2})\s*(?:-|–|—|to|&)\s*(\d{1,2})\b")
_KID_SINGLE_AGE_RE = re.compile(r"(?i)\bages?\s*(\d{1,2})\s*(?:\+|and up|& up|and older)")

_KID_KINDS = (  # key, label, emoji, pattern (checked in order)
    ("show", "Shows", "🎭", r"\b(?:puppets?|theat(?:er|re)|musical|magic(?:ian)?|circus|ballet|film|movie|cinema|perform(?:ance|ers)?|concert)\b"),
    ("story", "Storytime", "📚", r"\b(?:stor(?:y|ies)|storytimes?|read(?:ing|-?alouds?)?|books?|lap ?time|tales|rhymes?)\b"),
    ("music", "Music & movement", "🎵", r"\b(?:sing(?:-?along|ing)?|songs?|music(?:al)?|danc(?:e|ing)|movement|rave|jam|drums?|rhythm|beats|wiggles?|yoga|groove|ukulele|guitar)\b"),
    ("nature", "Nature & animals", "🌿", r"\b(?:nature|walks?|hikes?|owls?|birds?|birding|gardens?|farm|goats?|animals?|zoo|aquarium|arboretum|ponds?|leaf|leaves|trails?|outdoors?|bugs?|insects?|trees?|turkeys?|fish|penguins?|seals?|whales?)\b"),
    ("make", "Arts, crafts & STEAM", "🎨", r"\b(?:crafts?|art|arts|make|makers?|lego|paint(?:ing)?|draw(?:ing)?|build(?:ing|ers)?|steam|stem|science|scientists?|cook(?:ing)?|bak(?:e|ing)|sew(?:ing)?|clay|creat(?:e|ive|ivity)|engineer(?:ing)?|robots?|coding|experiments?|dinosaurs?|museum)\b"),
    ("play", "Play & games", "🧸", r"\b(?:play(?:group|time|date)?s?|open gym|drop-?in|games?|puzzles?|blocks|chess|pokemon|pokémon|playground|sensory)\b"),
)
_KID_KIND_RES = [(k, lbl, emo, re.compile("(?i)" + pat)) for k, lbl, emo, pat in _KID_KINDS]
_KID_OTHER = ("other", "Everything else", "🎈")


def _kid_tags(e):
    """(age bucket keys, kind key, emoji, age label) for a Kids & Family card, from its title and
    description: "Toddler Tales (ages 1.5-3)" -> (["toddler"], "story", "📚", "Ages 1.5–3")."""
    title = e.get("name") or e.get("title") or ""
    desc = (e.get("description") or "")[:300]
    blob = f"{title} {desc}"
    ages, label = set(), ""
    spans = []
    # ages from the title; else from the description's "ages 2-5" / "for babies" wording
    for rx, scale in _KID_RANGE_RES:
        for m in rx.finditer(title) or ():
            lo, hi = float(m.group(1)) * scale, float(m.group(2)) * scale
            if 0 <= lo <= hi <= 18:
                spans.append((lo, hi))
                if not label:
                    unit = " months" if scale != 1.0 else ""
                    label = (f"Ages {m.group(1)}–{m.group(2)}" if not unit else f"{m.group(1)}–{m.group(2)} months")
    for m in _KID_GRADE_RE.finditer(title):
        g0 = 0 if m.group(1).lower() in ("k", "pre-k", "prek") else int(m.group(1))
        g1 = int(m.group(2))
        if g0 <= g1 <= 12:
            spans.append((g0 + 5, g1 + 6))
            label = label or f"Grades {m.group(1).upper()}–{g1}"
    m = _KID_SINGLE_AGE_RE.search(title)
    if m and int(m.group(1)) <= 12:
        spans.append((int(m.group(1)), 12))
        label = label or f"Ages {m.group(1)}+"
    for lo, hi in spans:
        for key, _lbl, (blo, bhi) in _KID_AGE_BUCKETS:
            if lo < bhi and hi > blo or (lo == hi and blo <= lo <= bhi):
                ages.add(key)
    if not spans:
        for key, pat in _KID_AGE_WORDS:
            if re.search("(?i)" + pat, title):
                ages.add(key)
    if not spans and not ages and desc:
        for rx, scale in _KID_RANGE_RES[:2]:  # "(3-5)" alone in prose is too loose
            for m in rx.finditer(desc):
                lo, hi = float(m.group(1)) * scale, float(m.group(2)) * scale
                if 0 <= lo <= hi <= 18:
                    spans.append((lo, hi))
        for m in _KID_GRADE_RE.finditer(desc):
            g0 = 0 if m.group(1).lower() in ("k", "pre-k", "prek") else int(m.group(1))
            if g0 <= int(m.group(2)) <= 12:
                spans.append((g0 + 5, int(m.group(2)) + 6))
        for lo, hi in spans:
            for key, _lbl, (blo, bhi) in _KID_AGE_BUCKETS:
                if lo < bhi and hi > blo:
                    ages.add(key)
        if not spans:
            for key, pat in _KID_AGE_WORDS:
                if re.search("(?i)" + pat, desc):
                    ages.add(key)
    if not ages or _KID_FAMILY_RE.search(title):
        ages.add("family")
    kind = _KID_OTHER
    for k, lbl, emo, rx in _KID_KIND_RES:
        if rx.search(title):
            kind = (k, lbl, emo)
            break
    else:
        for k, lbl, emo, rx in _KID_KIND_RES:
            if rx.search(blob):
                kind = (k, lbl, emo)
                break
    order = [k for k, _l, _r in _KID_AGE_BUCKETS] + ["family"]
    return sorted(ages, key=order.index), kind[0], kind[2], label


_KID_AGE_PILL = {"baby": "Babies (0–1)", "toddler": "Toddlers (1–3)", "preschool": "Preschool (3–5)", "bigkid": "Kids (5–12)", "family": "All ages"}

_KIDS_FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
               '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
               '<link href="https://fonts.googleapis.com/css2?family=Baloo+2:wght@600;700;800&family=Nunito:wght@400;600;700;800&display=swap" rel="stylesheet">')

_KIDS_HERO_ART = """<svg class="kids-hero-art" viewBox="0 0 900 220" aria-hidden="true" preserveAspectRatio="xMidYMid slice">
  <defs><linearGradient id="kh-sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#bfe5fb"/><stop offset="1" stop-color="#e6f5fd"/></linearGradient></defs>
  <rect width="900" height="220" fill="url(#kh-sky)"/>
  <g opacity="0.9" fill="none" stroke-linecap="round" stroke-width="16">
    <path d="M590,220 A160,160 0 0 1 910,220" stroke="#ffb3b3"/><path d="M606,220 A144,144 0 0 1 894,220" stroke="#ffd59e"/>
    <path d="M622,220 A128,128 0 0 1 878,220" stroke="#fff1a8"/><path d="M638,220 A112,112 0 0 1 862,220" stroke="#c6efc9"/>
    <path d="M654,220 A96,96 0 0 1 846,220" stroke="#b9dcff"/><path d="M670,220 A80,80 0 0 1 830,220" stroke="#dcc8ff"/>
  </g>
  <g transform="translate(92,62)"><circle r="34" fill="#ffd45c"/>
    <g stroke="#ffd45c" stroke-width="7" stroke-linecap="round">
      <line x1="0" y1="-50" x2="0" y2="-62"/><line x1="0" y1="50" x2="0" y2="62"/><line x1="-50" y1="0" x2="-62" y2="0"/><line x1="50" y1="0" x2="62" y2="0"/>
      <line x1="35" y1="35" x2="44" y2="44"/><line x1="-35" y1="35" x2="-44" y2="44"/><line x1="35" y1="-35" x2="44" y2="-44"/><line x1="-35" y1="-35" x2="-44" y2="-44"/></g>
    <circle cx="-11" cy="-6" r="4" fill="#6b4b1f"/><circle cx="11" cy="-6" r="4" fill="#6b4b1f"/>
    <path d="M-13,9 Q0,21 13,9" stroke="#6b4b1f" stroke-width="4" fill="none" stroke-linecap="round"/>
    <circle cx="-20" cy="7" r="5" fill="#ffab7a" opacity="0.6"/><circle cx="20" cy="7" r="5" fill="#ffab7a" opacity="0.6"/></g>
  <g fill="#ffffff"><g transform="translate(250,58)"><ellipse cx="0" cy="10" rx="58" ry="20"/><circle cx="-24" cy="0" r="22"/><circle cx="8" cy="-10" r="28"/><circle cx="34" cy="4" r="18"/></g>
    <g transform="translate(470,40) scale(0.7)"><ellipse cx="0" cy="10" rx="58" ry="20"/><circle cx="-24" cy="0" r="22"/><circle cx="8" cy="-10" r="28"/><circle cx="34" cy="4" r="18"/></g>
    <g transform="translate(800,70) scale(0.8)"><ellipse cx="0" cy="10" rx="58" ry="20"/><circle cx="-24" cy="0" r="22"/><circle cx="8" cy="-10" r="28"/><circle cx="34" cy="4" r="18"/></g></g>
  <g transform="translate(560,40) rotate(12)"><polygon points="0,-34 26,0 0,40 -26,0" fill="#ff8fab"/><line x1="0" y1="-34" x2="0" y2="40" stroke="#fff" stroke-width="3"/><line x1="-26" y1="0" x2="26" y2="0" stroke="#fff" stroke-width="3"/>
    <path d="M0,40 q-14,22 6,38 q18,16 -2,34" stroke="#7a6a9a" stroke-width="2.5" fill="none"/>
    <path d="M-4,66 l-10,-4 l4,10 z M2,96 l-10,-2 l6,9 z" fill="#ffd45c"/></g>
  <g font-family="Baloo 2, Trebuchet MS, sans-serif" font-weight="800" font-size="34" text-anchor="middle">
    <g transform="translate(150,172) rotate(-6)"><rect x="-27" y="-27" width="54" height="54" rx="9" fill="#ff9aa2"/><text y="12" fill="#fff">A</text></g>
    <g transform="translate(206,178) rotate(5)"><rect x="-27" y="-27" width="54" height="54" rx="9" fill="#7cc6f5"/><text y="12" fill="#fff">B</text></g>
    <g transform="translate(178,124) rotate(-2)"><rect x="-27" y="-27" width="54" height="54" rx="9" fill="#8fd6a8"/><text y="12" fill="#fff">C</text></g>
  </g>
  <g transform="translate(380,182)"><rect x="-70" y="-9" width="140" height="18" rx="9" fill="#b9a3ff"/><polygon points="70,-9 92,0 70,9" fill="#f3d9b1"/><polygon points="84,-3 92,0 84,3" fill="#5b4a8a"/><rect x="-70" y="-9" width="22" height="18" rx="9" fill="#9a84e8"/></g>
  <g fill="#ffd45c"><path d="M330,120 l5,11 12,2 -9,8 2,12 -10,-6 -10,6 2,-12 -9,-8 12,-2 z"/><path d="M700,30 l3,7 8,1 -6,5 2,8 -7,-4 -7,4 2,-8 -6,-5 8,-1 z"/></g>
  <path d="M0,206 Q150,192 300,206 T600,206 T900,206 L900,220 L0,220 Z" fill="#a8dcb1"/>
</svg>"""

_KIDS_CSS = """
  .hub-card { background: var(--card); display: flex; flex-direction: column; }
  .hub-card[hidden], .hub-day[hidden], .kid-city-section[hidden] { display: none; }
  .hub-card-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
  .hub-title { margin: 0; line-height: 1.3; }
  .hub-title a { text-decoration: none; }
  .hub-meta { display: flex; gap: 6px; color: var(--muted); }
  .hub-desc { margin: 6px 0 0; }
  .kids-hub .cta-btn { display: inline-block; border-radius: 999px; text-decoration: none; }
  .kids-hub .badge { padding: 1px 8px; border-radius: 999px; white-space: nowrap; }
  body.kids-hub {
    --bg: #fbf6ec; --card: #ffffff; --card-hover: #ffffff; --fg: #3a3550; --muted: #7c7590;
    --accent: #2f86c8; --border: #efe4d2; --green: #2f9e5b; --sky: #d6eefc; --sky-deep: #8fcdf0;
    background: #fbf6ec radial-gradient(#efe2cc 1.2px, transparent 1.4px) 0 0 / 22px 22px;
    font-family: "Nunito", "Avenir Next Rounded", "Avenir Next", "Trebuchet MS", system-ui, sans-serif;
  }
  .kids-hub h1, .kids-hub h2, .kids-hub h3, .kids-hub .logo, .kids-hub .kid-chip, .kids-hub .cta-btn {
    font-family: "Baloo 2", "Avenir Next Rounded", "Trebuchet MS", system-ui, sans-serif;
  }
  .kids-hub header { background: #ffffffd9; backdrop-filter: blur(8px); border-bottom: 2px dashed #e7d8bf;
    position: sticky; top: env(safe-area-inset-top, 0px); z-index: 5; flex-wrap: wrap; gap: 8px; }
  .kids-hub .logo { color: var(--fg); font-size: 18px; }
  .kids-hub .logo span { color: #f27e9a; }
  .kids-hub .hub-nav a { color: var(--muted); }
  .kids-hub .hub-nav a.active, .kids-hub .hub-nav a:hover { color: var(--accent); }
  .kids-hub main { max-width: 980px; padding-top: 22px; }
  .kids-hub .hero { border: 0; padding: 0; margin-bottom: 18px; background: #fff; border-radius: 28px;
    overflow: hidden; box-shadow: 0 6px 0 #e9dcc6, 0 14px 30px rgba(120, 100, 60, 0.10); }
  .kids-hero-art { display: block; width: 100%; height: 190px; }
  .kids-hero-copy { padding: 18px 22px 24px; }
  .kids-hub .hero h1 { font-size: clamp(30px, 6vw, 44px); line-height: 1.05; margin: 0 0 8px; color: #2b5d86; letter-spacing: -0.01em; }
  .kids-hub .hero h1 .wave { display: inline-block; transform-origin: 70% 70%; animation: kid-wave 2.4s ease-in-out infinite; }
  @keyframes kid-wave { 0%, 60%, 100% { transform: rotate(0); } 10%, 30% { transform: rotate(14deg); } 20%, 40% { transform: rotate(-8deg); } }
  @media (prefers-reduced-motion: reduce) { .kids-hub .hero h1 .wave { animation: none; } }
  .kids-hub .hero h1 small { display: block; font-size: 0.45em; color: #b08a5a; font-weight: 700; letter-spacing: 0.01em; margin-top: 4px; }
  .kids-hub .hero p { color: var(--muted); font-size: 16px; margin-bottom: 16px; }
  .kids-hub .cta-btn { background: #2f86c8; color: #fff; box-shadow: 0 4px 0 #1f6aa3; font-weight: 700; font-size: 16px; padding: 9px 22px; }
  .kids-hub .cta-btn:hover { transform: translateY(-1px); filter: brightness(1.05); }
  .kids-stats { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; margin: 0 0 16px; }
  .kids-stat { background: var(--sky); color: #24648f; border-radius: 999px; padding: 4px 14px; font-weight: 800; font-size: 14px; }
  .kids-filters { background: #fff; border-radius: 22px; padding: 14px 16px 6px; margin-bottom: 18px;
    box-shadow: 0 4px 0 #e9dcc6; border: 2px solid #f1e6d4; }
  .kid-filter-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
  .kid-filter-label { font-weight: 800; color: #b08a5a; font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em; min-width: 58px; }
  .kid-chip { font-size: 15px; font-weight: 700; padding: 4px 14px 3px; border-radius: 999px; cursor: pointer;
    border: 2px solid #e6dccb; background: #fffaf2; color: var(--fg); transition: transform 0.12s ease, background 0.12s ease; }
  .kid-chip:hover { transform: translateY(-1px); border-color: var(--sky-deep); }
  .kid-chip.active { background: var(--sky); border-color: #6dbbea; color: #1f5d88; box-shadow: 0 3px 0 #9fd3f2; }
  .kids-hub .hub-day { border: 0; margin: 26px 0 2px; padding: 0; font-size: 22px; color: #2b5d86; display: flex; align-items: center; gap: 10px; }
  .kids-hub .hub-day::before { content: ""; width: 34px; height: 22px; flex: none;
    background: radial-gradient(circle at 30% 60%, #fff 9px, transparent 10px), radial-gradient(circle at 62% 45%, #fff 11px, transparent 12px), radial-gradient(circle at 82% 66%, #fff 8px, transparent 9px), var(--sky);
    border-radius: 12px; }
  .kids-hub .hub-day::after { content: ""; flex: 1; border-bottom: 3px dotted #e2d3ba; }
  .kids-hub .hub-grid { gap: 14px; grid-template-columns: minmax(0, 1fr); }
  @media (min-width: 640px) { .kids-hub .hub-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  .kids-hub .hub-card a, .kids-hub .hub-desc { overflow-wrap: anywhere; }
  .kids-hub .hub-card { border: 2px solid #f1e6d4; border-radius: 22px; padding: 0; overflow: hidden; justify-content: flex-start; min-width: 0;
    box-shadow: 0 4px 0 #ece0cb; transition: transform 0.15s ease, box-shadow 0.15s ease; }
  .kids-hub .hub-card:hover { transform: translateY(-2px) rotate(-0.3deg); box-shadow: 0 7px 0 #e3d4ba; border-color: #e6d6bb; }
  .kid-card-band { height: 10px; background: var(--band, #d6eefc); }
  .kid-card-body { padding: 12px 16px 14px; display: flex; gap: 12px; }
  .kid-emoji { flex: none; width: 46px; height: 46px; border-radius: 16px; display: grid; place-items: center;
    font-size: 24px; background: var(--band, #d6eefc); }
  .kid-card-main { min-width: 0; flex: 1; }
  .kids-hub .hub-card-head { margin-bottom: 4px; }
  .kids-hub .hub-date { color: #2f86c8; font-size: 13px; font-weight: 800; letter-spacing: 0.02em; text-transform: none; }
  .kids-hub .hub-title { font-family: "Nunito", system-ui, sans-serif; font-weight: 800; font-size: 16.5px; margin-bottom: 6px; }
  .kids-hub .hub-title a { color: #3a3550; }
  .kids-hub .hub-title a:hover { color: #2f86c8; }
  .kids-hub .hub-meta { flex-wrap: wrap; font-size: 13px; }
  .kids-hub .hub-desc { color: #6f6884; font-size: 13.5px; }
  .kid-ages { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
  .kid-age { font-size: 12px; font-weight: 800; padding: 1px 9px; border-radius: 999px; background: #fff4dc; color: #9a6b24; border: 1px solid #f3dfb3; }
  .kids-hub .badge-free { background: #dff5e6; color: #23824a; font-size: 12px; font-weight: 800; }
  .kids-hub .badge-price { background: #f4efe6; color: #6f6884; font-size: 12px; }
  .kid-city-section {
    grid-column: 1 / -1;
    margin-bottom: 22px;
    background: #ffffff;
    border: 1px solid #efe4d2;
    border-left: 4px solid var(--city-color, #2f86c8);
    border-radius: 18px;
    padding: 16px;
    box-shadow: 0 4px 0 #ede1cd;
  }
  .kid-city-section[data-city="manhattan"] { --city-color: #2f86c8; }
  .kid-city-section[data-city="brooklyn"] { --city-color: #f43f5e; }
  .kid-city-section[data-city="queens"] { --city-color: #f59e0b; }
  .kid-city-section[data-city="bronx"] { --city-color: #2f9e5b; }
  .kid-city-section[data-city="staten_island"] { --city-color: #8b5cf6; }
  .kid-city-section[data-city="citywide"] { --city-color: #7c7590; }
  .kid-city-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-bottom: 10px;
    margin-bottom: 14px;
    border-bottom: 2px dashed #f2e7d5;
  }
  .kid-city-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: var(--city-color);
    font-size: 13.5px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .kid-city-pill .city-dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--city-color);
    box-shadow: 0 0 6px var(--city-color);
    display: inline-block;
  }
  .kid-city-head .count {
    background: #fbf6ec;
    color: #7c7590;
    font-size: 12px;
    font-weight: 800;
    padding: 2px 9px;
    border-radius: 999px;
    border: 1px solid #efe4d2;
  }
  .kid-city-cards {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 14px;
  }
  @media (min-width: 640px) {
    .kid-city-cards {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
  .kid-k-story { --band: #fff1b8; } .kid-k-music { --band: #e7dcff; } .kid-k-nature { --band: #d4f3e1; }
  .kid-k-make { --band: #ffe0cf; } .kid-k-show { --band: #ffd6e6; } .kid-k-play { --band: #d6eefc; } .kid-k-other { --band: #f1e6d4; }
  .kids-hub .no-hub-events { text-align: center; color: var(--muted); font-size: 16px; padding: 30px 0; }
  .kids-hub footer { border-top: 2px dashed #e7d8bf; }
  @media (max-width: 640px) {
    .kids-hero-art { height: 130px; }
    .kid-filter-label { min-width: 100%; }
    .kids-hub .hub-nav { font-size: 12px; gap: 8px 10px; }
  }
"""

_KIDS_FILTER_JS = """<script>
(function () {
  var chips = document.querySelectorAll('.kid-chip');
  if (!chips.length) return;
  var cards = document.querySelectorAll('.hub-card');
  var heads = document.querySelectorAll('.hub-day');
  var citySecs = document.querySelectorAll('.kid-city-section');
  var state = { city: 'all', age: 'all', kind: 'all', price: 'all' };
  function matches(c) {
    if (state.city !== 'all' && c.dataset.city !== state.city) return false;
    if (state.age !== 'all' && (' ' + c.dataset.age + ' ').indexOf(' ' + state.age + ' ') === -1) return false;
    if (state.kind !== 'all' && c.dataset.kind !== state.kind) return false;
    if (state.price !== 'all' && c.dataset.price !== state.price) return false;
    return true;
  }
  function render(save) {
    var days = {}, n = 0;
    cards.forEach(function (c) { var on = matches(c); c.hidden = !on; if (on) { days[c.dataset.day] = 1; n++; } });
    heads.forEach(function (h) { h.hidden = !days[h.dataset.day]; });
    citySecs.forEach(function (sec) {
      var visible = sec.querySelectorAll('.hub-card:not([hidden])').length;
      sec.hidden = (visible === 0);
      var cCount = sec.querySelector('.kid-city-head .count');
      if (cCount) cCount.textContent = visible;
    });
    chips.forEach(function (b) { b.classList.toggle('active', state[b.dataset.group] === b.dataset.val); });
    var none = document.getElementById('hub-none');
    if (none) none.hidden = n > 0;
    if (save) {
      var parts = Object.keys(state).filter(function (k) { return state[k] !== 'all'; }).map(function (k) { return k + '=' + state[k]; });
      history.replaceState(null, '', parts.length ? '#' + parts.join('&') : location.pathname);
    }
  }
  chips.forEach(function (b) {
    b.addEventListener('click', function () { state[b.dataset.group] = b.dataset.val; render(true); });
  });
  location.hash.replace(/^#/, '').split('&').forEach(function (p) {
    var kv = p.split('=');
    if (kv.length === 2 && state.hasOwnProperty(kv[0]) && document.querySelector('.kid-chip[data-group="' + kv[0] + '"][data-val="' + kv[1] + '"]')) state[kv[0]] = kv[1];
  });
  render(false);
})();
</script>"""


_CITY_ORDER = ("manhattan", "brooklyn", "queens", "bronx", "staten_island", "citywide")
_CITY_CHIPS = (("all", "All boroughs"), ("manhattan", "Manhattan"), ("brooklyn", "Brooklyn"), ("queens", "Queens"),
               ("bronx", "The Bronx"), ("staten_island", "Staten Island"), ("citywide", "Citywide"))
CARD_LIMIT = 600  # about three weeks


def _chip(group, val, label):
    return f'<button type="button" class="kid-chip" data-group="{group}" data-val="{val}">{label}</button>'


def render_body(events, city_of, is_free, query, title, subtitle, city_labels):
    """(hero html, filters html, sections html) for date-sorted events. city_of(e) gives a borough."""
    age_counts, kind_counts, free, places = {}, {}, 0, set()
    by_day = {}

    def card(e, city):
        nonlocal free
        ages, kind, emoji, age_label = _kid_tags(e)
        for a in ages:
            age_counts[a] = age_counts.get(a, 0) + 1
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        paid = not is_free(e)
        free += 0 if paid else 1
        places.add(e.get("venue") or "")
        t = e["_time"]
        when = "Time TBA" if e.get("_time_unknown") else ("All day" if (t.hour, t.minute) == (0, 0) else t.strftime("%-I:%M %p"))
        if not paid:
            badge = '<span class="badge badge-free">Free</span>'
        elif e.get("price"):
            badge = f'<span class="badge badge-price">{escape(str(e["price"]))[:24]}</span>'
        else:
            badge = ""
        pills = [age_label] if age_label else [_KID_AGE_PILL[a] for a in ages]
        pills_html = "".join(f'<span class="kid-age">{escape(p)}</span>' for p in pills)
        desc = re.sub(r"\s+", " ", str(e.get("description") or "")).strip()
        desc_html = f'<p class="hub-desc">{escape(desc[:160] + ("…" if len(desc) > 160 else ""))}</p>' if desc else ""
        return f"""<article class="hub-card kid-k-{kind}" data-city="{escape(city)}" data-day="{t.date().isoformat()}" data-age="{' '.join(ages)}" data-kind="{kind}" data-price="{'paid' if paid else 'free'}">
  <div class="kid-card-band"></div>
  <div class="kid-card-body">
    <div class="kid-emoji" aria-hidden="true">{emoji}</div>
    <div class="kid-card-main">
      <div class="hub-card-head"><time class="hub-date">{when}</time><div class="hub-badges">{badge}</div></div>
      <h3 class="hub-title"><a href="{escape(e.get('url') or '../')}" target="_blank" rel="noopener">{escape(e.get('name') or 'Event')}</a></h3>
      <div class="hub-meta"><span class="hub-venue">📍 {escape(e.get('venue') or e.get('_source_venue') or '')}</span></div>
      {desc_html}
      <div class="kid-ages">{pills_html}</div>
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
            sections.append(f"""<div class="kid-city-section" data-city="{city}" data-day="{iso}">
  <div class="kid-city-head">
    <span class="kid-city-pill"><span class="city-dot"></span>{escape(city_labels.get(city, city.title()))}</span>
    <span class="count">{len(city_events)}</span>
  </div>
  <div class="kid-city-cards">{cards}</div>
</div>""")

    where = "".join(_chip("city", k, lbl) for k, lbl in _CITY_CHIPS if k == "all" or k in present)
    ages = _chip("age", "all", "Any age") + "".join(
        _chip("age", k, lbl) for k, lbl, _r in _KID_AGE_BUCKETS if age_counts.get(k)) + (
        _chip("age", "family", "🏡 All Ages / Family") if age_counts.get("family") else "")
    kinds = _chip("kind", "all", "Everything") + "".join(
        _chip("kind", k, f"{emo} {lbl}") for k, lbl, emo, _rx in _KID_KIND_RES if kind_counts.get(k))
    prices = _chip("price", "all", "Any price") + _chip("price", "free", "💛 Free only")
    filters = f"""<div class="kids-filters" role="group" aria-label="Filter kids events">
    <div class="kid-filter-row"><span class="kid-filter-label">Where</span>{where}</div>
    <div class="kid-filter-row"><span class="kid-filter-label">Ages</span>{ages}</div>
    <div class="kid-filter-row"><span class="kid-filter-label">What</span>{kinds}</div>
    <div class="kid-filter-row"><span class="kid-filter-label">Cost</span>{prices}</div>
  </div>"""
    n_cards = sum(kind_counts.values())
    hero = f"""<div class="hero">
    {_KIDS_HERO_ART}
    <div class="kids-hero-copy">
      <h1>{escape(title)} <span class="wave" aria-hidden="true">👋</span><small>across all five boroughs</small></h1>
      <p>{escape(subtitle)}</p>
      <div class="kids-stats"><span class="kids-stat">🗓️ {n_cards} activities in the next {len(by_day)} days</span><span class="kids-stat">💛 {free} free</span><span class="kids-stat">📍 {len(places)} places</span></div>
      <a href="../{query}" class="cta-btn">See them on the full calendar →</a>
    </div>
  </div>"""
    body = "\n".join(sections) or '<p class="no-hub-events">No kids events are listed right now.</p>'
    none = '<p id="hub-none" class="no-hub-events" hidden>Nothing matches those filters. Try another age or activity.</p>'
    return hero, filters, f"{body}\n{none}"
