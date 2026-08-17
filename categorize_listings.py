"""
Xirja -- shared shopping-category classifier.

What this does, in plain terms:
  This fills in listing.shopping_category for every listing in the
  database, using the rules in category_taxonomy.py. This is a DIFFERENT,
  simpler idea than product_matcher.py's cross-chain product matching:
  product_matcher.py tries to work out that "Coca Cola 2L" at Greens and
  "Coca-Cola 2 Litre" at PAVI PAMA are the exact same physical product.
  This script only works out that both of them are "Carbonated Drinks" --
  a much coarser, much more reliable question, and the one the shopping-list
  feature actually needs (see SETUP.md's "Category normalization" section
  for the full reasoning behind this).

  It's read-only towards the outside world -- it never touches any of the
  three sites, it only reads and updates your own database.

Safe to run as often as you like. It re-classifies every listing every run
(not just new ones), so improving category_taxonomy.py's rules and running
this again will re-categorize everything with the improved rules -- but it
only ever writes rows whose category actually changed, to keep each run
cheap.

Known limitations, worth knowing about before trusting the output blindly:
  - This is a first-draft taxonomy (see the top of category_taxonomy.py) --
    some category assignments are reasonable approximations, not perfect
    fits, and are noted inline there.
  - The keyword classifier (used for all of Welbee's, plus Greens' two big
    catch-all buckets and a few others) can only classify what it has a
    keyword for. Anything it doesn't recognise is left NULL rather than
    guessed at -- this script prints a tally of the most common
    unclassified (store, chain_category) combinations at the end, so gaps
    are visible instead of silent. Use that tally to add more keywords to
    category_taxonomy.py's KEYWORD_RULES over time.

How to run it:
  See SETUP.md's "Category normalization" section. In short: set
  DATABASE_URL, then run `python categorize_listings.py`. No browser, no
  network access to any of the three sites -- this only talks to your
  database. Also runnable by hand from the GitHub Actions "Categorize
  listings" workflow.

  Before the first run, you need to add the shopping_category column to
  your existing database once -- see the ALTER TABLE statement in
  SETUP.md's "Category normalization" section (also included permanently
  in schema.sql for anyone setting up a fresh database from now on).
"""
import itertools
import sys
from collections import Counter

import psycopg2.extras

from product_matcher import (
    DB_WRITE_HARD_TIMEOUT_SECONDS,
    WRITE_BATCH_SIZE,
    _chunks,
    _run_batch,
    get_connection,
    run_with_timeout,
)
from category_taxonomy import classify_listing, matching_categories_by_name


def fetch_listings(cur):
    cur.execute(
        """
        SELECT listing.id, outlet.store_id, listing.chain_category,
               listing.chain_product_name, listing.shopping_category
        FROM listing
        JOIN outlet ON outlet.id = listing.outlet_id
        """
    )
    return cur.fetchall()


def _bulk_update_categories(cur, pairs):
    """pairs: [(listing_id, shopping_category), ...]."""
    psycopg2.extras.execute_values(
        cur,
        """
        UPDATE listing AS l SET shopping_category = v.shopping_category
        FROM (VALUES %s) AS v(listing_id, shopping_category)
        WHERE l.id = v.listing_id::uuid
        """,
        pairs,
    )
    return cur.rowcount


def find_category_collisions(listings):
    """Scans every listing's product name for words belonging to more than
    one KEYWORD_RULES category, where the ambiguity is real -- i.e. two or
    more categories are tied at the STRONGEST tier that matched at all --
    exactly the shape every real miscategorization bug found through the
    app so far has had. Purely a report: doesn't read shopping_category,
    doesn't change anything, doesn't affect what gets written to the
    database.

    Only pairs categories tied at the listing's OWN strongest (lowest
    numbered) tier, not just any shared tier -- a weaker match already
    correctly loses to a stronger one by design (e.g. "Extra Virgin Olive
    Oil 1L" also matches bare "oil" and bare "olive" at tier 2, but the
    specific "olive oil" phrase at tier 1 already wins, every time, so
    that's not a real ambiguity). An earlier version of this function got
    this wrong -- it paired categories sharing ANY tier, even when a
    stronger tier already settled the listing -- which made it the single
    biggest source of false positives in the report (649 "Oils / Olives"
    pairs in one real run, all of them already correctly classified as
    Olive Oil). Found and fixed from real data, not guessed.

    Also skips a listing entirely when its strongest tier is 0 (a
    MULTI_KEYWORD_RULES match) -- see the 12 Aug 2026 fix further down for
    why: list order within MULTI_KEYWORD_RULES is itself the deliberate,
    checked-in resolution mechanism (e.g. the "chocolate"+"chips" carve-out
    is listed before the general "chips" rule on purpose), so two tier-0
    matches on the same listing are never a real, unresolved ambiguity --
    classify_by_name already resolves them correctly, every time, by list
    order. This used to be flagged anyway (pure noise): real examples were
    "Lamb Brand Pure Ground Almonds" hitting both the Nuts and Herbs &
    Spices Pass-0 rules, and "M.Busto Organic Apple Cider Vinegar" hitting
    both Vinegars and Ciders -- both already correctly classified, just
    also showing up here as if unresolved. Found by noticing the same
    shape of "noise" pair recurring report after report for categories
    that were never actually broken.

    Returns (pair_counts, pair_examples): pair_counts maps a sorted
    (category_a, category_b) tuple to how many listings triggered it;
    pair_examples maps the same tuple to up to 3 real product names, so
    the report below can show *why* a pair is flagged, not just that it
    was."""
    pair_counts = Counter()
    pair_examples = {}

    for row in listings:
        name = row["chain_product_name"]
        if not name:
            continue
        tiers = matching_categories_by_name(name)
        if len(tiers) < 2:
            continue

        strongest_tier = min(tiers.values())
        if strongest_tier == 0:
            continue
        tied_categories = sorted(category for category, tier in tiers.items() if tier == strongest_tier)
        if len(tied_categories) < 2:
            continue

        for pair in itertools.combinations(tied_categories, 2):
            pair_counts[pair] += 1
            examples = pair_examples.setdefault(pair, [])
            if len(examples) < 3 and name not in examples:
                examples.append(name)

    return pair_counts, pair_examples


def categorize_all(conn, cur):
    listings = fetch_listings(cur)

    to_update = []
    unclassified_tally = {}
    classified_count = 0
    unchanged_count = 0

    for row in listings:
        new_category = classify_listing(row["store_id"], row["chain_category"], row["chain_product_name"])

        if new_category is None:
            key = (row["store_id"], row["chain_category"])
            unclassified_tally[key] = unclassified_tally.get(key, 0) + 1

        if new_category == row["shopping_category"]:
            unchanged_count += 1
            continue

        to_update.append((row["id"], new_category))
        if new_category is not None:
            classified_count += 1

    updated = 0
    for chunk in _chunks(to_update, WRITE_BATCH_SIZE):
        updated += _run_batch(
            conn, lambda chunk=chunk: _bulk_update_categories(cur, chunk), "writing shopping categories"
        ) or 0

    # Read-only report, computed from the same listings already fetched
    # above -- no extra database round trip. See find_category_collisions'
    # docstring for what this is looking for and why.
    collision_pairs, collision_examples = find_category_collisions(listings)

    return {
        "total": len(listings),
        "updated": updated,
        "unchanged": unchanged_count,
        "newly_classified": classified_count,
        "unclassified_tally": unclassified_tally,
        "collision_pairs": collision_pairs,
        "collision_examples": collision_examples,
    }


def main():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            summary = run_with_timeout(
                lambda: categorize_all(conn, cur),
                DB_WRITE_HARD_TIMEOUT_SECONDS,
            )

        total_unclassified = sum(summary["unclassified_tally"].values())
        print(f"Done: {summary['total']} listing(s) checked, {summary['updated']} row(s) written "
              f"(category changed or newly set), {summary['unchanged']} already up to date, "
              f"{total_unclassified} listing(s) still unclassified.")

        if summary["unclassified_tally"]:
            # No cap here -- printed in full, not just the top slice. This
            # used to stop at the top 25, which meant a new batch of gaps
            # only became visible after the current visible ones were
            # fixed, forcing many small rounds instead of one big one.
            # Found via real feedback (17 Aug 2026): the review cycle was
            # taking too long precisely because of this cap.
            print("\n  Unclassified (store, chain_category) combinations, ranked by how often "
                  "they occur -- add keywords for these to category_taxonomy.py's KEYWORD_RULES "
                  "to close the gap:")
            ranked = sorted(summary["unclassified_tally"].items(), key=lambda kv: kv[1], reverse=True)
            for (store_id, chain_category), count in ranked:
                print(f"    {count:>5}  {store_id} / {chain_category!r}")

        collision_pairs = summary["collision_pairs"]
        total_collisions = sum(collision_pairs.values())
        if collision_pairs:
            # Same fix, same reason -- every distinct pair now, not just
            # the top 30.
            print(f"\n  {total_collisions} listing(s) whose name matches keywords from MORE THAN ONE "
                  f"category -- these are the most likely place the next real miscategorization bug is "
                  f"hiding (this is the exact pattern behind every bug found through the app so far). "
                  f"All pairs, ranked by how often they occur:")
            ranked_pairs = sorted(collision_pairs.items(), key=lambda kv: kv[1], reverse=True)
            for (category_a, category_b), count in ranked_pairs:
                examples = summary["collision_examples"][(category_a, category_b)]
                print(f"    {count:>5}  {category_a} / {category_b}")
                for example in examples:
                    print(f"             e.g. {example!r}")
    except Exception as exc:  # noqa: BLE001 -- surface any failure plainly, then exit non-zero
        conn.rollback()
        print(f"ERROR during categorization: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
