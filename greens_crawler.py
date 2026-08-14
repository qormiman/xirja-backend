"""
Xirja crawler -- Greens Supermarket.

What this does, in plain terms:
  For every outlet we support (Swieqi, Mriehel, Gozo) and every product
  category on greens.com.mt, this asks Greens' own product-list address for
  that category's products, and saves what it gets back into our database:
  one row per product per outlet ("listing"), and one dated price row per
  product per crawl ("price_observation" -- never overwritten, so we can see
  price history and notice if a crawl silently stops finding real prices).

  It's read-only. It never logs in, never adds anything to a cart, and never
  changes anything on greens.com.mt -- it only asks for public product pages,
  the same way your browser does when you look at the site.

How this evolved (worth knowing if something breaks later):
  Version 1 just asked Greens' product-list address directly, the way you'd
  fetch any ordinary web page. Testing showed that doesn't work on its own --
  Greens' site quietly attaches two extra things to every request its own
  page makes: a "Cart" value (any placeholder works) and an "Authorization"
  token the page's own JavaScript computes fresh each time it loads (not a
  login, just a "this came from a real browser" check).

  Version 2 fixed that by briefly opening a real, invisible (headless)
  browser (via a tool called Playwright) once per outlet, to load one Greens
  page the way you did by hand, and reading off the token it generates --
  then reusing that token for the rest of the outlet's crawl via plain,
  lightweight requests.

  Version 2 then ran into a second problem: individual requests would
  sometimes stall for many minutes without ever actually erroring out.
  Python's usual request timeout only counts *gaps* between bits of data
  arriving -- a server that trickles a response just fast enough to avoid
  ever going fully quiet can dodge that timeout indefinitely, even though
  the overall wait is far too long to be reasonable.

  Version 3 (this one) fixes that, and changes the overall strategy on a
  request that a non-developer flagged as important: don't let one stuck
  request block everything, but also don't let the fix silently drop real
  products. So now:
    - Every single request runs on a genuine, independent 45-second
      stopwatch (using a background thread) -- if nothing comes back in
      that time, we give up on THAT SPECIFIC request, no matter how the
      network is behaving.
    - The crawler does one full pass through every category first. Anything
      that fails along the way is written down and skipped over immediately
      -- so the rest of the catalogue keeps moving instead of getting stuck
      behind one bad request.
    - Only after that entire first pass finishes does it go back and retry,
      once, every single thing that failed -- picking up a category exactly
      where it left off if the retry succeeds.
    - Anything that still fails even after that retry is recorded plainly in
      the crawl_run row as a "partial" result (a new status, alongside
      "success" and "failed"), listing exactly which category/page didn't
      make it -- never silently treated as a complete success.
    - There's also a generous per-category safety cap (300 pages, i.e. over
      14,000 products) that exists purely as a backstop against a genuine
      bug (like a pagination loop that never realises it's done), sized with
      real headroom above the biggest real category we've actually seen
      (Groceries at Swieqi, 5,000+ products). If it's ever hit, it's logged
      loudly and marked "partial", not hidden.

  Version 3 also turned up a second, unrelated gap once tested: the
  browser-launch step that fetches the access token had NO ceiling of its
  own (only the page-load part inside it did) -- so if opening the browser
  itself ever stalled, nothing would stop it. That's now covered by the
  same kind of independent stopwatch (90 seconds, since a real browser
  legitimately takes longer than a plain request). Separately, the run
  also appeared to "freeze" in the GitHub Actions log for long stretches
  even when it might have still been working -- that turned out to be
  Python quietly holding print() output in memory rather than showing it
  immediately, which happens by default whenever output isn't going
  straight to a screen (exactly GitHub Actions' situation). The workflow
  now explicitly disables that buffering, so the log can be trusted to
  show what's actually happening as it happens.

  Version 4 added an optional "only run these categories" filter (see
  ONLY_CATEGORIES below), so a single wrong/missing category can be patched
  by itself once its correct codes are confirmed, instead of needing a full
  multi-hour crawl again just to fix one spot.

  Version 5 fixed the CATEGORIES list itself. It used to be a long, hand-
  guessed list of (top-level category, subcategory) pairs, scraped from the
  site's navigation menu before any real request had been confirmed. A real
  request captured straight out of Chrome (a "cURL" copy, not a guess)
  proved that leaving the subcategory blank and only specifying the
  top-level category returns EVERYTHING in that category in one go, exactly
  matching the site's own category page. So the list is now just the
  top-level category codes, each fetched with no subcategory filter --
  removing the entire class of "guessed a subcategory spelling wrong, lost
  those products silently" bugs. The same captured request also fixed the
  Referer header to match the real one exactly.

  Version 6 fixed a real instance of exactly that same "guessed and lost
  data silently" problem, just for a branch instead of a category: Mriehel's
  location code was guessed as "MR" (following the same first-two-letters
  pattern as Swieqi's "SM" and Gozo's "GZ"), and a real run against it came
  back with a valid access token but a clean zero products in every single
  category -- Greens' site doesn't error on an unrecognised location, it
  just quietly returns nothing, so this had been silently producing zero
  data for Mriehel. Confirmed via a live DevTools capture (Network tab,
  "Loc" query parameter) with the site's own store switcher actually set to
  Mriehel: the real code is "MH". Swieqi and Gozo's codes are both
  independently confirmed correct by real product data already having come
  back for both. Two other changes came out of specifically auditing for
  more of this same failure mode: the per-kg/per-litre price calculation
  now logs a note whenever it sees a SIZE_UOM value it doesn't recognise,
  instead of silently skipping it (a real, partial version of the same bug
  was found this way -- about 40% of Greens' weighted fruit & veg items
  were missing a per-unit price with nothing in the log to show it); and an
  optional "only run these outlets" filter was added (see ONLY_OUTLETS
  below), so a single wrong/missing branch code can be patched by itself,
  the same way ONLY_CATEGORIES already let you patch a single category.

Before you rely on this:
  This version has still not been tested end-to-end from inside the
  environment that wrote it (no general internet access there) -- but every
  piece of it (the Cart value, the Authorization token, the request headers,
  and the timeout behaviour) was built from what actually happened during
  your real test runs, not guessed. Run it and check the crawl_run table
  afterwards, same as before -- and this time, also check for any rows with
  status = 'partial', which mean "mostly worked, but here's exactly what
  didn't" rather than a clean pass.

How to run it:
  See SETUP.md. In short: set the DATABASE_URL environment variable to your
  Neon connection string, then run `python greens_crawler.py`. GitHub
  Actions (see .github/workflows/crawl-greens.yml) also installs a headless
  Chromium browser before running this, which the token step needs.
"""

import os
import sys
import time
import json
import threading
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

STORE_ID = "greens"
BASE_URL = "https://www.greens.com.mt/apiservices/retail/sync/productlist"
CATEGORY_PAGE_URL = "https://www.greens.com.mt/products"

# A normal-looking browser identity, with an honest, contactable extra bit
# tacked on -- per the README's legal-footing guidance, Greens' server logs
# should be able to tell this apart from an ordinary shopper if they look.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 "
    "XirjaCrawler/0.3 (+contact: ranier.chircop@gmail.com; polite, low-volume, once-daily crawl)"
)

# Robots.txt for greens.com.mt specifies a 5-second crawl delay. We sleep at
# least that long between every product-list request, no exceptions. (The
# one-off browser page load used to fetch a token is a single page visit,
# same as a shopper opening the site -- not part of this budget.)
REQUEST_DELAY_SECONDS = 5

# The hard, independent ceiling on any single request, described above.
# Chosen generously above what a normal response should ever take, so it
# only ever fires on a genuinely stuck request.
REQUEST_HARD_TIMEOUT_SECONDS = 45

# Purely a backstop against a pagination bug, not a guess at how big a real
# category can get -- this was originally set to 50 (2,400 products) assuming
# no single category would come close. That assumption turned out to be
# wrong: a real run confirmed "Groceries" at Swieqi alone has 5,000+ products,
# which needs 105+ pages at 48 per page. Raised generously above that with
# real headroom to grow, while still catching a genuine pagination bug (which
# would loop essentially forever, not just run a bit long).
MAX_PAGES_PER_CATEGORY = 300

# Each outlet's id here MUST match the outlet.id rows inserted by seed.sql.
#
# Mriehel's code was originally guessed as "MR" (matching the initial-letter
# pattern of Swieqi's "SM" and Gozo's "GZ") and that guess turned out to be
# wrong -- a real run against it came back with a valid token but a clean
# zero products in every single category, which is what a real site does
# with an unrecognised location rather than an error. Confirmed via a real
# DevTools capture (Network tab, "Loc" query parameter) with the store
# switcher actually set to Mriehel on the live site: the real code is "MH".
# Swieqi and Gozo's codes are both independently confirmed correct (real
# products came back for both), so this was a Mriehel-only mistake, not a
# sign the others need rechecking too.
OUTLETS = [
    {"outlet_id": "greens_swieqi", "source_code": "SM"},
    {"outlet_id": "greens_mriehel", "source_code": "MH"},
    {"outlet_id": "greens_gozo", "source_code": "GZ"},
]

# Optional: restrict a run to just one or a few outlets/branches, instead of
# all three -- e.g. to re-crawl just Mriehel after fixing its location code,
# without sitting through a multi-hour Swieqi + Gozo crawl that doesn't need
# repeating. Set via the "only_outlets" box when manually running the GitHub
# Actions workflow (see .github/workflows/crawl-greens.yml) -- comma-
# separated, case-insensitive. Accepts either the full outlet id
# ("greens_mriehel") or just the short form after the "greens_" ("mriehel"),
# whichever's easier to type. Leave it blank (the normal case, and always
# the case for the automatic nightly run) and every outlet above runs, same
# as before this existed.
ONLY_OUTLETS_RAW = os.environ.get("ONLY_OUTLETS", "").strip()
if ONLY_OUTLETS_RAW:
    _wanted_outlets = {o.strip().lower() for o in ONLY_OUTLETS_RAW.split(",") if o.strip()}

    def _outlet_matches(outlet):
        full_id = outlet["outlet_id"].lower()
        short_id = full_id.split("_", 1)[1] if "_" in full_id else full_id
        return full_id in _wanted_outlets or short_id in _wanted_outlets

    ACTIVE_OUTLETS = [o for o in OUTLETS if _outlet_matches(o)]
    if not ACTIVE_OUTLETS:
        print(f"WARNING: ONLY_OUTLETS={ONLY_OUTLETS_RAW!r} didn't match any outlet above -- "
              f"check spelling (e.g. \"greens_mriehel\" or just \"mriehel\"). Running EVERY "
              f"outlet instead, same as a normal full run.", file=sys.stderr)
        ACTIVE_OUTLETS = OUTLETS
else:
    ACTIVE_OUTLETS = OUTLETS

# Confirmed via testing: the site's product-list address needs *a* Cart
# value to be present to be recognised as a valid request at all, but it
# doesn't need to be a real one.
CART_PLACEHOLDER = "00000000-0000-0000-0000-000000000000"

# Version 5 change (worth knowing if you're reading this later): this used
# to be a much longer list of (top-level category, guessed subcategory)
# pairs, scraped by hand from the site's navigation menu before we had a
# real, working API request to check it against. A real captured request
# (a "cURL" a non-developer copied out of Chrome's DevTools) proved that
# guess was subtly wrong -- and also proved something more useful: asking
# for a top-level category with NO subcategory filter (Type left blank)
# returns EVERY product in that category in one go, paginated, the exact
# same way the site's own category landing page works. That's a direct
# copy of a real, confirmed-working request -- not a guess -- and it
# sidesteps the whole problem of guessing subcategory spellings, since we
# don't need them at all.
#
# So this list is now just the top-level category codes (still originally
# sourced from the site's navigation menu, so still worth re-checking
# against the real site occasionally in case Greens adds/renames one), each
# queried with an empty subcategory ("" for Type) to pull everything in it.
CATEGORIES = [
    ("Baby", ""),
    ("Bakery", ""),
    ("Beverages", ""),
    ("Butcher", ""),
    ("CheeseCounter", ""),
    ("ChilledAndDairy", ""),
    ("CondimentsAndSeasoning", ""),
    ("Confectionery", ""),
    ("Cosmetics", ""),
    ("Delicatessen", ""),
    ("Fish", ""),
    ("FlowersAndPlants", ""),
    ("FrozenFoods", ""),
    ("FruitsAndVegetables", ""),
    ("Groceries", ""),
    ("Health", ""),
    ("HomeGarden", ""),
    ("Household", ""),
    ("New", ""),
    ("Organic", ""),
    ("PersonalCare", ""),
    ("Pets", ""),
    ("WineCellar", ""),
]

PAGE_SIZE = 48  # matches the value confirmed working in the spike capture

# Sizes that make a per-kg / per-litre price meaningful to compute. These two
# exact strings ("Kilogram", "Litre") are what the real, working Swieqi and
# Gozo crawls have actually been matching against -- but unlike PAVI PAMA and
# Welbee's, nothing here used to log when SIZE_UOM held something else, so a
# silently wrong or incomplete guess here could hide the same way Mriehel's
# wrong location code did (no error, just quietly fewer per-unit prices than
# there should be). See the logging added below for unrecognised values.
WEIGHT_UNITS = {"Kilogram": "kg", "Litre": "l"}

# Optional: restrict a run to just one or a few top-level categories, instead
# of the full list above -- e.g. to patch a single category once its correct
# codes are confirmed, without waiting through a multi-hour full crawl again.
# Set via the "only_categories" box when manually running the GitHub Actions
# workflow (see .github/workflows/crawl-greens.yml) -- comma-separated,
# case-insensitive, matched against the FIRST part of each (cat, typ) pair
# above, e.g. "FruitsAndVegetables" or "FruitsAndVegetables,Bakery". Leave it
# blank (the normal case, and always the case for the automatic nightly run)
# and every category above runs, same as before this existed.
ONLY_CATEGORIES_RAW = os.environ.get("ONLY_CATEGORIES", "").strip()
if ONLY_CATEGORIES_RAW:
    _wanted = {c.strip().lower() for c in ONLY_CATEGORIES_RAW.split(",") if c.strip()}
    ACTIVE_CATEGORIES = [pair for pair in CATEGORIES if pair[0].lower() in _wanted]
    if not ACTIVE_CATEGORIES:
        print(f"WARNING: ONLY_CATEGORIES={ONLY_CATEGORIES_RAW!r} didn't match any category "
              f"in the CATEGORIES list above -- check spelling. Running EVERY category instead, "
              f"same as a normal full run.", file=sys.stderr)
        ACTIVE_CATEGORIES = CATEGORIES
else:
    ACTIVE_CATEGORIES = CATEGORIES


# ----------------------------------------------------------------------------
# A genuine, independent wall-clock ceiling, reusable for anything that
# might hang -- confirmed safe to use around Playwright's browser calls too
# (tested: launching, navigating, reading cookies, and closing all work
# fine from inside a background thread).
# ----------------------------------------------------------------------------

def run_with_timeout(fn, timeout_seconds, *args, **kwargs):
    """Runs fn(*args, **kwargs) on a background thread and gives up waiting
    after timeout_seconds if it hasn't finished -- unlike a plain request
    timeout (which only counts quiet gaps between bits of data, and can be
    dodged by a slow trickle), this is a hard ceiling on the whole call, no
    matter what it's doing internally. If we do give up, the background
    thread is left to finish (or fail) harmlessly on its own -- it's marked
    as a daemon thread so it can never stop the program from exiting."""
    outcome = {}

    def worker():
        try:
            outcome["value"] = fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 -- report back to the caller, whatever it is
            outcome["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout_seconds)

    if thread.is_alive():
        raise TimeoutError(f"No result within {timeout_seconds}s")
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]


# How long we'll wait for the whole token-fetching step (opening a browser,
# loading a page, reading cookies) before giving up on it entirely. Longer
# than a plain product request, since a real browser genuinely takes longer
# to do its thing than a lightweight HTTP call does.
TOKEN_FETCH_HARD_TIMEOUT_SECONDS = 90

# Same idea, for saving one page's products to the database. Generous --
# a normal save is dozens of small statements plus a commit, which should
# take a small fraction of a second on a healthy connection.
DB_WRITE_HARD_TIMEOUT_SECONDS = 30

# If a save fails, how long we'll wait for a plain rollback (cleaning up so
# the connection is usable again) before giving up on that connection
# entirely and opening a fresh one instead.
DB_RECOVERY_TIMEOUT_SECONDS = 15


# ----------------------------------------------------------------------------
# Getting a valid access token (real browser, once per outlet)
# ----------------------------------------------------------------------------

def fetch_fresh_session(loc, timeout_ms=45000):
    """Opens a real, invisible browser, loads one Greens category page for
    this outlet -- the same as a shopper would -- and reads off the
    Authorization token and cookies the page's own script sends when it
    asks Greens for products. Returns (auth_header_value, cookie_header)."""
    url = f"{CATEGORY_PAGE_URL}?cat=Bakery&typ=Bread&loc={loc}"
    captured = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()

        def handle_request(request):
            if "apiservices/retail/sync/productlist" in request.url and "token" not in captured:
                auth = request.headers.get("authorization")
                if auth:
                    captured["token"] = auth

        page.on("request", handle_request)

        try:
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            # Some background tracking requests never fully go quiet -- that
            # doesn't mean the page (or our token) failed to load.
            pass

        # A little extra headroom in case the request fires just after our
        # wait above finishes.
        page.wait_for_timeout(3000)

        cookies = context.cookies()
        browser.close()

    if "token" not in captured:
        raise RuntimeError(f"Could not capture an Authorization token while loading {url}")

    cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    return captured["token"], cookie_header


# ----------------------------------------------------------------------------
# Fetching product pages (plain, lightweight requests, reusing the token)
# ----------------------------------------------------------------------------

def fetch_page(cat, typ, loc, page, session):
    """Ask Greens for one page of one category, at one outlet. Returns the
    parsed JSON response, or raises an exception on failure."""
    params = {
        "Agent": "GREENS",
        "Loc": loc,
        "Eid": "N/A",
        "SearchCriteria": "",
        "page": page,
        "NumberOfRecords": PAGE_SIZE,
        "SortType": "Position",
        "SortDirection": "Asc",
        "Category": cat,
        "Category2": "",
        "Category3": "",
        "Type": typ,
        "Cid": "00000000-0000-0000-0000-000000000000",
        "Cart": CART_PLACEHOLDER,
        "SubType": "",
        "Brand": "",
        "ProductListType": "products",
        "Mobdev": "False",
        "Detailed": "True",
    }
    url = BASE_URL + "?" + urllib.parse.urlencode(params)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Authorization": session["token"],
        "X-Requested-With": "XMLHttpRequest",
        # Matches the real address the site's own page shows when browsing
        # this category (confirmed via a captured real request) -- e.g.
        # https://www.greens.com.mt/products?cat=FruitsAndVegetables&srch=
        "Referer": f"{CATEGORY_PAGE_URL}?cat={cat}&srch=",
        "Content-Type": "application/json",
    }
    if session.get("cookie"):
        headers["Cookie"] = session["cookie"]

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_page_bounded(cat, typ, loc, page, session):
    """Same as fetch_page, but enforces a genuine, independent wall-clock
    ceiling (REQUEST_HARD_TIMEOUT_SECONDS) via run_with_timeout. Plain
    request timeouts only count quiet gaps between bits of data -- a
    response trickled in slowly enough can dodge that indefinitely, which
    is what happened during testing."""
    try:
        return run_with_timeout(fetch_page, REQUEST_HARD_TIMEOUT_SECONDS, cat, typ, loc, page, session)
    except TimeoutError:
        raise TimeoutError(f"No response within {REQUEST_HARD_TIMEOUT_SECONDS}s for {cat}/{typ} page {page}")


# ----------------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------------

def parse_products(payload):
    """Turn one page's raw response into a list of plain dicts ready to store."""
    out = []
    for item in payload.get("ProductList", []):
        d = item.get("ProductDetails", {})
        code = d.get("PART_NUMBER")
        name = d.get("PART_DESCRIPTION")
        if not code or not name:
            continue  # skip anything malformed rather than guess

        price = d.get("SALES_PRICE")
        rrp = d.get("SALES_PRICE_RRP")
        size_value = d.get("SIZE_VALUE")
        size_uom = d.get("SIZE_UOM")

        price_per_unit = None
        price_per_unit_measure = None
        if size_value and size_uom in WEIGHT_UNITS and price is not None:
            try:
                if float(size_value) > 0:
                    price_per_unit = round(float(price) / float(size_value), 4)
                    price_per_unit_measure = WEIGHT_UNITS[size_uom]
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        elif size_uom and size_uom not in WEIGHT_UNITS:
            # Previously this just silently skipped -- added after finding
            # the Mriehel location-code bug, specifically so a wrong/missing
            # unit spelling here shows up in the log instead of quietly
            # producing fewer per-unit prices than there should be.
            print(f"    (note: unrecognised size unit {size_uom!r} on {name!r} "
                  f"-- storing the product, just without a per-unit price)")

        category = " / ".join(
            filter(None, [d.get("GROUP_1"), d.get("GROUP_2"), d.get("GROUP_3")])
        ) or None

        out.append({
            "chain_product_code": str(code),
            "chain_product_name": name,
            "chain_category": category,
            "url": f"https://www.greens.com.mt/productdetails?pid={code}",
            "price": price,
            "regular_price": rrp if rrp and rrp != price else None,
            "price_per_unit": price_per_unit,
            "price_per_unit_measure": price_per_unit_measure,
        })
    return out


# ----------------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------------

def get_connection():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set.", file=sys.stderr)
        sys.exit(1)
    conn = psycopg2.connect(
        database_url,
        # A crawl can hold this one connection open for well over an hour.
        # Without these, a connection that's quietly gone stale (a dropped
        # network path, the database going idle and not waking up cleanly)
        # can make the *next* write just hang forever, with nothing ever
        # raising an error to catch. These are standard, well-documented
        # Postgres/psycopg2 settings for exactly that situation:
        connect_timeout=30,
        # Ask the operating system to actively check the connection is
        # still alive during quiet periods, instead of assuming silence
        # means "fine" -- so a truly dead connection gets noticed quickly.
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )
    # Tell Postgres itself to cancel any single statement that runs longer
    # than 30 seconds, rather than let a stuck query sit there indefinitely.
    # This USED to be passed as a connection startup option (options="-c
    # statement_timeout=...") but that failed against Neon's pooled
    # connection endpoint with "unsupported startup parameter in options"
    # -- confirmed live, not a guess. Setting it as a normal SQL command
    # right after connecting achieves the same protection and works fine
    # through the pooler.
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = 30000")
    conn.commit()
    return conn


def upsert_listing(cur, outlet_id, product):
    cur.execute(
        """
        INSERT INTO listing (outlet_id, chain_product_code, chain_product_name, chain_category, url)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (outlet_id, chain_product_code)
        DO UPDATE SET chain_product_name = EXCLUDED.chain_product_name,
                      chain_category = EXCLUDED.chain_category,
                      url = EXCLUDED.url
        RETURNING id
        """,
        (outlet_id, product["chain_product_code"], product["chain_product_name"],
         product["chain_category"], product["url"]),
    )
    return cur.fetchone()[0]


def insert_price_observation(cur, listing_id, product):
    cur.execute(
        """
        INSERT INTO price_observation
            (listing_id, price, regular_price, price_per_unit, price_per_unit_measure, source)
        VALUES (%s, %s, %s, %s, %s, 'site')
        """,
        (listing_id, product["price"], product["regular_price"],
         product["price_per_unit"], product["price_per_unit_measure"]),
    )


def store_page(cur, outlet_id, payload):
    """Save every product on one already-fetched page. Returns how many
    priced products were saved."""
    saved = 0
    for product in parse_products(payload):
        listing_id = upsert_listing(cur, outlet_id, product)
        if product["price"] is not None:
            insert_price_observation(cur, listing_id, product)
            saved += 1
    return saved


def save_page(cur, conn, outlet_id, payload):
    """store_page, plus the commit, as one unit -- used together with
    run_with_timeout so a database write can never hang forever either
    (the fetch from Greens already had this protection; this closes the
    matching gap on the save side)."""
    saved = store_page(cur, outlet_id, payload)
    conn.commit()
    return saved


def safe_recover_connection(conn, outlet_id):
    """After a save fails, try to leave the database connection clean and
    usable again. A plain rollback is normally enough. If even that hangs
    or fails, that's a strong sign the connection itself has quietly died
    -- in that case we stop trying to save it and just open a fresh one,
    rather than risk getting stuck again."""
    try:
        run_with_timeout(conn.rollback, DB_RECOVERY_TIMEOUT_SECONDS)
        return conn
    except Exception as exc:
        print(f"  {outlet_id}: couldn't cleanly recover the database connection "
              f"({type(exc).__name__}: {exc}) -- opening a fresh one instead")
        try:
            conn.close()
        except Exception:
            pass
        return get_connection()


# ----------------------------------------------------------------------------
# Crawl one outlet
# ----------------------------------------------------------------------------

def crawl_outlet(conn, outlet_id, source_code):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO crawl_run (store_id, outlet_id, status) VALUES (%s, %s, 'running') RETURNING id",
        (STORE_ID, outlet_id),
    )
    run_id = cur.fetchone()[0]
    conn.commit()

    item_count = 0
    pending_retries = []  # [{"cat":..., "typ":..., "page":...}, ...]
    still_failed = []     # same shape, for anything that fails even on retry
    error_message = None

    try:
        if ONLY_CATEGORIES_RAW:
            print(f"  RESTRICTED RUN: only crawling categories matching "
                  f"{ONLY_CATEGORIES_RAW!r} ({len(ACTIVE_CATEGORIES)} of {len(CATEGORIES)} "
                  f"category/subcategory pairs) -- not a full crawl.")
        print(f"  Opening a real browser to fetch a valid access token for {outlet_id}...")
        session = {}
        try:
            session["token"], session["cookie"] = run_with_timeout(
                fetch_fresh_session, TOKEN_FETCH_HARD_TIMEOUT_SECONDS, source_code
            )
        except TimeoutError:
            raise TimeoutError(
                f"Browser/token step did not finish within {TOKEN_FETCH_HARD_TIMEOUT_SECONDS}s for {outlet_id}"
            )
        print(f"  Got a token, starting first pass for {outlet_id}...")

        # ---- First pass: walk every category once. Anything that fails is
        # noted down and skipped immediately -- never blocks the rest. ----
        for cat, typ in ACTIVE_CATEGORIES:
            page = 1
            while True:
                try:
                    payload = fetch_page_bounded(cat, typ, source_code, page, session)
                except Exception as exc:
                    print(f"  {outlet_id} / {cat}/{typ} page {page}: FAILED first attempt "
                          f"({type(exc).__name__}: {exc}) -- will retry after the full scan")
                    pending_retries.append({"cat": cat, "typ": typ, "page": page})
                    break  # don't guess whether this category continues; the retry pass will find out

                try:
                    saved = run_with_timeout(save_page, DB_WRITE_HARD_TIMEOUT_SECONDS, cur, conn, outlet_id, payload)
                except Exception as exc:
                    print(f"  {outlet_id} / {cat}/{typ} page {page}: FAILED saving to the database "
                          f"({type(exc).__name__}: {exc}) -- will retry after the full scan")
                    pending_retries.append({"cat": cat, "typ": typ, "page": page})
                    conn = safe_recover_connection(conn, outlet_id)
                    cur = conn.cursor()
                    break

                item_count += saved
                print(f"  {outlet_id} / {cat}/{typ} page {page}: "
                      f"{len(payload.get('ProductList', []))} products")

                page_end = payload.get("pageEnd", True)
                if page_end or not payload.get("ProductList"):
                    break
                if page >= MAX_PAGES_PER_CATEGORY:
                    print(f"  {outlet_id} / {cat}/{typ}: hit the {MAX_PAGES_PER_CATEGORY}-page safety "
                          f"cap -- this almost certainly means a pagination bug, not a real category "
                          f"this large. Stopping here and flagging for review.")
                    pending_retries.append({"cat": cat, "typ": typ, "page": page + 1})
                    break
                page += 1
                time.sleep(REQUEST_DELAY_SECONDS)

            time.sleep(REQUEST_DELAY_SECONDS)

        # ---- Second pass: retry everything that failed, once each. A
        # successful retry resumes that category's pagination from exactly
        # where it stopped. ----
        if pending_retries:
            print(f"  First pass done for {outlet_id}. Retrying {len(pending_retries)} "
                  f"failed page(s)...")

            for entry in pending_retries:
                cat, typ, page = entry["cat"], entry["typ"], entry["page"]
                try:
                    payload = fetch_page_bounded(cat, typ, source_code, page, session)
                except Exception as exc:
                    print(f"  RETRY FAILED: {outlet_id} / {cat}/{typ} page {page} "
                          f"({type(exc).__name__}: {exc})")
                    still_failed.append(entry)
                    time.sleep(REQUEST_DELAY_SECONDS)
                    continue

                # Recovered -- save this page, then keep going in case this
                # category has more pages after the one that failed.
                current_page = page
                while True:
                    try:
                        saved = run_with_timeout(
                            save_page, DB_WRITE_HARD_TIMEOUT_SECONDS, cur, conn, outlet_id, payload
                        )
                    except Exception as exc:
                        print(f"  RETRY FAILED saving to the database: {outlet_id} / {cat}/{typ} "
                              f"page {current_page} ({type(exc).__name__}: {exc})")
                        still_failed.append({"cat": cat, "typ": typ, "page": current_page})
                        conn = safe_recover_connection(conn, outlet_id)
                        cur = conn.cursor()
                        break

                    item_count += saved
                    print(f"  {outlet_id} / {cat}/{typ} page {current_page}: "
                          f"{len(payload.get('ProductList', []))} products (recovered on retry)")

                    page_end = payload.get("pageEnd", True)
                    if page_end or not payload.get("ProductList") or current_page >= MAX_PAGES_PER_CATEGORY:
                        break
                    current_page += 1
                    time.sleep(REQUEST_DELAY_SECONDS)
                    try:
                        payload = fetch_page_bounded(cat, typ, source_code, current_page, session)
                    except Exception as exc:
                        print(f"  RETRY FAILED (continuation): {outlet_id} / {cat}/{typ} "
                              f"page {current_page} ({type(exc).__name__}: {exc})")
                        still_failed.append({"cat": cat, "typ": typ, "page": current_page})
                        break

                time.sleep(REQUEST_DELAY_SECONDS)

        if still_failed:
            listing = "; ".join(f"{e['cat']}/{e['typ']} p{e['page']}" for e in still_failed[:25])
            more = "" if len(still_failed) <= 25 else f" (+{len(still_failed) - 25} more)"
            error_message = f"{len(still_failed)} page(s) failed even after retry: {listing}{more}"
            status = "partial"
        else:
            status = "success"

    except Exception as exc:  # noqa: BLE001 -- we want to log ANY failure and move on
        status = "failed"
        error_message = f"{type(exc).__name__}: {exc}"
        print(f"  ERROR crawling {outlet_id}: {error_message}", file=sys.stderr)

    if ONLY_CATEGORIES_RAW:
        # Stamped onto crawl_run even on success, so anyone looking at crawl
        # history later (e.g. a much lower item_count than usual) isn't left
        # wondering whether something broke -- this explains it was
        # deliberately a partial, targeted run.
        note = f"[RESTRICTED RUN -- only categories: {ONLY_CATEGORIES_RAW}]"
        error_message = f"{note} {error_message}" if error_message else note

    def finish_crawl_run():
        cur.execute(
            "UPDATE crawl_run SET finished_at = %s, status = %s, item_count = %s, error_message = %s WHERE id = %s",
            (datetime.now(timezone.utc), status, item_count, error_message, run_id),
        )
        conn.commit()

    try:
        run_with_timeout(finish_crawl_run, DB_WRITE_HARD_TIMEOUT_SECONDS)
    except Exception as exc:
        # Even this last write is guarded -- if the connection has somehow
        # gone bad right at the end, don't let this hang the whole run.
        print(f"  {outlet_id}: couldn't record the final crawl_run status "
              f"({type(exc).__name__}: {exc})", file=sys.stderr)

    try:
        cur.close()
    except Exception:
        pass

    print(f"Finished {outlet_id}: status={status}, item_count={item_count}")
    return status == "success"


# ----------------------------------------------------------------------------

def main():
    if ONLY_OUTLETS_RAW:
        print(f"RESTRICTED RUN: only crawling outlets matching {ONLY_OUTLETS_RAW!r} "
              f"({len(ACTIVE_OUTLETS)} of {len(OUTLETS)} outlets) -- not a full crawl.")

    all_ok = True
    for outlet in ACTIVE_OUTLETS:
        print(f"\n=== Crawling {outlet['outlet_id']} ===")
        # A fresh connection per outlet, rather than one shared across the
        # whole multi-hour run -- an outlet's crawl can take a long time,
        # and starting each one clean reduces the chance of ever hitting a
        # connection that's gone stale from sitting open too long. (If
        # crawl_outlet has to reconnect partway through anyway, that's
        # handled internally and doesn't need anything from here.)
        conn = get_connection()
        try:
            ok = crawl_outlet(conn, outlet["outlet_id"], outlet["source_code"])
        finally:
            try:
                conn.close()
            except Exception:
                pass
        all_ok = all_ok and ok

    if not all_ok:
        # Non-zero exit so GitHub Actions marks the run with a red cross --
        # covers both "failed" and "partial" outlets, since both mean
        # something is worth a look in crawl_run, even if partial means
        # most of the data still came through fine.
        sys.exit(1)


if __name__ == "__main__":
    main()
