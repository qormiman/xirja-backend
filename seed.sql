-- ============================================================================
-- Seed data: the stores and outlets we know about so far.
-- Run this once, after schema.sql, before running the crawler for the first
-- time.
-- ============================================================================

INSERT INTO store (id, name, brand, short_code, color) VALUES
    ('greens', 'Greens Supermarket', 'Greens', 'GR', 'oklch(0.55 0.12 152)');

-- Mriehel's source_code was originally guessed as 'MR' and confirmed wrong
-- by a real crawl (valid token, but zero products in every category) --
-- fixed to 'MH', the real code confirmed via a live DevTools capture with
-- the site's own store switcher set to Mriehel. Swieqi and Gozo's codes are
-- both independently confirmed correct (real products came back for both).
INSERT INTO outlet (id, store_id, name, locality, source_code) VALUES
    ('greens_swieqi',  'greens', 'Greens - Swieqi',  'Swieqi',    'SM'),
    ('greens_mriehel', 'greens', 'Greens - Mriehel', 'Birkirkara','MH'),
    ('greens_gozo',    'greens', 'Greens - Gozo',    'Victoria',  'GZ');

-- PAVI PAMA: confirmed there's no separate Pavi-vs-Pama store distinction --
-- pavipama.com.mt has no store selector while browsing, and checkout only
-- offers a fulfilment choice (delivery, Pama pickup at Mosta, Pavi pickup at
-- Qormi), not a different catalogue or different prices. So this is one
-- shared price list, seeded here as a single outlet rather than two.
INSERT INTO store (id, name, brand, short_code, color) VALUES
    ('pavipama', 'PAVI PAMA', 'PAVI PAMA', 'PP', 'oklch(0.58 0.15 40)');

INSERT INTO outlet (id, store_id, name, locality, source_code) VALUES
    ('pavipama', 'pavipama', 'PAVI PAMA', NULL, 'PP');

-- Welbee's: confirmed (via two real page-source checks, Bakery and Drinks
-- categories) that prices sit in the plain page HTML, with no store
-- selector while browsing and no branch-specific pricing anywhere -- same
-- "one shared price list" situation as PAVI PAMA, now confirmed rather than
-- assumed. Seeded here as a single outlet, same pattern as PAVI PAMA.
INSERT INTO store (id, name, brand, short_code, color) VALUES
    ('welbees', 'Welbee''s Supermarket', 'Welbee''s', 'WB', 'oklch(0.52 0.10 300)');

INSERT INTO outlet (id, store_id, name, locality, source_code) VALUES
    ('welbees', 'welbees', 'Welbee''s', NULL, 'WB');
