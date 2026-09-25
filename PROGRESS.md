# Xirja — progress record

This file is the source of truth for where the project stands. Unlike a
chat conversation, this survives regardless of what any AI session does or
doesn't remember — read this file (and the actual code) before trusting any
recap, including one I might give you in a new session. Update the "Last
verified" line and the relevant section whenever real progress happens.

**Last verified against the actual code/deployment: 25 Sept 2026 (updated
thirteen times across 24–25 Sept — real shopping-list feature, then Browse +
basic navigation, a reliability fix for Render free-tier cold starts, a
real Compare screen, a fix for the database connection pool going stale, a
real Store lists screen, a real Item detail screen with genuine price
history, a real Shopping mode, a first (incomplete) attempt at its blank
progress bar, then the real fix: `store.color` was seeded as `oklch(...)`,
which real React Native doesn't render — see below, then a React
Navigation migration whose first version had a real "stuck, no way back to
the tabs" bug, then a root-stack restructure that fixed that, then a
second real bug the restructure exposed — a half-cut-off tab bar, caused by
a missing `SafeAreaProvider` — see below, and finally discovering the
Snack project itself runs Expo SDK 54, not the SDK 51 `package.json` had
been pinned to this whole time — see below).**

**A third real discrepancy, found via Snack's own dependency-check panel
rather than by reading code**: `package.json` had been pinned to Expo SDK
51 (`expo: ~51.0.28`, React Native 0.74.5) since before this session, but
the actual Snack project this app runs in is on SDK 54. Snack flagged five
packages (`@react-native-async-storage/async-storage`,
`expo-status-bar`, `react-native-gesture-handler`,
`react-native-safe-area-context`, `react-native-screens`) as pinned to
versions that don't match SDK 54, each with its own "Update to X" button.
`package.json` is now updated to SDK 54-compatible versions throughout
(`expo: ~54.0.0`, `react: 19.1.0`, `react-native: 0.81.4`, plus the five
flagged packages at the versions Snack itself recommended) so this
shouldn't resurface. The three `@react-navigation/*` packages weren't
flagged by Snack and were left as they were — they aren't part of Expo's
version-locked SDK bundle the way the other five are. Worth remembering:
whatever SDK a given Snack project is actually running can drift from
what's recorded in this repo's `package.json` — Snack's own Problems panel
is the source of truth for that, not this file or the text of the file
itself.

**A second lesson-learned note, on the navigation bugs (two, found one at a
time by actually using the app on Snack, not from re-reading the code)**:
the first React Navigation version nested "Item detail" inside "My list"'s
own stack and "Store lists"/"Shopping mode" inside "Compare"'s own stack,
and hid the tab bar dynamically by matching each tab's currently-focused
nested route name against a list of "hide the bar on these" names — the
pattern React Navigation's own docs recommend for this. It looked right and
passed a manual code review, but going Store lists <-> Shopping mode worked
while there was genuinely no way back to the three main tabs. Fixed by
removing that dynamic-hiding logic entirely: "Item detail", "Store lists"
and "Shopping mode" now live as their own screens on ONE root-level stack,
with a single "Tabs" screen (the actual tab bar) as a sibling screen on
that same stack. Confirmed by the user this actually fixed the "stuck"
problem — but revealed a second, real bug: back on the tabs, the tab bar
itself rendered half cut off at the bottom (screenshot confirmed on Snack's
Web preview). Cause: React Navigation's bottom tab bar reads its own bottom
inset from `react-native-safe-area-context` (`useSafeAreaInsets`) to size
and pad itself against the real device safe area — that package was
already a dependency (added as a required peer of `@react-navigation/
bottom-tabs`) but the app was never actually wrapped in its
`SafeAreaProvider`, only in the unrelated plain `SafeAreaView` from
"react-native" (which only pads its own children away from a notch/status
bar and provides none of this context). Without a real provider, the hook
had nothing to read and fell back to bad values. Fixed by wrapping the
whole app in `SafeAreaProvider` (outermost, per React Navigation's own
setup docs) in addition to the existing `SafeAreaView`. Not yet
re-confirmed by the user as of this writing.

**On the personal-use deployment plan (agreed 25 Sept)**: three technical
steps remain before a permanent install on your own Android phone —
(1) a real navigation library (done, this update), (2) persisting Shopping
mode's checked-off state so it survives an app close/reload, and (3) an EAS
build turned into a sideloadable `.apk`. Doing them in this order on
purpose: navigation first because Shopping mode's persistence and any
future "Trip summary" screen both build on top of real navigation state
(e.g. route params) rather than the old local-state screen string; then
persistence; then the build step, once there's nothing left to rebuild
around.

**A note on that last one, because it's a useful lesson for future
debugging in this app**: the progress bar looked blank, so the first fix
assumed the bug was in the progress-bar CODE (a percentage-width React
Native quirk) and rebuilt it a more robust way. That was a real
improvement but not the actual cause — the bar's code was fine all along.
The real bug was upstream, in the DATA: `store.color` in the database was
seeded with values like `oklch(0.55 0.12 152)`, which is valid CSS that
any browser renders fine, but which React Native's own color parser does
not understand at all on a real device — it silently drops the color
instead of erroring, so any UI element using a store's color as a real
background (this progress bar, item ribbons, store chips, the Compare/
Store lists bars) rendered nothing. It likely affected those other spots
too in a subtler, easier-to-miss way; only this screen's big, obviously-
blank bar made it impossible to overlook. Fixed at the source — the
database column, via `migration_002_hex_store_colors.sql` — not by
special-casing color handling in the app, so every screen that uses a
store's color is fixed by the same one change. Lesson: when something
renders as "blank" rather than visibly wrong, check the DATA feeding it
before rewriting the code that displays it. Confirmed fixed by the user on
25 Sept — real color now shows throughout: the Shopping mode progress bar,
item ribbons on My list, store chips on Item detail and Store lists, and
the highlighted bar on Compare.

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
  ranking), `GET /categories/{category}/history` (new — up to 8 weeks of
  REAL weekly price history per store, bucketed from the actual
  `price_observation` rows the crawlers have been collecting all along;
  the first endpoint that looks further back than "the single latest
  price," powers Item detail's chart), and a full shopping-list CRUD set —
  `GET /lists/{user_id}`,
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
- **Database — store colors fixed to real hex**:
  `migration_002_hex_store_colors.sql` (in `xirja-backend`) converts
  `store.color` from `oklch(...)` (set in the original `seed.sql`, valid
  CSS but not something React Native renders on a real device) to real hex
  equivalents — same colors, a format every platform actually understands.
  `seed.sql` itself is also fixed for any future fresh database. Must be
  run once against the real database (same way migration_001 was) before
  the app's colors — the Shopping mode progress bar, item ribbons, store
  chips — actually show up.
- **Mobile app — 6 real screens now, with basic navigation**: `App.js`
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
  clickable prototype linked the two screens. Confirmed working end to end
  on 24 Sept (button appears, screen renders real per-store cards, back
  arrow returns to Compare). "Item detail" (new): tap any item on "My
  list" to see its cheapest price, the full current price at every store
  that carries it, and a real 8-week price-history bar chart per store
  (switch stores via chips) pulled fresh from the new `/history` endpoint,
  with a plain-language trend line ("Price is down 6% since Aug 4").
  Confirmed working end to end on 24 Sept (tap-through, current prices,
  chips, chart, and back navigation all tested on Snack). "Shopping mode"
  (new): tap a store card on Store lists to get a real checklist for that
  stop — tick items off, watch the running total and a progress bar update,
  switch between stores in the plan without detouring back through Store
  lists, and jump straight to the next unfinished store once the current
  one's done. Deliberately does NOT include the original prototype's
  barcode scanning or "fix this price"/"swap store" actions — those need a
  camera and the price-correction workflow respectively, neither of which
  exist yet. Checked-off state lives only in memory (component state in
  `App()`), not persisted — closing/reloading the app mid-trip loses your
  checkmarks. That's a known, real gap, not an oversight: persisting it
  (AsyncStorage, keyed by list_id) is a natural small follow-up once this
  screen itself is confirmed working. The numbers ("X of N checked",
  running total) were confirmed correct on first testing (24 Sept), but the
  visual progress bar itself stayed blank. Root cause turned out to be
  upstream in the DATA, not the bar's code — see the `migration_002`
  entry above and the note at the top of this file: `store.color` was
  seeded as `oklch(...)`, which React Native doesn't render on a real
  device. The bar was also rebuilt to use flex proportions instead of a
  percentage width along the way (a genuine, separate improvement — more
  reliable when a screen stays mounted while its own state changes, rather
  than being freshly re-rendered from a list each time — but not itself
  what was hiding the color). Confirmed fully working end to end on 25
  Sept, colors included, after `migration_002_hex_store_colors.sql` was run.
  Navigation is now REAL (new, 25 Sept, and fixed once already — see the
  lesson-learned note above): a root-level stack holds one "Tabs" screen
  (the actual three-tab bar — "My list"/"Browse"/"Compare") plus "Item
  detail", "Store lists" and "Shopping mode" as sibling screens on that
  SAME root stack, pushed on top of "Tabs" rather than nested inside a
  tab's own stack. This gets genuine push/back navigation, including the
  Android hardware back button, instead of the old hand-rolled `screen`
  string plus a manual render branch — and the tab bar is simply absent on
  the pushed screens (nothing dynamic to get wrong: it only exists on the
  "Tabs" screen at all), matching how the original clickable prototype
  behaved. Shared app state (the list, categories, stores, loading/error
  flags, and the handler functions) is threaded through an
  `AppStateContext` rather than passed as navigator props — deliberately,
  because a `Tab.Screen`/`RootStack.Screen`'s `component` must be a stable
  function reference or React Navigation remounts it (losing navigation
  state) on every re-render; passing state as inline render-prop `children`
  instead would have recreated a new function every time `App()`'s own
  state changed (e.g. every quantity tap). Needs 3 new packages that
  weren't in `package.json` before this update — `@react-navigation/native`,
  `@react-navigation/bottom-tabs`, `@react-navigation/native-stack` — plus
  their peer dependencies `react-native-screens`,
  `react-native-safe-area-context`, `react-native-gesture-handler`, all
  pinned to versions that match this app's Expo SDK 51 / React Native
  0.74.5. Verified by re-cloning the live `xirja-app` repo and diffing
  against it (confirms exactly the intended change and nothing else
  touched) and by a manual bracket-balance + styles-used-vs-defined check
  of the whole file (no real JS/JSX parser is available in this
  environment — `npm install` is blocked by the sandbox's network policy,
  confirmed again this session — so this is done with a small custom
  script). NOT yet confirmed on a real device/Snack as of this writing —
  the first version of this migration passed the same kind of check and
  still had the "stuck, no way back to the tabs" bug once actually used,
  so treat this specific screen-navigation behavior as unconfirmed until
  you've tapped through it yourself: My list → an item → back; Compare →
  Split into store lists → a store → Shopping mode → back → back. Uses a
  random per-device id (`AsyncStorage`) in place of real accounts, which
  don't exist yet — documented in `xirja-app/SETUP.md` as a deliberate,
  swappable shortcut, not an oversight.

## Not started / explicitly designed-only (confirmed absent from the code)

- Real code for 3 of the 9 designed screens (Trip summary, Settings,
  Onboarding) — these exist only in the clickable `.dc.html` prototype.
  "My list", "Browse", "Compare", "Store lists", "Item detail", and
  "Shopping mode" are now real; everything else isn't yet.
- Shopping mode's checked-off state is in-memory only (see `App.js`'s top
  comment and the note in the mobile-app section above) — no "Trip
  summary" screen yet to land on once every store's fully checked off, and
  no persistence if the app closes mid-trip. This is the next of the three
  agreed personal-use deployment steps (navigation is now done — see the
  mobile-app section above).
- EAS build → sideloadable Android `.apk` for a permanent personal install
  — not started (third of the three agreed steps). Needs `app.json`/
  `eas.json` config, an app icon/splash, an Expo account, and running
  `eas build`.
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
