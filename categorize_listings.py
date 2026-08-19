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
    unclassified (store, chain_category) combinations at the end, with a
    few real product name examples per bucket, so gaps are visible (and
    diagnosable) instead of silent. Use that tally and its examples to add
    more keywords to category_taxonomy.py's KEYWORD_RULES over time.

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
from category_taxonomy import classify_listing, matching_categories_by_name, KNOWN_ACCEPTED_COLLISIONS
from github_issue_notify import flag as flag_issue, resolve as resolve_issue

# 20 Aug 2026 -- stable title used to dedup GitHub issues across runs, see
# github_issue_notify.py's own docstring for why this needs to be an exact,
# unchanging string rather than something with a count baked in (a title
# with "12 listings" in it would never match next run's "14 listings" and
# a new issue would open every single time).
UNCLASSIFIED_ISSUE_TITLE = "Categorize listings: unclassified items need new keyword rules"


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

    Also skips a pair entirely when it's listed in category_taxonomy.py's
    KNOWN_ACCEPTED_COLLISIONS -- a real product that genuinely, correctly
    matches both categories at once (e.g. "chicken & salmon" cat food),
    already individually reviewed and decided, not a bug. Still counted
    (see accepted_counts below) so nothing is silently hidden, just not
    re-printed with examples every single run -- see that constant's own
    comment for the full reasoning and the 17 Aug 2026 feedback behind it.

    Returns (pair_counts, pair_examples, accepted_counts): pair_counts maps
    a sorted (category_a, category_b) tuple to how many listings triggered
    it; pair_examples maps the same tuple to up to 3 real product names, so
    the report below can show *why* a pair is flagged, not just that it
    was; accepted_counts maps a KNOWN_ACCEPTED_COLLISIONS pair to how many
    listings it matched, for the single compact summary line in main()."""
    pair_counts = Counter()
    pair_examples = {}
    accepted_counts = Counter()

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
            if frozenset(pair) in KNOWN_ACCEPTED_COLLISIONS:
                accepted_counts[pair] += 1
                continue
            pair_counts[pair] += 1
            examples = pair_examples.setdefault(pair, [])
            if len(examples) < 3 and name not in examples:
                examples.append(name)

    return pair_counts, pair_examples, accepted_counts


def categorize_all(conn, cur):
    listings = fetch_listings(cur)

    to_update = []
    unclassified_tally = {}
    unclassified_examples = {}
    # Every distinct unclassified product name, not just the 8 examples per
    # bucket that get printed. The printed report is for a human skimming the
    # Actions log; this full list is what actually lets a whole bucket be
    # closed in one pass instead of eight names at a time. Written out to
    # UNCLASSIFIED_EXPORT_PATH at the end of the run and uploaded by the
    # workflow as a downloadable file. A set (not a list) because the same
    # product appears once per outlet -- 129,703 listings collapse to far
    # fewer distinct names, which is the thing worth reading.
    unclassified_names = set()
    classified_count = 0
    unchanged_count = 0

    for row in listings:
        new_category = classify_listing(row["store_id"], row["chain_category"], row["chain_product_name"])

        if new_category is None:
            key = (row["store_id"], row["chain_category"])
            unclassified_tally[key] = unclassified_tally.get(key, 0) + 1
            # A few real product names per bucket, same idea as
            # collision_examples above -- the tally alone (e.g. "3271
            # welbees / 'Food Cupboard'") gives no way to tell which
            # keywords are missing. Capped at 8 (not 3) so large, diverse
            # catch-all buckets -- "Food Cupboard", "Health & Beauty" --
            # give enough real names to actually close the gap in one or
            # two rounds instead of dribbling out 3 at a time; small
            # buckets are unaffected since they simply run out of distinct
            # names before hitting the cap. Deduped so one repeated
            # product doesn't waste a slot. Raised from 3 to 8 on 18 Aug
            # 2026 after the first full-production run showed 3 wasn't
            # enough signal for buckets in the thousands.
            name = row["chain_product_name"]
            examples = unclassified_examples.setdefault(key, [])
            if name and len(examples) < 8 and name not in examples:
                examples.append(name)
            if name:
                unclassified_names.add((row["store_id"], row["chain_category"] or "", name))

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
    collision_pairs, collision_examples, accepted_collisions = find_category_collisions(listings)

    return {
        "total": len(listings),
        "updated": updated,
        "unchanged": unchanged_count,
        "newly_classified": classified_count,
        "unclassified_tally": unclassified_tally,
        "unclassified_examples": unclassified_examples,
        "unclassified_names": unclassified_names,
        "collision_pairs": collision_pairs,
        "collision_examples": collision_examples,
        "accepted_collisions": accepted_collisions,
    }


UNCLASSIFIED_EXPORT_PATH = "unclassified_listings.txt"


def write_unclassified_export(unclassified_names, path=UNCLASSIFIED_EXPORT_PATH):
    """
    Writes every distinct unclassified product name to a plain text file,
    grouped by (store, chain category) and alphabetically sorted within each
    group.

    Why this exists: the printed report caps each bucket at 8 example names.
    That is fine for a bucket of 12, and useless for a bucket of 3,050 --
    you close 8 names, run again three days later, and get 8 more. This file
    is the whole list, so a bucket can actually be worked through in one
    sitting. The workflow uploads it as a downloadable artifact.

    Deliberately plain text with no counts or extra columns: the point is to
    be readable, greppable, and small enough to hand to someone (or paste
    into a chat) whole.
    """
    grouped = {}
    for store_id, chain_category, name in unclassified_names:
        grouped.setdefault((store_id, chain_category), []).append(name)

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(
            f"{sum(len(v) for v in grouped.values())} distinct unclassified "
            f"product name(s), across {len(grouped)} (store, chain category) "
            "group(s).\n"
        )
        for (store_id, chain_category), names in sorted(
            grouped.items(), key=lambda kv: (-len(kv[1]), kv[0])
        ):
            handle.write(f"\n=== {store_id} / {chain_category!r} -- {len(names)} name(s) ===\n")
            for name in sorted(names):
                handle.write(f"{name}\n")

    return path


def _connect_and_categorize():
    conn = get_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        summary = run_with_timeout(
            lambda: categorize_all(conn, cur),
            DB_WRITE_HARD_TIMEOUT_SECONDS,
        )
    return conn, summary


def main():
    conn = None
    try:
        try:
            conn, summary = _connect_and_categorize()
        except psycopg2.OperationalError:
            # Same real issue already found and fixed in api/main.py's
            # run_query(): Neon's free tier puts the database to sleep
            # after a few idle minutes, and this script leaves a real gap
            # between its one big SELECT (fetch_listings) and its first
            # WRITE -- re-classifying every listing in memory, now against
            # a much bigger keyword list than when this script was first
            # written, can itself take a couple of minutes with no
            # database traffic at all. If Neon suspends the connection
            # during that gap, the next query raises "OperationalError:
            # SSL connection has been closed unexpectedly" -- seen for
            # real on 24 Aug 2026's first automatic run.
            #
            # Discard the dead connection and retry the *entire* run
            # exactly once with a fresh one, which forces Neon to wake
            # back up. Redoing the whole thing (not just the failed write)
            # is safe and correct here: categorize_all() is idempotent by
            # design (see this module's own docstring -- safe to run as
            # often as you like, it only ever writes rows whose category
            # actually changed), so there's no risk of double-writing or
            # skipping anything by starting over.
            if conn is not None:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001 -- already dead, nothing to clean up
                    pass
                conn = None
            print("(lost the database connection mid-run -- Neon's free tier likely put it to "
                  "sleep -- retrying the whole run once with a fresh connection)", file=sys.stderr)
            conn, summary = _connect_and_categorize()

        export_path = write_unclassified_export(summary["unclassified_names"])

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
                for example in summary["unclassified_examples"].get((store_id, chain_category), []):
                    print(f"             e.g. {example!r}")
            print(f"\n  The COMPLETE list of every distinct unclassified product name (not just "
                  f"the 8 examples shown per bucket above) has been written to {export_path} -- "
                  "download it from this run's 'Artifacts' section at the bottom of the Actions "
                  "summary page. That file is what makes it possible to close a whole bucket in "
                  "one pass.")

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

        accepted_collisions = summary["accepted_collisions"]
        if accepted_collisions:
            # A compact summary only, no examples -- these pairs are
            # already individually reviewed and decided (see
            # category_taxonomy.py's KNOWN_ACCEPTED_COLLISIONS), so
            # there's nothing new here to look at every run. Still printed
            # in full (not truncated) so the count stays honest.
            total_accepted = sum(accepted_collisions.values())
            print(f"\n  {total_accepted} more listing(s) matched a KNOWN, already-reviewed category pair "
                  f"(dual-protein meat products, almond milk, etc) -- not shown individually since these "
                  f"are decided, not bugs. See category_taxonomy.py's KNOWN_ACCEPTED_COLLISIONS for the "
                  f"full list and reasoning. Breakdown:")
            ranked_accepted = sorted(accepted_collisions.items(), key=lambda kv: kv[1], reverse=True)
            for (category_a, category_b), count in ranked_accepted:
                print(f"    {count:>5}  {category_a} / {category_b}")

        if total_unclassified > 0:
            # 20 Aug 2026 -- changed from "exit non-zero so the run shows
            # as failed" to this. Reasoning: categorizing itself always
            # succeeded here -- nothing actually went wrong -- so a red X
            # was misleading (it looked like the workflow was broken, not
            # like "some listings need new keyword rules"). This still
            # gets a human's attention the same way as before (a GitHub
            # notification email), just via an issue instead of a failed
            # run -- see github_issue_notify.py's own docstring for the
            # full reasoning and how it avoids opening a duplicate issue
            # every single run. The run now exits 0 (green) either way;
            # everything above this point (the categorize step itself, the
            # full unclassified-listings.txt export) has already completed
            # and been written regardless.
            top_ranked = sorted(summary["unclassified_tally"].items(), key=lambda kv: kv[1], reverse=True)[:10]
            top_lines = "\n".join(f"- {count} x {store_id} / {chain_category!r}"
                                   for (store_id, chain_category), count in top_ranked)
            flag_issue(
                UNCLASSIFIED_ISSUE_TITLE,
                f"{total_unclassified} listing(s) are still unclassified after this run.\n\n"
                f"Top (store, chain_category) groups by how many listings they affect:\n{top_lines}\n\n"
                f"See this run's log for the full report (every group, with example product "
                f"names), and the unclassified_listings.txt artifact on the run for the complete "
                f"list of distinct product names -- that's what makes it possible to close a "
                f"whole group in one pass by adding keywords to category_taxonomy.py's "
                f"KEYWORD_RULES.",
            )
        else:
            # Nothing unclassified this run -- if an issue from an earlier
            # run is still open, this closes it automatically so it
            # doesn't sit open forever after the gap's already been
            # closed by adding keyword rules.
            resolve_issue(
                UNCLASSIFIED_ISSUE_TITLE,
                "This run found 0 unclassified listings -- looks resolved.",
            )
    except Exception as exc:  # noqa: BLE001 -- surface any failure plainly, then exit non-zero
        # Real bug found on 24 Aug 2026: if the connection is already dead
        # (e.g. the OperationalError above, on its second/final attempt),
        # conn.rollback() itself raises "InterfaceError: connection
        # already closed" -- which then replaces the real error in the
        # traceback with a confusing, unrelated-looking second one. Guard
        # it so a dead connection can't mask the actual failure.
        if conn is not None:
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001 -- connection may already be dead; nothing more to do
                pass
        print(f"ERROR during categorization: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 -- already closed/dead is fine here
                pass


if __name__ == "__main__":
    main()
