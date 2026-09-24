# Xirja — progress record

This file is the source of truth for where the project stands. Unlike a
chat conversation, this survives regardless of what any AI session does or
doesn't remember — read this file (and the actual code) before trusting any
recap, including one I might give you in a new session. Update the "Last
verified" line and the relevant section whenever real progress happens.

**Last verified against the actual code/deployment: 24 Sept 2026 (updated
same day three times — real shopping-list feature, then Browse + basic
navigation, then a reliability fix for Render free-tier cold starts).**

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
- **Price API**: `api/main.py` — real FastAPI service, deployed on Render
  (`https://xirja-backend.onrender.com` per the mobile app's config —
  confirm this matches the live Render dashboard address). Endpoints:
  `GET /categories/{category}/prices` (cheapest current price per store),
  `GET /categories` (every category with a live price, for the app's
  add-item search), and a full shopping-list CRUD set —
  `GET /lists/{user_id}`, `POST /lists/{user_id}/items`,
  `PATCH /lists/{user_id}/items/{item_id}`,
  `DELETE /lists/{user_id}/items/{item_id}`.
- **Database — list tables extended**: `migration_001_list_by_category.sql`
  (in `xirja-backend`) makes `app_list_item` support an item identified by
  shared category (`shopping_category`), not only a matched `product_id` —
  needed because product-matching coverage is still partial. Must be run
  once against the real database before the list endpoints above work —
  confirm it's actually been run in Neon, this file only records that the
  migration was written and delivered.
- **Mobile app — 2 real screens now, with basic navigation**: `App.js`
  (`xirja-app` repo). "My list": search-and-add a category, change
  quantity, remove an item, pull to refresh. "Browse" (new): scroll every
  category with a live price, tap to add, shows how many are already on
  the list. A simple two-tab bar switches between them — local state, not
  the React Navigation library yet (not needed until there are more than 2
  screens). Both screens share one live connection to the real API/database.
  Uses a random per-device id (`AsyncStorage`) in place of real accounts,
  which don't exist yet — documented in `xirja-app/SETUP.md` as a
  deliberate, swappable shortcut, not an oversight.

## Not started / explicitly designed-only (confirmed absent from the code)

- Real code for 7 of the 9 designed screens (Compare, Item detail, Store
  lists, Shopping mode, Trip summary, Settings, Onboarding) — these exist
  only in the clickable `.dc.html` prototype. "My list" and "Browse" are
  now real; everything else isn't yet.
- Real navigation library (React Navigation or similar) — today's 2-screen
  switch is a simple local-state toggle, fine for 2 screens, won't scale
  cleanly much past that.
- The price-correction workflow (`user_price` table, site-vs-mine trust
  logic) — designed in the prototype and spec, not ported to real code.
- Legal / Terms-of-Service review for each chain — flagged as overdue in
  the original spec, no evidence it's been done.
- The LIDL / crowdsourced-pricing product decision — still explicitly
  unresolved.
- Failure alerting beyond "the job crashed" — a job that runs but silently
  stops finding prices isn't caught yet.
- Automated tests for the new list endpoints (`get_or_create_list`,
  `add_item`, etc) — written and manually reviewed for correctness, not
  covered by an automated test the way `check_crawl_freshness.py` is.
- The API's CORS is still wide open (`allow_origins=["*"]`) and Render is
  still on the free tier (sleeps after 15 min idle, ~30-60s cold start) —
  fine for testing, not for real users. Confirmed in real testing (24 Sept)
  that a cold start can cause one of two simultaneous requests to fail with
  a raw network error while the other succeeds — the app now retries once
  automatically on that specific failure and no longer discards an
  already-successful result just because a second, unrelated request
  failed. The underlying free-tier sleep behavior itself is unchanged —
  moving off the free tier is the real fix, this just makes the app
  tolerate it better in the meantime.

## How to keep this file honest

- Before believing any status claim (from a chat session, an old summary,
  anything) — check it against the actual repo/deployment, the way this
  file's contents were checked on 24 Sept 2026, not against what a
  conversation "remembers."
- Update this file at the end of any session where real progress happens,
  and commit it in the same batch as the code change it describes.
