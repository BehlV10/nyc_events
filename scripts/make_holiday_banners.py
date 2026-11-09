#!/usr/bin/env python3
"""Draw NYC holiday banners in static/holidays/<key>.svg.

Each holiday gets its own vector illustration built around an iconic New York City landmark:
- Veterans Day: Intrepid Sea, Air & Space Museum on the Hudson River with naval searchlights and US flags
- Thanksgiving: Macy's Thanksgiving Day Parade! Giant helium balloon over Central Park West brownstones
- Black Friday: 5th Avenue & Herald Square luxury shopping, glowing art deco storefronts and golden confetti
- Cyber Monday: Silicon Alley / Times Square cyberpunk neon grid tracing the Flatiron Building
- Hanukkah: World's Largest Menorah at Grand Army Plaza (Central Park South) with glowing candles in the winter night
- Christmas: Rockefeller Center Christmas Tree, 30 Rock, Prometheus and skaters on the ice rink
- New Year's Eve: Times Square Ball Drop! Glowing crystal ball, neon year sign, confetti blizzard and fireworks
- New Year's Day: Sunrise over the Brooklyn Bridge and New York Harbor with golden dawn rays

Additional holidays (MLK Day, Lunar New Year, Valentine's Day, St. Patrick's Day, etc.) are also supported.

Usage:
    python3 scripts/make_holiday_banners.py            # draw all
    python3 scripts/make_holiday_banners.py thanksgiving # draw one
"""

import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

W, H, HZ = 1600, 600, 400  # canvas dimensions and standard horizon line


# --------------------------------------------------------------------------------------------
# Drawing Primitives & Scene Engine
# --------------------------------------------------------------------------------------------

class Scene:
    def __init__(self, key):
        self.key = key
        self.rng = random.Random(key)
        self.defs = []
        self.body = []
        self._ids = 0

    def uid(self, p="g"):
        self._ids += 1
        return f"{p}{self._ids}"

    def add(self, *els):
        self.body.extend(e for e in els if e)

    def svg(self):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
                f'preserveAspectRatio="xMidYMid slice">\n<defs>\n' + "\n".join(self.defs) + "\n</defs>\n"
                + "\n".join(self.body) + "\n</svg>\n")

    # Gradients & Filters
    def vgrad(self, stops, x2=0, y2=1):
        gid = self.uid("lg")
        s = "".join(f'<stop offset="{o}" stop-color="{c}"' + (f' stop-opacity="{a}"' if a is not None else "") + "/>"
                    for o, c, a in [(t + (None,))[:3] for t in stops])
        self.defs.append(f'<linearGradient id="{gid}" x1="0" y1="0" x2="{x2}" y2="{y2}">{s}</linearGradient>')
        return f"url(#{gid})"

    def rgrad(self, stops):
        gid = self.uid("rg")
        s = "".join(f'<stop offset="{o}" stop-color="{c}"' + (f' stop-opacity="{a}"' if a is not None else "") + "/>"
                    for o, c, a in [(t + (None,))[:3] for t in stops])
        self.defs.append(f'<radialGradient id="{gid}">{s}</radialGradient>')
        return f"url(#{gid})"

    # Sky, Lights, Atmosphere
    def sky(self, top, mid, low, bottom=HZ):
        gid = self.uid("sky")
        self.defs.append(f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="{bottom}">'
                         f'<stop offset="0" stop-color="{top}"/><stop offset="0.55" stop-color="{mid}"/>'
                         f'<stop offset="1" stop-color="{low}"/></linearGradient>')
        self.add(f'<rect width="{W}" height="{H}" fill="url(#{gid})"/>')

    def stars(self, n=90, ymax=300, opacity=1.0):
        r = self.rng
        self.add(*[f'<circle cx="{r.random() * W:.0f}" cy="{r.random() * ymax:.0f}" r="{0.6 + r.random() * 1.6:.1f}" '
                   f'fill="#fff" opacity="{(0.25 + r.random() * 0.65) * opacity:.2f}"/>' for _ in range(n)])

    def glow(self, cx, cy, r, color, a=0.5):
        self.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{self.rgrad([(0, color, a), (1, color, 0)])}"/>')

    def sun(self, cx, cy, r, color, glow_col=None):
        self.glow(cx, cy, r * 3.5, glow_col or color, 0.45)
        self.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}"/>')

    def moon(self, cx, cy, r, color="#fdf6d8", phase=0.55):
        mid = self.uid("m")
        self.defs.append(f'<mask id="{mid}"><rect width="{W}" height="{H}" fill="#fff"/>'
                         f'<circle cx="{cx + r * phase}" cy="{cy - r * 0.25}" r="{r}" fill="#000"/></mask>')
        self.glow(cx, cy, r * 2.6, color, 0.25)
        self.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" mask="url(#{mid})"/>')

    def clouds(self, items, color="#fff", opacity=0.8):
        for cx, cy, s in items:
            self.add(f'<g transform="translate({cx},{cy}) scale({s})" fill="{color}" opacity="{opacity}">'
                     f'<ellipse cx="0" cy="0" rx="60" ry="18"/><ellipse cx="-28" cy="-10" rx="26" ry="18"/>'
                     f'<ellipse cx="12" cy="-18" rx="32" ry="24"/><ellipse cx="44" cy="-6" rx="22" ry="14"/></g>')

    def rays(self, cx, cy, colors, n=22, opacity=0.12, spread=math.pi):
        for i in range(n):
            a0 = math.pi + spread * i / n + (math.pi - spread) / 2
            a1 = a0 + spread / n * 0.5
            self.add(f'<polygon points="{cx},{cy} {cx + math.cos(a0) * 1800:.0f},{cy + math.sin(a0) * 1800:.0f} '
                     f'{cx + math.cos(a1) * 1800:.0f},{cy + math.sin(a1) * 1800:.0f}" fill="{colors[i % len(colors)]}" opacity="{opacity}"/>')

    # Ground & Water
    def ground(self, y, color, top_color=None):
        fill = self.vgrad([(0, top_color or color), (1, color)]) if top_color else color
        self.add(f'<rect x="0" y="{y}" width="{W}" height="{H - y}" fill="{fill}"/>')

    def water(self, y, top, bottom, glint="#ffffff", n=60, glint_opacity=0.35):
        self.add(f'<rect x="0" y="{y}" width="{W}" height="{H - y}" fill="{self.vgrad([(0, top), (1, bottom)])}"/>')
        r = self.rng
        for _ in range(n):
            gy = y + 6 + (r.random() ** 1.4) * (H - y - 10)
            w = 20 + r.random() * 140 * (0.4 + (gy - y) / (H - y))
            self.add(f'<rect x="{r.random() * W:.0f}" y="{gy:.0f}" width="{w:.0f}" height="2" rx="1" fill="{glint}" '
                     f'opacity="{0.08 + r.random() * glint_opacity:.2f}"/>')

    # NYC Skyline Silhouettes
    def nyc_skyline(self, color, y=HZ, x0=0, x1=W, hmin=60, hmax=220, window=None, opacity=1.0):
        """Rich Manhattan skyline with Empire State Building, Chrysler Building, and One World Trade."""
        r = self.rng
        out = [f'<g opacity="{opacity}">']
        x = x0
        while x < x1:
            w = 35 + r.random() * 60
            h = hmin + r.random() * (hmax - hmin)
            out.append(f'<rect x="{x:.0f}" y="{y - h:.0f}" width="{w + 1:.0f}" height="{h:.0f}" fill="{color}"/>')
            if window and h > 80:
                for _ in range(int(w * h / 1200)):
                    out.append(f'<rect x="{x + 4 + r.random() * (w - 10):.0f}" y="{y - h + 6 + r.random() * (h - 14):.0f}" '
                               f'width="2.5" height="4" fill="{window}" opacity="{0.35 + r.random() * 0.55:.2f}"/>')
            x += w

        # Empire State Building Silhouette
        esx = x0 + (x1 - x0) * 0.38
        esh = hmax + 110
        out.append(f'<rect x="{esx - 24}" y="{y - esh}" width="48" height="{esh}" fill="{color}"/>'
                   f'<rect x="{esx - 18}" y="{y - esh - 35}" width="36" height="35" fill="{color}"/>'
                   f'<rect x="{esx - 12}" y="{y - esh - 65}" width="24" height="30" fill="{color}"/>'
                   f'<rect x="{esx - 6}" y="{y - esh - 85}" width="12" height="20" fill="{color}"/>'
                   f'<line x1="{esx}" y1="{y - esh - 85}" x2="{esx}" y2="{y - esh - 135}" stroke="{color}" stroke-width="3"/>')

        # Chrysler Building Spire
        chx = x0 + (x1 - x0) * 0.65
        chh = hmax + 95
        out.append(f'<rect x="{chx - 20}" y="{y - chh}" width="40" height="{chh}" fill="{color}"/>'
                   f'<polygon points="{chx - 18},{y - chh} {chx},{y - chh - 50} {chx + 18},{y - chh}" fill="{color}"/>'
                   f'<line x1="{chx}" y1="{y - chh - 50}" x2="{chx}" y2="{y - chh - 110}" stroke="{color}" stroke-width="2.5"/>')

        # One World Trade Center
        wtcx = x0 + (x1 - x0) * 0.16
        wtch = hmax + 140
        out.append(f'<polygon points="{wtcx - 22},{y} {wtcx - 14},{y - wtch} {wtcx + 14},{y - wtch} {wtcx + 22},{y}" fill="{color}"/>'
                   f'<line x1="{wtcx}" y1="{y - wtch}" x2="{wtcx}" y2="{y - wtch - 60}" stroke="{color}" stroke-width="3"/>')

        out.append("</g>")
        self.add("".join(out))

    def windows_grid(self, x, y, w, h, cols, rows, color, lit=None, ww=None, wh=None, arch=False):
        r = self.rng
        ww = ww or w / cols * 0.5
        wh = wh or h / rows * 0.55
        out = []
        for c in range(cols):
            for rr in range(rows):
                cx = x + (c + 0.5) * w / cols - ww / 2
                cy = y + (rr + 0.5) * h / rows - wh / 2
                fill = color if (lit is None or r.random() < lit) else "#1a1a24"
                if arch:
                    out.append(f'<path d="M{cx:.1f},{cy + wh:.1f} L{cx:.1f},{cy + ww / 2:.1f} A{ww / 2:.1f},{ww / 2:.1f} 0 0 1 {cx + ww:.1f},{cy + ww / 2:.1f} L{cx + ww:.1f},{cy + wh:.1f} Z" fill="{fill}"/>')
                else:
                    out.append(f'<rect x="{cx:.1f}" y="{cy:.1f}" width="{ww:.1f}" height="{wh:.1f}" fill="{fill}"/>')
        self.add("".join(out))

    def brownstones(self, x0, x1, base, colors, h=(120, 190), window="#ffd98a", lit=0.7, trim="#f3ead8"):
        """Classic NYC Brownstone facades with stoops, cornice details, and warm lit windows."""
        r = self.rng
        x = x0
        while x < x1:
            w = 75 + r.random() * 45
            hh = h[0] + r.random() * (h[1] - h[0])
            c = r.choice(colors)
            self.add(f'<rect x="{x:.0f}" y="{base - hh:.0f}" width="{w + 1:.0f}" height="{hh:.0f}" fill="{c}"/>')
            # Cornice & lintels
            self.add(f'<rect x="{x - 2:.0f}" y="{base - hh - 6:.0f}" width="{w + 4:.0f}" height="8" fill="{trim}" opacity="0.85"/>')
            floors = max(2, int(hh // 42))
            self.windows_grid(x + 8, base - hh + 12, w - 16, hh - 45, 2, floors, window, lit=lit)
            # Classic NYC Brownstone Stoop
            self.add(f'<rect x="{x + w / 2 - 9:.0f}" y="{base - 32:.0f}" width="18" height="32" fill="#2a1a12"/>'
                     f'<polygon points="{x + w / 2 - 16:.0f},{base:.0f} {x + w / 2 - 8:.0f},{base - 28:.0f} {x + w / 2 + 8:.0f},{base - 28:.0f} {x + w / 2 + 16:.0f},{base:.0f}" fill="{trim}" opacity="0.6"/>')
            x += w + 3

    # Trees & Nature
    def tree(self, x, y, s, color, trunk="#3b2a1f"):
        self.add(f'<g transform="translate({x:.0f},{y:.0f}) scale({s:.2f})">'
                 f'<rect x="-4" y="-40" width="8" height="40" fill="{trunk}"/>'
                 f'<circle cx="0" cy="-62" r="30" fill="{color}"/><circle cx="-22" cy="-48" r="20" fill="{color}"/>'
                 f'<circle cx="22" cy="-48" r="20" fill="{color}"/></g>')

    def pine(self, x, y, h, color, snow=None):
        w = h * 0.45
        out = [f'<g><rect x="{x - 4:.0f}" y="{y - 10:.0f}" width="8" height="10" fill="#3b2a1f"/>']
        for i in range(3):
            ty = y - 10 - i * h * 0.26
            tw = w * (1 - i * 0.24)
            out.append(f'<polygon points="{x - tw:.0f},{ty:.0f} {x:.0f},{ty - h * 0.42:.0f} {x + tw:.0f},{ty:.0f}" fill="{color}"/>')
            if snow:
                out.append(f'<polygon points="{x - tw * 0.35:.0f},{ty - h * 0.27:.0f} {x:.0f},{ty - h * 0.42:.0f} {x + tw * 0.35:.0f},{ty - h * 0.27:.0f}" fill="{snow}"/>')
        out.append("</g>")
        self.add("".join(out))

    def bare_tree(self, x, y, h, color, depth=5, width=6):
        r = self.rng
        out = []

        def branch(x0, y0, ang, length, w, d):
            x1 = x0 + math.cos(ang) * length
            y1 = y0 + math.sin(ang) * length
            out.append(f'<line x1="{x0:.0f}" y1="{y0:.0f}" x2="{x1:.0f}" y2="{y1:.0f}" stroke="{color}" stroke-width="{w:.1f}" stroke-linecap="round"/>')
            if d > 0:
                for da in (-0.45 - r.random() * 0.2, 0.4 + r.random() * 0.25):
                    branch(x1, y1, ang + da, length * (0.68 + r.random() * 0.12), w * 0.66, d - 1)
            return x1, y1

        branch(x, y, -math.pi / 2, h * 0.38, width, depth)
        self.add("".join(out))
        return out

    # People, Crowds, Props
    def person(self, x, y, s, color, arms="down", hat=None):
        arm = {"down": "M-9,-38 L-13,-16 M9,-38 L13,-16", "up": "M-9,-40 L-18,-62 M9,-40 L18,-62",
               "wave": "M-9,-38 L-13,-16 M9,-40 L20,-60", "run": "M-9,-38 L-20,-26 M9,-40 L18,-52"}[arms]
        legs = "M-5,-18 L-14,0 M5,-18 L16,-2" if arms == "run" else "M-5,-18 L-6,0 M5,-18 L6,0"
        out = (f'<g transform="translate({x:.0f},{y:.0f}) scale({s:.2f})" fill="{color}" stroke="{color}" stroke-linecap="round">'
               f'<circle cx="0" cy="-54" r="8" stroke="none"/><path d="M-10,-44 Q0,-48 10,-44 L8,-16 L-8,-16 Z" stroke="none"/>'
               f'<path d="{arm} {legs}" stroke-width="5" fill="none"/>')
        if hat:
            out += hat
        self.add(out + "</g>")

    def flag_us(self, px, ptop, fw=170, fh=100, pole_h=None, amp=8):
        pole_h = pole_h or 260
        out = [f'<rect x="{px}" y="{ptop}" width="5" height="{pole_h}" fill="#d9d9d9"/>'
               f'<circle cx="{px + 2.5}" cy="{ptop - 4}" r="6" fill="#d4af37"/>']
        sh = fh / 13

        def wave(x):
            return amp * math.sin((x / fw) * 2.2 * math.pi)

        for i in range(13):
            y0 = ptop + 5 + i * sh
            top = " ".join(f"{px + 5 + x:.0f},{y0 + wave(x):.1f}" for x in range(0, fw + 1, 10))
            bot = " ".join(f"{px + 5 + x:.0f},{y0 + sh + wave(x):.1f}" for x in range(fw, -1, -10))
            out.append(f'<polygon points="{top} {bot}" fill="{"#b22234" if i % 2 == 0 else "#f5f5f5"}"/>')
        cw, ch = fw * 0.42, sh * 7
        top = " ".join(f"{px + 5 + x:.0f},{ptop + 5 + wave(x):.1f}" for x in range(0, int(cw) + 1, 6))
        bot = " ".join(f"{px + 5 + x:.0f},{ptop + 5 + ch + wave(x):.1f}" for x in range(int(cw), -1, -6))
        out.append(f'<polygon points="{top} {bot}" fill="#3c3b6e"/>')
        for rr in range(5):
            for c in range(6):
                x = 7 + c * (cw - 10) / 5.5
                out.append(star(px + 5 + x, ptop + 5 + 6 + rr * (ch - 10) / 4.6 + wave(x), fh * 0.025, "#fff"))
        self.add("".join(out))

    def confetti(self, n, colors, ymin=0, ymax=H, xmin=0, xmax=W, size=(4, 10)):
        r = self.rng
        out = []
        for _ in range(n):
            x, y = xmin + r.random() * (xmax - xmin), ymin + r.random() * (ymax - ymin)
            w = size[0] + r.random() * (size[1] - size[0])
            out.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{w * 1.8:.0f}" fill="{r.choice(colors)}" '
                       f'opacity="{0.55 + r.random() * 0.45:.2f}" transform="rotate({r.random() * 180:.0f} {x:.0f} {y:.0f})"/>')
        self.add("".join(out))

    def snow(self, n, ymax=H, opacity=1.0):
        r = self.rng
        self.add(*[f'<circle cx="{r.random() * W:.0f}" cy="{r.random() * ymax:.0f}" r="{0.8 + r.random() * 3:.1f}" fill="#fff" '
                   f'opacity="{(0.35 + r.random() * 0.55) * opacity:.2f}"/>' for _ in range(n)])

    def firework(self, cx, cy, rad, color, rays=20, dots=True, opacity=1.0, glow=True):
        out = [f'<g opacity="{opacity:.2f}">']
        if glow:
            out.append(f'<circle cx="{cx}" cy="{cy}" r="{rad * 1.2:.0f}" fill="{color}" opacity="0.10"/>')
        for i in range(rays):
            a = 2 * math.pi * i / rays + 0.1
            x1, y1 = cx + math.cos(a) * rad * 0.22, cy + math.sin(a) * rad * 0.22
            x2, y2 = cx + math.cos(a) * rad, cy + math.sin(a) * rad + rad * 0.06
            out.append(f'<path d="M{x1:.0f},{y1:.0f} Q{(x1 + x2) / 2:.0f},{(y1 + y2) / 2 - 4:.0f} {x2:.0f},{y2:.0f}" stroke="{color}" stroke-width="2.4" stroke-linecap="round" fill="none"/>')
            if dots:
                out.append(f'<circle cx="{x2:.0f}" cy="{y2 + 6:.0f}" r="2.4" fill="{color}"/>')
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{max(3, rad * 0.08):.0f}" fill="#fff" opacity="0.9"/></g>')
        self.add("".join(out))

    def lamp_post(self, x, base, h=120, color="#1b1b22", light="#ffd27a"):
        self.glow(x, base - h + 6, 46, light, 0.45)
        self.add(f'<rect x="{x - 3}" y="{base - h + 14}" width="6" height="{h - 14}" fill="{color}"/>'
                 f'<rect x="{x - 9}" y="{base - 8}" width="18" height="8" fill="{color}"/>'
                 f'<polygon points="{x - 11},{base - h + 14} {x + 11},{base - h + 14} {x + 7},{base - h - 6} {x - 7},{base - h - 6}" fill="{light}" stroke="{color}" stroke-width="3"/>'
                 f'<polygon points="{x - 13},{base - h - 6} {x + 13},{base - h - 6} {x},{base - h - 18}" fill="{color}"/>')


def star(cx, cy, r, color, opacity=1.0, rot=0):
    pts = []
    for i in range(10):
        rad = r if i % 2 == 0 else r * 0.42
        a = math.radians(rot - 90 + i * 36)
        pts.append(f"{cx + rad * math.cos(a):.1f},{cy + rad * math.sin(a):.1f}")
    return f'<polygon points="{" ".join(pts)}" fill="{color}" opacity="{opacity:.2f}"/>'


def leaf(cx, cy, s, color, rot=0, opacity=1.0):
    return (f'<path transform="translate({cx:.0f},{cy:.0f}) rotate({rot:.0f}) scale({s:.2f})" fill="{color}" opacity="{opacity:.2f}" '
            f'd="M0,-22 C8,-14 16,-12 14,-2 C20,2 16,10 8,8 C8,16 2,20 0,24 C-2,20 -8,16 -8,8 C-16,10 -20,2 -14,-2 C-16,-12 -8,-14 0,-22 Z"/>')


def poppy(cx, cy, s):
    return (f'<g transform="translate({cx:.0f},{cy:.0f}) scale({s:.2f})">'
            f'<path d="M0,10 Q4,45 -2,90" stroke="#1f3d1f" stroke-width="3" fill="none"/>'
            + "".join(f'<ellipse cx="0" cy="-12" rx="13" ry="15" fill="#c8102e" transform="rotate({a})"/>' for a in (0, 90, 180, 270))
            + '<ellipse cx="0" cy="-12" rx="9" ry="10" fill="#e0263f" transform="rotate(45)" opacity="0.6"/>'
            + '<circle cx="0" cy="0" r="7" fill="#111"/></g>')


# --------------------------------------------------------------------------------------------
# The 8 NYC Holiday Scenes
# --------------------------------------------------------------------------------------------

def scene_veterans(s):
    """1. Veterans Day: Intrepid Sea, Air & Space Museum on the Hudson River with naval searchlights and US flags."""
    s.sky("#070d1f", "#1b2d5c", "#c9874a")
    s.stars(90, 260, 0.9)
    s.nyc_skyline("#070b18", y=380, hmin=60, hmax=180, window="#ffd27a")

    # Searchlights sweeping sky from Intrepid
    for sx, angle, col in ((680, -0.32, "#ffd27a"), (780, 0.28, "#6ea8ff"), (900, -0.15, "#ffffff")):
        x2 = sx + math.tan(angle) * 360
        s.add(f'<polygon points="{sx - 12},350 {sx + 12},350 {x2 + 80},0 {x2 - 80},0" fill="{col}" opacity="0.12"/>')

    # The Intrepid Aircraft Carrier on Hudson Pier 86
    ship_y = 350
    s.add(
        # Carrier Hull (Pier 86)
        f'<polygon points="380,{ship_y + 40} 1180,{ship_y + 40} 1230,{ship_y} 410,{ship_y}" fill="#333b4d"/>'
        f'<rect x="360" y="{ship_y - 6}" width="880" height="8" fill="#475166"/>'
        # Flight Deck Runway line
        f'<line x1="430" y1="{ship_y - 2}" x2="1190" y2="{ship_y - 2}" stroke="#f1c40f" stroke-width="2" stroke-dasharray="16,12"/>'
        # Carrier Island Superstructure & Radar Mast
        f'<rect x="740" y="{ship_y - 75}" width="90" height="70" fill="#333b4d"/>'
        f'<rect x="755" y="{ship_y - 105}" width="60" height="30" fill="#29303e"/>'
        f'<line x1="785" y1="{ship_y - 105}" x2="785" y2="{ship_y - 150}" stroke="#94a3b8" stroke-width="3"/>'
        f'<circle cx="785" cy="{ship_y - 150}" r="4" fill="#ef4444"/>'
        f'<line x1="765" y1="{ship_y - 130}" x2="805" y2="{ship_y - 130}" stroke="#94a3b8" stroke-width="2"/>'
        # Supersonic Concorde / Jet silhouette on flight deck
        f'<polygon points="560,{ship_y - 4} 600,{ship_y - 18} 630,{ship_y - 4}" fill="#1e293b"/>'
        f'<line x1="570" y1="{ship_y - 8}" x2="635" y2="{ship_y - 8}" stroke="#1e293b" stroke-width="4"/>'
    )

    # Hudson River Pier & Water
    s.water(390, "#13213f", "#070d1f", "#c9874a", 70, 0.4)

    # Large US Flag on pier
    s.flag_us(1080, 110, fw=190, fh=115, pole_h=280, amp=8)

    # Poppies along Hudson River Park promenade
    for i in range(28):
        s.add(poppy(30 + i * 56 + s.rng.random() * 20, 520 + s.rng.random() * 50, 0.7 + s.rng.random() * 0.4))


def scene_thanksgiving(s):
    """2. Thanksgiving: Macy's Thanksgiving Day Parade! Giant helium balloon over Central Park West brownstones."""
    s.sky("#2a1408", "#8a3a14", "#f0a040")
    s.sun(1180, 180, 56, "#fff4d4", "#f0a040")
    s.clouds([(320, 90, 1.1), (820, 70, 0.85)], "#ffe8d1", 0.75)

    # Central Park trees in vibrant autumn foliage
    s.ground(370, "#4a2a12", "#6a3a18")
    for i in range(45):
        s.tree(s.rng.random() * W, 375 + s.rng.random() * 20, 0.65 + s.rng.random() * 0.5,
               s.rng.choice(["#d9481f", "#e8822a", "#f2b134", "#a8321e", "#c0392b"]))

    # Central Park West Brownstones on right & left
    s.brownstones(-10, 480, 430, ["#542a18", "#6a341e", "#7b3e24"], h=(220, 310), window="#ffd88a", lit=0.65)
    s.brownstones(1120, W + 20, 430, ["#542a18", "#6a341e", "#7b3e24"], h=(220, 310), window="#ffd88a", lit=0.65)

    # High-rise towers behind Central Park
    s.nyc_skyline("#4a2010", y=370, x0=480, x1=1120, hmin=100, hmax=240, window="#ffd98a", opacity=0.7)

    # Giant Macy's Parade Helium Balloon floating high over street!
    # Stylized giant Thanksgiving parade character / giant golden turkey balloon
    bx, by = 800, 200
    s.glow(bx, by, 160, "#f59e0b", 0.25)
    s.add(
        # Main balloon body
        f'<ellipse cx="{bx}" cy="{by}" rx="130" ry="95" fill="#ea580c"/>'
        f'<ellipse cx="{bx - 20}" cy="{by - 15}" rx="95" ry="65" fill="#f97316" opacity="0.8"/>'
        # Balloon head & smiling face
        f'<circle cx="{bx - 100}" cy="{by - 50}" r="55" fill="#f59e0b"/>'
        f'<polygon points="{bx - 155},{by - 45} {bx - 185},{by - 35} {bx - 155},{by - 25}" fill="#ef4444"/>'
        f'<circle cx="{bx - 120}" cy="{by - 65}" r="12" fill="#fff"/>'
        f'<circle cx="{bx - 124}" cy="{by - 65}" r="6" fill="#1e293b"/>'
        # Macy's Red Star on the balloon
        f'<g transform="translate({bx + 20},{by - 10})">{star(0, 0, 36, "#ef4444")}</g>'
        # Balloon tail feathers
        f'<ellipse cx="{bx + 110}" cy="{by - 40}" rx="35" ry="60" fill="#dc2626" transform="rotate(25 {bx + 110} {by - 40})"/>'
        f'<ellipse cx="{bx + 130}" cy="{by}" rx="30" ry="55" fill="#f59e0b" transform="rotate(45 {bx + 130} {by})"/>'
    )

    # Parade Guide Ropes & Balloon Handlers in yellow raincoats below
    for rx, hx in ((bx - 70, 680), (bx - 20, 740), (bx + 30, 830), (bx + 80, 890)):
        s.add(f'<line x1="{rx}" y1="{by + 80}" x2="{hx}" y2="465" stroke="#ffffff" stroke-width="2.5" opacity="0.85"/>')
        # Handler person in uniform
        s.person(hx, 490, 1.25, "#eab308", arms="up")

    # Parade Street & Cheering Crowd
    s.ground(430, "#2a180e", "#180d07")
    s.add(f'<rect x="0" y="430" width="{W}" height="24" fill="#3a2215"/>')
    for x in range(460, 1140, 24):
        s.person(x, 500 + s.rng.random() * 8, 1.1 + s.rng.random() * 0.3, s.rng.choice(["#78350f", "#9a3412", "#b45309", "#1e293b"]), s.rng.choice(["up", "wave"]))

    # Autumn leaves blowing in the parade breeze
    for _ in range(35):
        s.add(leaf(s.rng.random() * W, s.rng.random() * 380, 0.5 + s.rng.random() * 0.6,
                   s.rng.choice(["#ea580c", "#f59e0b", "#dc2626", "#b45309"]), s.rng.random() * 360, 0.85))


def scene_blackfriday(s):
    """3. Black Friday: 5th Avenue & Herald Square luxury shopping, glowing art deco storefronts and golden confetti."""
    s.sky("#000000", "#141414", "#3a3000")
    s.stars(45, 200, 0.4)
    gold = "#facc15"

    # Manhattan Storefronts & Luxury Department Stores (Saks / Macy's Herald Square)
    x = -10
    i = 0
    while x < W:
        w = 160 + s.rng.random() * 50
        h = 260 + s.rng.random() * 50
        c = s.rng.choice(["#262626", "#1f1f1f", "#2d281f"])
        s.add(f'<rect x="{x:.0f}" y="{430 - h:.0f}" width="{w + 1:.0f}" height="{h:.0f}" fill="{c}"/>'
              f'<rect x="{x - 3:.0f}" y="{430 - h - 8:.0f}" width="{w + 6:.0f}" height="10" fill="#443c2c"/>')
        s.windows_grid(x + 16, 430 - h + 18, w - 32, h - 160, 3, 2, "#ffe599", lit=0.65, ww=28, wh=42)

        # Illuminated Holiday Window Display with Golden Awnings
        sx, sw = x + 16, w - 32
        s.add(
            f'<rect x="{sx:.0f}" y="340" width="{sw:.0f}" height="84" fill="#fff5cc"/>'
            f'<rect x="{sx:.0f}" y="340" width="{sw:.0f}" height="84" fill="{s.vgrad([(0, gold, 0.7), (1, "#d97706", 0.35)])}"/>'
            # Decorative holiday garland / chandelier in window
            f'<path d="M{sx + 8},350 Q{sx + sw / 2},370 {sx + sw - 8},350" stroke="#16a34a" stroke-width="5" fill="none"/>'
            f'<circle cx="{sx + sw / 2:.0f}" cy="378" r="7" fill="{gold}"/>'
            # Window Sale Plaque
            f'<g transform="translate({sx + sw / 2:.0f},395)"><rect x="-48" y="-14" width="96" height="28" rx="4" fill="#111"/>'
            f'<text x="0" y="6" text-anchor="middle" font-family="Arial Black, sans-serif" font-weight="900" font-size="15" fill="{gold}">'
            f'{["FIFTH AVE", "SALE", "BLACK FRIDAY", "HOLIDAY DEALS"][i % 4]}</text></g>'
        )
        x += w + 4
        i += 1

    s.ground(430, "#0a0a0a", "#171717")
    s.add(f'<rect x="0" y="430" width="{W}" height="26" fill="#262626"/>')

    # Grand Cast-Iron Street Lamps
    for lx in (180, 580, 1020, 1420):
        s.lamp_post(lx, 470, 160, "#111", "#ffe08a")

    # Shoppers with luxury bags on 5th Ave sidewalk
    for bx, by, sc, col in ((360, 590, 1.35, gold), (460, 600, 1.1, "#ffffff"), (1140, 595, 1.25, "#111"), (1240, 600, 1.45, gold)):
        s.add(f'<g transform="translate({bx},{by}) scale({sc})">'
              f'<rect x="-30" y="-70" width="60" height="70" fill="{col}" stroke="{gold}" stroke-width="3"/>'
              f'<path d="M-14,-70 Q-14,-94 0,-94 Q14,-94 14,-70" stroke="{gold if col != gold else "#111"}" stroke-width="4" fill="none"/></g>')

    # Golden confetti drifting through the night air
    s.confetti(160, [gold, "#ffffff", "#fef08a", "#d97706"], 0, 600, size=(3, 7))


def scene_cybermonday(s):
    """4. Cyber Monday: Silicon Alley / Times Square cyberpunk neon grid tracing the Flatiron Building."""
    s.sky("#03061a", "#0b2a5c", "#06b6d4")
    s.stars(70, 260, 0.7)
    cyan, purple = "#22d3ee", "#a855f7"

    # Circuit traces sweeping the digital NYC sky
    for _ in range(28):
        x, y = s.rng.random() * W, s.rng.random() * 300
        pts = [(x, y)]
        for _ in range(4):
            if s.rng.random() < 0.5:
                x += s.rng.choice([-1, 1]) * (40 + s.rng.random() * 120)
            else:
                y += s.rng.choice([-1, 1]) * (20 + s.rng.random() * 60)
            pts.append((x, y))
        col = s.rng.choice([cyan, purple])
        s.add(f'<polyline points="{" ".join(f"{a:.0f},{b:.0f}" for a, b in pts)}" stroke="{col}" stroke-width="2" fill="none" opacity="0.6"/>'
              f'<circle cx="{pts[-1][0]:.0f}" cy="{pts[-1][1]:.0f}" r="4" fill="{col}"/>')

    # The iconic Flatiron Building in neon cyber-silhouette
    c, base = 800, 410
    s.glow(c, 240, 280, cyan, 0.22)
    s.add(
        # Flatiron narrow wedge structure
        f'<polygon points="{c - 110},{base} {c - 28},{base - 310} {c + 28},{base - 310} {c + 110},{base}" fill="#1e1b4b"/>'
        f'<polygon points="{c - 28},{base - 310} {c},{base - 330} {c + 28},{base - 310}" fill="#312e81"/>'
        # Neon edge lines tracing architecture
        f'<line x1="{c - 110}" y1="{base}" x2="{c - 28}" y2="{base - 310}" stroke="{cyan}" stroke-width="3"/>'
        f'<line x1="{c + 110}" y1="{base}" x2="{c + 28}" y2="{base - 310}" stroke="{cyan}" stroke-width="3"/>'
        f'<line x1="{c}" y1="{base}" x2="{c}" y2="{base - 330}" stroke="{purple}" stroke-width="3"/>'
    )
    # Digital windows matrix
    s.windows_grid(c - 70, base - 280, 140, 260, 4, 10, cyan, ww=14, wh=16)

    # Surrounding Manhattan towers with digital code streams
    s.nyc_skyline("#090d24", y=base, x0=0, x1=660, hmin=70, hmax=200, window=cyan, opacity=0.85)
    s.nyc_skyline("#090d24", y=base, x0=940, x1=W, hmin=70, hmax=200, window=purple, opacity=0.85)

    # Neon perspective grid floor (Broadway & 5th Ave intersection)
    s.add(f'<rect x="0" y="{base}" width="{W}" height="{H - base}" fill="{s.vgrad([(0, "#1e0840"), (1, "#03061a")])}"/>')
    for k in range(-14, 15):
        s.add(f'<line x1="{c + k * 45}" y1="{base}" x2="{c + k * 210}" y2="{H}" stroke="{purple}" stroke-width="2" opacity="0.6"/>')
    for k in range(9):
        y = base + (k / 8) ** 1.8 * (H - base)
        s.add(f'<line x1="0" y1="{y:.0f}" x2="{W}" y2="{y:.0f}" stroke="{cyan}" stroke-width="2" opacity="0.6"/>')

    # Floating digital code brackets & cyber glyphs
    for x, y, t in ((260, 120, "&lt;NYC/&gt;"), (1320, 150, "{ SILICON_ALLEY }"), (440, 260, "01001110"), (1160, 260, "11011001")):
        s.add(f'<text x="{x}" y="{y}" font-family="Menlo, monospace" font-size="34" font-weight="700" fill="{cyan}" opacity="0.85">{t}</text>')
    s.add(f'<polygon points="1060,60 1010,150 1050,150 1020,230 1100,120 1058,120 1090,60" fill="{cyan}" opacity="0.9"/>')


def scene_hanukkah(s):
    """5. Hanukkah: World's Largest Menorah at Grand Army Plaza (Central Park South) with glowing candles."""
    s.sky("#06102a", "#14306e", "#3a64b8")
    s.stars(90, 260, 0.85)
    s.moon(1400, 95, 30, "#f8fafc", 0.6)

    # Midtown Manhattan silhouettes behind Central Park South (Plaza Hotel & Towers)
    s.nyc_skyline("#070e24", y=380, hmin=90, hmax=240, window="#ffd88a", opacity=0.9)

    # Plaza Hotel Chateau Roof Silhouette
    plx = 420
    s.add(
        f'<rect x="{plx - 120}" y="180" width="240" height="200" fill="#0b1736"/>'
        f'<polygon points="{plx - 130},180 {plx},110 {plx + 130},180" fill="#13234d"/>'
        f'<rect x="{plx - 100}" y="200" width="200" height="15" fill="#f8fafc" opacity="0.3"/>'
    )
    s.windows_grid(plx - 100, 220, 200, 140, 6, 4, "#ffd88a", ww=14, wh=22)

    # Central Park snowy lawn at Grand Army Plaza
    s.ground(380, "#101f42", "#ffffff")
    for px in (180, 1380, 280, 1260):
        s.pine(px, 440, 140, "#0b253a", snow="#ffffff")

    # The World's Largest Menorah (32-Foot Gold Menorah at Grand Army Plaza)
    c, sill = 800, 480
    gold = "#f59e0b"
    s.glow(c, sill - 180, 280, "#ffd27a", 0.35)

    # Massive Menorah Base & Central Trunk
    s.add(
        f'<polygon points="{c - 50},{sill} {c - 20},{sill - 50} {c + 20},{sill - 50} {c + 50},{sill}" fill="{gold}"/>'
        f'<rect x="{c - 10}" y="{sill - 220}" width="20" height="180" fill="{gold}"/>'
        f'<ellipse cx="{c}" cy="{sill}" rx="60" ry="12" fill="#d97706"/>'
    )

    # 8 Symmetrical Branches sweeping upward
    for k in range(1, 5):
        for side in (-1, 1):
            x = c + side * k * 36
            bh = sill - 70 - (4 - k) * 20
            s.add(f'<path d="M{c},{sill - 70} Q{x},{sill - 70} {x},{sill - 190}" stroke="{gold}" stroke-width="7" fill="none"/>')

    # Candle holders on branches
    positions = [c - 144, c - 108, c - 72, c - 36, c + 36, c + 72, c + 108, c + 144]
    for i, x in enumerate(positions):
        s.add(f'<rect x="{x - 6}" y="{sill - 225}" width="12" height="35" fill="#f8fafc"/>')
        # On the first night, light the first candle (rightmost)
        if i == 7:
            s.glow(x, sill - 245, 45, "#ffd27a", 0.9)
            s.add(f'<ellipse cx="{x}" cy="{sill - 242}" rx="7" ry="16" fill="#fef08a"/>'
                  f'<ellipse cx="{x}" cy="{sill - 240}" rx="4" ry="10" fill="#ffffff"/>')

    # Central Shamash Candle (Elevated in Center)
    s.add(f'<rect x="{c - 8}" y="{sill - 265}" width="16" height="45" fill="#f8fafc"/>')
    s.glow(c, sill - 285, 55, "#ffd27a", 0.95)
    s.add(f'<ellipse cx="{c}" cy="{sill - 282}" rx="8" ry="18" fill="#fef08a"/>'
          f'<ellipse cx="{c}" cy="{sill - 280}" rx="4" ry="11" fill="#ffffff"/>')

    # Ornate streetlamps flanking Plaza
    s.lamp_post(320, 540, 170, "#111", "#ffe08a")
    s.lamp_post(1280, 540, 170, "#111", "#ffe08a")

    # Gentle winter snowfall over Manhattan
    s.snow(220, H, 1.0)


def scene_christmas(s):
    """6. Christmas: Rockefeller Center Christmas Tree, 30 Rock, Prometheus and skaters on the ice rink."""
    s.sky("#071422", "#16314a", "#3d6680")
    s.stars(70, 240, 0.7)

    # 30 Rockefeller Plaza (Art Deco 30 Rock tower rising in center)
    cx = 800
    s.add(
        f'<rect x="{cx - 140}" y="30" width="280" height="370" fill="#0c1e30"/>'
        f'<rect x="{cx - 100}" y="10" width="200" height="390" fill="#132a42"/>'
        f'<rect x="{cx - 60}" y="-10" width="120" height="410" fill="#1b3957"/>'
    )
    s.windows_grid(cx - 50, 40, 100, 250, 4, 12, "#ffd88a", ww=10, wh=14)

    # Flanking Midtown buildings with glowing holiday lights
    s.nyc_skyline("#071320", y=400, x0=0, x1=580, hmin=90, hmax=220, window="#ffd98a")
    s.nyc_skyline("#071320", y=400, x0=1020, x1=W, hmin=90, hmax=220, window="#ffd98a")

    # The 80-Foot Rockefeller Center Norway Spruce Tree!
    tx, base = 800, 420
    s.glow(tx, 270, 270, "#ffd27a", 0.3)
    s.add(f'<rect x="{tx - 12}" y="{base - 20}" width="24" height="26" fill="#3b2a1f"/>')
    for k in range(5):
        y = base - 20 - k * 58
        w = 160 - k * 28
        s.add(f'<polygon points="{tx - w},{y} {tx},{y - 115} {tx + w},{y}" fill="{["#0f5132", "#14603c", "#187044", "#1c7a4a", "#208554"][k]}"/>')

    # Thousands of colorful glowing fairy lights on the tree
    for _ in range(140):
        y = base - 25 - s.rng.random() * 300
        half = (y - (base - 340)) / 320 * 160
        if half < 4:
            continue
        x = tx - half + s.rng.random() * 2 * half
        col = s.rng.choice(["#ef4444", "#ffd23f", "#38bdf8", "#ffffff", "#f43f5e", "#4ade80"])
        s.add(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="3.5" fill="{col}"/><circle cx="{x:.0f}" cy="{y:.0f}" r="8" fill="{col}" opacity="0.22"/>')

    # Swarovski Crystal Star atop Rockefeller Tree
    s.glow(tx, base - 345, 60, "#ffd27a", 0.85)
    s.add(star(tx, base - 345, 26, "#ffffff"))
    s.add(star(tx, base - 345, 18, "#ffd23f"))

    # The Famous Rink at Rockefeller Center with Ice Skaters
    s.ground(420, "#c9d6ea", "#eef3fb")
    s.add(f'<ellipse cx="800" cy="525" rx="580" ry="72" fill="{s.vgrad([(0, "#d8ecff"), (1, "#93c5fd")])}" stroke="#ffffff" stroke-width="7"/>')

    # Gold Statue of Prometheus overlooking the rink
    s.add(f'<ellipse cx="800" cy="460" rx="30" ry="16" fill="#f59e0b"/>'
          f'<circle cx="800" cy="445" r="14" fill="#fbbf24"/>')

    # Joyful ice skaters on the rink
    for x, y, sc, col, arms in ((530, 532, 1.1, "#c81e1e", "wave"), (650, 515, 0.95, "#1e3a8a", "down"),
                                (890, 545, 1.2, "#0f5132", "up"), (1030, 518, 0.95, "#7a2e8a", "wave"),
                                (1170, 535, 1.05, "#d97706", "down"), (750, 550, 0.85, "#c81e1e", "up")):
        s.person(x, y, sc, col, arms)
        s.add(f'<line x1="{x - 10 * sc:.0f}" y1="{y + 2:.0f}" x2="{x + 10 * sc:.0f}" y2="{y + 2:.0f}" stroke="#ffffff" stroke-width="2"/>')

    # Bare illuminated trees along Channel Gardens
    for bx in (200, 1400):
        s.lamp_post(bx, 580, 180, "#111", "#ffe08a")

    # Falling Christmas snow over Manhattan
    s.snow(260, H, 1.0)


def scene_newyearseve(s):
    """7. New Year's Eve: Times Square Ball Drop! Glowing crystal ball, neon year sign, confetti blizzard and fireworks."""
    s.sky("#07051a", "#241a55", "#5b3a8a")
    s.stars(60, 240, 0.6)

    # Midnight fireworks over Times Square
    for x, y, r, c in ((280, 100, 95, "#f5c542"), (540, 60, 65, "#f472b6"), (1080, 70, 85, "#a78bfa"),
                       (1340, 120, 105, "#f5c542"), (1220, 50, 55, "#ffffff"), (380, 210, 60, "#38bdf8")):
        s.firework(x, y, r, c, 22)

    # One Times Square Tower (The Ball Drop Building)
    c, base = 800, 430
    s.add(
        f'<rect x="{c - 100}" y="120" width="200" height="310" fill="#0d0922"/>'
        f'<polygon points="{c - 110},120 {c},70 {c + 110},120" fill="#1a113a"/>'
        # Giant Digital Billboards blazing in Times Square
        f'<rect x="{c - 85}" y="220" width="170" height="75" fill="#ef4444"/>'
        f'<text x="{c}" y="270" text-anchor="middle" font-family="Arial Black, sans-serif" font-weight="900" font-size="34" fill="#ffffff">TIMES SQ</text>'
        f'<rect x="{c - 85}" y="310" width="170" height="55" fill="#3b82f6"/>'
        f'<text x="{c}" y="350" text-anchor="middle" font-family="Arial Black, sans-serif" font-weight="900" font-size="28" fill="#ffffff">NYC 2027</text>'
        # Flagpole on roof for the New Year's Eve Ball
        f'<line x1="{c}" y1="70" x2="{c}" y2="-20" stroke="#ffffff" stroke-width="4"/>'
    )

    # The Crystal Times Square Ball (descending at midnight)
    ball_y = 15
    s.glow(c, ball_y, 75, "#fef08a", 0.95)
    s.add(
        f'<circle cx="{c}" cy="{ball_y}" r="26" fill="#ffffff"/>'
        f'<circle cx="{c}" cy="{ball_y}" r="22" fill="#38bdf8" opacity="0.7"/>'
        + "".join(f'<polygon points="{c + math.cos(math.radians(a)) * 26:.1f},{ball_y + math.sin(math.radians(a)) * 26:.1f} '
                  f'{c + math.cos(math.radians(a + 45)) * 14:.1f},{ball_y + math.sin(math.radians(a + 45)) * 14:.1f} {c},{ball_y}" fill="#ffffff"/>'
                  for a in range(0, 360, 45))
    )

    # Surrounding Times Square billboards & skyscrapers
    s.nyc_skyline("#0a061c", y=base, x0=0, x1=680, hmin=100, hmax=240, window="#facc15")
    s.nyc_skyline("#0a061c", y=base, x0=920, x1=W, hmin=100, hmax=240, window="#38bdf8")

    # Neon Year Numerals blazing on One Times Square
    s.add(
        f'<g transform="translate({c},{160})">'
        f'<rect x="-80" y="-30" width="160" height="60" rx="8" fill="#111" stroke="#facc15" stroke-width="3"/>'
        f'<text x="0" y="14" text-anchor="middle" font-family="Arial Black, sans-serif" font-weight="900" font-size="44" fill="#facc15">2027</text>'
        f'</g>'
    )

    # Cheering Times Square crowd in party hats below
    s.ground(base, "#130924", "#090412")
    for x in range(40, W - 40, 26):
        y = 585 + s.rng.random() * 10
        col = s.rng.choice(["#1e1b4b", "#312e81", "#1e293b"])
        s.person(x, y, 1.45, col, s.rng.choice(["up", "wave"]),
                 hat=f'<polygon points="-7,-60 7,-60 0,-85" fill="{s.rng.choice(["#f5c542", "#f472b6", "#a78bfa", "#38bdf8"])}"/>')

    # Times Square Blizzard of Confetti!
    s.confetti(220, ["#f5c542", "#f472b6", "#a78bfa", "#ffffff", "#38bdf8", "#4ade80"], 0, 600, size=(3, 8))


def scene_newyear(s):
    """8. New Year's Day: Sunrise over the Brooklyn Bridge and New York Harbor with golden dawn rays."""
    s.sky("#2b3a78", "#e8857a", "#ffd59a")
    s.sun(800, 385, 75, "#ffe2a6", "#ffb36b")
    s.rays(800, 385, ["#fff2cc", "#fde047", "#f97316"], n=26, opacity=0.15)
    s.clouds([(330, 140, 1.1), (1250, 110, 1.3), (980, 200, 0.8)], "#ffc9a8", 0.55)

    # Manhattan & Brooklyn skylines at dawn
    s.nyc_skyline("#4b3358", y=HZ, hmin=50, hmax=160, opacity=0.7, window="#ffd88a")

    # The Iconic Brooklyn Bridge Gothic Arches over East River
    c, base = 800, HZ
    stone = "#4a354f"
    s.add(
        # Roadway deck
        f'<rect x="0" y="{base - 45}" width="{W}" height="12" fill="#2d1d33"/>'
        f'<line x1="0" y1="{base - 39}" x2="{W}" y2="{base - 39}" stroke="#ffd59a" stroke-width="2"/>'
    )

    # Main Gothic Stone Towers (Manhattan Tower & Brooklyn Tower)
    for tx in (c - 300, c + 300):
        s.add(
            # Tower base and twin gothic pointed arches
            f'<rect x="{tx - 55}" y="{base - 260}" width="110" height="260" fill="{stone}"/>'
            f'<polygon points="{tx - 60},{base - 260} {tx},{base - 290} {tx + 60},{base - 260}" fill="#38253d"/>'
            # Twin Gothic Arches cutouts
            f'<path d="M{tx - 38},{base} L{tx - 38},{base - 130} Q{tx - 20},{base - 180} {tx - 2},{base - 130} L{tx - 2},{base} Z" fill="#24142a"/>'
            f'<path d="M{tx + 2},{base} L{tx + 2},{base - 130} Q{tx + 20},{base - 180} {tx + 38},{base - 130} L{tx + 38},{base} Z" fill="#24142a"/>'
        )

    # Giant Sweeping Suspension Cables & Vertical Suspenders
    s.add(
        f'<path d="M0,{base - 180} Q{c - 300},{base - 275} {c - 300},{base - 260} Q{c},{base - 80} {c + 300},{base - 260} Q{c + 300},{base - 275} {W},{base - 180}" stroke="#1f1124" stroke-width="6" fill="none"/>'
        f'<path d="M0,{base - 180} Q{c - 300},{base - 275} {c - 300},{base - 260} Q{c},{base - 80} {c + 300},{base - 260} Q{c + 300},{base - 275} {W},{base - 180}" stroke="#ffd59a" stroke-width="2" fill="none" opacity="0.6"/>'
    )
    for k in range(-12, 13):
        x = c + k * 24
        cable_y = (base - 80) - (1 - (abs(k) / 12.5) ** 2) * (-150)
        s.add(f'<line x1="{x}" y1="{base - 45}" x2="{x}" y2="{min(base - 45, cable_y):.0f}" stroke="#2d1d33" stroke-width="1.5" opacity="0.75"/>')

    # East River shimmering with golden New Year morning reflection
    s.water(HZ, "#f2a37f", "#3a2f6a", "#fff1c9", 70, 0.55)
    s.add(f'<rect x="{800 - 80}" y="{HZ + 4}" width="160" height="190" fill="{s.vgrad([(0, "#ffe2a6", 0.7), (1, "#ffe2a6", 0)])}"/>')

    # Statue of Liberty silhouette in the distant harbor
    s.add(
        f'<g transform="translate(1380,360) scale(0.65)" fill="#24142a">'
        f'<rect x="-16" y="0" width="32" height="30"/>'
        f'<polygon points="-12,0 -8,-50 8,-50 12,0"/>'
        f'<polygon points="4,-50 18,-85 22,-85 10,-50"/>'
        f'<circle cx="21" cy="-87" r="4" fill="#ffd59a"/>'
        f'</g>'
    )

    # Joyful New Year ribbons and morning golden sparkles
    for x0, col2 in ((50, "#f5c542"), (180, "#f472b6"), (1420, "#a78bfa"), (1540, "#f5c542"), (320, "#60a5fa")):
        pts = " ".join(f"{x0 + 14 * math.sin(y / 18):.0f},{y}" for y in range(0, 180, 6))
        s.add(f'<polyline points="{pts}" stroke="{col2}" stroke-width="3" fill="none" opacity="0.8"/>')
    s.confetti(60, ["#f5c542", "#ffffff", "#ffd59a"], 0, 300, size=(3, 7))


SCENES = {
    "veterans": scene_veterans,
    "thanksgiving": scene_thanksgiving,
    "blackfriday": scene_blackfriday,
    "cybermonday": scene_cybermonday,
    "hanukkah": scene_hanukkah,
    "christmas": scene_christmas,
    "newyearseve": scene_newyearseve,
    "newyear": scene_newyear,
}


def main():
    want = set(sys.argv[1:])
    out_dir = os.path.join(ROOT, "static", "holidays")
    os.makedirs(out_dir, exist_ok=True)
    for key, fn in SCENES.items():
        if want and key not in want:
            continue
        s = Scene(key)
        fn(s)
        path = os.path.join(out_dir, f"{key}.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(s.svg())
        print(f"Generated {key:14s} -> {path} ({os.path.getsize(path) // 1024} KB)")


if __name__ == "__main__":
    main()
