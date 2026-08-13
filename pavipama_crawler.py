"""
Xirja crawler -- PAVI PAMA.

What this does, in plain terms:
  Asks PAVI PAMA's own product API for every product in every category, and
  saves what it gets back into our database: one row per product ("listing"),
  and one dated price row per product per crawl ("price_observation" --
  never overwritten, so we can see price history and notice if a crawl
  silently stops finding real prices).

  It's read-only. It never logs in, never adds anything to a cart, and never
  changes anything on pavipama.com.mt -- it only asks for public product
  pages, the same way your browser does when you browse the site.

How this is different from the Greens crawler, and why:
  PAVI PAMA turned out to be simpler than Greens in two real ways, both
  confirmed by hand before writing this, not assumed:

  1. No login needed. The product API was first captured while logged into
     a personal PAVI PAMA account, which would have meant storing real login
     credentials to automate it -- a materially bigger risk than Greens ever
     needed. A second capture, done from a logged-out/incognito browser,
     confirmed the exact same request works anonymously (status 200, real
     products visible) -- so this crawler never logs in or holds any
     account credentials.

  2. No per-branch prices. Unlike Greens (which genuinely has different
     stock and different prices per branch), PAVI PAMA has no store
     selector while browsing, and checkout only offers a fulfilment choice
     (delivery, Pama pickup at Mosta, Pavi pickup at Qormi) -- nothing
     suggesting different prices per option. So this crawler treats PAVI
     PAMA as a single outlet with one shared price list, rather than
     crawling multiple branches like Greens does.

  Because there's no login step, there's also no browser/Playwright step at
  all here -- every request is a plain, lightweight HTTP request from the
  start. That removes the single biggest source of flakiness the Greens
  crawler had to work around.

  Category codes came directly from PAVI PAMA's own category API
  (/api/cli/categories), not a guess from the navigation menu -- and were
  independently cross-checked against a screenshot of the site's own
  category grid, which matched exactly (same 23 names, nothing missing or
  extra). Requesting a top-level category code with no subcategory filter
  returns everything in that category, the same "no filter needed" pattern
  Greens turned out to use -- confirmed by a real captured response, not
  assumed from the Greens pattern alone.

  Price fields: PAVI PAMA returns both "price" (the regular/shelf price)
  and "netPrice" (what you'd actually pay right now). These were confirmed
  against a real example with an active promotion (Pink Lady apples: price
  EUR2.39, netPrice EUR2.19, with a visible "Offerta" promotion) -- so
  netPrice maps to price_observation.price, and price maps to
  price_observation.regular_price.

  No robots.txt exists for this site (both with and without "www" just
  serve the app's own generic fallback page), so there's no site-provided
  crawl-delay to follow. This crawler defaults to the same 5-second minimum
  gap between requests used for Greens, as a reasonable, polite default in
  the absence of explicit guidance.

  Same safety design as the Greens crawler throughout, for the same
  reasons: every single request and every single database save runs on its
  own independent hard timeout (so a stuck request or a stale database
  connection can never silently hang the whole run); the crawler does one
  full pass through every category first, noting failures and moving on,
  then retries everything that failed exactly once; anything still failing
  after that is recorded plainly as a "partial" result, never silently
  treated as complete.

Before you rely on this:
  Like the Greens crawler, this has not been tested end-to-end from inside
  the environment that wrote it (no general internet access there) -- but
  every piece of it (the endpoint, the category codes, the field names, the
  price mapping, and the pagination fields) was built from real, captured
  evidence, not guessed. Run it and check the crawl_run table afterwards,
  same as Greens -- and check for status = 'partial' rows too.

How to run it:
  See SETUP.md. In short: set the DATABASE_URL environment variable to your
  Neon connection string, then run `python pavipama_crawler.py`. No browser
  install needed for this one (unlike Greens).
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

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

STORE_ID = "pavipama"
OUTLET_ID = "pavipama"
BASE_URL = "https://pavipama.com.mt/api/cli/ecommerce/products"
CATEGORY_PAGE_URL = "https://www.pavipama.com.mt/"

# A normal-looking browser identity, with an honest, contactable extra bit
# tacked on -- per the README's legal-footing guidance, PAVI PAMA's server
# logs should be able to tell this apart from an ordinary shopper if they
# look.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 "
    "XirjaCrawler/0.1 (+contact: ranier.chircop@gmail.com; polite, low-volume, once-daily crawl)"
)

# No robots.txt exists for this site to give us a specific number, so this
# defaults to the same politeness used for Greens (which robots.txt there
# did specify) rather than guessing something less careful.
REQUEST_DELAY_SECONDS = 5

# The hard, independent ceiling on any single request -- see greens_crawler.py
# for why this matters (a slow-trickling response can dodge a normal timeout
# indefinitely). Chosen generously above what a normal response should ever
# take, so it only ever fires on a genuinely stuck request.
REQUEST_HARD_TIMEOUT_SECONDS = 45

# Purely a backstop against a pagination bug -- PAVI PAMA's page size is 20
# (smaller than Greens' 48), so this allows for a much bigger category
# (6,000+ products) than any single one here is expected to have, before
# treating it as a bug rather than a real category.
MAX_PAGES_PER_CATEGORY = 300

DB_WRITE_HARD_TIMEOUT_SECONDS = 30
DB_RECOVERY_TIMEOUT_SECONDS = 15

# The full top-level category list, from PAVI PAMA's own /api/cli/categories
# endpoint -- independently cross-checked against a screenshot of the site's
# own category grid (23 names, exact match). Requesting one of these codes
# with no subcategory filter returns everything in that category -- no
# subcategory guessing needed, confirmed by a real captured response.
CATEGORIES = [
    ("0002", "CONFECTIONERY"),
    ("0003", "FRUIT & VEG"),
    ("0004", "DELICATESSEN"),
    ("0005", "VOUCHERS"),
    ("0006", "FISH"),
    ("0007", "BUTCHER"),
    ("0009", "FROZEN"),
    ("0010", "CHILLED"),
    ("0012", "BABY"),
    ("0013", "PERSONAL CARE"),
    ("0015", "PASTA SHOP"),
    ("0016", "HOMEWARE"),
    ("0018", "FOODS"),
    ("0019", "CELLAR"),
    ("0020", "BAKERY"),
    ("0021", "BEVERAGES"),
    ("0022", "PETSHOP"),
    ("0023", "CLEANING"),
    ("0024", "AUTO & BOAT CARE"),
    ("0025", "HEALTH"),
    ("0076", "DO IT YOURSELF"),
    ("0077", "FOOD BANK"),
    ("0078", "SEASONAL"),
]

# Sizes that make a per-kg / per-litre price meaningful to compute. PAVI
# PAMA's response already includes a ready-made per-unit price (pricePerUm),
# so this is only used to decide whether that value is trustworthy enough to
# store -- unrecognised units are logged and left out rather than guessed.
KNOWN_UNITS = {"KG": "kg", "LT": "l", "L": "l", "GR": "g", "ML": "ml"}

# Optional: restrict a run to just one or a few categories -- see
# greens_crawler.py's ONLY_CATEGORIES for the full explanation. Matched
# against the category CODE (e.g. "0003"), case-insensitive.
ONLY_CATEGORIES_RAW = os.environ.get("ONLY_CATEGORIES", "").strip()
if ONLY_CATEGORIES_RAW:
    _wanted = {c.strip().lower() for c in ONLY_CATEGORIES_RAW.split(",") if c.strip()}
    ACTIVE_CATEGORIES = [pair for pair in CATEGORIES if pair[0].lower() in _wanted]
    if not ACTIVE_CATEGORIES:
        print(f"WARNING: ONLY_CATEGORIES={ONLY_CATEGORIES_RAW!r} didn't match any category "
              f"code above -- check spelling. Running EVERY category instead, same as a "
              f"normal full run.", file=sys.stderr)
        ACTIVE_CATEGORIES = CATEGORIES
else:
    ACTIVE_CATEGORIES = CATEGORIES


# ----------------------------------------------------------------------------
# A genuine, independent wall-clock ceiling, reusable for anything that
# might hang.
# ----------------------------------------------------------------------------

def run_with_timeout(fn, timeout_seconds, *args, **kwargs):
    """Runs fn(*args, **kwargs) on a background thread and gives up waiting
    after timeout_seconds, no matter what fn is doing. Raises TimeoutError
    if it never finished in time, or re-raises whatever exception fn itself
    raised if it finished but failed."""
    result = {}

    def target():
        try:
            result["value"] = fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 -- deliberately broad, re-raised below
            result["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout_seconds)

    if thread.is_alive():
        raise TimeoutError(f"{getattr(fn, '__name__', 'operation')} did not finish within {timeout_seconds}s")
    if "error" in result:
        raise result["error"]
    return result.get("value")


# ----------------------------------------------------------------------------
# Fetching product pages
# ----------------------------------------------------------------------------

def fetch_page(category_id, page):
    """Ask PAVI PAMA for one page of one category. Returns the parsed JSON
    response, or raises an exception on failure. No login, no token -- this
    was confirmed to work anonymously."""
    params = {
        "store": "",
        "q": "",
        "p": page,
        "category": category_id,
        "onlyPromotions": "false",
        "onlyBranded": "false",
        "tag": "",
    }
    url = BASE_URL + "?" + urllib.parse.urlencode(params)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.pavipama.com.mt",
        "Referer": CATEGORY_PAGE_URL,
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def fetch_page_bounded(category_id, page):
    try:
        return run_with_timeout(fetch_page, REQUEST_HARD_TIMEOUT_SECONDS, category_id, page)
    except TimeoutError:
        raise TimeoutError(
            f"Request for category {category_id} page {page} did not finish "
            f"within {REQUEST_HARD_TIMEOUT_SECONDS}s"
        )


def parse_products(payload):
    """Turns one page's worth of PAVI PAMA's own JSON shape into our own
    plain dicts, ready to save. Confirmed field names and price meaning
    against a real captured response with an active promotion."""
    products = []
    for item in payload.get("data", []):
        weight = item.get("weight")
        unit_raw = (item.get("umPerUm") or "").strip().upper()
        unit = KNOWN_UNITS.get(unit_raw)
        price_per_unit = None
        price_per_unit_measure = None
        if unit is not None and item.get("pricePerUm") is not None:
            # PAVI PAMA already computes this for us -- no need to derive it
            # ourselves, just trust it when the unit is one we recognise.
            price_per_unit = item["pricePerUm"]
            price_per_unit_measure = unit
        elif unit_raw and unit_raw not in KNOWN_UNITS:
            print(f"    (note: unrecognised unit {unit_raw!r} on {item.get('description')!r} "
                  f"-- storing the product, just without a per-unit price)")

        products.append({
            "chain_product_code": item.get("id"),
            "chain_product_name": item.get("description"),
            "chain_category": item.get("categoryDescription"),
            "barcode": item.get("barcode") or None,
            "url": None,  # no confirmed product-detail page pattern yet
            "price": item.get("netPrice"),          # what you'd actually pay right now
            "regular_price": item.get("price"),      # non-promo price
            "price_per_unit": price_per_unit,
            "price_per_unit_measure": price_per_unit_measure,
            "size_value": weight,
            "size_unit": unit,
            "in_stock": bool(item.get("available", True)),
        })
    return products


# ----------------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------------

def get_connection():
    database_url = os.environ["DATABASE_URL"]
    return psycopg2.connect(
        database_url,
        connect_timeout=30,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
        options="-c statement_timeout=30000",
    )


def upsert_listing(cur, outlet_id, product):
    cur.execute(
        """
        INSERT INTO listing (outlet_id, chain_product_code, chain_product_name,
                              chain_category, barcode, url)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (outlet_id, chain_product_code) DO UPDATE SET
            chain_product_name = EXCLUDED.chain_product_name,
            chain_category = EXCLUDED.chain_category,
            barcode = EXCLUDED.barcode,
            url = EXCLUDED.url
        RETURNING id
        """,
        (outlet_id, product["chain_product_code"], product["chain_product_name"],
         product["chain_category"], product["barcode"], product["url"]),
    )
    return cur.fetchone()[0]


def insert_price_observation(cur, listing_id, product):
    cur.execute(
        """
        INSERT INTO price_observation (listing_id, price, regular_price,
                                        price_per_unit, price_per_unit_measure,
                                        in_stock, source)
        VALUES (%s, %s, %s, %s, %s, %s, 'site')
        """,
        (listing_id, product["price"], product["regular_price"],
         product["price_per_unit"], product["price_per_unit_measure"],
         product["in_stock"]),
    )


def store_page(cur, outlet_id, payload):
    products = parse_products(payload)
    saved_count = 0
    for product in products:
        if product["chain_product_code"] is None or product["price"] is None:
            continue  # nothing usable to save -- and NOT counted, so item_count
                       # only ever reflects what actually made it into the database
        listing_id = upsert_listing(cur, outlet_id, product)
        insert_price_observation(cur, listing_id, product)
        saved_count += 1
    return saved_count


def save_page(cur, conn, outlet_id, payload):
    saved = store_page(cur, outlet_id, payload)
    conn.commit()
    return saved


def safe_recover_connection(conn, outlet_id):
    try:
        run_with_timeout(conn.rollback, DB_RECOVERY_TIMEOUT_SECONDS)
        return conn
    except Exception:
        print(f"  {outlet_id}: connection looked stuck even trying to roll back -- "
              f"opening a fresh one instead")
        try:
            conn.close()
        except Exception:
            pass
        return get_connection()


# ----------------------------------------------------------------------------
# The crawl itself
# ----------------------------------------------------------------------------

def crawl_pavipama(conn):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO crawl_run (store_id, outlet_id, status) VALUES (%s, %s, 'running') RETURNING id",
        (STORE_ID, OUTLET_ID),
    )
    run_id = cur.fetchone()[0]
    conn.commit()

    item_count = 0
    pending_retries = []  # [{"category_id":..., "page":...}, ...]
    still_failed = []
    error_message = None
    status = "success"

    try:
        if ONLY_CATEGORIES_RAW:
            print(f"  RESTRICTED RUN: only crawling categories matching "
                  f"{ONLY_CATEGORIES_RAW!r} ({len(ACTIVE_CATEGORIES)} of {len(CATEGORIES)} "
                  f"categories) -- not a full crawl.")

        # ---- First pass: walk every category once. Anything that fails is
        # noted down and skipped immediately -- never blocks the rest. ----
        for category_id, label in ACTIVE_CATEGORIES:
            page = 0
            while True:
                try:
                    payload = fetch_page_bounded(category_id, page)
                except Exception as exc:
                    print(f"  {category_id} ({label}) page {page}: FAILED first attempt "
                          f"({type(exc).__name__}: {exc}) -- will retry after the full scan")
                    pending_retries.append({"category_id": category_id, "label": label, "page": page})
                    break

                try:
                    saved = run_with_timeout(save_page, DB_WRITE_HARD_TIMEOUT_SECONDS, cur, conn, OUTLET_ID, payload)
                except Exception as exc:
                    print(f"  {category_id} ({label}) page {page}: FAILED saving to the database "
                          f"({type(exc).__name__}: {exc}) -- will retry after the full scan")
                    pending_retries.append({"category_id": category_id, "label": label, "page": page})
                    conn = safe_recover_connection(conn, OUTLET_ID)
                    cur = conn.cursor()
                    break

                item_count += saved
                print(f"  {category_id} ({label}) page {page}: {len(payload.get('data', []))} products")

                is_last = payload.get("last", True)
                if is_last or not payload.get("data"):
                    break
                if page >= MAX_PAGES_PER_CATEGORY:
                    print(f"  {category_id} ({label}): hit the {MAX_PAGES_PER_CATEGORY}-page "
                          f"safety cap -- this almost certainly means a pagination bug, not a "
                          f"real category. Marking as failed for this category and moving on.")
                    pending_retries.append({"category_id": category_id, "label": label, "page": page + 1})
                    break
                page += 1
                time.sleep(REQUEST_DELAY_SECONDS)

        # ---- Second pass: retry everything that failed, exactly once. ----
        for entry in pending_retries:
            category_id, label, page = entry["category_id"], entry["label"], entry["page"]
            try:
                payload = fetch_page_bounded(category_id, page)
            except Exception as exc:
                print(f"  {category_id} ({label}) page {page}: still failed on retry "
                      f"({type(exc).__name__}: {exc}) -- giving up on this one")
                still_failed.append(entry)
                continue

            try:
                saved = run_with_timeout(save_page, DB_WRITE_HARD_TIMEOUT_SECONDS, cur, conn, OUTLET_ID, payload)
            except Exception as exc:
                print(f"  {category_id} ({label}) page {page}: still failed saving on retry "
                      f"({type(exc).__name__}: {exc}) -- giving up on this one")
                still_failed.append(entry)
                conn = safe_recover_connection(conn, OUTLET_ID)
                cur = conn.cursor()
                continue

            item_count += saved
            print(f"  {category_id} ({label}) page {page}: RECOVERED on retry, "
                  f"{len(payload.get('data', []))} products")

            # If the retry succeeded and there's more to this category, keep
            # going from here -- same as the first pass would have.
            next_page = page + 1
            while not payload.get("last", True) and payload.get("data"):
                if next_page > page + MAX_PAGES_PER_CATEGORY:
                    print(f"  {category_id} ({label}): hit the safety cap continuing after "
                          f"retry -- stopping here.")
                    still_failed.append({"category_id": category_id, "label": label, "page": next_page})
                    break
                time.sleep(REQUEST_DELAY_SECONDS)
                try:
                    payload = fetch_page_bounded(category_id, next_page)
                    saved = run_with_timeout(save_page, DB_WRITE_HARD_TIMEOUT_SECONDS, cur, conn, OUTLET_ID, payload)
                except Exception as exc:
                    print(f"  {category_id} ({label}) page {next_page}: failed continuing after "
                          f"retry ({type(exc).__name__}: {exc}) -- stopping here")
                    still_failed.append({"category_id": category_id, "label": label, "page": next_page})
                    break
                item_count += saved
                print(f"  {category_id} ({label}) page {next_page}: {len(payload.get('data', []))} products")
                next_page += 1

        if still_failed:
            listing = "; ".join(f"{e['category_id']} ({e['label']}) p{e['page']}" for e in still_failed[:25])
            more = "" if len(still_failed) <= 25 else f" (+{len(still_failed) - 25} more)"
            error_message = f"{len(still_failed)} page(s) failed even after retry: {listing}{more}"
            status = "partial"

    except Exception as exc:  # noqa: BLE001 -- log ANY failure and move on
        status = "failed"
        error_message = f"{type(exc).__name__}: {exc}"
        print(f"  ERROR crawling PAVI PAMA: {error_message}", file=sys.stderr)

    if ONLY_CATEGORIES_RAW:
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
        print(f"  Couldn't record the final crawl_run status ({type(exc).__name__}: {exc})", file=sys.stderr)

    try:
        cur.close()
    except Exception:
        pass

    print(f"Finished PAVI PAMA: status={status}, item_count={item_count}")
    return status == "success"


def main():
    conn = get_connection()
    try:
        ok = crawl_pavipama(conn)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
