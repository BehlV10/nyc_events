"""What a change does to the page: which cards appear, disappear or change category.

Merge and category rules interact in ways unit tests miss (a rule that merges AllEvents copies
of Broadway shows also merged a hookah night into Q.E.D. Astoria). This renders the same saved
crawl with two checkouts of the code and lists every difference in the coming days.

    python scripts/card_diff.py --base ../main-checkout --head . --events events.json --out diff.md

Each side runs in its own process, so the two versions of template.py never mix.
"""
import argparse
import json
import os
import subprocess
import sys

_DUMP = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import template
data = json.load(open(sys.argv[2], encoding="utf-8"))
dated, _tba, _ongoing = template.group_by_date(data["venues"] if isinstance(data, dict) else data)
cards = {}
for day, events in dated[:int(sys.argv[3])]:
    for e in events:
        key = f"{day} | {e.get('name')} | {e.get('venue') or ''}"
        cards[key] = {"category": e.get("category"), "url": (e.get("url") or "")[:120]}
json.dump(cards, sys.stdout)
"""


def cards(code_dir, events, days):
    out = subprocess.run([sys.executable, "-W", "ignore", "-c", _DUMP, os.path.abspath(code_dir), os.path.abspath(events), str(days)],
                         capture_output=True, text=True, cwd=os.path.abspath(code_dir))
    if out.returncode:
        raise SystemExit(f"rendering with {code_dir} failed:\n{out.stderr[-2000:]}")
    return json.loads(out.stdout)


def compare(base, head, limit=60):
    """Markdown report of the differences between two {card key: {category, url}} maps."""
    gone = sorted(set(base) - set(head))
    new = sorted(set(head) - set(base))
    moved = sorted(k for k in set(base) & set(head) if base[k]["category"] != head[k]["category"])
    relinked = sorted(k for k in set(base) & set(head) if base[k]["url"] != head[k]["url"])
    lines = ["## Card diff", "",
             f"{len(base):,} cards before, {len(head):,} after: **{len(gone)} gone, {len(new)} new, "
             f"{len(moved)} changed category, {len(relinked)} changed link**.", ""]

    def section(title, keys, fmt):
        if not keys:
            return
        lines.extend([f"<details><summary>{title} ({len(keys)})</summary>", ""])
        lines.extend(fmt(k) for k in keys[:limit])
        if len(keys) > limit:
            lines.append(f"- … and {len(keys) - limit} more")
        lines.extend(["", "</details>", ""])
    section("Gone", gone, lambda k: f"- {k}  ({base[k]['category']})")
    section("New", new, lambda k: f"- {k}  ({head[k]['category']})")
    section("Changed category", moved, lambda k: f"- {k}: {base[k]['category']} → {head[k]['category']}")
    section("Changed link", relinked, lambda k: f"- {k}: {base[k]['url']} → {head[k]['url']}")
    if not (gone or new or moved or relinked):
        lines.append("No difference on this crawl.")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", required=True, help="checkout of the code before the change")
    ap.add_argument("--head", default=".", help="checkout of the code after the change")
    ap.add_argument("--events", required=True, help="events.json from a crawl")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--out")
    args = ap.parse_args()
    report = compare(cards(args.base, args.events, args.days), cards(args.head, args.events, args.days))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report)
    print(report)


if __name__ == "__main__":
    main()
