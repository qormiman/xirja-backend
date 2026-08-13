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

-- PAVI PAMA and Welbee's are deliberately NOT seeded yet.
--
-- PAVI PAMA: we confirmed the JSON API works, but we captured it with the
-- store filter left blank (the default/combined view). Before crawling for
-- real we still need the actual store codes for Pavi vs Pama specifically --
-- a two-minute check: open pavipama.com.mt, switch the store selector, and
-- read the `store=` value that appears in the network request.
--
-- Welbee's: confirmed prices are in the plain page source, but we haven't
-- captured its branch-selection mechanism yet, and the README notes an open
-- question about whether Welbee's prices differ per branch or are set
-- centrally -- worth confirming before deciding how many outlet rows it needs.
--
-- INSERT INTO store (id, name, brand, short_code, color) VALUES
--     ('pavipama_pavi', 'Pavi', 'PAVI', 'PV', 'oklch(0.55 0.12 250)'),
--     ('pavipama_pama', 'Pama', 'PAMA', 'PM', 'oklch(0.55 0.12 250)'),
--     ('welbees', 'Welbee''s Supermarket', 'Welbee''s', 'WB', 'oklch(0.52 0.10 300)');
