"""MergeJudge fresh slice - mine post-cutoff sympy tasks from merged PRs.

The fresh slice is a held-out set of tasks merged after the models'
training data could have contained them. It is reported separately,
forever: its tasks and runs never enter the Portfolio or any public-task
aggregate (src/compare.py splits them out by tasks/fresh/index.json).

Construction, per merged sympy PR in the window (merged on or after
--since), oldest first:
  1. Structure: the PR must touch both test files and non-test sympy/
     source files. Base commit = the merge commit's first parent; gold
     patch = the non-test diff (minus .mailmap/AUTHORS bookkeeping); test
     patch = the test diff. Size bounds keep tasks SWE-bench-shaped:
     gold touches 1-3 source files and at most 100 diff lines; the test
     patch touches 1-3 test files.
  2. Problem statement: the linked issue (closing reference or
     "Fixes #N"), title + body, body at least 150 characters. PRs without
     a usable issue fall back to a substantive PR body (template comments
     and release notes stripped, at least 400 characters).
  3. Test lists by execution, in envs/sympy-modern. At base + test patch
     run the touched test files: failures (including tests that do not
     exist or do not collect yet) are candidate FAIL_TO_PASS, passes are
     the PASS_TO_PASS pool. At base + gold + test patch every
     FAIL_TO_PASS candidate must pass and every pool test must still pass,
     or the task is rejected. Kept: 1-10 FAIL_TO_PASS, no short-name
     collisions (the scorer keys pytest results by short name).
Kept tasks are written to tasks/fresh/ (record + issue/test/gold files)
and listed with provenance in tasks/fresh/index.json. The scorer's
validation gate (gold resolved, empty not_resolved) runs afterwards.

Run from the project root, inside the project .venv:
  python3 src/mine_fresh.py --since 2026-01-01 --target 5
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLONE = ROOT / "repos" / "sympy_src"
PYTHON = ROOT / "envs" / "sympy-modern" / "bin" / "python"
FRESH = ROOT / "tasks" / "fresh"
INDEX = FRESH / "index.json"
REPO = "sympy/sympy"
TEST_TIMEOUT_S = 1800

TEST_FILE = re.compile(r"(^|/)tests?/|(^|/)test_[^/]*\.py$|conftest\.py$")
BOOKKEEPING = {".mailmap", "AUTHORS"}
CLOSING = re.compile(r"(?i)\b(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s*:?\s*"
                     r"(?:https://github\.com/sympy/sympy/issues/|#)(\d+)")
MAX_GOLD_FILES, MAX_GOLD_LINES, MAX_TEST_FILES = 3, 100, 3
MIN_ISSUE_BODY, MIN_PR_BODY = 150, 400
F2P_RANGE = (1, 10)


def sh(cmd, cwd=None, timeout=None):
    done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout)
    return done.returncode, done.stdout + done.stderr


def gh_json(args):
    code, out = sh(["gh", *args])
    if code != 0:
        raise SystemExit(f"gh {' '.join(args)} failed: {out[-300:]}")
    return json.loads(out)


def merged_prs(since):
    prs = gh_json(["pr", "list", "--repo", REPO, "--state", "merged",
                   "--search", f"merged:>={since}", "--limit", "2000",
                   "--json", "number,title,body,mergedAt,mergeCommit,"
                             "closingIssuesReferences,files,url"])
    return sorted(prs, key=lambda p: p["mergedAt"])


def strip_template(body):
    body = re.sub(r"<!--.*?-->", "", body or "", flags=re.S)
    body = re.sub(r"(?is)<!-- BEGIN RELEASE NOTES -->.*", "", body)
    body = re.sub(r"(?is)#+\s*release notes.*", "", body)
    return body.strip()


def problem_statement(pr):
    """(source, url, text) or None."""
    numbers = [i["number"] for i in pr.get("closingIssuesReferences") or []]
    numbers += [int(n) for n in CLOSING.findall(pr.get("body") or "")]
    for number in dict.fromkeys(numbers):
        code, out = sh(["gh", "issue", "view", str(number), "--repo", REPO,
                        "--json", "title,body,url"])
        if code != 0:
            continue  # a PR number, or an issue we cannot read
        issue = json.loads(out)
        body = (issue.get("body") or "").strip()
        if len(body) >= MIN_ISSUE_BODY:
            return "issue", issue["url"], f"{issue['title']}\n\n{body}\n"
    body = strip_template(pr.get("body"))
    if len(body) >= MIN_PR_BODY:
        return "pr_body", pr["url"], f"{pr['title']}\n\n{body}\n"
    return None


def diff_lines(patch):
    return sum(1 for line in patch.splitlines()
               if line[:1] in "+-" and line[:3] not in ("+++", "---"))


def construct(pr):
    """Structural task record from a PR, or (None, reason)."""
    merge = (pr.get("mergeCommit") or {}).get("oid")
    if not merge:
        return None, "no merge commit"
    code, base = sh(["git", "-C", str(CLONE), "rev-parse", f"{merge}^1"])
    if code != 0:
        return None, "merge commit not in clone"
    base = base.strip()
    code, out = sh(["git", "-C", str(CLONE), "diff", "--name-only", base,
                    merge])
    files = [f for f in out.split() if f not in BOOKKEEPING]
    tests = [f for f in files if TEST_FILE.search(f)]
    source = [f for f in files if not TEST_FILE.search(f)]
    if not tests or not [f for f in source
                         if f.startswith("sympy/") and f.endswith(".py")]:
        return None, "needs test files and sympy/ source files"
    if len(source) > MAX_GOLD_FILES or len(tests) > MAX_TEST_FILES:
        return None, f"too broad ({len(source)} source, {len(tests)} test)"
    _, gold = sh(["git", "-C", str(CLONE), "diff", base, merge, "--",
                  *source])
    _, test = sh(["git", "-C", str(CLONE), "diff", base, merge, "--",
                  *tests])
    if diff_lines(gold) > MAX_GOLD_LINES:
        return None, f"gold too large ({diff_lines(gold)} lines)"
    return {"instance_id": f"sympy__sympy-{pr['number']}", "repo": REPO,
            "slice": "fresh", "version": "fresh",
            "pr_url": pr["url"], "merged_at": pr["mergedAt"],
            "merge_commit": merge, "base_commit": base,
            "gold_patch": gold, "test_patch": test,
            "test_files": [f for f in tests if f.endswith(".py")
                           and Path(f).name.startswith("test_")]}, None


def run_tests(record, with_gold):
    """{nodeid: status} for the touched test files in a fresh worktree."""
    short = record["instance_id"].split("__")[-1]
    wt = ROOT / "worktrees" / f"fresh-{short}"
    sh(["git", "-C", str(CLONE), "worktree", "remove", "--force", str(wt)])
    if wt.exists():
        shutil.rmtree(wt)
    try:
        sh(["git", "-C", str(CLONE), "worktree", "add", "--detach", str(wt),
            record["base_commit"]])
        for key in (("gold_patch", "test_patch") if with_gold
                    else ("test_patch",)):
            patch = wt.parent / f".fresh-{short}-{key}.diff"
            patch.write_text(record[key])
            code, out = sh(["git", "-C", str(wt), "apply", str(patch)])
            patch.unlink()
            if code != 0:
                raise RuntimeError(f"{key} does not apply: {out[-200:]}")
        code, out = sh([str(PYTHON), "-m", "pytest", *record["test_files"],
                        "-v", "--tb=no", "-p", "no:cacheprovider"], cwd=wt,
                       timeout=TEST_TIMEOUT_S)
        return dict(re.findall(r"^(\S+::\S+)\s+(PASSED|FAILED|ERROR)", out,
                               flags=re.M)), out
    finally:
        sh(["git", "-C", str(CLONE), "worktree", "remove", "--force",
            str(wt)])
        if wt.exists():
            shutil.rmtree(wt)


def derive(record):
    """Fill FAIL_TO_PASS / PASS_TO_PASS by execution; reason if rejected."""
    if not record["test_files"]:
        return "no runnable test_*.py files"
    base, _ = run_tests(record, with_gold=False)
    gold, gold_out = run_tests(record, with_gold=True)
    if not gold:
        return "no tests ran with gold: " + gold_out.strip()[-200:]
    f2p = sorted(t for t in gold if base.get(t) != "PASSED")
    p2p = sorted(t for t, st in base.items() if st == "PASSED")
    broken = [t for t in f2p + p2p if gold.get(t) != "PASSED"]
    if broken:
        return f"{len(broken)} test(s) not passing with gold, e.g. {broken[0]}"
    if not F2P_RANGE[0] <= len(f2p) <= F2P_RANGE[1]:
        return f"{len(f2p)} FAIL_TO_PASS (need {F2P_RANGE[0]}-{F2P_RANGE[1]})"
    names = Counter(t.split("::")[-1] for t in f2p + p2p)
    if any(n > 1 for n in names.values()):
        return "short-name collision across test files"
    record["FAIL_TO_PASS"], record["PASS_TO_PASS"] = f2p, p2p
    return None


def write_task(record):
    FRESH.mkdir(parents=True, exist_ok=True)
    short = record["instance_id"].split("__")[-1]
    (FRESH / f"{short}-issue.txt").write_text(record["problem_statement"])
    (FRESH / f"{short}-test_patch.diff").write_text(record["test_patch"])
    (FRESH / f"{short}-gold_patch.diff").write_text(record["gold_patch"])
    (FRESH / f"{short}.json").write_text(json.dumps(record, indent=2) + "\n")


def write_index(since, tasks):
    INDEX.write_text(json.dumps({
        "slice": "fresh",
        "cutoff": f"merged on or after {since}",
        "built": date.today().isoformat(),
        "reported": "separately; never in the Portfolio or any public-task "
                    "aggregate",
        "tasks": [{k: t[k] for k in ("instance_id", "pr_url", "merged_at",
                                     "base_commit", "merge_commit",
                                     "problem_source", "problem_url")}
                  for t in tasks],
    }, indent=2) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-01-01")
    ap.add_argument("--target", type=int, default=5,
                    help="stop after this many tasks pass construction")
    args = ap.parse_args()

    prs = merged_prs(args.since)
    print(f"{len(prs)} merged {REPO} PRs on or after {args.since}")
    reasons, kept = Counter(), []
    for pr in prs:
        record, reason = construct(pr)
        if record is None:
            reasons[reason.split(" (")[0]] += 1
            continue
        statement = problem_statement(pr)
        if statement is None:
            reasons["no usable problem statement"] += 1
            continue
        (record["problem_source"], record["problem_url"],
         record["problem_statement"]) = statement
        print(f"{record['instance_id']} ({pr['mergedAt'][:10]}): deriving")
        try:
            reason = derive(record)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            reason = str(exc)[:200]
        if reason:
            print(f"  rejected: {reason}")
            reasons["execution: " + reason.split(",")[0].split(":")[0]] += 1
            continue
        print(f"  kept: {len(record['FAIL_TO_PASS'])} FAIL_TO_PASS, "
              f"{len(record['PASS_TO_PASS'])} PASS_TO_PASS")
        kept.append(record)
        if len(kept) >= args.target:
            break
    for record in kept:
        write_task(record)
    write_index(args.since, kept)
    print(f"\n{len(kept)} task(s) constructed; filtered out before stopping:")
    for reason, n in reasons.most_common():
        print(f"  {n:4d}  {reason}")


if __name__ == "__main__":
    main()
