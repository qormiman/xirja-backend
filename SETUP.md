# Xirja backend — setup guide

This gets the Greens price crawler running on a schedule, storing results in
a real database, with no software installed on your own computer. Everything
happens through two websites: Neon (the database) and GitHub (where the
crawler code lives and runs).

Budget about 20–30 minutes, most of it copy-pasting and clicking, not
technical work. Every step says exactly what to click.

**Reminder of where things stand:** the crawler code was written without
being able to test it against the real internet (this working environment
can't reach outside websites). The first manual run (step 6 below) is the
real test. If it fails, that's expected-possible, not a sign you did
something wrong — see "If the first run fails" at the end.

---

## 1. Create your Neon database

1. Go to [neon.tech](https://neon.tech) and sign up (free tier is enough).
2. Create a new project. Any name is fine — e.g. "xirja".
3. Once it's created, Neon shows you a **connection string** — a long line
   starting with `postgresql://...`. Copy it somewhere safe (a notes app is
   fine for now). This is effectively the password to your database, so
   don't share it or paste it anywhere public.

## 2. Set up the database structure

Neon has a built-in SQL editor in your browser — you don't need to install
anything.

1. In your Neon project, find **"SQL Editor"** in the left sidebar and open it.
2. Open `schema.sql` (in this folder) in any text editor, select all the
   text, copy it.
3. Paste it into Neon's SQL editor and run it (there's a "Run" button).
   This creates all the tables. You should see a success message and no
   red errors.
4. Do the same with `seed.sql`: open it, copy all the text, paste into the
   SQL editor, run it. This adds the three Greens branches (Swieqi,
   Mriehel, Gozo) so the crawler has somewhere to attach prices to.

To sanity-check it worked: in the SQL editor, run `SELECT * FROM outlet;`
— you should see three rows.

## 3. Create a GitHub repository

GitHub is where the crawler's code will live, and it's also what runs the
crawler on a schedule for you (for free, on GitHub's own computers).

1. Go to [github.com](https://github.com) and sign up if you don't already
   have an account.
2. Click the **+** in the top right → **New repository**.
3. Name it something like `xirja-backend`. It can be **private** — nobody
   else needs to see it.
4. Click **Create repository**.

## 4. Upload these files

On the new repository's page, there's an "uploading an existing file" link
(or **Add file → Upload files**).

Upload the whole `xirja-backend` folder's contents, **keeping the folder
structure**:

```
xirja-backend/
├── .github/
│   └── workflows/
│       └── crawl-greens.yml
├── greens_crawler.py
├── requirements.txt
├── schema.sql
├── seed.sql
└── SETUP.md
```

GitHub's upload page lets you drag a whole folder in and it preserves the
structure — the `.github/workflows/crawl-greens.yml` path matters, since
that's specifically where GitHub looks for scheduled-run instructions.

Commit the upload (there's a green "Commit changes" button, default
settings are fine).

## 5. Add your database connection as a secret

This is what lets the crawler talk to your database, without the
connection string ever appearing in the code itself (so it stays private
even though the repository could later be made public).

1. In your repository, go to **Settings** (top tab) → **Secrets and
   variables** → **Actions** (left sidebar).
2. Click **New repository secret**.
3. Name: `DATABASE_URL` (exactly this, capital letters matter).
4. Value: paste the Neon connection string from step 1.
5. Click **Add secret**.

## 6. Run it once, manually, to test

1. Go to the **Actions** tab in your repository.
2. You should see "Crawl Greens prices" listed on the left. Click it.
3. Click **Run workflow** (a button on the right) → **Run workflow** again
   to confirm.
4. It'll show as a yellow dot (running), then either a green tick
   (succeeded) or a red cross (failed) after a while — this run installs a
   small invisible browser (a one-time-per-run download, adds a minute or
   so), then goes through every product category at all three Greens
   branches with a polite 5-second pause between requests. Real-world
   testing showed Greens can respond slowly, so budget more like an hour
   or two for all three branches together, not the 20–30 minutes originally
   guessed. That's expected — no need to keep watching it; a red cross
   here doesn't necessarily mean total failure (see step 7 below, "partial"
   results are a real, useful outcome, not just success/failure).

## 7. Check it actually worked

Back in Neon's SQL editor:

```sql
SELECT * FROM crawl_run ORDER BY started_at DESC LIMIT 5;
```

You want to see rows with `status = 'success'` and an `item_count` that's a
real number (hundreds or thousands, not 0 or 1).

You might instead see `status = 'partial'` — that means the crawl mostly
worked but a handful of specific pages failed even after being retried once.
That's a real, useful outcome, not a broken run: `item_count` will still
reflect everything that *did* come through, and the `error_message` column
spells out exactly which category/page(s) didn't make it, e.g.
`"3 page(s) failed even after retry: Bakery/Bread p2; ..."`. GitHub Actions
will still show this run with a red cross (since something's worth a look),
but don't read that cross as "nothing worked" — check `item_count` and
`error_message` before assuming the worst.

```sql
SELECT chain_product_name, price
FROM listing
JOIN price_observation ON price_observation.listing_id = listing.id
LIMIT 20;
```

You want to see real product names and prices that look right (not all
€0.00).

**If `item_count` is 0 or very low, or the run fails outright**, come back
and tell me — paste the failed run's log (Actions tab → the failed run →
click into it → copy the text). The crawler now depends on Greens' site
behaving the same way it did when we last checked it by hand (in DevTools);
if they change something about how their access token works, this is where
it would show up.

## Greens crawl timing out (fixed) and what it means for GitHub Actions minutes

A real run once got killed by GitHub's hard 6-hour-per-job ceiling before
finishing (Actions shows this as "The job has exceeded the maximum execution
time of 6h0m0s"). That wasn't a bug -- Greens' catalogue is genuinely big
(Swieqi's "Groceries" category alone has 5,000+ products), the crawler
respects a 5-second-per-page delay because that's what greens.com.mt's own
robots.txt asks for, and all of that added up to more real time than fits in
one 6-hour job when all three branches run one after another.

The fix: `crawl-greens.yml` now runs each branch (Swieqi, Mriehel, Gozo) as
its own separate job, all three starting at the same time instead of one
after another. Each branch comfortably finishes on its own well within 6
hours, so nothing gets cut off, and the Actions tab now shows one green
tick/red cross per branch instead of one for the whole crawl -- so a problem
with just one branch doesn't hide inside an otherwise-fine run anymore. This
applies automatically, both to the nightly schedule and to a normal manual
"Run workflow" click with both boxes left blank.

**Important: this does NOT reduce the total GitHub Actions minutes used.**
Three roughly-2-hour jobs running at once still add up to roughly the same
combined ~6 hours of billed time as one long sequential job did -- it just
means that time is spent finishing the crawl instead of being spent on a
run that gets killed partway through. If a crawl at this scale, every
night, is using up your free monthly Actions minutes (private repositories
get 2,000 free minutes/month; public repositories get unlimited free
minutes), that's a separate decision from this timeout fix, with a few
honest options:

- **Crawl less often than nightly** -- edit the `cron:` line near the top of
  `crawl-greens.yml` (e.g. every 2-3 days, or weekly). Supermarket prices
  don't usually change several times a day, so nightly freshness may be more
  than you actually need, and this cuts total minutes used proportionally.
- **Make the repository public** -- GitHub Actions becomes completely free
  and unlimited. Your database connection stays secret either way (it's
  stored as an encrypted GitHub secret, never in the code), but your
  crawler code and project structure become visible to anyone.
- **Add a payment method** in GitHub's Billing settings and pay for the
  minutes beyond the free quota -- a real recurring cost (roughly $0.006 per
  minute for a standard runner at the time this was written -- check
  GitHub's own current pricing before relying on that number).

This isn't something to decide inside this file -- it's worth deciding
deliberately, based on how you actually want to run this project long-term.

## Patching a single category or branch, without a full crawl again

If everything works except one specific category (for example, because we
find out its category code was guessed wrong) or one specific branch (for
example, Mriehel's location code), you don't need to sit through another
multi-hour full crawl just to fix that one spot. The crawler supports a
"restricted run" that only touches the category and/or branch you name:

1. Go to the **Actions** tab → **Crawl Greens prices** → **Run workflow**
   (same button as step 6 above).
2. Two text boxes appear:
   - **"only_categories"** — the category name(s) to fix, comma-separated if
     more than one, e.g. `FruitsAndVegetables`. Has to match the internal
     name used inside `greens_crawler.py`'s `CATEGORIES` list.
   - **"only_outlets"** — the branch(es) to fix, comma-separated if more
     than one, e.g. `mriehel` or `swieqi,gozo`. Accepts either the short
     branch name or the full outlet id (`greens_mriehel`).
   Fill in either one on its own, or both together (e.g. `only_outlets:
   mriehel` + `only_categories: FruitsAndVegetables` crawls just Mriehel's
   Fruit & Veg, skipping everything else entirely). Leave both blank for a
   normal, full run.
3. Click **Run workflow** to confirm.

A category restriction on its own still crawls that category for all three
branches, just skipping every other category — a branch restriction on its
own still crawls every category, just skipping the other branches. Either
way it finishes in a few minutes instead of an hour or two. It's safe to run
any time — it only touches that category's and/or branch's own data, and
updates/adds to it the same way a normal crawl would (nothing about the rest
is affected, and nothing is duplicated if you run it more than once).

One thing to expect: the `crawl_run` rows from a restricted run will show a
much lower `item_count` than a full run (since it covers less ground) — and
if you restricted by outlet, you'll simply see fewer `crawl_run` rows appear
for that run (one per outlet actually crawled) rather than the usual three.
That's normal, not a sign something's wrong. A category restriction is also
spelled out directly in the `error_message` column as `[RESTRICTED RUN --
only categories: ...]`, so it's always clear, looking back later, that a
particular run was a deliberate patch and not a broken full crawl.

Leaving both boxes blank (or just clicking the button on the Actions page
directly without opening the inputs first) runs a normal, full crawl covering
every branch and category — as three separate jobs running at the same time
(see "Greens crawl timing out" above), not one combined job, but the result
is the same full coverage either way. The automatic nightly run always does
this full run too.

## Adding the PAVI PAMA crawler

This is a second, separate crawler for a second chain — it runs on its own
schedule, independently of Greens, and adds to the same database. It's
simpler than the Greens one: no login, no headless browser step, one shared
price list instead of per-branch ones.

1. Upload two new files to the same GitHub repository, keeping them in the
   same folder structure as before:
   - `pavipama_crawler.py` (goes at the top level, next to
     `greens_crawler.py`)
   - `.github/workflows/crawl-pavipama.yml` (goes inside the existing
     `.github/workflows/` folder, alongside `crawl-greens.yml`)
2. In Neon's SQL editor, run just this (not the whole `seed.sql` file again
   — that would fail on the Greens rows already being there):
   ```sql
   INSERT INTO store (id, name, brand, short_code, color) VALUES
       ('pavipama', 'PAVI PAMA', 'PAVI PAMA', 'PP', 'oklch(0.58 0.15 40)');

   INSERT INTO outlet (id, store_id, name, locality, source_code) VALUES
       ('pavipama', 'pavipama', 'PAVI PAMA', NULL, 'PP');
   ```
   (This is already in the updated `seed.sql` file too, for the record —
   this step is just so you don't have to re-upload and re-run the whole
   file.)
3. Go to the **Actions** tab → **Crawl PAVI PAMA prices** → **Run workflow**
   → **Run workflow** again to confirm, same as the first Greens test run.
   No `only_categories` box needed this time — leave it blank for a normal
   full run.
4. It should finish much faster than Greens (no browser step, and only one
   outlet instead of three) — check `crawl_run` the same way as before:
   ```sql
   SELECT * FROM crawl_run WHERE store_id = 'pavipama' ORDER BY started_at DESC LIMIT 5;
   ```

## Adding the Welbee's crawler

This is a third, separate crawler for a third chain — it runs on its own
schedule, independently of Greens and PAVI PAMA, and adds to the same
database. Like PAVI PAMA, it's simpler than Greens: no login, no headless
browser step, one shared price list instead of per-branch ones.

1. Upload two new files to the same GitHub repository, keeping them in the
   same folder structure as before:
   - `welbees_crawler.py` (goes at the top level, next to
     `greens_crawler.py` and `pavipama_crawler.py`)
   - `.github/workflows/crawl-welbees.yml` (goes inside the existing
     `.github/workflows/` folder, alongside the other two)
2. In Neon's SQL editor, run just this (not the whole `seed.sql` file again
   — that would fail on the Greens and PAVI PAMA rows already being there):
   ```sql
   INSERT INTO store (id, name, brand, short_code, color) VALUES
       ('welbees', 'Welbee''s Supermarket', 'Welbee''s', 'WB', 'oklch(0.52 0.10 300)');

   INSERT INTO outlet (id, store_id, name, locality, source_code) VALUES
       ('welbees', 'welbees', 'Welbee''s', NULL, 'WB');
   ```
   (This is already in the updated `seed.sql` file too, for the record —
   this step is just so you don't have to re-upload and re-run the whole
   file.)
3. Go to the **Actions** tab → **Crawl Welbee's prices** → **Run workflow**
   → **Run workflow** again to confirm, same as the first Greens and PAVI
   PAMA test runs. No `only_categories` box needed this time — leave it
   blank for a normal full run.
4. Check `crawl_run` the same way as before:
   ```sql
   SELECT * FROM crawl_run WHERE store_id = 'welbees' ORDER BY started_at DESC LIMIT 5;
   ```
   One thing worth knowing going in: Welbee's biggest category confirmed so
   far (Drinks) has 31 pages, and there are 17 categories in total, so this
   will likely take longer than PAVI PAMA but probably still well under
   Greens' multi-hour run (no login/browser step, and only one outlet).

## Matching products across chains

**Note (added after this section was first written):** this step is no
longer required for the shopping-list feature as it's actually planned --
see "Category normalization" below, which is the simpler thing that feature
actually needs. This matching step is still here, still works, and is still
worth running if you want it, because it answers a genuinely different
question ("are these two listings literally the same physical product?")
that a future feature — e.g. tracking one specific product's price history
across stores — would need. But if your only goal right now is "let someone
search 'milk' and see the cheapest across all three shops," skip straight to
Category normalization; you don't need this section at all for that.

Once all three crawlers have real data in them, this step connects the same
product across chains (and across a chain's own branches) so the app can
eventually show "this costs X at Greens, Y at PAVI PAMA, Z at Welbee's" for
one product. Unlike the crawlers, this doesn't run on a schedule yet — it's
meant to be triggered by hand, whenever you want to run it, since it only
makes sense to run once there's real crawled data to match against.

1. Upload two new files, same as before:
   - `product_matcher.py` (top level, next to the three crawlers)
   - `.github/workflows/match-products.yml` (inside `.github/workflows/`)
2. Go to the **Actions** tab → **Match products across chains** → **Run
   workflow** → **Run workflow** again to confirm. No inputs to fill in.
3. It should finish quickly — it only talks to your database, not to any of
   the three sites, and the amount of data involved (thousands of products,
   not millions) is well within what a straightforward comparison can chew
   through in well under a minute.
4. Check what it did:
   ```sql
   SELECT match_confidence, count(*) FROM product GROUP BY match_confidence;
   ```
   `high` rows are auto-linked and ready to use. `medium` rows are linked
   too, but worth a look — see "Reviewing medium-confidence matches" below.
   Nothing shows up for listings it couldn't confidently match at all —
   those just stay as they were, and get reconsidered automatically next
   time you run this (e.g. after another crawl adds more data to compare
   against).

It's safe to run as often as you like — it only ever looks at products that
aren't matched yet, so running it again (after another night's crawl, say)
just adds to what's already there rather than redoing or undoing anything,
including anything you've manually confirmed.

### Reviewing medium-confidence matches in bulk

If you only have a handful of medium matches to check, the one-off SQL
method at the bottom of this section is quickest. If you have a lot (a
few hundred or more), use the spreadsheet workflow instead -- it lets you
review all of them in Excel or Google Sheets, and applies your decisions
back to the database in one go.

1. Upload three new files, same as before:
   - `export_medium_matches.py` and `apply_reviewed_matches.py` (top level,
     next to `product_matcher.py`)
   - `.github/workflows/export-review.yml` and
     `.github/workflows/apply-review.yml` (inside `.github/workflows/`)
2. Go to **Actions** → **Export medium matches for review** → **Run
   workflow** → **Run workflow** again to confirm. It only reads from the
   database, so it's always safe to run.
3. When it finishes, open that run's page and scroll to the bottom to
   **Artifacts**. Click **review-spreadsheet** to download a zip file;
   unzip it to get `review_medium_matches.xlsx`.
4. Open the file. The **Instructions** tab explains what to do; the
   **Review** tab has one row per medium-confidence product, with the
   chains' listing names side by side and a **decision** column with a
   dropdown. For each row, type or pick:
   - `keep` if it's genuinely the same product across chains
   - `reject` if it isn't
   - leave it blank if you're unsure or don't get to it -- nothing happens
     to a blank row, and you can review it another time
5. Save the file. Go back to your GitHub repo, **Add file** → **Upload
   files**, and upload it with the *exact same filename*
   (`review_medium_matches.xlsx`) to the repo root, replacing the copy
   that's there (there isn't one yet the first time -- just upload it).
6. Go to **Actions** → **Apply reviewed matches** → **Run workflow** → **Run
   workflow** again to confirm. It reads the file you just uploaded and:
   - `keep` rows become `match_confidence = 'manual'` (confirmed, never
     touched again by the matcher)
   - `reject` rows get unlinked and deleted, so those listings go back to
     unmatched and get reconsidered next time you run `product_matcher.py`
   - blank rows are left exactly as they were
7. Check the run's log for a one-line summary of how many were confirmed
   and how many were rejected.

You don't have to review everything in one sitting -- leave the rows you
haven't gotten to blank, run "Apply reviewed matches" whenever you like,
and run "Export medium matches for review" again later to get a fresh
spreadsheet (it'll no longer include anything you've already confirmed or
rejected, since those are no longer `medium`).

### Reviewing a handful of matches directly in SQL

For just a few matches, this is quicker than the spreadsheet round-trip.
This shows every "medium" product side by side with the real listing names
that got linked to it, so you can eyeball whether it's actually right:

```sql
SELECT product.id, product.canonical_name, product.size_value, product.size_unit,
       store.brand, listing.chain_product_name
FROM product
JOIN listing ON listing.product_id = product.id
JOIN outlet ON outlet.id = listing.outlet_id
JOIN store ON store.id = outlet.store_id
WHERE product.match_confidence = 'medium'
ORDER BY product.id;
```

If a match looks right, confirm it so it's never reconsidered or touched again:

```sql
UPDATE product SET match_confidence = 'manual' WHERE id = '<product id from above>';
```

If a match looks wrong, undo it -- this unlinks its listings (they'll be
picked up fresh, and can match differently, next time you run the matcher)
and removes the incorrect product row:

```sql
UPDATE listing SET product_id = NULL WHERE product_id = '<product id from above>';
DELETE FROM product WHERE id = '<product id from above>';
```

## Category normalization

This is what actually powers the shopping-list feature as planned: someone
searches "milk" (or "almond milk", or "shampoo") and the app finds every
matching listing across all three chains, without needing to know that two
listings are the exact same physical product (that's the harder, separate
question "Matching products across chains" above answers instead).

Each chain describes its own products in its own words. Greens might file
something under `Chilled And Dairy / Milk And Eggs`, PAVI PAMA under `MILK`,
and Welbee's doesn't have a useful category for it at all -- just one broad
`Groceries` bucket covering hundreds of unrelated things. This step gives
every listing OUR OWN shared category (`Milk`, `Beef`, `Shampoos`, and so
on -- about 200 in total) so "find all the milk" becomes one simple database
query instead of something that has to understand three different chains'
filing systems.

**How it decides a listing's category**, in order:

1. **PAVI PAMA**: its own category is already close to the right
   granularity, so it's basically just relabelled (e.g. `MILK` → `Milk`).
2. **Greens**: its own categories have a two-level structure (e.g.
   `Butcher / Beef`) and that pair is looked up directly.
3. **Everything else**: classified by looking for keywords in the product's
   own name instead (e.g. a name containing "shampoo" → `Shampoos`). This
   covers all of Welbee's (its own categories are too broad to use
   directly), plus a couple of Greens' own categories that mix too many
   different kinds of product together to assign one category to
   (`Personal Care / Personal Hygiene And Care` and `Household / Household
   Care And Essentials`, each several thousand very different products
   filed under one heading).

**Worth knowing before trusting it blindly:** this is a first-draft
taxonomy, built from your real category data but not yet checked against
real classified output at scale. All the mapping rules and their reasoning
live in `category_taxonomy.py`, with the imperfect-fit approximations
called out inline (e.g. Greens doesn't split wine by colour at the level
this maps from, so all of it currently lands on `Wine - Red`). The keyword
matching step only knows what to look for, tested against about two dozen
realistic examples (see `test_category_taxonomy.py` in this same
conversation) but not against your actual thousands of real listings yet --
`categorize_listings.py` prints a tally of the most common
(store, category) combinations it couldn't classify at the end of every
run, specifically so gaps like this stay visible instead of silently
guessed at. Treat the first real run's tally as the starting point for
tuning `KEYWORD_RULES`, the same way the crawlers' own per-unit fallback
logging worked earlier in this project.

### One-time setup

Before the first run, add the new column this needs. Run this once in
Neon's SQL editor against your existing database (it's also included
permanently in `schema.sql` now, for anyone setting up a brand new database
from scratch from now on):

```sql
ALTER TABLE listing ADD COLUMN shopping_category TEXT;
CREATE INDEX idx_listing_shopping_category ON listing (shopping_category);
```

### Running it

1. Upload two new files, same as before:
   - `category_taxonomy.py` and `categorize_listings.py` (top level, next to
     `product_matcher.py`)
   - `.github/workflows/categorize-listings.yml` (inside
     `.github/workflows/`)
2. Go to **Actions** → **Categorize listings** → **Run workflow** → **Run
   workflow** again to confirm. No inputs to fill in.
3. It should finish quickly for the same reason `product_matcher.py` does --
   it only talks to your database.
4. Check what it did:
   ```sql
   SELECT shopping_category, count(*) FROM listing GROUP BY shopping_category ORDER BY count(*) DESC;
   ```
   A `NULL` row in that result is everything still unclassified -- cross-
   reference it against the run's own log output (the tally described
   above) to see exactly which (store, chain category) combinations make up
   that number.

Safe to run as often as you like -- unlike the crawlers and the matcher, it
doesn't even need new data to be useful: improving `KEYWORD_RULES` in
`category_taxonomy.py` and running this again re-checks every listing
against the improved rules, not just new ones, though it only ever writes
the rows whose category actually changed.

### Spot-checking and improving it

Once you've run it once, the most useful thing to do is look at a sample of
real results and see if they look right:

```sql
SELECT store.brand, listing.chain_product_name, listing.chain_category, listing.shopping_category
FROM listing
JOIN outlet ON outlet.id = listing.outlet_id
JOIN store ON store.id = outlet.store_id
ORDER BY random()
LIMIT 50;
```

If you spot a wrong or missing category, the fix always happens in
`category_taxonomy.py`, never by hand-editing the database: add or adjust an
entry in `PAVI_CATEGORY_MAP` / `GREENS_CATEGORY_MAP` / `GREENS_SUBCATEGORY_MAP`
/ `KEYWORD_RULES` as appropriate (`GREENS_SUBCATEGORY_MAP` is for Greens'
"everything mixed together" buckets specifically -- see the comment above it
in the file), upload the updated file, and re-run "Categorize listings" --
it'll pick up the fix for every affected listing automatically, not just
one.

## Running the API server

This is the new piece the app itself talks to -- a small web server that
sits between the phone app and your database (the app is never allowed to
hold your database password directly, since anyone could read it back out
of the installed app). It has one real endpoint so far:
`/categories/<name>/prices`, which returns the cheapest current price for
that shared category at each store.

Upload two new files, same as before:
- `api/main.py` and `api/requirements.txt` -- these go in a **new folder**
  called `api`, so the structure looks like:
  ```
  xirja-backend/
  ├── api/
  │   ├── main.py
  │   └── requirements.txt
  ├── .github/
  ├── greens_crawler.py
  ├── ...
  ```

Unlike the crawlers, this isn't something GitHub Actions runs on a
schedule -- an API needs to be running *all the time*, ready to answer
whenever the app asks, not just once a night. That means it needs an
always-on home, which GitHub Actions isn't built for. There are two ways
to run it:

### Running the API locally, for quick testing

This is the fastest way to see it working, before bothering with a real
deployment. It runs on your own computer, and your phone (running the app
via Expo Go) can reach it as long as they're both on the same WiFi.

1. Install Node.js if you haven't already (see `xirja-app/SETUP.md`) --
   not needed for the API itself, just mentioned here in case you're doing
   this step before that one.
2. Open a terminal in the `api` folder and run:
   ```
   pip install -r requirements.txt
   ```
3. Set your database connection (same value as the `DATABASE_URL` secret
   in GitHub -- your Neon connection string from step 1 way above):
   - Mac/Linux: `export DATABASE_URL="postgresql://...your Neon string..."`
   - Windows (PowerShell): `$env:DATABASE_URL="postgresql://...your Neon string..."`
4. Start the server:
   ```
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```
5. Open `http://127.0.0.1:8000/docs` in a browser on your computer --
   FastAPI builds this page automatically. Try the
   `/categories/{category}/prices` endpoint right there (click it, "Try it
   out", type `Milk`, "Execute") before ever involving the app -- if you
   get real prices back here, the database side is definitely working.
6. Leave this running, and point the app at your computer's network
   address (see `xirja-app/SETUP.md` step 4) to test the real screen.

### Running the API online (Render)

This gives the API a permanent web address that works from anywhere, not
just your own WiFi -- needed once you're not sitting next to the computer
running it, and definitely needed before anyone else ever uses the app.

1. Go to [render.com](https://render.com) and sign up (a free tier is
   enough for now).
2. Click **New** → **Web Service**.
3. Connect your GitHub account if asked, then pick the `xirja-backend`
   repository.
4. Fill in:
   - **Root Directory**: `api` (this tells Render your project lives in
     the `api` subfolder, not the repo root -- important, since the repo
     root has the crawlers' own `requirements.txt`, a different set of
     packages entirely).
   - **Runtime**: Python 3.
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: the free tier is fine to start.
5. Under **Environment Variables**, add one:
   - Key: `DATABASE_URL`
   - Value: your Neon connection string (same one as the GitHub secret).
6. Click **Create Web Service**. Render builds and starts it -- takes a
   couple of minutes the first time.
7. Once it says "Live", Render shows you the app's address, something like
   `https://xirja-api.onrender.com`. Test it by opening
   `https://xirja-api.onrender.com/health` in a browser -- you should see
   `{"status":"ok"}`. Then try
   `https://xirja-api.onrender.com/categories/Milk/prices` for real data.

**One honest thing to know about Render's free tier**: a free web service
"spins down" after 15 minutes of no traffic, and the next request after
that takes 30-60 seconds to wake it back up (everything after that is
fast again). That's fine for testing, but worth knowing about so a slow
first load doesn't look like a bug. Paid tiers remove this if it ever
matters for real use.

## Ideas for later (not started -- revisit when designing the app)

- **Substitute products.** Right now, rejecting a proposed match (see
  "Reviewing medium-confidence matches" above) just makes the two listings
  fully unrelated -- there's no record that they were ever considered
  similar. But a rejected medium-confidence match is a natural candidate
  for a *different* kind of relationship: not "the same product," but "a
  reasonable substitute if the one you want isn't available at this store"
  (e.g. two different brands/flavours of the same kind of item, each only
  sold at one chain). Nothing captures this today -- when the app itself
  gets designed, it's worth deciding whether/how to track and surface
  substitutes, possibly reusing the same review data this section already
  generates.

## What happens next

Once a manual run succeeds, no more action is needed — the schedules in
`crawl-greens.yml`, `crawl-pavipama.yml`, and `crawl-welbees.yml` run
automatically every night. You can check on any of them any time via the
Actions tab, or by re-running the `crawl_run` query above (filtering by
`store_id` if you only want one chain's results). The product matcher
(above) is the one piece that's still manual-only for now -- run it
whenever you want fresh matches picked up.

## If the first run fails

This is genuinely possible and not a sign of a mistake on your part — this
crawler was written without being able to test it against the real
internet. Come back with:

1. The failed run's log (Actions tab → click the failed run → click into
   the "Run the Greens crawler" step → copy the output).
2. What `SELECT * FROM crawl_run ORDER BY started_at DESC LIMIT 1;` shows.

That'll be enough to diagnose and fix it without needing anything else
from you.
