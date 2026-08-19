"""
Xirja -- watches the schedule file written by plan_crawl_schedule.py and
starts the real crawl workflow when one of its planned random moments
arrives.

Why this needs to exist at all, rather than the crawl workflow just
watching its own schedule directly: GitHub Actions' `schedule:` trigger
only understands fixed, repeating cron expressions -- it has no way to say
"run at this one specific, different-every-week moment". So this script is
the thing that actually watches the clock; when a planned moment is due,
it starts the real crawl workflow (crawl-greens.yml / crawl-pavipama.yml)
via GitHub's own "workflow_dispatch" trigger -- the exact same mechanism
as clicking "Run workflow" by hand.

Run by poll-crawl-schedule.yml, every 15 minutes, for each chain that uses
randomized scheduling. On almost every run (roughly 92 of the 96 checks a
day) nothing is due, and that's the expected, normal outcome -- not a
problem.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

SCHEDULE_DIR = ".github/schedule"

# If a planned moment is found more than this long in the past, it's
# treated as MISSED rather than triggered late -- e.g. if this poller
# itself had a rare outage for a few hours, or GitHub delayed a scheduled
# run (a known, documented possibility for `schedule:` triggers, especially
# during high load). Firing off an hours-late crawl trigger for a
# now-stale "random moment" isn't worth it; a genuinely missed crawl is
# already covered separately by the daily freshness healthcheck.
CATCH_UP_WINDOW = timedelta(hours=3)


def _schedule_path(chain):
    return os.path.join(SCHEDULE_DIR, f"{chain}_schedule.json")


def check_and_trigger(chain, workflow_file, now, runner=None):
    """Reads <chain>_schedule.json, triggers workflow_file for any
    due-and-not-yet-triggered entry, and marks entries triggered/missed as
    appropriate. Returns (updated_data_or_None, actions) where actions is a
    list of ("triggered"|"missed", target_iso_string) tuples for logging.
    `now` and `runner` (a callable taking the same args as
    subprocess.run, defaulting to subprocess.run itself) are both
    parameters specifically so this is testable without touching the real
    clock or actually invoking `gh`."""
    if runner is None:
        runner = subprocess.run

    path = _schedule_path(chain)
    if not os.path.exists(path):
        print(f"  {chain}: no schedule file yet ({path}) -- nothing to check "
              f"(the weekly planner hasn't run yet for this chain)")
        return None, []

    with open(path) as f:
        data = json.load(f)

    actions = []
    changed = False
    for entry in data["runs"]:
        if entry.get("triggered"):
            continue
        target = datetime.fromisoformat(entry["target"])
        if target > now:
            continue  # not due yet

        if now - target > CATCH_UP_WINDOW:
            print(f"  {chain}: missed planned run at {entry['target']} by more "
                  f"than {CATCH_UP_WINDOW} -- marking as missed rather than "
                  f"triggering this late")
            entry["triggered"] = True
            entry["missed"] = True
            changed = True
            actions.append(("missed", entry["target"]))
            continue

        print(f"  {chain}: planned run at {entry['target']} is due now -- "
              f"triggering {workflow_file}")
        runner(["gh", "workflow", "run", workflow_file], check=True)
        entry["triggered"] = True
        changed = True
        actions.append(("triggered", entry["target"]))

    return (data if changed else None), actions


def main():
    if len(sys.argv) != 3:
        print("Usage: check_and_trigger_crawl.py <chain-name> <workflow-file>", file=sys.stderr)
        sys.exit(1)
    chain, workflow_file = sys.argv[1], sys.argv[2]

    now = datetime.now(timezone.utc)
    updated, actions = check_and_trigger(chain, workflow_file, now)

    if updated is not None:
        with open(_schedule_path(chain), "w") as f:
            json.dump(updated, f, indent=2)
            f.write("\n")

    if not actions:
        print(f"  {chain}: nothing due right now")

    # Deliberately always exits 0 -- "nothing due yet" is the expected
    # outcome on nearly every run, not a failure. If `gh workflow run`
    # itself fails (e.g. a real permissions problem), that exception
    # propagates up and DOES fail this run loudly, on purpose -- a crawl
    # that was due and silently never got triggered is exactly the kind of
    # thing that should show up as a red X.


if __name__ == "__main__":
    main()
