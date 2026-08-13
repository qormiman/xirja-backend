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

## What happens next

Once a manual run succeeds, no more action is needed — the schedule in
`crawl-greens.yml` runs it automatically every night. You can check on it
any time via the Actions tab, or by re-running the `crawl_run` query above.

## If the first run fails

This is genuinely possible and not a sign of a mistake on your part — this
crawler was written without being able to test it against the real
internet. Come back with:

1. The failed run's log (Actions tab → click the failed run → click into
   the "Run the Greens crawler" step → copy the output).
2. What `SELECT * FROM crawl_run ORDER BY started_at DESC LIMIT 1;` shows.

That'll be enough to diagnose and fix it without needing anything else
from you.
