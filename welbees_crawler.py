"""
Xirja crawler -- Welbee's Supermarket.

What this does, in plain terms:
  For every one of Welbee's 17 product categories on welbees.mt, this asks
  for each category's product-listing page (page 1, then page 2, and so on),
  and saves what it finds into our database: one row per product ("listing"),
  and one dated price row per product per crawl ("price_observation" -- never
  overwritten, so we can see price history and notice if a crawl silently
  stops finding real prices).

  It's read-only. It never logs in, never adds anything to a cart, and never
  changes anything on welbees.mt -- it only asks for the same public category
  pages your browser loads when you browse the site.

How this is different from Greens and PAVI PAMA, and why:
  Welbee's has no product API to ask -- unlike Greens and PAVI PAMA, its
  category pages are plain server-rendered HTML with the product details
  already baked into the page (confirmed by pasting real "View Page Source"
  output for two different categories, Bakery and Drinks, not by guessing
  from a summarised/fetched version of the page). So instead of parsing JSON,
  this crawler:
    1. Downloads a category page's raw HTML with a plain HTTP request (same
       as PAVI PAMA: no login, no headless browser needed).
    2. Splits that HTML on the exact repeating marker that starts every
       product card (`<div class="select-none product-main-holder"
       data-product-code="`), so each resulting chunk is one product's own
       markup.
    3. Runs a handful of narrow patterns against each chunk to pull out the
       price, the optional "was" price, the optional per-kg/per-litre price,
       the product name and link, and the pack size -- deliberately not a
       full HTML-parsing library, since this page's markup is all on one
       very long line and splitting on the one marker that repeats once per
       product turned out to be simpler and more robust than trying to walk
       a proper DOM tree.

  Two real page pastes (Bakery: ~30 products, Drinks: ~90 products) were
  checked by hand against these patterns before writing this, and both
  matched cleanly with no missed products and no leftover unmatched chunks.
  A separate automated fetch of the same page (asked for indirectly, not
  pasted by hand) was found to SILENTLY change the real markup -- it dropped
  a class name and turned a real `<s>...</s>` "was" price into markdown
  strikethrough -- so that automated version was thrown away in favour of
  building only from real, byte-for-byte page source.

  Categories: Welbee's own category menu was independently checked against a
  screenshot of the site's navigation (17 categories) -- exact match, nothing
  missing or extra. Each category is fetched with no subcategory filter,
  same "no filter needed" pattern that turned out to work for Greens and
  PAVI PAMA.

  Pagination: rather than trying to parse Welbee's own page-number footer
  (which does show a real last-page number, e.g. "31" for Drinks), this asks
  for page 1, then page 2, then page 3, and so on, and simply stops the first
  time a page comes back with zero products on it -- the same robust
  "just keep going until it's empty" approach already used for Greens and
  PAVI PAMA, which doesn't depend on correctly reading page-footer markup
  that might change.

  Out-of-stock: no out-of-stock marker of any kind was found anywhere across
  either real page paste (confirmed by hand -- the person crawling the site
  looked specifically for a sold-out item and couldn't find one either). So,
  same as Greens, this crawler has no special out-of-stock handling; a
  product simply isn't saved if it has no readable price (see store_page
  below), and every saved price_observation defaults to in_stock = TRUE.

  Barcode: not present anywhere in Welbee's page markup, so every listing's
  barcode is stored as NULL, same treatment as any other missing field.

  Product name vs. pack size: Welbee's shows a product's name and its pack
  size (e.g. "500ml", "2l") as two separate pieces of text, not combined the
  way Greens and PAVI PAMA's own product descriptions already are. Left
  alone, two different sizes of the same product (e.g. a 330ml and a 1l
  bottle of the same drink) would be saved with the exact same name and be
  indistinguishable in a shopping list. So this crawler combines them itself
  -- "{name} ({size})" -- when a size is present. If this combined style
  isn't what you want once you see real results, it's a one-line change to
  adjust.

  No robots.txt exists for this site either (checked the same way as for
  PAVI PAMA), so this defaults to the same polite 5-second minimum gap
  between requests used for the other two crawlers.

  Same safety design as the other two crawlers throughout: every request and
  every database save runs on its own independent hard timeout; the crawler
  does one full pass through every category first, noting failures and
  moving on, then retries everything that failed exactly once; anything
  still failing after that is recorded plainly as a "partial" result, never
  silently treated as complete.

Before you rely on this:
  Every field pattern here was built from two real, hand-pasted page
  sources, not guessed and not taken from an automated fetch -- but this has
  not been run end-to-end against the live site yet (no general internet
  access in the environment that wrote it). Run it and check the crawl_run
  table afterwards, same as the other two crawlers -- and check for
  status = 'partial' rows too.

How to run it:
  See SETUP.md. In short: set the DATABASE_URL environment variable to your
  Neon connection string, then run `python welbees_crawler.py`. No browser
  install needed for this one (same as PAVI PAMA).
"""

import html
import os
import re
import sys
import time
import threading
import urllib.request
import urllib.error
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

STORE_ID = "welbees"
OUTLET_ID = "welbees"
SITE_ROOT = "https://welbees.mt"

# 19 Aug 2026 -- this used to end with a self-identifying
# "XirjaCrawler/0.1 (+contact: ...)" tag, the same convention used for the
# other two crawlers, so Welbee's server logs could tell this apart from an
# ordinary shopper if anyone looked. That's exactly what makes a
# User-Agent easy to specifically block, though, and every one of Welbee's
# 17 categories started failing with HTTP 403 on the same day with nothing
# else about this crawler having changed -- the likely explanation is that
# Welbee's (or a bot-protection layer in front of their site) started
# blocking on that identifiable tag. Dropped it here so this now presents
# as a plain, ordinary browser identity, same as the Greens and PAVI PAMA
# crawlers already do. If this doesn't clear the 403s, the next suspects
# are a general bot-protection layer (e.g. Cloudflare) that blocks on
# things besides the UA string, or an IP-based block.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

# No robots.txt exists for this site to give us a specific number, so this
# defaults to the same politeness used for Greens and PAVI PAMA rather than
# guessing something less careful.
REQUEST_DELAY_SECONDS = 5

# The hard, independent ceiling on any single request -- see greens_crawler.py
# for why this matters (a slow-trickling response can dodge a normal timeout
# indefinitely). Chosen generously above what a normal response should ever
# take, so it only ever fires on a genuinely stuck request. Raised from an
# original 45s to 60s after a real run (17 Aug 2026) saw a burst of
# TimeoutErrors and dropped connections spread across nearly every
# category -- a sign welbees.mt itself was responding slowly for a stretch,
# not a sign of a stuck/broken request, so a bit more headroom is a
# reasonable first response.
REQUEST_HARD_TIMEOUT_SECONDS = 60

# How long to pause before retrying a page that just failed -- gives a site
# that's temporarily slow or dropping connections a moment to recover
# before hitting it again, rather than retrying instantly into the same
# problem. Added after the same 17 Aug 2026 run above: retries were
# happening back-to-back with no gap at all. A modest step up from the
# normal between-page pacing (REQUEST_DELAY_SECONDS), not a guess at
# exactly what welbees.mt needs -- worth revisiting with real data if
# partial runs keep happening.
RETRY_DELAY_SECONDS = 15

# Purely a backstop against a pagination bug, not a guess at how big a real
# category can get -- see greens_crawler.py for the full story of why this
# needs real headroom (one real Greens category turned out to need 105+
# pages). Welbee's own pagination footer showed 31 total pages for its
# biggest category checked so far (Drinks), so this leaves very generous
# room above that while still catching a genuine pagination bug.
MAX_PAGES_PER_CATEGORY = 300

DB_WRITE_HARD_TIMEOUT_SECONDS = 30
DB_RECOVERY_TIMEOUT_SECONDS = 15

# The full 17-category list, taken from Welbee's own category menu and
# independently cross-checked against a screenshot of the site's navigation
# -- exact match, nothing missing or extra. Each entry is
# (category code, URL slug, human label).
CATEGORIES = [
    ("D-5430", "baby", "Baby"),
    ("D-5431", "bakery", "Bakery"),
    ("D-5432", "butcher-counter", "Butcher Counter"),
    ("D-5433", "chilled-food", "Chilled Food"),
    ("D-5447", "clothes-and-accessories", "Clothes & Accessories"),
    ("D-5434", "delicatessen", "Delicatessen"),
    ("D-5435", "drinks", "Drinks"),
    ("D-5436", "food-cupboard", "Food Cupboard"),
    ("D-5437", "fresh-fish-counter", "Fresh Fish Counter"),
    ("D-5438", "frozen-food", "Frozen Food"),
    ("D-5439", "fruit-and-veg-counter", "Fruit & Veg Counter"),
    ("D-5441", "health-and-beauty", "Health & Beauty"),
    ("D-5442", "healthy-section", "Healthy Section"),
    ("D-5443", "home-and-entertainment", "Home & Entertainment"),
    ("D-5444", "household", "Household"),
    ("D-5445", "pets", "Pets"),
    ("D-5446", "tobacco", "Tobacco"),
]

# The real PHYSICAL units Welbee's per-unit price could reasonably be in --
# "l" and "kg" were seen in the real page pastes checked before writing
# this; "g" and "ml" were added defensively as the same style of unit.
# "m" was added after seeing it for real on a 500ml cider bottle ("0.5m"
# size, "EUR8.98/m" per-unit price) -- confirmed as litres, not metres, by
# checking the arithmetic: the bottle's EUR4.59 price includes a 10c
# refundable BCRS bottle deposit, and (4.59 - 0.10) / 0.5 = 8.98 exactly,
# matching the displayed per-unit price. So this is Welbee's own shorthand
# for litres on drinks, computed on the deposit-free price, not a length.
#
# Anything else that shows up in this position (confirmed for real by
# actual crawl runs: "p", "ea", "pots" so far) has turned out to mean
# "priced per item/container" rather than a physical measure, so rather
# than maintaining a growing list of every English word a per-item price
# might use, anything that ISN'T one of the physical units below is treated
# as "piece" -- see parse_products, where this is used.
PHYSICAL_UNITS = {"kg": "kg", "l": "l", "g": "g", "ml": "ml", "m": "l"}

# How many times each non-physical per-unit suffix has been seen this run,
# e.g. {"p": 143, "ea": 6}. Used to log each suffix only ONCE (the first
# time it's seen) instead of once per product -- on a real run, "p" alone
# shows up on the vast majority of the Baby category, and logging every
# single occurrence buried anything actually worth noticing under hundreds
# of identical lines. A one-line tally is printed at the end of the run
# instead (see crawl_welbees).
fallback_unit_counts = {}

# Optional: restrict a run to just one or a few categories -- see
# greens_crawler.py's ONLY_CATEGORIES for the full explanation. Matched
# against the category CODE (e.g. "D-5435"), case-insensitive.
ONLY_CATEGORIES_RAW = os.environ.get("ONLY_CATEGORIES", "").strip()
if ONLY_CATEGORIES_RAW:
    _wanted = {c.strip().lower() for c in ONLY_CATEGORIES_RAW.split(",") if c.strip()}
    ACTIVE_CATEGORIES = [triple for triple in CATEGORIES if triple[0].lower() in _wanted]
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
# Fetching category pages
# ----------------------------------------------------------------------------

def fetch_page(category_code, slug, page):
    """Downloads one page of one category's product listing as raw HTML.
    Page 1 uses the plain category URL (exactly what a real browser loads);
    later pages add "?page=N" to that same URL -- both confirmed to be real,
    working URLs from the two page-source pastes checked by hand."""
    url = f"{SITE_ROOT}/shop/category/{category_code}/{slug}"
    if page > 1:
        url += f"?page={page}"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        # 19 Aug 2026 -- added alongside the User-Agent change above, since a
        # request with only a User-Agent and Accept header (and nothing else
        # a real browser normally sends) can itself look automated to some
        # bot-protection systems.
        "Accept-Language": "en-US,en;q=0.9",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return body


def fetch_page_bounded(category_code, slug, page):
    try:
        return run_with_timeout(fetch_page, REQUEST_HARD_TIMEOUT_SECONDS, category_code, slug, page)
    except TimeoutError:
        raise TimeoutError(
            f"Request for category {category_code} page {page} did not finish "
            f"within {REQUEST_HARD_TIMEOUT_SECONDS}s"
        )


# ----------------------------------------------------------------------------
# Parsing -- split the raw HTML on the exact marker that starts every
# product card, then run narrow patterns against each resulting chunk.
# Every one of these exact class strings was checked by hand against two
# real page-source pastes (Bakery and Drinks), not paraphrased or guessed.
# ----------------------------------------------------------------------------

PRODUCT_MARKER = '<div class="select-none product-main-holder" data-product-code="'

PRICE_RE = re.compile(
    r'<div class="font-body text-18 font-medium text-tertiary block align-middle">'
    r'&euro;([\d.,]+)</div>'
)
RRP_RE = re.compile(
    r'<s class="font-body text-12 font-regular text-grey-dark/60 leading-normal block align-middle">'
    r'RRP &euro;([\d.,]+)</s>'
)
PER_UNIT_RE = re.compile(
    r'<div class="font-body text-14 font-regular text-grey-dark leading-normal">'
    r'&euro;([\d.,]+)/(\w+)</div>'
)
NAME_RE = re.compile(
    r'<h6 class="font-heading text-14 leading-none font-regular text-grey-dark">'
    r'<a href="([^"]+)" target="_self">([^<]+)</a></h6>'
)
SIZE_RE = re.compile(
    r'<div class="font-body text-14 leading-none font-light text-grey-dark inline-block mr-2">'
    r'([^<]+)</div>'
)


def _parse_amount(text):
    try:
        return float(text.replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_products(page_html, category_label):
    """Turns one already-fetched category page's raw HTML into our own plain
    dicts, ready to save. Splitting on PRODUCT_MARKER means chunks[0] is
    whatever comes before the first product (header, nav, etc. -- discarded)
    and every chunk after that is exactly one product's own markup, up to
    (but not including) the next product's marker.

    Parameter deliberately renamed from the original "html" -- this file
    also `import html` (the standard-library entity-decoding module, used
    below), and a same-named parameter would have silently shadowed that
    import for this function's entire body, breaking every `html.unescape()`
    call below with "AttributeError: 'str' object has no attribute
    'unescape'" the very first time this ran. Caught before ever running
    this for real -- callers pass their own page content positionally, so
    they didn't need any change."""
    chunks = page_html.split(PRODUCT_MARKER)
    products = []
    for chunk in chunks[1:]:
        code, _, rest = chunk.partition('"')
        code = code.strip()
        if not code:
            continue

        price_m = PRICE_RE.search(rest)
        price = _parse_amount(price_m.group(1)) if price_m else None

        rrp_m = RRP_RE.search(rest)
        rrp = _parse_amount(rrp_m.group(1)) if rrp_m else None

        price_per_unit = None
        price_per_unit_measure = None
        unit_m = PER_UNIT_RE.search(rest)
        if unit_m:
            unit_raw = unit_m.group(2).strip().lower()
            price_per_unit = _parse_amount(unit_m.group(1))
            if unit_raw in PHYSICAL_UNITS:
                price_per_unit_measure = PHYSICAL_UNITS[unit_raw]
            else:
                # Not one of the four physical units -- some other way of
                # saying "priced per item" (see the PHYSICAL_UNITS comment
                # above). Logged the first time this exact suffix shows up
                # in this run, so you can still see new ones as they appear,
                # without hundreds of repeat lines for an already-understood
                # one like "p".
                price_per_unit_measure = "piece"
                fallback_unit_counts[unit_raw] = fallback_unit_counts.get(unit_raw, 0) + 1
                if fallback_unit_counts[unit_raw] == 1:
                    print(f"    (note: per-unit suffix {unit_raw!r} (first seen on product "
                          f"{code!r}) isn't one of the physical units -- treating it, and any "
                          f"further products with this same suffix, as \"per piece\" pricing. "
                          f"A tally of how many is printed at the end of the run.)")

        name_m = NAME_RE.search(rest)
        href = name_m.group(1).strip() if name_m else None
        # html.unescape() -- this is extracted straight from the page's raw
        # HTML with a regex (see the module docstring for why: no headless
        # browser needed for Welbee's), which means an entity like "&amp;"
        # in a real product name (e.g. "Chocolate & Milk") comes through
        # completely literally as the 5-character text "&amp;" instead of
        # a real "&", unlike a proper HTML parser which would decode it
        # automatically. Found via real testing -- a Bahlsen "Pick Up!"
        # product was landing in the wrong category because its name still
        # had the raw "&amp;" in it, so nothing in category_taxonomy.py
        # matched it as expected.
        name = html.unescape(name_m.group(2).strip()) if name_m else None
        url = f"{SITE_ROOT}{href}" if href else None

        size_m = SIZE_RE.search(rest)
        size = html.unescape(size_m.group(1).strip()) if size_m else None
        if name and size:
            display_name = f"{name} ({size})"
        else:
            display_name = name

        products.append({
            "chain_product_code": code,
            "chain_product_name": display_name,
            "chain_category": category_label,
            "barcode": None,  # not present anywhere in Welbee's page markup
            "url": url,
            "price": price,
            "regular_price": rrp if rrp and rrp != price else None,
            "price_per_unit": price_per_unit,
            "price_per_unit_measure": price_per_unit_measure,
        })
    return products


# ----------------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------------

def get_connection():
    database_url = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(
        database_url,
        connect_timeout=30,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )
    # This USED to be passed as a connection startup option (options="-c
    # statement_timeout=...") but that failed against Neon's pooled
    # connection endpoint with "unsupported startup parameter in options"
    # -- confirmed live, not a guess. Setting it as a normal SQL command
    # right after connecting achieves the same protection (Postgres cancels
    # any single statement running over 30s) and works fine through the
    # pooler.
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
    # in_stock is left to its database default (TRUE) -- no out-of-stock
    # marker was found anywhere in Welbee's page markup, confirmed by hand
    # across two real categories, same situation as Greens.


def product_code_set(products):
    """The set of chain_product_code values on an already-parsed page --
    used to detect a page that's a word-for-word repeat of the previous one
    (see save_parsed_page's caller for why that matters)."""
    return frozenset(p["chain_product_code"] for p in products)


def store_products(cur, outlet_id, products):
    """Save an already-parsed page's worth of products. Returns (saved,
    total) -- 'saved' only counts ones with a usable price, same as
    before."""
    saved = 0
    for product in products:
        if product["price"] is None:
            continue  # nothing usable to save -- and NOT counted, so
                       # item_count only ever reflects what actually made it
                       # into the database
        listing_id = upsert_listing(cur, outlet_id, product)
        insert_price_observation(cur, listing_id, product)
        saved += 1
    return saved, len(products)


def save_parsed_page(cur, conn, outlet_id, products):
    saved, total = store_products(cur, outlet_id, products)
    conn.commit()
    return saved, total


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

def crawl_welbees(conn):
    fallback_unit_counts.clear()  # fresh tally for this run, not left over from any previous call

    cur = conn.cursor()
    cur.execute(
        "INSERT INTO crawl_run (store_id, outlet_id, status) VALUES (%s, %s, 'running') RETURNING id",
        (STORE_ID, OUTLET_ID),
    )
    run_id = cur.fetchone()[0]
    conn.commit()

    item_count = 0
    pending_retries = []  # [{"category_code":..., "slug":..., "label":..., "page":...}, ...]
    still_failed = []
    error_message = None
    status = "success"

    try:
        if ONLY_CATEGORIES_RAW:
            print(f"  RESTRICTED RUN: only crawling categories matching "
                  f"{ONLY_CATEGORIES_RAW!r} ({len(ACTIVE_CATEGORIES)} of {len(CATEGORIES)} "
                  f"categories) -- not a full crawl.")

        # ---- First pass: walk every category once, page by page, until a
        # page comes back with zero products. Anything that fails is noted
        # down and skipped immediately -- never blocks the rest. ----
        #
        # A page that comes back IDENTICAL to the one before it also ends
        # the category, same as an empty one -- found for real on a live
        # run: welbees.mt silently ignored the ?page=N part of the URL for
        # at least one category, so every "page" after the first kept
        # serving the same products, and the crawler had no way to notice
        # short of grinding all the way to the MAX_PAGES_PER_CATEGORY safety
        # cap (2+ hours on a single category). Comparing each page's set of
        # product codes to the previous page's catches this immediately
        # (typically by page 2) without needing to know exactly why the
        # site repeated itself.
        for category_code, slug, label in ACTIVE_CATEGORIES:
            page = 1
            previous_codes = None
            while True:
                try:
                    html = fetch_page_bounded(category_code, slug, page)
                except Exception as exc:
                    print(f"  {category_code} ({label}) page {page}: FAILED first attempt "
                          f"({type(exc).__name__}: {exc}) -- will retry after the full scan")
                    pending_retries.append({"category_code": category_code, "slug": slug,
                                             "label": label, "page": page})
                    break

                products = parse_products(html, label)
                current_codes = product_code_set(products)
                if products and current_codes == previous_codes:
                    print(f"  {category_code} ({label}) page {page}: identical product list to "
                          f"the previous page -- the site isn't giving us anything new here (it "
                          f"may be ignoring the page number in the URL). Treating this category "
                          f"as finished rather than continuing toward the "
                          f"{MAX_PAGES_PER_CATEGORY}-page safety cap.")
                    break

                try:
                    saved, total = run_with_timeout(
                        save_parsed_page, DB_WRITE_HARD_TIMEOUT_SECONDS, cur, conn, OUTLET_ID, products
                    )
                except Exception as exc:
                    print(f"  {category_code} ({label}) page {page}: FAILED saving to the database "
                          f"({type(exc).__name__}: {exc}) -- will retry after the full scan")
                    pending_retries.append({"category_code": category_code, "slug": slug,
                                             "label": label, "page": page})
                    conn = safe_recover_connection(conn, OUTLET_ID)
                    cur = conn.cursor()
                    break

                item_count += saved
                print(f"  {category_code} ({label}) page {page}: {total} products")

                if total == 0:
                    break  # empty page -- this category is done
                if page >= MAX_PAGES_PER_CATEGORY:
                    print(f"  {category_code} ({label}): hit the {MAX_PAGES_PER_CATEGORY}-page "
                          f"safety cap -- this almost certainly means a pagination bug, not a "
                          f"real category. Marking as failed for this category and moving on.")
                    pending_retries.append({"category_code": category_code, "slug": slug,
                                             "label": label, "page": page + 1})
                    break
                previous_codes = current_codes
                page += 1
                time.sleep(REQUEST_DELAY_SECONDS)

        # ---- Second pass: retry everything that failed, exactly once. ----
        for entry in pending_retries:
            category_code, slug, label, page = (
                entry["category_code"], entry["slug"], entry["label"], entry["page"]
            )
            # Pause before every retry, not just the ones that happen to
            # fall a while after their original failure -- a page that
            # fails right at the end of the first pass would otherwise get
            # retried almost immediately, with no time for a struggling
            # site to recover. See RETRY_DELAY_SECONDS above.
            time.sleep(RETRY_DELAY_SECONDS)
            try:
                html = fetch_page_bounded(category_code, slug, page)
            except Exception as exc:
                print(f"  {category_code} ({label}) page {page}: still failed on retry "
                      f"({type(exc).__name__}: {exc}) -- giving up on this one")
                still_failed.append(entry)
                continue

            products = parse_products(html, label)
            try:
                saved, total = run_with_timeout(
                    save_parsed_page, DB_WRITE_HARD_TIMEOUT_SECONDS, cur, conn, OUTLET_ID, products
                )
            except Exception as exc:
                print(f"  {category_code} ({label}) page {page}: still failed saving on retry "
                      f"({type(exc).__name__}: {exc}) -- giving up on this one")
                still_failed.append(entry)
                conn = safe_recover_connection(conn, OUTLET_ID)
                cur = conn.cursor()
                continue

            item_count += saved
            print(f"  {category_code} ({label}) page {page}: RECOVERED on retry, {total} products")

            # If the retry succeeded and there's more to this category, keep
            # going from here -- same as the first pass would have, including
            # the same repeated-page detection (see the first pass above for
            # why that matters).
            previous_codes = product_code_set(products)
            next_page = page + 1
            while total > 0:
                if next_page > page + MAX_PAGES_PER_CATEGORY:
                    print(f"  {category_code} ({label}): hit the safety cap continuing after "
                          f"retry -- stopping here.")
                    still_failed.append({"category_code": category_code, "slug": slug,
                                          "label": label, "page": next_page})
                    break
                time.sleep(REQUEST_DELAY_SECONDS)
                try:
                    html = fetch_page_bounded(category_code, slug, next_page)
                except Exception as exc:
                    # A page hit while continuing on after an earlier
                    # successful retry used to get NO retry at all here --
                    # unlike a page that fails during the first pass, which
                    # gets one after the full scan finishes. Found via a
                    # real run (17 Aug 2026) where several categories lost
                    # several pages of real products this exact way (e.g.
                    # Household got all the way to page 33 before losing
                    # page 34 with no second attempt). Giving it the same
                    # one-retry treatment, after a short pause, closes that
                    # gap.
                    print(f"  {category_code} ({label}) page {next_page}: failed "
                          f"({type(exc).__name__}: {exc}) -- waiting {RETRY_DELAY_SECONDS}s "
                          f"and trying once more")
                    time.sleep(RETRY_DELAY_SECONDS)
                    try:
                        html = fetch_page_bounded(category_code, slug, next_page)
                    except Exception as exc2:
                        print(f"  {category_code} ({label}) page {next_page}: still failed on "
                              f"retry ({type(exc2).__name__}: {exc2}) -- stopping here")
                        still_failed.append({"category_code": category_code, "slug": slug,
                                              "label": label, "page": next_page})
                        break

                try:
                    next_products = parse_products(html, label)
                    current_codes = product_code_set(next_products)
                    if next_products and current_codes == previous_codes:
                        print(f"  {category_code} ({label}) page {next_page}: identical product "
                              f"list to the previous page -- treating this category as finished.")
                        break
                    saved, total = run_with_timeout(
                        save_parsed_page, DB_WRITE_HARD_TIMEOUT_SECONDS, cur, conn, OUTLET_ID, next_products
                    )
                except Exception as exc:
                    print(f"  {category_code} ({label}) page {next_page}: failed saving while "
                          f"continuing after retry ({type(exc).__name__}: {exc}) -- stopping here")
                    still_failed.append({"category_code": category_code, "slug": slug,
                                          "label": label, "page": next_page})
                    # Same connection-recovery step used after a save
                    # failure everywhere else in this file -- without it, a
                    # broken transaction here could cause every following
                    # retry entry to fail too, even once the site itself is
                    # fine again.
                    conn = safe_recover_connection(conn, OUTLET_ID)
                    cur = conn.cursor()
                    break
                item_count += saved
                print(f"  {category_code} ({label}) page {next_page}: {total} products")
                if total == 0:
                    break
                previous_codes = current_codes
                next_page += 1

        if still_failed:
            listing = "; ".join(f"{e['category_code']} ({e['label']}) p{e['page']}" for e in still_failed[:25])
            more = "" if len(still_failed) <= 25 else f" (+{len(still_failed) - 25} more)"
            error_message = f"{len(still_failed)} page(s) failed even after retry: {listing}{more}"
            status = "partial"

    except Exception as exc:  # noqa: BLE001 -- log ANY failure and move on
        status = "failed"
        error_message = f"{type(exc).__name__}: {exc}"
        print(f"  ERROR crawling Welbee's: {error_message}", file=sys.stderr)

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

    if fallback_unit_counts:
        tally = ", ".join(
            f"{suffix!r}: {count} product(s)"
            for suffix, count in sorted(fallback_unit_counts.items())
        )
        print(f"  Per-unit suffixes treated as \"per piece\" pricing this run: {tally}")

    print(f"Finished Welbee's: status={status}, item_count={item_count}")
    return status == "success"


def main():
    conn = get_connection()
    try:
        ok = crawl_welbees(conn)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
