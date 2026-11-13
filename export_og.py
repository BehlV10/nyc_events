"""NYC Events — OpenGraph (social preview) images, 1200x630 JPEG, rendered with Pillow.

og-image.jpg      main card: brand, live listing count, and the next few upcoming events
og-<hub>.jpg      one card per landing page in seo.HUBS (badge, title, subtitle, listing count)

Rendered during `python server.py export html` and deployed with the Pages artifact rather
than committed, so refreshed cards don't accumulate in git history. If Pillow isn't
installed the export skips these quietly and pages fall back to whatever image exists.
"""

import os

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:  # pragma: no cover - optional dependency
    HAS_PIL = False

W, H = 1200, 630
BG = "#0b0f17"
ACCENT = "#5d9bff"
GOLD = "#ffcc00"
MUTED = "#94a3b8"
CAT_COLORS = {
    "music": "#7aa2f7", "clubbing": "#f7768e", "dance": "#ff7ab2", "comedy": "#bb9af7",
    "theater": "#e0af68", "film": "#7dcfff", "art": "#ffd866", "books": "#9ece6a", "food": "#ff9e64",
    "outdoors": "#73daca", "sports": "#2ac3de", "gaming": "#b4f9f8", "community": "#c0caf5",
}

_FONT_CANDIDATES = {
    True: [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ],
    False: [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ],
}


def _font(size, bold=False):
    for p in _FONT_CANDIDATES[bold]:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap(draw, text, font, max_w, max_lines):
    words, lines, cur = (text or "").split(), [], ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if draw.textlength(cand, font=font) <= max_w:
            cur = cand
            continue
        if cur:
            lines.append(cur)
        cur = w
        if len(lines) == max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and " ".join(lines) != " ".join(words):
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_w:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines


def _frame(draw):
    draw.ellipse([(880, -160), (1360, 320)], fill="#111b2e")
    draw.ellipse([(-160, 420), (260, 840)], fill="#10182a")
    # skyline silhouette along the bottom
    x, heights = 0, [70, 120, 90, 160, 110, 200, 130, 85, 150, 105, 175, 95, 140, 115, 80, 165, 100, 125]
    for i, h in enumerate(heights):
        w = 54 + (i * 17) % 30
        draw.rectangle([(x, H - h), (x + w, H)], fill="#0f1626")
        x += w + 6
        if x > W:
            break
    for i, col in enumerate(["#5d9bff", "#ffcc00", "#f7768e", "#73daca"]):
        draw.rectangle([(i * W // 4, 0), ((i + 1) * W // 4, 7)], fill=col)


def _footer(draw, site_label):
    f = _font(20, bold=True)
    x = 70
    for text, col in (("NYC EVENTS", "#f8fafc"), ("  ·  ", "#475569"), (site_label, ACCENT)):
        draw.text((x, 568), text, fill=col, font=f)
        x += draw.textlength(text, font=f)


def _pill(draw, xy, text, fg, bg, outline, font):
    x, y = xy
    tw = draw.textlength(text, font=font)
    draw.rounded_rectangle([(x, y), (x + tw + 28, y + 38)], radius=10, fill=bg, outline=outline, width=1)
    draw.text((x + 14, y + 7), text, fill=fg, font=font)
    return x + tw + 28


def render_main_card(path, count_label, picks, site_label):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    _frame(d)
    f_pill = _font(19, bold=True)
    x = _pill(d, (70, 56), "● LIVE · UPDATED EVERY 30 MIN", "#34d399", "#06261f", "#10b981", f_pill)
    _pill(d, (x + 14, 56), f"{count_label} EVENTS", GOLD, "#1c1708", "#806600", f_pill)
    d.text((70, 120), "NYC Events", fill="#ffffff", font=_font(78, bold=True))
    sub = "Concerts, DJ nights, comedy, theater, run clubs, hikes & free things to do — all five boroughs."
    y = 216
    for line in _wrap(d, sub, _font(27), 1060, 2):
        d.text((70, y), line, fill=MUTED, font=_font(27))
        y += 38
    # real upcoming picks
    y = 318
    f_t, f_m = _font(25, bold=True), _font(19)
    for e in picks[:4]:
        col = CAT_COLORS.get(e.get("category"), ACCENT)
        d.rounded_rectangle([(70, y), (1130, y + 50)], radius=10, fill="#121a2b", outline="#1e293b", width=1)
        d.rounded_rectangle([(70, y), (77, y + 50)], radius=3, fill=col)
        t = e["_time"]
        when = f"{t.strftime('%a')} {t.strftime('%-I:%M%p').lower()}"
        d.text((94, y + 12), when, fill=col, font=f_m)
        title = _wrap(d, e.get("name") or "", f_t, 560, 1)
        d.text((250, y + 10), title[0] if title else "", fill="#f8fafc", font=f_t)
        venue = _wrap(d, e.get("venue") or "", f_m, 270, 1)
        if venue:
            d.text((1110 - d.textlength(venue[0], font=f_m), y + 13), venue[0], fill="#64748b", font=f_m)
        y += 58
    _footer(d, site_label)
    img.save(path, "JPEG", quality=88, optimize=True)


def render_hub_card(path, badge, title, subtitle, count_label, site_label):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    _frame(d)
    f_pill = _font(20, bold=True)
    x = _pill(d, (70, 70), f"● {badge}", "#34d399", "#06261f", "#10b981", f_pill)
    if count_label:
        _pill(d, (x + 14, 70), f"{count_label} LISTINGS", MUTED, "#1e293b", "#334155", f_pill)
    y = 150
    f_title = _font(64, bold=True)
    for line in _wrap(d, title, f_title, 1060, 2):
        d.text((70, y), line, fill="#ffffff", font=f_title)
        y += 80
    y += 18
    f_sub = _font(28)
    for line in _wrap(d, subtitle, f_sub, 1060, 3):
        d.text((70, y), line, fill=MUTED, font=f_sub)
        y += 40
    _footer(d, site_label)
    img.save(path, "JPEG", quality=88, optimize=True)


def write_og_images(base_dir, dated, total_events, site_url):
    """Render og-image.jpg and one og-<hub>.jpg per landing page. Returns paths written."""
    if not HAS_PIL:
        print("Pillow not installed; skipping OpenGraph images")
        return []
    from export_feeds import feed_events
    from seo import HUBS, _rounded_count, hub_events

    site_label = site_url.split("://", 1)[-1].rstrip("/")
    out = []
    main = os.path.join(base_dir, "og-image.jpg")
    picks, seen = [], set()
    for e in feed_events(dated, days=2):
        key = (e.get("name") or "").strip().lower()
        if key not in seen:
            seen.add(key)
            picks.append(e)
    render_main_card(main, _rounded_count(total_events), picks, site_label)
    out.append(main)
    for slug, hub in HUBS.items():
        n = len(hub_events(hub, dated))
        path = os.path.join(base_dir, f"og-{slug}.jpg")
        render_hub_card(path, hub["badge"], hub["title"], hub["subtitle"], _rounded_count(n) if n else "", site_label)
        out.append(path)
    return out
