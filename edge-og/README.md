# Dynamic OG cards on Cloudflare Workers (optional)

Renders a 1200x630 **SVG** preview card for any event from query parameters, cached at the edge:

```
https://nyc-events-og.<your-subdomain>.workers.dev/og?title=Boy+Harsher&venue=Knockdown+Center&city=Queens&date=Thu+Nov+5+·+9pm&badge=Live+Music
```

Deploy (needs a Cloudflare account):

```bash
cd edge-og
npx wrangler login
npx wrangler deploy
```

**Limitation:** Facebook, X/Twitter, LinkedIn, iMessage, and Slack only accept raster (PNG/JPEG)
`og:image`s, so SVG cards won't unfurl there. The site itself uses the JPEG cards rendered by
`export_og.py` on every export (`og-image.jpg`, `og-<landing-page>.jpg`). This worker is useful for
embeds and tools that accept SVG, or as a starting point for a raster renderer (e.g. `@resvg/resvg-wasm`)
if per-event share links are added later.
