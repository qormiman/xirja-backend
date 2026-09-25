-- Migration 002: store colors as real hex, not oklch()
--
-- `store.color` was seeded with oklch(...) strings (see seed.sql) --
-- perfectly valid CSS, straight from the original browser-based clickable
-- prototype, where every modern browser renders oklch() natively. React
-- Native's own style/color parser does NOT understand oklch() at all: on
-- a real device it silently drops the color instead of erroring, so
-- anywhere the app used a store's color as an actual UI color (Shopping
-- mode's progress bar, item ribbons, store chips, the Compare/Store lists
-- bars) rendered nothing instead of failing loudly -- which is exactly
-- why this went unnoticed until a big, obviously-blank progress bar made
-- it impossible to miss.
--
-- These are the SAME colors, just converted to a format every platform
-- actually understands (OKLCH -> linear sRGB -> sRGB, via the standard
-- OKLab conversion matrices) -- nothing about the app's visual design is
-- meant to change, only whether it actually shows up.
--
-- Run this once in Neon's SQL editor, the same way migration_001 was run.

UPDATE store SET color = '#2e854d' WHERE id = 'greens';    -- was oklch(0.55 0.12 152)
UPDATE store SET color = '#c1552c' WHERE id = 'pavipama';  -- was oklch(0.58 0.15 40)
UPDATE store SET color = '#725b9a' WHERE id = 'welbees';   -- was oklch(0.52 0.10 300)
