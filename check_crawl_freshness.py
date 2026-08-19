"""
Xirja -- crawl freshness healthcheck.

What this does, in plain terms:
  GitHub already emails you when a crawler CRASHES (see each crawler's own
  "on failure" behaviour and the workflow files' failure notifications).
  What that doesn't catch is the sneakier case: a crawler that runs
  "successfully" every night, writes a crawl_run row with status='success',
  but quietly finds zero (or almost zero) prices -- because the site
  changed its HTML, moved behind a login wall, started blocking the
  crawler, or some other silent breakage that isn't a Python exception.
  The app would then keep showing confidently wrong, stale prices with no
  warning at all.

  This script closes that gap. For every outlet this project knows about
  (from the `outlet` table), it looks at the most recent crawl_run and
  flags anything that looks wrong:
    - no crawl_run has EVER been recorded for this outlet
    - the most recent crawl_run finished more than STALE_AFTER_HOURS ago
      (default 48, matching the original spec's own number)
    - the most recent crawl_run "succeeded" (status success/partial) but
      wrote a suspiciously low item_count -- MIN_HEALTHY_ITEM_COUNT is
      deliberately conservative (10) rather than tuned to each chain's
      usual size, since the point here is only to catch "basically found
      nothing", not to police exact volumes
    - the most recent crawl_run is still sitting in status='running' from
      more than STALE_AFTER_HOURS ago -- almost certainly means the job
      got killed/timed out without ever reaching its own finally block
      (crawl_run rows start as 'running' and are only ever updated to
      success/partial/failed at the very end of a crawl -- see e.g.
      welbees_crawler.py's finish_crawl_run())

  It's read-only: this only ever reads crawl_run and outlet, never writes
  anything, and never touches any of the three sites.

Safe to run any time, as often as you like.

How to run it:
  Set DATABASE_URL, then run `python check_crawl_freshness.py`. Also
  runnable from the GitHub Actions "Crawl freshness healthcheck" workflow,
  which runs it once a day.

Exit code:
  Deliberately exits non-zero (after printing the full report) if ANY
  outlet is flagged -- same pattern as categorize_listings.py's "exit
  non-zero so GitHub emails a failure notification" trick, added
  18 Aug 2026. A red X here means "a chain's prices may be going stale",
  not "this script is broken".
"""
import sys
from datetime import datetime, timedelta, timezone

import psycopg2.extras

from product_matcher import get_connection

STALE_AFTER_HOURS = 48
MIN_HEALTHY_ITEM_COUNT = 10


def check_freshness(cur, now=None):
    """Returns a list of (outlet_id, store_id, outlet_name, reason) tuples,
    one per problem found. Empty list means everything looks healthy.
    `now` is injectable for testing; defaults to the real current time.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(hours=STALE_AFTER_HOURS)

    cur.execute("SELECT id, store_id, name FROM outlet ORDER BY id")
    outlets = cur.fetchall()

    problems = []
    for outlet in outlets:
        outlet_id, store_id, outlet_name = outlet["id"], outlet["store_id"], outlet["name"]

        cur.execute(
            """
            SELECT status, started_at, finished_at, item_count, error_message
            FROM crawl_run
            WHERE outlet_id = %s
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (outlet_id,),
        )
        latest = cur.fetchone()

        if latest is None:
            problems.append((outlet_id, store_id, outlet_name,
                              "no crawl_run has ever been recorded for this outlet"))
            continue

        status = latest["status"]
        started_at = latest["started_at"]
        finished_at = latest["finished_at"]
        item_count = latest["item_count"]

        if status == "running":
            if started_at is not None and started_at < stale_cutoff:
                age_hours = (now - started_at).total_seconds() / 3600
                problems.append((outlet_id, store_id, outlet_name,
                                  f"latest crawl_run has been stuck in status='running' for "
                                  f"{age_hours:.0f}h (started {started_at.isoformat()}) -- almost "
                                  f"certainly killed/timed out without finishing cleanly"))
            continue

        if status == "failed":
            # Already covered by the crawler's own GitHub Actions failure
            # notification when this happened -- nothing new to say here.
            continue

        # status is 'success' or 'partial' from here on.
        if finished_at is None:
            problems.append((outlet_id, store_id, outlet_name,
                              f"latest crawl_run has status={status!r} but no finished_at "
                              f"timestamp -- looks like a bug in the crawler's own bookkeeping"))
            continue

        if finished_at < stale_cutoff:
            age_hours = (now - finished_at).total_seconds() / 3600
            problems.append((outlet_id, store_id, outlet_name,
                              f"latest successful crawl finished {age_hours:.0f}h ago "
                              f"({finished_at.isoformat()}), more than {STALE_AFTER_HOURS}h -- "
                              f"this chain hasn't reported fresh prices recently"))
            continue

        if item_count is None or item_count < MIN_HEALTHY_ITEM_COUNT:
            problems.append((outlet_id, store_id, outlet_name,
                              f"latest crawl_run says status={status!r} (finished "
                              f"{finished_at.isoformat()}) but only found item_count="
                              f"{item_count!r} -- looks like a silent breakage (site layout "
                              f"changed, blocked, etc), not a real success"))

    return problems


def main():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            problems = check_freshness(cur)
    finally:
        conn.close()

    if not problems:
        print(f"All outlets have a healthy crawl_run within the last {STALE_AFTER_HOURS}h, "
              f"with a real item count. Nothing to report.")
        return

    print(f"{len(problems)} outlet(s) failed the freshness check:\n")
    for outlet_id, store_id, outlet_name, reason in problems:
        print(f"  {outlet_name} ({store_id} / {outlet_id})")
        print(f"    {reason}\n")

    print("Exiting non-zero so this run shows as \"failed\" and GitHub emails a notification "
          "-- see the reasons above for what to check.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
