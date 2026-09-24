# Xirja — progress record

This file is the source of truth for where the project stands. Unlike a
chat conversation, this survives regardless of what any AI session does or
doesn't remember — read this file (and the actual code) before trusting any
recap, including one I might give you in a new session. Update the "Last
verified" line and the relevant section whenever real progress happens.

**Last verified against the actual code/deployment: 24 Sept 2026 (updated
same day six times — real shopping-list feature, then Browse + basic
navigation, a reliability fix for Render free-tier cold starts, a real
Compare screen, a fix for the database connection pool going stale, then a
real Store lists screen).**

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
  add-item search), `GET /stores` (every real store, for Compare — added
  so a store carrying none of a list's items still appears in the
  ranking), and a full shopping-list CRUD set — `GET /lists/{user_id}`,
  `POST /lists/{user_id}/items`, `PATCH /lists/{user_id}/items/{item_id}`,
  `DELETE /lists/{user_id}/items/{item_id}`. Every endpoint now goes
  through one shared helper (`run_with_db`) instead of repeating its own
  connection-handling: found via a real Render log (24 Sept), a pooled
  database connection can go stale without warning (Render's free tier
  sleeping after 15 idle minutes, or Neon closing a connection it decides
  has been idle too long), and using a stale one crashed the request with
  `psycopg2.OperationalError: SSL connection has been closed
  unexpectedly`. The helper now discards a connection that fails this way
  and retries the same request once with a fresh one, instead of letting
  it crash — confirmed both by reading the code path and by the app
  working normally afterwards (My list, Browse, and Compare all confirmed
  working again on 24 Sept, with no further "Not Found" errors).
- **Database — list tables extended**: `migration_001_list_by_category.sql`
  (in `xirja-backend`) makes `app_list_item` support an item identified by
  shared category (`shopping_category`), not only a matched `product_id` —
  needed because product-matching coverage is still partial. Must be run
  once against the real database before the list endpoints above work —
  confirm it's actually been run in Neon, this file only records that the
  migration was written and delivered.
- **Mobile app — 4 real screens now, with basic navigation**: `App.js`
  (`xirja-app` repo). "My list": search-and-add a category, change
  quantity, remove an item, pull to refresh. "Browse": scroll every
  category with a live price, tap to add. "Compare" (new): for each real
  store, the whole-basket total if everything on the list came from there
  (its own prices plus whatever it doesn't carry, bought at wherever's
  cheapest for that item) — ranked cheapest to most expensive, with a
  headline "cheapest vs most expensive" saving figure. This is the actual
  `storeTotal()` logic from the original prototype, now computed from real
  data rather than a hardcoded catalog, computed on the phone from data
  the list screen already has (see the comment above `computeStoreRanking`
  in `App.js`) plus the new `/stores` endpoint. "Store lists" (new): the
  complementary strategy to Compare — instead of "everything from one
  store," each item is assigned to its own individually cheapest store
  (`item.cheapest`), then grouped into one card per store with its item
  count, subtotal, and a preview of what's in it. Reached from a "Split
  into N store lists" button at the bottom of Compare (only shown when
  splitting would actually involve more than one store), with its own back
  arrow rather than a fourth tab — mirrors exactly how the original
  clickable prototype linked the two screens. A simple three-tab bar
  switches between "My list"/"Browse"/"Compare" — local state, not the
  React Navigation library yet (fine for 3 tabs, won't scale cleanly much
  further). Uses a random per-device id (`AsyncStorage`) in place of real
  accounts, which don't exist yet — documented in `xirja-app/SETUP.md` as a
  deliberate, swappable shortcut, not an oversight.

## Not started / explicitly designed-only (confirmed absent from the code)

- Real code for 5 of the 9 designed screens (Item detail, Shopping mode,
  Trip summary, Settings, Onboarding) — these exist only in the clickable
  `.dc.html` prototype. "My list", "Browse", "Compare", and "Store lists"
  are now real; everything else isn't yet.
- Real navigation library (React Navigation or similar) — today's screen
  switching is a simple local-state toggle (three tabs plus one sub-screen
  reached by a button), fine for now, won't scale cleanly much further —
  especially once Shopping mode needs to be reached FROM a specific store
  list, which a local `useState` string can express but won't stay clean
  for long.
- Store lists is the end of that path for now — it shows what to buy where,
  but there's no "check items off while shopping" screen yet (that's
  Shopping mode, still prototype-only) and no way to save/revisit a split
  once you leave the screen.
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
  failed. Also found via a real Render log (24 Sept): the same free-tier
  sleep (or a Neon-side idle timeout) can leave a stale connection sitting
  in the server's connection pool, which used to crash the request with
  `psycopg2.OperationalError` instead of recovering — the server now
  detects that specific failure and retries once with a fresh connection
  (see `run_with_db` in `api/main.py`). Both fixes make the free tier's
  rough edges tolerable, not solved — moving off the free tier is still
  the real fix for the underlying sleep/idle behavior itself.

## How to keep this file honest

- Before believing any status claim (from a chat session, an old summary,
  anything) — check it against the actual repo/deployment, the way this
  file's contents were checked on 24 Sept 2026, not against what a
  conversation "remembers."
- Update this file at the end of any session where real progress happens,
  and commit it in the same batch as the code change it describes.
