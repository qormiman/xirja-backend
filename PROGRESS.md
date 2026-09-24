# Xirja — progress record

This file is the source of truth for where the project stands. Unlike a
chat conversation, this survives regardless of what any AI session does or
doesn't remember — read this file (and the actual code) before trusting any
recap, including one I might give you in a new session. Update the "Last
verified" line and the relevant section whenever real progress happens.

**Last verified against the actual code/deployment: 24 Sept 2026.**

## What's built and confirmed real (verified by reading the actual code/repo, not from memory)

- **Price crawlers — all 3 chains**: `greens_crawler.py`, `pavipama_crawler.py`,
  `welbees_crawler.py` all exist and are substantial, real, working scripts.
- **Crawl scheduling**: Greens and PAVI PAMA run automatically via GitHub
  Actions, with an adaptive scheduler (`plan_crawl_schedule.py` /
  `check_and_trigger_crawl.py`) — confirmed active as recently as the week
  of 21 Sept 2026. Welbee's GitHub Actions nightly run is deliberately
  disabled (Welbee's blocks GitHub's cloud IPs via Cloudflare) — it instead
  runs from a home computer via `run_welbees.ps1` + a watchdog script,
  confirmed working via `schedule_log.txt`.
- **Database**: `schema.sql` / `seed.sql` exist and match the intended data
  model (store / outlet / listing / price_observation, etc).
- **Category taxonomy**: `category_taxonomy.py` + `categorize_listings.py` —
  extensively tuned across 10 rounds; open collisions reduced from an
  initial large backlog to 4 residual instances (2 pairs), all verified
  against the full ~96k-name catalog using production matching logic.
- **Cross-chain product matching**: `product_matcher.py` +
  `export_medium_matches.py` / `apply_reviewed_matches.py` — a real
  barcode/fuzzy-match system with a human review workflow for
  medium-confidence matches, deployed as GitHub Actions
  (`match-products.yml`, `apply-review.yml`, `export-review.yml`).
- **Price API**: `api/main.py` — real FastAPI service, one working endpoint
  (`GET /categories/{category}/prices`, cheapest current price per store),
  deployed on Render (`https://xirja-backend.onrender.com` per the mobile
  app's config — confirm this matches the live Render dashboard address).
- **Mobile app — first screen**: a real "My list" screen (`App.js`) that
  calls the live API and renders real prices for 4 hardcoded categories.
  As of 24 Sept 2026 this was recovered from a local download and turned
  into a proper, git-tracked project (`xirja-app` repo) — before that it
  only existed as a pasted-in Expo Snack session, which is why it wasn't
  showing up as "built" anywhere durable.

## Not started / explicitly designed-only (confirmed absent from the code)

- Real navigation across the other 8 designed screens (Browse, Compare,
  Item detail, Store lists, Shopping mode, Trip summary, Settings,
  Onboarding) — these exist only in the clickable `.dc.html` prototype.
- The `app_list` / `app_list_item` tables and the "add/remove item to my
  list" feature — the mobile app's category list is still hardcoded.
- The price-correction workflow (`user_price` table, site-vs-mine trust
  logic) — designed in the prototype and spec, not ported to real code.
- Legal / Terms-of-Service review for each chain — flagged as overdue in
  the original spec, no evidence it's been done.
- The LIDL / crowdsourced-pricing product decision — still explicitly
  unresolved.
- Failure alerting beyond "the job crashed" — a job that runs but silently
  stops finding prices isn't caught yet.

## How to keep this file honest

- Before believing any status claim (from a chat session, an old summary,
  anything) — check it against the actual repo/deployment, the way this
  file's contents were checked on 24 Sept 2026, not against what a
  conversation "remembers."
- Update this file at the end of any session where real progress happens,
  and commit it in the same batch as the code change it describes.
