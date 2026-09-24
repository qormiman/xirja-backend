"""
Xirja -- price API.

What this does, in plain terms:
  A small web server that sits between the app (on someone's phone) and the
  database. The phone app is never allowed to talk to Postgres directly --
  that would mean shipping your database password inside the app, which
  anyone who downloaded the app could then read out. Instead, the app calls
  this server over a normal web address, and this server is the only thing
  that ever holds the real database credentials.

  Started with exactly one endpoint -- the minimum needed to prove the whole
  chain works end to end: real prices, from the real database, reachable
  over the internet. This now adds the second real feature: a genuinely
  usable shopping list (add an item by category, see its cheapest current
  price, remove it, change quantity) -- the previous "My list" screen only
  showed 4 hardcoded categories with no way to change them.

  Still ahead: browsing by category, the price-correction workflow. Add
  those the same way this one was added -- one proven slice at a time.

Run locally:
    cd api
    pip install -r requirements.txt
    export DATABASE_URL="postgres://...same one the crawlers use..."
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

  Then open http://127.0.0.1:8000/docs in a browser -- FastAPI builds that
  page automatically, and it lets you try every endpoint by hand before the
  app ever calls it.

Deploy: see ../SETUP.md -> "Running the API online (Render)" for the
step-by-step walkthrough (no server administration experience needed).
Re-deploying an update: Render redeploys automatically on every push to
this repo's main branch (or every file upload through GitHub's web
interface, which creates a commit the same way) -- nothing extra to do on
Render's side.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
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

# Wide open for now -- every endpoint here is either public shelf-price
# information or a shopping list keyed by a random per-device id with
# nothing personally identifying in it (see "On user_id" below). Narrow
# this to the app's real domain once there's a production app to protect
# and something worth protecting it from (e.g. a competitor scraping this
# API instead of the chains' own sites, or someone guessing another
# device's list id).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)


# ============================================================================
# Shared helpers
# ============================================================================

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


def fetch_cheapest_for_category(cur, category):
    """
    Shared by both /categories/{category}/prices and the list endpoints, so
    "what's the cheapest price for this item" is computed exactly one way
    everywhere in the app -- never two slightly different versions of the
    same logic drifting apart.
    """
    cur.execute(CHEAPEST_PER_CATEGORY_SQL, (category,))
    rows = cur.fetchall()
    if not rows:
        return None
    stores = group_cheapest_per_store(rows)
    return {"cheapest": stores[0], "by_store": stores}


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
            result = fetch_cheapest_for_category(cur, category)
    finally:
        get_pool().putconn(conn)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No listings found for category '{category}'.",
        )

    return {"category": category, **result}


@app.get("/stores")
def list_stores():
    """
    Every real store (Greens, PAVI PAMA, Welbee's), regardless of whether
    it happens to carry anything currently on a given list. The Compare
    screen needs this rather than deriving "which stores exist" from a
    list's own items, since a store carrying NONE of today's items should
    still show up in the comparison (as "everything bought elsewhere"),
    not silently vanish from the ranking.
    """
    conn = get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, short_code, color FROM store ORDER BY name ASC")
            rows = cur.fetchall()
    finally:
        get_pool().putconn(conn)

    return {
        "stores": [
            {"store_id": sid, "name": name, "short_code": short_code, "color": color}
            for sid, name, short_code, color in rows
        ]
    }


@app.get("/categories")
def list_categories():
    """
    Every shared category that currently has at least one real, in-stock
    price behind it, with how many stores carry it -- what the app's "add
    an item" screen searches/browses against. Deliberately reads from real
    listing + price data (not a fixed list somewhere in code), so it can
    never show a category that would then come back empty when added to a
    list.
    """
    sql = """
        SELECT l.shopping_category, COUNT(DISTINCT o.store_id) AS store_count
        FROM listing l
        JOIN outlet o ON o.id = l.outlet_id
        JOIN LATERAL (
            SELECT 1 FROM price_observation po
            WHERE po.listing_id = l.id
            ORDER BY po.observed_at DESC
            LIMIT 1
        ) latest ON TRUE
        WHERE l.shopping_category IS NOT NULL
        GROUP BY l.shopping_category
        ORDER BY l.shopping_category ASC
    """
    conn = get_pool().getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    finally:
        get_pool().putconn(conn)

    return {
        "categories": [
            {"category": name, "store_count": count} for name, count in rows
        ]
    }


# ============================================================================
# Shopping list
# ============================================================================
#
# On user_id: there's no real login system yet (the spec always intended
# accounts to come later). Until then, the app generates one random id the
# first time it opens and keeps it on the phone -- see the app's own code
# for exactly how. That id is meaningless outside "which rows in app_list
# belong together" -- it's not an email, a name, or anything else personal.
# This is a deliberate, documented shortcut, not an oversight: swap it for
# a real logged-in user_id later without changing anything about how lists
# or items are stored.


class AddItemBody(BaseModel):
    category: str = Field(..., min_length=1)
    quantity: float = Field(default=1, gt=0)


class UpdateItemBody(BaseModel):
    quantity: float = Field(..., gt=0)


def get_or_create_list(cur, user_id: str):
    cur.execute("SELECT id FROM app_list WHERE user_id = %s LIMIT 1", (user_id,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO app_list (user_id) VALUES (%s) RETURNING id", (user_id,)
    )
    return cur.fetchone()[0]


def serialize_items(cur, list_id):
    cur.execute(
        """
        SELECT id, shopping_category, quantity
        FROM app_list_item
        WHERE list_id = %s
        ORDER BY id
        """,
        (list_id,),
    )
    rows = cur.fetchall()

    items = []
    for item_id, category, quantity in rows:
        priced = fetch_cheapest_for_category(cur, category)
        items.append(
            {
                "item_id": str(item_id),
                "category": category,
                "quantity": float(quantity),
                # None when nothing's currently in stock/priced anywhere for
                # this category -- the app shows "no price found" for this,
                # same wording as the old hardcoded screen used.
                "cheapest": priced["cheapest"] if priced else None,
                "by_store": priced["by_store"] if priced else [],
            }
        )
    return items


@app.get("/lists/{user_id}")
def get_list(user_id: str):
    """
    Returns this user's list (creating an empty one the very first time
    they're seen), with each item's real, current cheapest price attached
    -- the app never has to make a second round-trip per item.
    """
    conn = get_pool().getconn()
    try:
        with conn.cursor() as cur:
            list_id = get_or_create_list(cur, user_id)
            items = serialize_items(cur, list_id)
        conn.commit()
    finally:
        get_pool().putconn(conn)

    return {"list_id": str(list_id), "items": items}


@app.post("/lists/{user_id}/items")
def add_item(user_id: str, body: AddItemBody):
    """
    Adds a category to the list. If it's already on there, this bumps the
    existing row's quantity instead of creating a duplicate row for the
    same category -- "add Milk" twice should mean "2 milk", not two
    separate Milk rows.
    """
    conn = get_pool().getconn()
    try:
        with conn.cursor() as cur:
            list_id = get_or_create_list(cur, user_id)

            cur.execute(
                """
                SELECT id, quantity FROM app_list_item
                WHERE list_id = %s AND shopping_category = %s
                """,
                (list_id, body.category),
            )
            existing = cur.fetchone()
            if existing:
                item_id, current_qty = existing
                cur.execute(
                    "UPDATE app_list_item SET quantity = %s WHERE id = %s",
                    (float(current_qty) + body.quantity, item_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO app_list_item (list_id, shopping_category, quantity)
                    VALUES (%s, %s, %s)
                    """,
                    (list_id, body.category, body.quantity),
                )

            items = serialize_items(cur, list_id)
        conn.commit()
    finally:
        get_pool().putconn(conn)

    return {"list_id": str(list_id), "items": items}


@app.patch("/lists/{user_id}/items/{item_id}")
def update_item(user_id: str, item_id: str, body: UpdateItemBody):
    """Changes an item's quantity. To remove an item entirely, use DELETE."""
    conn = get_pool().getconn()
    try:
        with conn.cursor() as cur:
            list_id = get_or_create_list(cur, user_id)
            cur.execute(
                """
                UPDATE app_list_item SET quantity = %s
                WHERE id = %s AND list_id = %s
                """,
                (body.quantity, item_id, list_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Item not found on this list.")
            items = serialize_items(cur, list_id)
        conn.commit()
    finally:
        get_pool().putconn(conn)

    return {"list_id": str(list_id), "items": items}


@app.delete("/lists/{user_id}/items/{item_id}")
def remove_item(user_id: str, item_id: str):
    conn = get_pool().getconn()
    try:
        with conn.cursor() as cur:
            list_id = get_or_create_list(cur, user_id)
            cur.execute(
                "DELETE FROM app_list_item WHERE id = %s AND list_id = %s",
                (item_id, list_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Item not found on this list.")
            items = serialize_items(cur, list_id)
        conn.commit()
    finally:
        get_pool().putconn(conn)

    return {"list_id": str(list_id), "items": items}
