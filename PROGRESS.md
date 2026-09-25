# Xirja — progress record

This file is the source of truth for where the project stands. Unlike a
chat conversation, this survives regardless of what any AI session does or
doesn't remember — read this file (and the actual code) before trusting any
recap, including one I might give you in a new session. Update the "Last
verified" line and the relevant section whenever real progress happens.

**Last verified against the actual code/deployment: 25 Sept 2026. THE
PERSONAL-USE DEPLOYMENT GOAL IS DONE**: Xirja is now a real, permanent app
installed on the owner's own Android phone via a genuine EAS build,
confirmed opened and running there. That's the finish line for the plan
agreed earlier in this file (real navigation → persisted Shopping mode →
EAS build), all three steps done and confirmed. Full history of how it got
there (real shopping-list feature, Browse + basic navigation, a Render
cold-start reliability fix, a real Compare screen, a stale-connection-pool
fix, Store lists, Item detail with real price history, Shopping mode, the
`oklch()` color bug, the React Navigation migration and its two follow-up
bugs (a "stuck, no way back to tabs" bug fixed by a root-stack restructure,
then a half-cut-off tab bar fixed by adding `SafeAreaProvider`), an Expo
SDK 51→54 package.json correction, Shopping mode's persistence, and
finally the EAS build itself — including a locked-down work laptop forcing
a pivot to GitHub Codespaces, a broken browser-based `eas login` forcing a
pivot to an `EXPO_TOKEN` instead, and a missing `babel-preset-expo`
dependency that failed the first real build attempt) is preserved below,
in the order it actually happened — worth reading if a similar step (a
real build, a new dev environment, an unfamiliar CLI tool) comes up again,
since several of these were genuinely non-obvious the first time.

**On the personal-use deployment plan — COMPLETE**: (1) real navigation —
done and confirmed working. (2) persisting Shopping mode's checked-off
state — done and confirmed working. (3) EAS build → sideloadable `.apk` —
DONE: built successfully via GitHub Codespaces + `EXPO_TOKEN` auth,
downloaded and installed on the owner's own Android phone via the
`.apk` link, confirmed opened and running there without issues (25 Sept).
The app no longer depends on Snack, a dev server, or a cable to open day
to day.

**Update, 25 Sept**: the `babel-preset-expo` fix and the earlier SDK 54
`package.json` correction have both since been confirmed pushed to the
real `xirja-app` GitHub repo (verified by re-cloning it fresh) — the loose
end previously noted here is closed. A fresh clone or fresh Codespace today
builds correctly with no manual patching needed.

**Now underway: closing the gap between the 6 "real" screens and the
original design mockups.** After the personal-use deployment finished, the
owner compared the running app against the original design screenshots for
all 6 real screens (My list, Browse, Compare, Item detail, Store lists,
Shopping mode) and found each one missing pieces the design called for.
Decision made explicitly by the owner: fix ALL of it, screen by screen —
including the three large, backend-touching pieces (offline mode, barcode
scanning, the price-correction workflow) — rather than deferring the big
ones. See "Design-vs-implementation gap-closing (started 25 Sept)" below
for the full task list and progress.

**On the EAS build step (new, this update; revised once already — see
below)**: two new files — `app.json` (added `android.package:
"com.xirja.app"`, the unique id Android needs to identify the app; the
user confirmed no strong opinion either way, chosen as a reasonable
placeholder) and `eas.json` (a `preview` build profile producing a plain
installable `.apk` rather than the `.aab` format the Play Store wants —
deliberately NOT a production/Play Store profile, since that's a separate,
later decision with real business/legal considerations, not a technical
one to make casually). A new `EAS_BUILD.md` walks through the rest step by
step: creating a free Expo account, `npm install`, installing `eas-cli`,
`eas login`, `eas init` (this is the one part of the setup that has to
happen under the user's own account — it can't be done from here), then
`eas build --platform android --profile preview`, and finally getting the
resulting `.apk` onto the phone and sideloading it (allowing installs from
outside the Play Store, a normal step for any non-Play-Store app, not a
red flag).

**Real discrepancy #4, found immediately on the very first command**: the
original version of `EAS_BUILD.md` assumed a normal personal computer and
told the user to install Node.js directly. In reality this app's owner
uses a WORK laptop with IT-locked-down installs -- `node -v` failed, and
getting Node.js installed the normal way would need IT approval that's
"very unlikely to be given." This blocks the plain nodejs.org-installer
path entirely, not just as an inconvenience -- worth remembering for any
future step that assumes a normal, unrestricted personal computer.
`EAS_BUILD.md` is now rewritten around **GitHub Codespaces** instead: a
free, browser-based dev environment tied to the user's GitHub account,
with Node.js already installed there, so nothing installs on the work
laptop at all -- it's a browser tab, the same as Snack has been throughout
this whole project. The rest of the steps (Expo account, `npm install`,
`eas-cli`, `eas login`/`eas init`, the build itself, sideloading the
resulting `.apk`) are unchanged, just run from the Codespace's terminal
instead of a local PowerShell. CONFIRMED this worked well: the Codespace
opened cleanly on the `xirja-app` repo with Node.js 20.20.2 already
present, no laptop install needed at any point.

**Real discrepancy #5: `eas login`'s browser flow doesn't work from a
Codespace (or any remote/cloud terminal)**. `eas login` opens a browser tab
for OAuth and expects the browser to redirect back to `localhost:<port>` on
the SAME machine running the CLI -- but from a Codespace, "localhost" in
the user's own browser is their Windows laptop, not the remote container
actually running `eas`, so the redirect always fails with
`ERR_CONNECTION_REFUSED` no matter how many times it's retried. This isn't
a Codespaces-specific bug -- it's a structural mismatch that would hit any
remote/cloud terminal (SSH, a container, CI). Fixed by skipping interactive
login entirely: created a personal access token on expo.dev (Account
settings → Access Tokens), then `export EXPO_TOKEN=<token>` in the
Codespace terminal before running any `eas` command -- `eas whoami`
confirmed it worked immediately, no browser involved. Worth remembering
for next time a Codespace (or similar) is used for this project: skip
`eas login` and go straight to `EXPO_TOKEN`.

**Real discrepancy #6, the one that actually failed a full build**: first
`eas build --platform android --profile preview` attempt got all the way
through queuing, uploading, and starting the Android build, then failed at
the "Bundle JavaScript" phase with a generic "Unknown error." Reproducing
the exact failing command locally (`npx expo export:embed --eager
--platform android --dev false`) surfaced the real error underneath:
`Cannot find module 'babel-preset-expo'`. Root cause: `babel.config.js`
has always required `babel-preset-expo` (`presets: ['babel-preset-expo']`)
but `package.json` never listed it as a dependency -- probably true since
before this session even, since Snack doesn't use the project's own
`babel.config.js`/`package.json` at all and so never exercised this path.
This is exactly the class of gap Snack testing structurally cannot catch,
no matter how carefully `App.js` itself is reviewed. Fixed by adding
`"babel-preset-expo": "~54.0.0"` to `package.json`'s `devDependencies`.
Before the retry, did a full audit of every import in `App.js` against
`package.json` (all present), `babel.config.js` (fine), and both `app.json`
and `eas.json` (valid JSON, no other issues) specifically to avoid another
wasted ~20-minute build-queue cycle on a second silly gap -- found nothing
else missing. The retry succeeded. **This fix was applied by hand directly
inside the Codespace's `package.json` and has NOT been pushed back to the
actual `xirja-app` GitHub repo yet** -- see the note near the top of this
file. A fresh clone or a fresh Codespace today would still hit this exact
same failure until that upload happens.

**Outcome, confirmed 25 Sept**: the build succeeded, produced a
downloadable `.apk`, the user downloaded and installed it directly on
their Android phone (allowing installs from outside the Play Store when
prompted, as expected), and confirmed it opened and ran without issues.
This is the actual, real completion of the "personal use" deployment goal
first discussed earlier in this file -- not just "the steps are written
down" but "the app is installed and working on the phone it was meant
for."

**On persisting Shopping mode (new, this update)**: `checkedItemIds` (which
items are ticked off) now survives closing the app mid-trip, the same way
the device id itself does — `AsyncStorage`, keyed per device
(`xirja_checked_item_ids_<deviceId>`). Restored once on app start (before
the list itself finishes loading), pruned automatically whenever an item
is removed from the list or drops out on a refresh (so a stale id doesn't
linger in storage forever, though it was harmless either way), and saved
on every real change — cheap enough (a handful of ids) not to need
debouncing. A `checkedItemsHydrated` flag guards the save effect so it
can't fire with the initial empty Set and clobber a real saved one before
the restore has actually completed — that ordering bug would have silently
undone the entire point of this change, so it's worth remembering if this
code gets touched again. Verified the same way as the navigation changes
(re-cloned the live repo and diffed — confirms only this change, nothing
else touched — plus the manual bracket-balance and styles-used-vs-defined
checks; still no real JS/JSX parser available in this sandbox), AND
confirmed working end to end by the user on Snack (25 Sept): checked items
in Shopping mode, reloaded, checkmarks were still there.

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
  exist yet. Checked-off state now survives closing/reloading the app
  mid-trip (new, 25 Sept, confirmed working by the user on Snack) —
  persisted to `AsyncStorage`, keyed per device the same way the device id
  itself is; see the "On persisting Shopping mode" note near the top of
  this file. The numbers ("X of N checked",
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
- No "Trip summary" screen yet to land on once every store's fully checked
  off in Shopping mode — the checked-off state itself now persists (see
  above), but there's nothing that celebrates/summarizes finishing the
  whole trip across every store. (Task #7 of the gap-closing list below.)
- The price-correction workflow (`user_price` table, site-vs-mine trust
  logic) — designed in the prototype and spec, not ported to real code.
  (Task #11 of the gap-closing list below.)
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

## Design-vs-implementation gap-closing (started 25 Sept)

After the personal-use deployment was confirmed done, the owner compared
the app's 6 real screens against the original design mockup screenshots
and found real gaps in every one of them. Explicit decision: work through
ALL of it, screen by screen, in this order, including the three large
features rather than deferring them:

1. **My list** — DONE (see below).
2. Browse — department category filter chips; show "from €X" per row.
3. Compare — 3-way strategy toggle ("Cheapest each" / "2 stores" / "One
   store") inside Compare itself, a new "2 stores" optimal-split
   algorithm, and an expandable item-by-item breakdown.
4. Item detail — per-store freshness timestamp, unit/source subtitle.
5. Store lists — outlet locality/address, per-store progress on the card,
   a "Trip summary" link.
6. Shopping mode — category-grouped item list, circular progress ring.
7. New "Trip summary" screen.
8. New "Settings" screen + a 4-tab bar (List, Compare, Shop, Settings)
   with Shopping mode promoted to its own tab.
9. Offline mode — cache last-successful list/categories/stores to
   AsyncStorage, show cached data with an offline badge on a failed fetch.
   Scope still to be pinned down: the design implies read-write sync
   ("corrections sync when you're back on data"), which is considerably
   more work than a read-only cache — needs a decision before starting.
10. Barcode scanning in Shopping mode — needs a camera module (e.g.
    `expo-camera`) plus a new backend barcode-lookup endpoint/schema work.
11. Price-correction workflow ("Price different? Fix it") — new
    `user_price` table, new API endpoints, site-vs-mine trust logic, plus
    the UI hook in Shopping mode.

**Task 1 — "My list" — DONE, 25 Sept**, including a follow-up round of
fixes after the owner tested the first version on a real device. Verified
both rounds by re-cloning the live repo and diffing (each diff contains
only the intended additive changes, nothing else touched), plus the manual
bracket-balance and styles-used-vs-defined checks (still no real JS/JSX
parser available in this sandbox — `npm install` for one is blocked here
by the registry returning 403; `acorn`'s CLI is present but doesn't support
JSX). First round:
- **Per-item savings**: `ListRow` shows "save €X.XX" under the price,
  computed as `(most expensive listed store's price − cheapest price) ×
  quantity`, only when an item is actually priced at more than one store.
- **"Browse" shortcut**: a small button next to the add-item input,
  navigates straight to the Browse tab (`navigation.navigate("Browse")`).
- **"Find the best prices →" bottom CTA**: a button pinned under the list
  (shown once it has at least one item) that jumps straight to Compare
  (`navigation.navigate("CompareTab")`), and includes the list's total
  potential savings figure when there is one.
- **Editable list label**: a new, purely cosmetic, LOCAL-ONLY label (e.g.
  "WEEKLY SHOP") shown under the "My list" title, tap-to-edit, persisted
  via `AsyncStorage` per device (`xirja_list_label_<deviceId>`) the same
  way Shopping mode's checked-off state is — deliberately NOT synced to
  the backend, since there's still only one unnamed list per device in the
  real data model (`app_list`/`app_list_item`), so a per-device cosmetic
  label needs no schema or API change.

**Real discrepancy #7, found by the owner testing the real installed APK
(not Snack)**: the header ("My list") rendered underneath the phone's own
status bar (clock/wifi/battery), and the bottom tab bar showed broken/blank
icon glyphs above each label. Root cause of the header bug: `SafeAreaView`
was being imported from `"react-native"` itself, not from
`"react-native-safe-area-context"`. The plain React Native `SafeAreaView`
only does anything on iOS — on Android it's a no-op plain `View` that
reserves zero space for the status bar, so nothing before this ever
actually protected the header on Android; Snack's web preview has no real
status bar to overlap, which is why this was invisible until the app was
actually installed on a phone. Fixed by importing `SafeAreaView` from
`"react-native-safe-area-context"` instead (already a dependency, already
used for `SafeAreaProvider`) — that version pads correctly on both
platforms. For the tab bar icons: `App.js` never actually defined any
`tabBarIcon` — worth remembering that leaving it unset isn't a safe
no-icon fallback across every React Navigation/Expo SDK combination, it
can render broken placeholder glyphs instead. Fixed by adding a small
`TabIcon` component built entirely from plain `View`s (a stacked-lines
icon, a magnifying glass, a bar chart) — deliberately NOT an icon font
library like `@expo/vector-icons`, since that needs to be resolved and
bundled by Metro at build time and this project has already lost real
build time twice to exactly that class of dependency-resolution problem
(the SDK 51→54 drift, the missing `babel-preset-expo`). A few `View`s have
no version to drift and nothing to fail to resolve.

**Also fixed on the same pass, all owner-requested design tweaks**: removed
"(e.g. Milk)" from the add-item placeholder (now just "Add an item…");
removed the price total from the header entirely (no more "€X.XX at
cheapest prices" line); the item count is now a bigger, bolder number on
the right-hand side of the header instead of buried in a subtitle sentence;
and the "Find the best prices" button is now a neutral dark color instead
of the app's green — a deliberate placeholder, since a full color pass
across the app is a separate, later decision once the design itself is
settled, not something to get ahead of one button at a time.

Not yet confirmed by the owner on-device after this second round — that
confirmation is the actual close-out for this task.

## How to keep this file honest

- Before believing any status claim (from a chat session, an old summary,
  anything) — check it against the actual repo/deployment, the way this
  file's contents were checked on 24 Sept 2026, not against what a
  conversation "remembers."
- Update this file at the end of any session where real progress happens,
  and commit it in the same batch as the code change it describes.
