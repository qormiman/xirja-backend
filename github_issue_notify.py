"""
Xirja -- "flag it, don't fail it" notifications via GitHub Issues.

What this does, in plain terms:
  categorize_listings.py and check_crawl_freshness.py both have a
  legitimate "everything ran fine, but here's something worth a human
  look" case (some listings still need keyword rules; a chain's prices
  look stale). Up to 20 Aug 2026, both scripts handled that by exiting
  non-zero on purpose, which made the GitHub Actions run show a red X and
  triggered GitHub's own failure-notification email -- a cheap way to get
  an email with zero new setup, but it meant a run that did its job
  correctly still looked exactly like a broken workflow. Requested 20 Aug
  2026 to stop conflating the two: from now on, both scripts always exit
  0 (the Actions run stays green) when they completed their actual job,
  and use THIS module instead to get a human's attention -- by opening (or
  updating) a GitHub Issue in this repository. GitHub emails you the same
  way it already does for any new issue or comment in a repo you're
  watching -- same inbox, no new secrets, no SMTP setup.

  A genuine crash (the database is unreachable, an unhandled exception)
  is NOT this -- that's still a real failure and both scripts still exit
  non-zero for that case, same as before. This module is only for the
  "ran fine, but look at this" case.

How it avoids spamming your inbox:
  Each distinct thing worth flagging gets ONE stable issue title (e.g.
  "Categorize listings: unclassified items need new keyword rules").
  - First time it's seen: opens a new issue. You get one "new issue"
    email.
  - Still happening on a later run, and the issue is still open: adds a
    comment with the latest numbers instead of opening a second issue.
    You get one "new comment" email, not a duplicate issue.
  - Already fixed (you closed the issue after acting on it) and it comes
    back later: opens a fresh issue again, same as the first time --
    closing an issue means "I've dealt with this", not "never tell me
    about this again".
  - No longer happening at all (the underlying problem is gone) and an
    issue for it is still open: closes it automatically with a short
    "looks resolved as of this run" comment, so issues don't pile up
    needing to be closed by hand once whatever they were about is fixed.

Requires the `gh` command-line tool (already installed on every GitHub
Actions runner) and a GH_TOKEN/GITHUB_TOKEN environment variable with
permission to read and write issues -- both scripts' workflow files set
`permissions: issues: write` and pass
`GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}` for this. Nothing here talks to
the database or any of the three sites -- it only talks to GitHub's own
API, via `gh`.
"""
import json
import os
import subprocess
import sys


def _run_url():
    """Best-effort link back to the specific run that's doing the
    flagging, so the issue body can point straight at the full log
    instead of just summarizing it. Returns None if the environment
    variables GitHub Actions sets aren't present (e.g. running this by
    hand on a laptop) -- callers should handle that gracefully, not
    error out over a missing link."""
    server = os.environ.get("GITHUB_SERVER_URL")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    if server and repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return None


def find_open_issue(title, runner=subprocess.run):
    """Returns the issue number (as a string) of an OPEN issue whose
    title exactly matches `title`, or None if there isn't one. Fetches
    every open issue and compares titles in Python rather than using
    `gh issue list --search`, because GitHub's search does fuzzy/keyword
    matching -- not the exact, stable dedup key this needs."""
    result = runner(
        ["gh", "issue", "list", "--state", "open", "--json", "number,title", "--limit", "100"],
        capture_output=True, text=True, check=True,
    )
    issues = json.loads(result.stdout)
    for issue in issues:
        if issue["title"] == title:
            return str(issue["number"])
    return None


def flag(title, body, runner=subprocess.run):
    """Makes sure there's an OPEN GitHub issue with this title, containing
    this run's findings -- opens a new one if none exists, or adds a
    comment to the existing one so it doesn't go silent. Call this once
    per run when there's something worth a human look. Always call
    resolve() with the same title on the runs where nothing's wrong, so a
    fixed problem's issue gets closed automatically instead of sitting
    open forever."""
    link = _run_url()
    if link:
        body = f"{body}\n\nFull log for this run: {link}"

    existing = find_open_issue(title, runner)
    if existing is not None:
        runner(["gh", "issue", "comment", existing, "--body", body], check=True)
        print(f"Still happening -- added a comment to the existing GitHub issue #{existing} "
              f"({title!r}). GitHub will email you about the new comment the same way it does "
              f"for any issue you're watching in this repo.")
    else:
        result = runner(["gh", "issue", "create", "--title", title, "--body", body],
                         capture_output=True, text=True, check=True)
        print(f"Opened a new GitHub issue for this: {result.stdout.strip()}. GitHub will email "
              f"you about it the same way it does for any new issue opened in this repo. Close "
              f"the issue once you've acted on it -- if it happens again later, a fresh issue "
              f"will be opened.")


def resolve(title, note, runner=subprocess.run):
    """If an OPEN issue with this title exists, closes it with `note` as
    the closing comment. Call this on every run where the thing this
    title tracks is NOT currently happening -- if there's no open issue
    (the common case: it's never been a problem, or was already closed),
    this does nothing and prints nothing, so a healthy run's log stays
    quiet."""
    existing = find_open_issue(title, runner)
    if existing is not None:
        runner(["gh", "issue", "close", existing, "--comment", note], check=True)
        print(f"This looks resolved now, so GitHub issue #{existing} ({title!r}) was closed "
              f"automatically, with a note. If it comes back later, a fresh issue will be opened.")


def _self_check():
    """Not a real test suite (see test_github_issue_notify.py for that) --
    just lets this file be run directly for a quick sanity check against
    the REAL `gh` CLI and a REAL repo, useful when setting this up for
    the first time. Requires `gh auth login` to already be done locally.
    Usage: python github_issue_notify.py flag|resolve "<title>" "<body>"
    """
    if len(sys.argv) != 4 or sys.argv[1] not in ("flag", "resolve"):
        print(__doc__)
        print('Usage: python github_issue_notify.py flag|resolve "<title>" "<body>"')
        sys.exit(1)
    action, title, body = sys.argv[1], sys.argv[2], sys.argv[3]
    if action == "flag":
        flag(title, body)
    else:
        resolve(title, body)


if __name__ == "__main__":
    _self_check()
