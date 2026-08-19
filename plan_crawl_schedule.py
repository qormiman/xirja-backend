"""
Xirja -- weekly schedule PLANNER for Greens' and PAVI PAMA's randomized
crawl times.

What this does, in plain terms: picks 2 random days out of the next 7, and
for each a random time within a low-traffic overnight window, and writes
them into .github/schedule/<chain>_schedule.json. A separate script,
check_and_trigger_crawl.py, runs frequently (every 15 minutes) and watches
that file for when one of these planned moments arrives, then actually
starts that chain's crawl.

Why randomized instead of a fixed nightly cron time: crawling at the exact
same moment every night is an easy pattern to notice. A schedule that's
different every single week -- different days, different times -- has no
fixed pattern to notice at all. This mirrors the same idea already applied
to Welbee's crawler, which runs from a home computer instead of here and
has its own separate version of this same logic (see
plan_welbees_schedule.ps1 in that crawler's local setup files) -- the
reasoning is identical, just implemented differently because GitHub
Actions' own scheduler (unlike Windows' Task Scheduler) can't create a new
one-off appointment on the fly; see poll-crawl-schedule.yml's own comment
for how that gap is bridged here.

Run by plan-crawl-schedule.yml, once a week automatically for each chain
(Greens, PAVI PAMA), or by hand via that workflow's "Run workflow" button
to force an early re-roll.
"""
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone

SCHEDULE_DIR = ".github/schedule"

# Evening window candidates run from 19:00 UTC through 23:59 UTC -- roughly
# 9pm-2am Malta time in summer, similar low-traffic hours to the fixed
# 23:00 UTC time this replaces, just spread out across a window instead of
# pinned to one exact minute. Deliberately kept WITHIN one calendar day
# (doesn't cross midnight) so "2 distinct days" always means 2 genuinely
# distinct calendar dates, with no risk of a late-window pick on one day
# rolling into the same date as the next day's pick.
WINDOW_START_HOUR_UTC = 19
WINDOW_SPAN_MINUTES = 5 * 60  # 19:00 up to (not including) 24:00


def plan_two_random_runs(now):
    """Returns two distinct, randomly chosen datetimes (UTC, timezone-aware)
    within the next 7 days, each falling somewhere in the low-traffic
    overnight window, sorted earliest-first. `now` is passed in (rather
    than read internally) so this is testable without depending on the
    real clock."""
    day_offsets = random.sample(range(1, 8), 2)  # 2 distinct days, 1-7 days out
    runs = []
    for offset in sorted(day_offsets):
        base_day = (now + timedelta(days=offset)).date()
        window_start = datetime(
            base_day.year, base_day.month, base_day.day,
            WINDOW_START_HOUR_UTC, 0, 0, tzinfo=timezone.utc,
        )
        minutes_in = random.randint(0, WINDOW_SPAN_MINUTES - 1)
        runs.append(window_start + timedelta(minutes=minutes_in))
    return runs


def write_schedule(chain, now, runs):
    os.makedirs(SCHEDULE_DIR, exist_ok=True)
    path = os.path.join(SCHEDULE_DIR, f"{chain}_schedule.json")
    data = {
        "planned_at": now.isoformat(),
        "runs": [{"target": r.isoformat(), "triggered": False} for r in runs],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return path


def main():
    if len(sys.argv) != 2:
        print("Usage: plan_crawl_schedule.py <chain-name>", file=sys.stderr)
        sys.exit(1)
    chain = sys.argv[1]

    now = datetime.now(timezone.utc)
    runs = plan_two_random_runs(now)
    path = write_schedule(chain, now, runs)

    print(f"Planned {chain}'s next 2 crawl times (written to {path}):")
    for r in runs:
        print(f"  {r.isoformat()}")


if __name__ == "__main__":
    main()
