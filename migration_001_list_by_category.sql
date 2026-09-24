-- ============================================================================
-- Migration: let a shopping-list item be "a category" (e.g. "Milk"), not
-- only "a specific matched product".
-- ============================================================================
-- Why this is needed: app_list_item was originally built to reference
-- product(id) -- our own cross-chain-matched idea of "one real product".
-- But product matching is still partial (it was de-prioritized after the
-- shared-category system proved good enough for comparing prices), while
-- listing.shopping_category is reliably populated for ~85% of listings.
-- The app's own design also works this way: "My list" lets you add "Milk",
-- not a specific barcode.
--
-- What this does:
--   1. Makes app_list_item.product_id OPTIONAL (it was NOT NULL before).
--   2. Adds a new shopping_category column, also optional.
--   3. Adds a check so every row has EXACTLY ONE of the two set -- never
--      both, never neither -- so the two ways of referring to "an item"
--      can never silently disagree with each other.
--
-- Safe to run even though app_list_item has never had real rows in it yet
-- (nothing built wrote to it before now) -- this is here mainly so the
-- change is recorded and repeatable, the same way schema.sql itself is.
--
-- Run this ONCE, in Neon's SQL editor, the same way schema.sql was run.
-- ============================================================================

ALTER TABLE app_list_item
    ALTER COLUMN product_id DROP NOT NULL;

ALTER TABLE app_list_item
    ADD COLUMN shopping_category TEXT;

ALTER TABLE app_list_item
    ADD CONSTRAINT app_list_item_exactly_one_kind
    CHECK (
        (product_id IS NOT NULL AND shopping_category IS NULL)
        OR
        (product_id IS NULL AND shopping_category IS NOT NULL)
    );

-- Powers "does this list already have Milk on it" without scanning the
-- whole table.
CREATE INDEX idx_app_list_item_list_category
    ON app_list_item (list_id, shopping_category);
