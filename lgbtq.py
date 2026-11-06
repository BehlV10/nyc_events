"""LGBTQ+ tag for the "LGBTQ+ events only" filter.

A tag rather than a category: Queer Board Game Night is games, drag brunch is theater, a tea dance
is nightlife, so the tag rides alongside whatever category an event has. An event gets it when it's
at a queer venue, comes from a queer source, or says so in its title or description.
"""
import re

# Sources (VENUES "name") that only list queer events. Not the "Meetup: LGBTQ+" or "AllEvents: Lgbt"
# keyword feeds, which also return unrelated events (a salsa class, a Rockville Centre speed dating).
LGBTQ_SOURCES = {
    "the center (lgbtq+ community center)",
    "3 dollar bill (queer & drag venue)",
    "bureau of general services queer division",
    "crux lgbtqia+ climbing",
    "lgbt network community centers",
    "lips drag showpalace restaurant and bar",
    "meetup: new york lgbt board games group",
    "pride salsa",
    "queer social",
}

# Queer venues, whoever lists the event. Not "Main Drag Music" or "The Center for Fiction".
_VENUE_RE = re.compile(
    r"\bstonewall inn\b|\bcubbyhole\b|\bhenrietta hudson\b|\bthe monster\b|\bjulius'?\b|\bpieces bar\b|"
    r"\b3 dollar bill\b|\bgood judy\b|\bflaming saddles\b|\bindustry bar\b|\bnowhere bar\b|\beastern bloc\b|"
    r"\bbureau of general services\b|\bleslie[- ]lohman\b|\blips drag\b|\bthe center \(208 w",
    re.I,
)
# Organizers named as the venue. Not checked against source names: those are keyword feeds.
_ORGANIZER_RE = re.compile(r"\bqueer\b|\blgbt\w*\b|\bgay\b|\blesbians?\b", re.I)

# Words that mark an event as LGBTQ+ in its title.
_TITLE_RE = re.compile(
    r"(?<![\w-])(?:queer\w*|lgbt\w*\+?|2slgbt\w*\+?|gays?|gaymers?|lesbians?|sapphic|wlw|bisexual|bi\+|"
    r"trans|transgender|non-?binary|two-spirit|intersex|pride|drag|dykes?|voguing)(?![\w-])",
    re.I,
)
# In descriptions only unambiguous terms count: "we take pride in", "drag your friends along" and
# "a gay old time" don't make an event queer.
_DESC_RE = re.compile(
    r"(?<![\w-])(?:queer\w*|lgbt\w*\+?|2slgbt\w*\+?|lesbians?|sapphic|gaymers?|trans and non-?binary|"
    r"drag (?:queens?|kings?|shows?|performers?|brunch))(?![\w-])",
    re.I,
)
# Phrases that use those words for something else. Removed before matching.
_NOT_RE = re.compile(
    r"pride (?:and|&) prejudice|\bpride of\b|pride rock|(?:school|team|civic|hometown|irish|italian|"
    r"puerto rican|dominican|haitian|black) pride|\btrans am\b|"
    r"drag (?:racing|races? strip|strip|cars?|me to hell)|drag-?and-?drop",
    re.I,
)


def is_lgbtq_event(e):
    """True for an LGBTQ+ venue, source or event. e: an event dict (name, venue, _source_venue, description)."""
    source = (e.get("_source_venue") or "").strip().lower()
    if source in LGBTQ_SOURCES:
        return True
    venue = e.get("venue") or ""
    if _VENUE_RE.search(venue) or _VENUE_RE.search(source) or _ORGANIZER_RE.search(venue):
        return True
    name = _NOT_RE.sub(" ", e.get("name") or e.get("title") or "")
    if _TITLE_RE.search(name):
        return True
    return bool(_DESC_RE.search(_NOT_RE.sub(" ", e.get("description") or "")))
