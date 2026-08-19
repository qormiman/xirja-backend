"""
Tests for github_issue_notify.py -- pure logic, no real `gh` CLI or GitHub
API calls. Same style as this project's other test_*.py files: a `check()`
helper, a pass/fail tally, printed summary at the end.

A FakeRunner stands in for subprocess.run (github_issue_notify's `runner`
parameter is injectable exactly so this works), recording every command it
was asked to run and returning scripted responses -- same pattern already
used by test_check_and_trigger_crawl.py-style tests elsewhere in this
project.
"""
import json
import sys

sys.path.insert(0, "/tmp/xirja/xirja-backend")
from github_issue_notify import flag, resolve, find_open_issue


class FakeResult:
    def __init__(self, stdout=""):
        self.stdout = stdout


class FakeRunner:
    """`open_issues` is the list of {"number": int, "title": str} dicts
    `gh issue list` should report as currently open -- callers mutate it
    to simulate issues being opened/closed by earlier calls in the same
    test, same as the real GitHub state would change."""

    def __init__(self, open_issues):
        self.open_issues = open_issues
        self.calls = []
        self._next_number = max([i["number"] for i in open_issues], default=0) + 1

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        if cmd[:3] == ["gh", "issue", "list"]:
            return FakeResult(stdout=json.dumps(self.open_issues))
        if cmd[:3] == ["gh", "issue", "create"]:
            number = self._next_number
            self._next_number += 1
            title = cmd[cmd.index("--title") + 1]
            self.open_issues.append({"number": number, "title": title})
            return FakeResult(stdout=f"https://github.com/fake/repo/issues/{number}")
        if cmd[:3] == ["gh", "issue", "comment"]:
            return FakeResult()
        if cmd[:3] == ["gh", "issue", "close"]:
            number = int(cmd[3])
            self.open_issues[:] = [i for i in self.open_issues if i["number"] != number]
            return FakeResult()
        raise AssertionError(f"unexpected command: {cmd}")


passed = 0
failed = 0


def check(label, condition):
    global passed, failed
    status = "OK  " if condition else "FAIL"
    print(f"{status} {label}")
    if condition:
        passed += 1
    else:
        failed += 1


TITLE = "Categorize listings: unclassified items need new keyword rules"

# ---- find_open_issue: no issues at all ----
runner = FakeRunner(open_issues=[])
check("find_open_issue returns None when nothing is open", find_open_issue(TITLE, runner) is None)

# ---- find_open_issue: an open issue with a DIFFERENT title doesn't match ----
runner = FakeRunner(open_issues=[{"number": 5, "title": "Something unrelated"}])
check("find_open_issue ignores a differently-titled open issue", find_open_issue(TITLE, runner) is None)

# ---- find_open_issue: exact title match ----
runner = FakeRunner(open_issues=[{"number": 5, "title": TITLE}])
check("find_open_issue finds the matching open issue", find_open_issue(TITLE, runner) == "5")

# ---- flag(): first time seeing this problem -> opens a new issue ----
runner = FakeRunner(open_issues=[])
flag(TITLE, "12 listings still unclassified.", runner)
create_calls = [c for c in runner.calls if c[:3] == ["gh", "issue", "create"]]
check("flag() with no existing issue creates exactly one", len(create_calls) == 1)
check("flag() creates it with the right title", "--title" in create_calls[0] and TITLE in create_calls[0])

# ---- flag(): problem persists, issue already open -> comments, doesn't duplicate ----
runner = FakeRunner(open_issues=[{"number": 9, "title": TITLE}])
flag(TITLE, "14 listings still unclassified.", runner)
create_calls = [c for c in runner.calls if c[:3] == ["gh", "issue", "create"]]
comment_calls = [c for c in runner.calls if c[:3] == ["gh", "issue", "comment"]]
check("flag() with an existing open issue creates no new issue", len(create_calls) == 0)
check("flag() with an existing open issue adds exactly one comment", len(comment_calls) == 1)
check("flag() comments on the right issue number", comment_calls[0][3] == "9")

# ---- resolve(): nothing open -> does nothing (no crash, no calls beyond the list check) ----
runner = FakeRunner(open_issues=[])
resolve(TITLE, "All clear.", runner)
close_calls = [c for c in runner.calls if c[:3] == ["gh", "issue", "close"]]
check("resolve() with nothing open makes no close call", len(close_calls) == 0)

# ---- resolve(): an open issue for this exact problem -> closes it ----
runner = FakeRunner(open_issues=[{"number": 3, "title": TITLE}])
resolve(TITLE, "All clear now.", runner)
close_calls = [c for c in runner.calls if c[:3] == ["gh", "issue", "close"]]
check("resolve() with a matching open issue closes exactly one", len(close_calls) == 1)
check("resolve() closes the right issue number", close_calls[0][3] == "3")
check("resolve() leaves no open issues behind", runner.open_issues == [])

# ---- resolve(): an open issue for a DIFFERENT problem is left alone ----
runner = FakeRunner(open_issues=[{"number": 7, "title": "Some other alert"}])
resolve(TITLE, "All clear.", runner)
close_calls = [c for c in runner.calls if c[:3] == ["gh", "issue", "close"]]
check("resolve() never touches a differently-titled open issue", len(close_calls) == 0)
check("resolve() leaves the unrelated issue open", runner.open_issues == [{"number": 7, "title": "Some other alert"}])

# ---- Full lifecycle: flag opens it, flag again reuses it, resolve closes it,
#      flag after that opens a FRESH issue (closing means "handled", not
#      "never tell me again") ----
runner = FakeRunner(open_issues=[])
flag(TITLE, "round 1", runner)
first_number = runner.open_issues[0]["number"]
flag(TITLE, "round 2", runner)
check("lifecycle: still only one open issue after two flag() calls", len(runner.open_issues) == 1)
resolve(TITLE, "fixed", runner)
check("lifecycle: resolve() closed it", runner.open_issues == [])
flag(TITLE, "round 3, happening again", runner)
check("lifecycle: flag() after resolve() opens a brand new issue", len(runner.open_issues) == 1)
check("lifecycle: the new issue has a new number, not the old one",
      runner.open_issues[0]["number"] != first_number)

print(f"\n{passed} passed, {failed} failed")
if failed:
    sys.exit(1)
