"""NYC Events — seasonal calendar for promotional graphics.

Ported from Boston's themes.py (which defined seasons but wasn't wired to anything). Here the
weekly flyer (scripts/generate_this_week_flyer.py) uses get_theme() for its eyebrow line and
accent colors, so carousels pick up the season automatically. The website's own color
themes are separate (see get_seasonal_theme() in template.py).

Each season covers an inclusive (month, day) window; windows are checked in order, so short
special windows come before the broad seasons they sit inside.
"""

from datetime import date, datetime

from scrapers import EASTERN

SEASONS = [
    {"id": "halloween", "start": (10, 24), "end": (11, 1),
     "name": "Halloween in NYC", "eyebrow": "🎃 HALLOWEEN WEEK · VILLAGE PARADE · COSTUME PARTIES",
     "primary": "#ff6b1a", "accent": "#7c3aed", "soft": "#ffe4d1"},
    {"id": "thanksgiving", "start": (11, 20), "end": (11, 30),
     "name": "Thanksgiving & the Macy's Parade", "eyebrow": "🦃 THANKSGIVING WEEK · PARADE · FRIENDSGIVINGS",
     "primary": "#c2410c", "accent": "#92400e", "soft": "#fde7d3"},
    {"id": "fall", "start": (9, 15), "end": (11, 19),
     "name": "Fall in the City", "eyebrow": "🍂 FALL IN NYC · MARATHON SEASON · ROOFTOPS & FOLIAGE",
     "primary": "#b45309", "accent": "#0047e1", "soft": "#fdebd3"},
    {"id": "holidays", "start": (12, 1), "end": (12, 31),
     "name": "Holidays in NYC", "eyebrow": "🎄 HOLIDAY SEASON · ROCKEFELLER TREE · MARKETS & SKATING",
     "primary": "#b91c1c", "accent": "#15803d", "soft": "#fde2e2"},
    {"id": "winter", "start": (1, 1), "end": (2, 10),
     "name": "Winter in NYC", "eyebrow": "❄️ WINTER IN NYC · JAZZ CLUBS · RESTAURANT WEEK",
     "primary": "#1d4ed8", "accent": "#0f172a", "soft": "#dbeafe"},
    {"id": "valentines", "start": (2, 11), "end": (2, 16),
     "name": "Date Nights", "eyebrow": "💘 DATE NIGHT WEEK · CANDLELIT SHOWS · SPEED DATING",
     "primary": "#db2777", "accent": "#7f1d1d", "soft": "#fce7f3"},
    {"id": "spring", "start": (2, 17), "end": (5, 20),
     "name": "Spring in NYC", "eyebrow": "🌸 SPRING IN NYC · CHERRY BLOSSOMS · STREET FAIRS",
     "primary": "#be185d", "accent": "#0047e1", "soft": "#fce7f3"},
    {"id": "pride", "start": (6, 1), "end": (6, 30),
     "name": "Pride Month", "eyebrow": "🏳️‍🌈 PRIDE MONTH · MARCH · PARTIES · DRAG",
     "primary": "#7c3aed", "accent": "#e11d48", "soft": "#ede9fe"},
    {"id": "summer", "start": (5, 21), "end": (9, 14),
     "name": "Summer in NYC", "eyebrow": "☀️ SUMMER IN NYC · SUMMERSTAGE · ROOFTOPS · BEACHES",
     "primary": "#0047e1", "accent": "#e62e00", "soft": "#ffe4e6"},
]
DEFAULT_SEASON = {"id": "classic", "name": "NYC Events", "eyebrow": "THIS WEEK IN NEW YORK CITY",
                  "primary": "#0047e1", "accent": "#e62e00", "soft": "#ffccd5"}


def _in_window(d, start, end):
    key = (d.month, d.day)
    return start <= key <= end if start <= end else (key >= start or key <= end)


def get_theme(d=None):
    """Season dict for a date (defaults to today in New York)."""
    if d is None:
        d = datetime.now(EASTERN).date()
    elif isinstance(d, datetime):
        d = d.date()
    for season in SEASONS:
        if _in_window(d, season["start"], season["end"]):
            return season
    return DEFAULT_SEASON


if __name__ == "__main__":
    today = date.today()
    print(get_theme(today)["name"])
