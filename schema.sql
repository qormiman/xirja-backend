-- ============================================================================
-- Xirja database schema
-- ============================================================================
-- Plain-language guide, since this is meant to be readable without a database
-- background:
--
--   store            One row per supermarket chain (Greens, PAVI PAMA, Welbee's).
--   outlet           One row per physical branch. Prices belong to an outlet,
--                    never to a store directly -- "Greens" on its own has no
--                    price, only "Greens, Swieqi" does.
--   product          Our own idea of "one real-world product", shared across
--                    chains once we're confident two listings are the same
--                    thing. Empty/unmatched to start with -- this table only
--                    fills in once product matching (README step 2) happens.
--   listing          One chain's own listing of a product at one outlet, in
--                    that chain's own words. A listing may or may not be
--                    linked to a product yet.
--   price_observation  A single price reading for a listing, with a timestamp.
--                    Never overwritten -- every crawl adds new rows, so we can
--                    show price history and notice a crawler gone quiet.
--   user_price       A shopper's own in-store correction. Private to that
--                    shopper, kept separate from price_observation on purpose.
--   crawl_run        A log of every crawl attempt: when it ran, whether it
--                    worked, how many items it found. This is what powers
--                    "last updated" and staleness warnings in the app.
--
-- Run this file once, in full, against a fresh database (e.g. via Neon's
-- built-in SQL editor in your browser -- no local tools needed).
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto; -- lets Postgres generate UUIDs for us

-- ----------------------------------------------------------------------------
CREATE TABLE store (
    id          TEXT PRIMARY KEY,      -- short internal id, e.g. 'greens'
    name        TEXT NOT NULL,         -- e.g. 'Greens Supermarket'
    brand       TEXT NOT NULL,         -- e.g. 'Greens', 'PAVI', 'PAMA', 'Welbee''s'
    short_code  TEXT NOT NULL,         -- two-letter code for the app UI, e.g. 'GR'
    color       TEXT NOT NULL          -- brand colour token used in the app UI
);

-- ----------------------------------------------------------------------------
CREATE TABLE outlet (
    id           TEXT PRIMARY KEY,     -- e.g. 'greens_swieqi'
    store_id     TEXT NOT NULL REFERENCES store(id),
    name         TEXT NOT NULL,        -- e.g. 'Greens - Swieqi'
    locality     TEXT,                 -- e.g. 'Swieqi'
    source_code  TEXT NOT NULL         -- the code the chain's OWN site uses
                                        -- for this branch, e.g. Greens' 'SM'.
                                        -- This is what the crawler sends back
                                        -- to the chain's site to ask for this
                                        -- branch's prices.
);

-- ----------------------------------------------------------------------------
CREATE TABLE product (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name    TEXT NOT NULL,
    brand             TEXT,
    size_value        NUMERIC,         -- e.g. 0.4
    size_unit         TEXT,            -- normalised: 'kg', 'l', 'piece', ...
    barcode           TEXT,            -- the unambiguous match key, when we have one
    category          TEXT,
    match_confidence  TEXT NOT NULL DEFAULT 'unmatched'
                       -- 'unmatched' | 'low' | 'medium' | 'high' | 'manual'
);

-- ----------------------------------------------------------------------------
CREATE TABLE listing (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id          UUID REFERENCES product(id),  -- NULL until matched
    outlet_id           TEXT NOT NULL REFERENCES outlet(id),
    chain_product_code  TEXT NOT NULL,  -- the chain's own product id/SKU
                                          -- (Greens: PART_NUMBER. PAVI PAMA: id.)
    chain_product_name  TEXT NOT NULL,  -- exactly as the chain names it, unedited
    chain_category      TEXT,           -- the chain's own category label, for reference
    shopping_category   TEXT,           -- OUR shared category, the same across all
                                          -- three chains (e.g. 'Milk', 'Beef',
                                          -- 'Shampoos') -- set by
                                          -- categorize_listings.py, NULL until that's
                                          -- been run at least once. This is what
                                          -- lets the app search "milk" across every
                                          -- chain without needing to know two
                                          -- listings are the exact same product --
                                          -- see category_taxonomy.py and SETUP.md's
                                          -- "Category normalization" section.
    barcode             TEXT,           -- as reported by this chain, if any
    url                 TEXT,
    UNIQUE (outlet_id, chain_product_code)
);

-- Powers "find every listing in this shopping category" -- the core lookup
-- the shopping-list feature needs.
CREATE INDEX idx_listing_shopping_category ON listing (shopping_category);

-- ----------------------------------------------------------------------------
CREATE TABLE price_observation (
    id               BIGSERIAL PRIMARY KEY,
    listing_id       UUID NOT NULL REFERENCES listing(id),
    price            NUMERIC(10,2) NOT NULL,   -- what you'd actually pay right now
    regular_price    NUMERIC(10,2),            -- non-promo price, when it differs from price
    price_per_unit   NUMERIC(10,4),            -- normalised, e.g. price per kg -- nullable
                                                 -- when we can't derive it
    price_per_unit_measure  TEXT,              -- 'kg', 'l', 'piece', etc -- what
                                                 -- price_per_unit is in.
                                                 --
                                                 -- IMPORTANT for whoever builds the app UI:
                                                 -- 'piece' here is a VALUE-COMPARISON figure
                                                 -- only, e.g. price-per-capsule for a box of 16
                                                 -- coffee pods -- it is NOT a real purchasable
                                                 -- price. Nothing is sold one piece at a time;
                                                 -- this exists purely so two different pack
                                                 -- sizes of the same product (e.g. a 16-pack vs
                                                 -- a 36-pack) can be compared, the same way
                                                 -- price-per-kg compares a 1kg bag to a 2kg bag
                                                 -- of something you also only buy whole. Display
                                                 -- it as "€0.24/capsule (for comparison)" or
                                                 -- similar -- never as if it were a real price a
                                                 -- shopper could pay.
    in_stock         BOOLEAN NOT NULL DEFAULT TRUE,
    observed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    source           TEXT NOT NULL DEFAULT 'site'  -- always 'site' here;
                                                      -- shopper corrections live
                                                      -- in user_price instead
);
-- Append-only by convention: the crawler should only ever INSERT here,
-- never UPDATE or DELETE a row, so price history stays honest.

CREATE INDEX idx_price_observation_listing_time
    ON price_observation (listing_id, observed_at DESC);

-- ----------------------------------------------------------------------------
CREATE TABLE user_price (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    product_id  UUID NOT NULL REFERENCES product(id),
    outlet_id   TEXT NOT NULL REFERENCES outlet(id),
    price       NUMERIC(10,2) NOT NULL,
    entered_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    trust       TEXT NOT NULL DEFAULT 'ask'  -- 'mine' | 'site' | 'ask'
);

-- ----------------------------------------------------------------------------
CREATE TABLE crawl_run (
    id             BIGSERIAL PRIMARY KEY,
    store_id       TEXT NOT NULL REFERENCES store(id),
    outlet_id      TEXT NOT NULL REFERENCES outlet(id),
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ,
    status         TEXT NOT NULL DEFAULT 'running', -- 'running' | 'success' | 'partial' | 'failed'
                                                       -- 'partial' = mostly worked, but some
                                                       -- pages failed even after a retry --
                                                       -- see error_message for exactly which
    item_count     INTEGER,
    error_message  TEXT
);

-- ----------------------------------------------------------------------------
-- Not used by the crawler -- these support the app itself and are included
-- now so the schema is complete, per the README's sketch. Safe to leave
-- empty until the frontend needs them.

CREATE TABLE app_list (
    id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id  TEXT NOT NULL,
    name     TEXT NOT NULL DEFAULT 'My list',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE app_list_item (
    id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    list_id   UUID NOT NULL REFERENCES app_list(id),
    product_id UUID NOT NULL REFERENCES product(id),
    quantity  NUMERIC NOT NULL DEFAULT 1
);

CREATE TABLE tick (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    list_item_id UUID NOT NULL REFERENCES app_list_item(id),
    outlet_id   TEXT NOT NULL REFERENCES outlet(id),
    trip_date   DATE NOT NULL DEFAULT CURRENT_DATE,
    ticked_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
