"""
Xirja -- price API.

What this does, in plain terms:
  A small web server that sits between the app (on someone's phone) and the
  database. The phone app is never allowed to talk to Postgres directly --
  that would mean shipping your database password inside the app, which
  anyone who downloaded the app could then read out. Instead, the app calls
  this server over a normal web address, and this server is the only thing
  that ever holds the real database credentials.

  Right now this has exactly one real feature -- the minimum needed to prove
  the whole chain works end to end: real prices, from the real database,
  reachable over the internet, ready for a real screen to show. More
  endpoints (adding items to a list, browsing, price corrections) come
  later, once this first slice is proven out.

Run locally:
    cd api
    pip install -r requirements.txt
    export DATABASE_URL="postgres://...same one the crawlers use..."
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

  Then open http://127.0.0.1:8000/docs in a browser -- FastAPI builds that
  page automatically, and it lets you try the endpoint by hand before the
  app ever calls it.

Deploy: see ../SETUP.md -> "Running the API online (Render)" for the
step-by-step walkthrough (no server administration experience needed).
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from psycopg2 import pool as pg_pool

# A small, reusable pool of database connections, opened once when the
# server starts. Opening a brand new connection to Neon on every single
# request adds a noticeable delay (it's a security handshake with a
# database that may be on the other side of the world) -- a pool instead
# keeps a handful of connections open and hands them out as requests come
# in, the same way a restaurant keeps a few tables set rather than building
# a new one for every guest.
_pool = None


def get_pool():
    global _pool
    if _pool is None:
        database_url = os.environ["DATABASE_URL"]
        _pool = pg_pool.SimpleConnectionPool(
            1, 5, database_url, connect_timeout=30
        )
    return _pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_pool()  # open the pool as the server starts, so the very first
                # real request isn't the one stuck paying the setup cost
    yield
    if _pool is not None:
        _pool.closeall()


app = FastAPI(title="Xirja API", lifespan=lifespan)

# Wide open for now -- every endpoint here is read-only, public shelf-price
# information (nothing personal, nothing a shopper typed in), and the app
# is still being built and tested from lots of different places (a phone,
# a simulator, this sandbox). Narrow this to the app's real domain once
# there's a production app to protect and something worth protecting it
# from (e.g. a competitor scraping this API instead of the chains' own
# sites).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# Finds the cheapest CURRENT price per store for a shared category, e.g.
# "Milk". Written as: first narrow down to just the listings in that
# category (a few hundred rows at most), THEN look up only those listings'
# latest price -- rather than sorting the entire, ever-growing
# price_observation table on every request. The LATERAL join lets Postgres
# use the existing (listing_id, observed_at DESC) index to fetch each
# listing's newest row directly, instead of scanning history it doesn't
# need.
CHEAPEST_PER_CATEGORY_SQL = """
    WITH category_listings AS (
        SELECT
            l.id AS listing_id,
            o.store_id,
            s.name AS store_name,
            s.short_code,
            s.color,
            o.id AS outlet_id,
            o.name AS outlet_name,
            l.chain_product_name
        FROM listing l
        JOIN outlet o ON o.id = l.outlet_id
        JOIN store s ON s.id = o.store_id
        WHERE l.shopping_category = %s
    )
    SELECT
        cl.store_id,
        cl.store_name,
        cl.short_code,
        cl.color,
        cl.outlet_id,
        cl.outlet_name,
        cl.chain_product_name,
        latest.price,
        latest.price_per_unit,
        latest.price_per_unit_measure,
        latest.observed_at
    FROM category_listings cl
    JOIN LATERAL (
        SELECT price, price_per_unit, price_per_unit_measure, observed_at
        FROM price_observation po
        WHERE po.listing_id = cl.listing_id
        ORDER BY po.observed_at DESC
        LIMIT 1
    ) latest ON TRUE
    WHERE latest.price IS NOT NULL
    ORDER BY cl.store_id, latest.price ASC
"""


@app.get("/health")
def health():
    """
    A trivial endpoint with no real data in it -- lets you (or, later, an
    automated check) confirm the server is running AND can reach the
    database, separately from any real feature actually working.
    """
    conn = get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return {"status": "ok"}
    finally:
        get_pool().putconn(conn)


def group_cheapest_per_store(rows):
    """
    Pure logic, deliberately kept separate from the database call above it:
    given the raw rows the SQL query returns (already ordered cheapest-first
    within each store), collapse them down to one entry per store -- its
    single cheapest current listing in this category.

    Kept as a standalone function (rather than inlined into the endpoint)
    specifically so it can be unit-tested with plain Python data, without
    needing a real database connection.
    """
    by_store = {}
    for (
        store_id,
        store_name,
        short_code,
        color,
        outlet_id,
        outlet_name,
        product_name,
        price,
        price_per_unit,
        price_per_unit_measure,
        observed_at,
    ) in rows:
        # Rows arrive cheapest-first within each store (see the SQL's
        # ORDER BY), so the first time a store_id shows up here is already
        # its cheapest current listing in this category.
        if store_id in by_store:
            continue
        by_store[store_id] = {
            "store_id": store_id,
            "store_name": store_name,
            "short_code": short_code,
            "color": color,
            "outlet_id": outlet_id,
            "outlet_name": outlet_name,
            "product_name": product_name,
            "price": float(price),
            "price_per_unit": (
                float(price_per_unit) if price_per_unit is not None else None
            ),
            "price_per_unit_measure": price_per_unit_measure,
            "observed_at": observed_at.isoformat(),
        }

    return sorted(by_store.values(), key=lambda s: s["price"])


@app.get("/categories/{category}/prices")
def category_prices(category: str):
    """
    The cheapest current price for a shared category (e.g. "Milk"), at
    each store that carries it right now.

    Returns the single cheapest listing PER STORE, not per outlet -- if a
    chain has three branches, this collapses to whichever of the three
    currently has the lowest price, since "which store is cheapest for
    milk" is the question a shopper is actually asking, not "which exact
    branch."
    """
    conn = get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(CHEAPEST_PER_CATEGORY_SQL, (category,))
            rows = cur.fetchall()
    finally:
        get_pool().putconn(conn)

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No listings found for category '{category}'.",
        )

    stores = group_cheapest_per_store(rows)

    return {
        "category": category,
        "cheapest": stores[0],
        "by_store": stores,
    }
