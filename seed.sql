-- ============================================================================
-- Seed data: the stores and outlets we know about so far.
-- Run this once, after schema.sql, before running the crawler for the first
-- time.
-- ============================================================================

INSERT INTO store (id, name, brand, short_code, color) VALUES
    ('greens', 'Greens Supermarket', 'Greens', 'GR', 'oklch(0.55 0.12 152)');

INSERT INTO outlet (id, store_id, name, locality, source_code) VALUES
    ('greens_swieqi',  'greens', 'Greens - Swieqi',  'Swieqi',    'SM'),
    ('greens_mriehel', 'greens', 'Greens - Mriehel', 'Birkirkara','MR'),
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

-- Welbee's is deliberately NOT seeded yet -- confirmed prices are in the
-- plain page source and checkout only asks for a delivery location (no
-- indication of which branch), so it's likely the same "one shared price
-- list" situation as PAVI PAMA -- still needs its own DevTools/API check
-- before we commit to that, the same way we just did for PAVI PAMA.
--
-- INSERT INTO store (id, name, brand, short_code, color) VALUES
--     ('welbees', 'Welbee''s Supermarket', 'Welbee''s', 'WB', 'oklch(0.52 0.10 300)');
