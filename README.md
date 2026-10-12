# 🗽 NYC Events

A real-time, ultra-fast aggregator and mobile-friendly calendar of concerts, nightlife, theater, comedy, markets, and cultural happenings across all 5 boroughs of New York City (Manhattan, Brooklyn, Queens, The Bronx, and Staten Island).

Companion project to [Wicked Boston Events](https://github.com/BehlV10/boston_events).

---

## 🌟 Highlights & Features

- **62+ Live NYC Venues & Community Feeds**: Aggregates from independent concert halls, indie bookstores, public libraries, neighborhood dive bars, pub trivia leagues, Broadway lotteries, and curated local guides.
- **5-Borough Multi-Filter**: 1-tap filter pills for Manhattan, Brooklyn, Queens, The Bronx, Staten Island, and Tri-State / Greater NY.
- **Custom NYC Skyline Hero Art**: Handcrafted, responsive SVG banner featuring One World Trade Center with red beacon spire, Empire State Building, Chrysler Building, Brooklyn Bridge stone arches, Statue of Liberty silhouette, Yellow Taxi pin, starfield, and East River reflections.
- **Quick-Time Filters**: 1-tap shortcuts for *Today*, *Tomorrow*, *This Weekend*, *Next 7 Days*, and *Free Only*.
- **Live NYC Weather & Broadway Lotteries**: Real-time Central Park temperature/forecast chip via Open-Meteo, plus live active Broadway lottery draws via LuckySeat.
- **Calendar Integration**: 1-tap `+ GCal` button to add any event directly to Google Calendar, plus downloadable `.ics` support for Apple Calendar and Outlook.
- **Zero-Dependency Static Exporter**: Generates a self-contained, lightning-fast static `index.html` (1,800+ events) suitable for GitHub Pages, Cloudflare Pages, or any CDN.
- **Automated 30-Minute Scraper Pipeline**: GitHub Actions cron runner re-scrapes feeds, refreshes `events.json` and `index.html`, and commits updates automatically.

---

## 🏛️ Coverage Across All 5 Boroughs

### 🎷 Manhattan
- **Concerts & Clubs**: Bowery Ballroom, Mercury Lounge, Webster Hall, Terminal 5, Irving Plaza, Racket NYC, Le Poisson Rouge, Blue Note Jazz Club, Smalls Jazz Club, Gramercy Theatre, Sony Hall, The Town Hall, City Winery.
- **Iconic Halls**: Madison Square Garden, Radio City Music Hall, Beacon Theatre, Carnegie Hall, Apollo Theater, Lincoln Center.
- **Independent Bookstores & Readings**: Strand Book Store (Rare Book Room & Flagship author talks), McNally Jackson Books (SoHo & Seaport), Bluestockings Cooperative (LES).
- **Public Libraries**: New York Public Library (NYPL flagship Schwarzman & SNFL author talks, workshops, and exhibitions).
- **Independent Film & Comedy**: Film Forum (Greenwich Village), IFC Center (West Village), Caveat NYC, Comedy Cellar, Film Forum, Joe's Pub, The Public Theater.
- **Markets & Free Happenings**: Union Square Greenmarket, Grand Bazaar NYC (UWS), Bryant Park series, Central Park SummerStage.

### 🎸 Brooklyn
- **Indie & Nightlife**: Brooklyn Steel, Music Hall of Williamsburg, Elsewhere Bushwick, Warsaw Greenpoint, Baby's All Right, The Sultan Room, Good Room Greenpoint, Public Records Gowanus, C'mon Everybody Bed-Stuy.
- **Neighborhood Bars & Live Music**: Pete's Candy Store (Williamsburg — nightly backroom music, open mics & comedy), Skinny Dennis (Williamsburg — live honky tonk & roots music).
- **Independent Bookstores**: Books Are Magic (Cobble Hill & Brooklyn Heights author events), Greenlight Bookstore (Fort Greene).
- **Public Libraries**: Brooklyn Public Library (BPL Presents & branch programming).
- **Comedy, Film & Performing Arts**: The Bell House, Union Hall Brooklyn (Park Slope basement comedy), Littlefield, Kings Theatre Flatbush, Brooklyn Bowl Williamsburg, Nitehawk Cinema (Williamsburg & Prospect Park), Pioneer Works Red Hook, BAM (Brooklyn Academy of Music).
- **Arenas & Markets**: Barclays Center, Brooklyn Flea DUMBO, Smorgasburg (Williamsburg & Prospect Park).

### 🌳 Queens
- **Venues & Music**: Forest Hills Stadium, Knockdown Center Maspeth, TV Eye Ridgewood.
- **Public Libraries & Culture**: Queens Public Library (author talks & community programs), MoMA PS1, Museum of the Moving Image, Socrates Sculpture Park.

### ⚾ The Bronx
- **Sports & Performing Arts**: Yankee Stadium, Lehman Center for the Performing Arts, Bronx Zoo, New York Botanical Garden (NYBG), Wave Hill.

### 🎭 Staten Island
- **Historic & Arts Venues**: St. George Theatre, Snug Harbor Cultural Center & Botanical Garden.

### 🍻 Citywide Pub Trivia & Aggregators
- **NYC Trivia League**: 150+ weekly trivia & mixtape bingo nights across 70+ neighborhood bars in Manhattan, Brooklyn, and Queens (Bleecker Street Bar, The Winslow, The Ditty Astoria, Small Change, Bareburger Hell's Kitchen, Pig Beach, Black Forest, Gowanus Gardens).
- **DoNYC**: 10-day rolling citywide feed covering hundreds of local events.
- **The Skint NYC**: Cult-favorite daily curated newsletter for cheap and free NYC events.
- **Ticketmaster Discovery API**: Live NYC discovery feed (`lat/lng: 40.7128, -74.0060`).
- **Broadway Discount Portals**: LuckySeat API, Broadway Direct, TodayTix, TKTS Booths.
- **Public Culture**: NYC Culture Pass (free museum admission for NYC library cardholders), NYC Ferry harbor routes.

---

## 🚀 Local Development & Quickstart

### Prerequisites
- Python 3.9+
- Dependencies: `flask`, `requests`, `beautifulsoup4`, `python-dateutil`

### Setup
```bash
# Clone the repository
git clone git@github.com:BehlV10/nyc_events.git
cd nyc_events

# Create or reuse virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running Locally
```bash
# Start local development server on port 3001
python3 server.py

# Visit http://127.0.0.1:3001 in your browser
```

### CLI Diagnostic & Export Tools
```bash
# Run scraper diagnostics on all 46 venues
python3 server.py test

# Run diagnostic on a single venue (e.g. Bowery Ballroom)
python3 server.py test "Bowery"

# Re-scrape and export fresh events.json
python3 server.py export events.json

# Render static HTML from events.json
python3 server.py export html index.html
```

---

## 🤖 Automated Scraper Workflow

The repository includes [`.github/workflows/scrape.yml`](.github/workflows/scrape.yml):
- Runs every **30 minutes** via GitHub Actions cron (`*/30 * * * *`).
- Supports manual execution via `workflow_dispatch`.
- Fetches all venue pages concurrently.
- Deduplicates listings and updates `events.json`, `index.html`, and `events.html`.
- Commits changes back to `main` with a timestamped bot commit.

---

## 🌐 GitHub Pages & Custom Domain Setup

1. **Enable GitHub Pages**:
   - Go to **Settings** → **Pages** in the GitHub repository.
   - Set **Source** to `Deploy from a branch`.
   - Select branch `main` and folder `/ (root)`.
   - Save. Your site will be published at `https://<username>.github.io/nyc_events/`.

2. **Custom Domain (Cloudflare DNS)**:
   - In GitHub repository settings under **Custom domain**, enter your desired domain (e.g., `www.nycevents.com`).
   - In Cloudflare DNS, add a `CNAME` record pointing to `<username>.github.io` with Proxy status set to *Proxied* or *DNS only*.
   - Check *Enforce HTTPS* in GitHub Pages settings once DNS propagates.

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
