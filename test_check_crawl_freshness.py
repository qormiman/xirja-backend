"""
Tests for check_crawl_freshness.py's check_freshness() -- the pure logic
function, no real database or psycopg2 needed. Plain script, same style as
this project's other test_*.py files (a `check()` helper, a pass/fail
tally, printed summary at the end) rather than pytest.
"""
import sys, types, os
from datetime import datetime, timedelta, timezone

# ---- Stub out psycopg2 completely, same pattern used by this project's
# other test_*.py files -- no real database involved. check_crawl_freshness
# imports psycopg2.extras and product_matcher (which imports psycopg2 and
# psycopg2.errors) at module level, so this has to be in place before
# importing it. ----
fake_psycopg2 = types.ModuleType("psycopg2")
fake_extras = types.ModuleType("psycopg2.extras")
fake_errors = types.ModuleType("psycopg2.errors")


class FakeDeadlockDetected(Exception):
    pass


fake_errors.DeadlockDetected = FakeDeadlockDetected


def fake_execute_values(cur, query, argslist, **kwargs):
    cur.last_execute_values = list(argslist)
    cur.rowcount = len(argslist)


class FakeRealDictCursor:
    pass


fake_extras.execute_values = fake_execute_values
fake_extras.RealDictCursor = FakeRealDictCursor
fake_psycopg2.extras = fake_extras
fake_psycopg2.errors = fake_errors
fake_psycopg2.connect = lambda *a, **k: None
fake_psycopg2.OperationalError = type("OperationalError", (Exception,), {})

sys.modules["psycopg2"] = fake_psycopg2
sys.modules["psycopg2.extras"] = fake_extras
sys.modules["psycopg2.errors"] = fake_errors

os.environ["DATABASE_URL"] = "postgres://fake/fake"  # get_connection() reads this; never actually connects here

sys.path.insert(0, "/tmp/xirja/xirja-backend")
from check_crawl_freshness import check_freshness, STALE_AFTER_HOURS, MIN_HEALTHY_ITEM_COUNT

NOW = datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)

OUTLETS = [
    {"id": "greens_swieqi", "store_id": "greens", "name": "Greens - Swieqi"},
    {"id": "greens_mriehel", "store_id": "greens", "name": "Greens - Mriehel"},
    {"id": "greens_gozo", "store_id": "greens", "name": "Greens - Gozo"},
    {"id": "pavipama", "store_id": "pavipama", "name": "PAVI PAMA"},
    {"id": "welbees", "store_id": "welbees", "name": "Welbee's"},
]


class FakeCursor:
    """Answers exactly the two query shapes check_freshness() issues:
    the outlet list, and "most recent crawl_run for this outlet_id".
    `runs_by_outlet` maps outlet_id -> a single fake crawl_run row dict
    (or None for "no crawl_run ever").
    """

    def __init__(self, runs_by_outlet):
        self.runs_by_outlet = runs_by_outlet
        self._last_result = None

    def execute(self, query, params=None):
        if "FROM outlet" in query:
            self._last_result = ("outlets", None)
        elif "FROM crawl_run" in query:
            (outlet_id,) = params
            self._last_result = ("crawl_run", self.runs_by_outlet.get(outlet_id))
        else:
            raise AssertionError(f"unexpected query: {query}")

    def fetchall(self):
        kind, _ = self._last_result
        assert kind == "outlets"
        return OUTLETS

    def fetchone(self):
        kind, row = self._last_result
        assert kind == "crawl_run"
        return row


passed = 0
failed = 0


def check(label, runs_by_outlet, expected_flagged_outlet_ids):
    global passed, failed
    cur = FakeCursor(runs_by_outlet)
    problems = check_freshness(cur, now=NOW)
    got_ids = sorted(p[0] for p in problems)
    expected_ids = sorted(expected_flagged_outlet_ids)
    ok = got_ids == expected_ids
    status = "OK  " if ok else "FAIL"
    print(f"{status} {label}: flagged {got_ids} (expected {expected_ids})")
    if not ok:
        for p in problems:
            print(f"       reason: {p}")
    if ok:
        passed += 1
    else:
        failed += 1


def healthy_run(hours_ago, item_count=500, status="success"):
    return {
        "status": status,
        "started_at": NOW - timedelta(hours=hours_ago, minutes=10),
        "finished_at": NOW - timedelta(hours=hours_ago),
        "item_count": item_count,
        "error_message": None,
    }


# ---- All five outlets healthy: nothing flagged ----
check(
    "all outlets healthy",
    {o["id"]: healthy_run(hours_ago=6) for o in OUTLETS},
    [],
)

# ---- One outlet has never had a crawl_run at all ----
runs = {o["id"]: healthy_run(hours_ago=6) for o in OUTLETS}
del runs["greens_gozo"]
check("one outlet never crawled", runs, ["greens_gozo"])

# ---- One outlet's last successful crawl is more than 48h old ----
runs = {o["id"]: healthy_run(hours_ago=6) for o in OUTLETS}
runs["welbees"] = healthy_run(hours_ago=72)
check("one outlet stale (72h)", runs, ["welbees"])

# ---- Exactly at the 48h boundary should NOT be flagged (only strictly older) ----
runs = {o["id"]: healthy_run(hours_ago=6) for o in OUTLETS}
runs["welbees"] = healthy_run(hours_ago=47)
check("one outlet at 47h -- still healthy", runs, [])

# ---- One outlet "succeeded" but found almost nothing -- silent breakage ----
runs = {o["id"]: healthy_run(hours_ago=6) for o in OUTLETS}
runs["pavipama"] = healthy_run(hours_ago=6, item_count=0)
check("one outlet succeeded with 0 items", runs, ["pavipama"])

runs = {o["id"]: healthy_run(hours_ago=6) for o in OUTLETS}
runs["pavipama"] = healthy_run(hours_ago=6, item_count=MIN_HEALTHY_ITEM_COUNT - 1)
check("one outlet succeeded with item_count just under the floor", runs, ["pavipama"])

runs = {o["id"]: healthy_run(hours_ago=6) for o in OUTLETS}
runs["pavipama"] = healthy_run(hours_ago=6, item_count=MIN_HEALTHY_ITEM_COUNT)
check("one outlet succeeded with item_count exactly at the floor -- healthy", runs, [])

# ---- A 'partial' status with a healthy item count should NOT be flagged
#      just for being 'partial' (that's already a known, acceptable state) ----
runs = {o["id"]: healthy_run(hours_ago=6) for o in OUTLETS}
runs["greens_mriehel"] = healthy_run(hours_ago=6, item_count=800, status="partial")
check("one outlet 'partial' but healthy item count", runs, [])

# ---- A 'failed' run is NOT flagged here -- the crawler's own GitHub
#      Actions failure notification already covers that case ----
runs = {o["id"]: healthy_run(hours_ago=6) for o in OUTLETS}
runs["welbees"] = {"status": "failed", "started_at": NOW - timedelta(hours=6, minutes=10),
                    "finished_at": NOW - timedelta(hours=6), "item_count": 0,
                    "error_message": "site down"}
check("one outlet's latest run failed -- not this script's job", runs, [])

# ---- A run stuck in 'running' for a long time (killed/timed out without
#      ever reaching its own finally block) ----
runs = {o["id"]: healthy_run(hours_ago=6) for o in OUTLETS}
runs["greens_swieqi"] = {"status": "running", "started_at": NOW - timedelta(hours=50),
                          "finished_at": None, "item_count": None, "error_message": None}
check("one outlet stuck in 'running' for 50h", runs, ["greens_swieqi"])

# ---- A run that's still 'running' but recently started -- not stale yet ----
runs = {o["id"]: healthy_run(hours_ago=6) for o in OUTLETS}
runs["greens_swieqi"] = {"status": "running", "started_at": NOW - timedelta(minutes=20),
                          "finished_at": None, "item_count": None, "error_message": None}
check("one outlet 'running' for only 20 minutes -- still healthy", runs, [])

# ---- Multiple outlets flagged at once ----
runs = {o["id"]: healthy_run(hours_ago=6) for o in OUTLETS}
runs["welbees"] = healthy_run(hours_ago=72)
runs["pavipama"] = healthy_run(hours_ago=6, item_count=0)
del runs["greens_gozo"]
check("three outlets flagged at once, different reasons",
      runs, ["welbees", "pavipama", "greens_gozo"])

print(f"\n{passed} passed, {failed} failed")
if failed:
    sys.exit(1)
