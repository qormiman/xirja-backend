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
import sys

import psycopg2.extras

from product_matcher import (
    DB_WRITE_HARD_TIMEOUT_SECONDS,
    WRITE_BATCH_SIZE,
    _chunks,
    _run_batch,
    get_connection,
    run_with_timeout,
)
from category_taxonomy import classify_listing


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

    return {
        "total": len(listings),
        "updated": updated,
        "unchanged": unchanged_count,
        "newly_classified": classified_count,
        "unclassified_tally": unclassified_tally,
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
            print("\n  Most common unclassified (store, chain_category) combinations -- add "
                  "keywords for these to category_taxonomy.py's KEYWORD_RULES to close the gap:")
            ranked = sorted(summary["unclassified_tally"].items(), key=lambda kv: kv[1], reverse=True)
            for (store_id, chain_category), count in ranked[:25]:
                print(f"    {count:>5}  {store_id} / {chain_category!r}")
            if len(ranked) > 25:
                print(f"    ...and {len(ranked) - 25} more distinct combination(s)")
    except Exception as exc:  # noqa: BLE001 -- surface any failure plainly, then exit non-zero
        conn.rollback()
        print(f"ERROR during categorization: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
