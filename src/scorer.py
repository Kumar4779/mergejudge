"""MergeJudge scorer v1 - grade one agent patch for one SWE-bench task.

The recipe (done by hand 3 times on 2026-11-19: baseline, gold, agent):
  1. Fresh worktree at the task's base commit (clean checkout).
  2. Anti-cheat: a patch touching a test file or test config is
     disqualified before any test runs.
  3. Apply the agent patch, then the task's test patch.
  4. Run the grading test files with the task's own Python env,
     collecting every test's result by name.
  5. Verdict from the NAMED tests only. Write the result JSON.

The scorer never imports the target repo - it drives git and pytest
from outside, so tests run in a process the agent cannot touch.

Run from the project root, inside the project .venv:
  python3 src/scorer.py --task sympy__sympy-11400 --patch results/sympy-11400-claude.patch --agent claude
  python3 src/scorer.py --task sympy__sympy-11400 --patch tasks/sympy-11400-gold_patch.diff --agent gold
  python3 src/scorer.py --task sympy__sympy-11400 --patch NONE --agent none
"""

import argparse
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from datasets import load_dataset

ROOT = Path(__file__).resolve().parent.parent
TEST_TIMEOUT_S = 5 * 60  # same test timeout as src/runner.py

# What the dataset cannot tell us: where the repo is cloned here, and
# which Python can run its tests. One entry per task - Task 2 adds a line.
TASK_SETUP = {
    "sympy__sympy-11400": {
        "clone": "repos/sympy_src",
        "python": "envs/sympy-py39/bin/python",
    },
}

CONFIG_NAMES = {"conftest.py", "pytest.ini", "tox.ini", "setup.cfg"}


def run(cmd, cwd=None, timeout=None):
    done = subprocess.run(cmd, cwd=cwd, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True)
    return done.returncode, done.stdout


def patch_files(patch_text):
    files = re.findall(r"^\+\+\+ b/(.+)$", patch_text, flags=re.M)
    files += re.findall(r"^--- a/(.+)$", patch_text, flags=re.M)
    return sorted(set(files))


def patch_stats(patch_text):
    files = patch_files(patch_text)
    added = sum(1 for ln in patch_text.splitlines()
                if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in patch_text.splitlines()
                  if ln.startswith("-") and not ln.startswith("---"))
    return files, added, removed


def is_cheating_file(path):
    parts = Path(path).parts
    name = Path(path).name
    return "tests" in parts or name.startswith("test_") or name in CONFIG_NAMES


def load_task(task_id):
    ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    task = next(x for x in ds if x["instance_id"] == task_id)

    def as_list(value):
        return json.loads(value) if isinstance(value, str) else list(value)

    return {
        "base_commit": task["base_commit"],
        "fail_to_pass": as_list(task["FAIL_TO_PASS"]),
        "pass_to_pass": as_list(task["PASS_TO_PASS"]),
        "test_patch": task["test_patch"],
    }


def short_name(test_name):
    return test_name.split("::")[-1]


def grade(task_id, patch_path, agent):
    info = load_task(task_id)
    setup = TASK_SETUP[task_id]
    clone = ROOT / setup["clone"]
    python = ROOT / setup["python"]
    short = task_id.split("__")[-1]

    if patch_path == "NONE":
        patch_text, patch_file = "", None
    else:
        patch_file = Path(patch_path)
        if not patch_file.is_absolute():
            patch_file = ROOT / patch_file
        patch_text = patch_file.read_text()

    files, added, removed = patch_stats(patch_text)
    result = {
        "task": task_id,
        "agent": agent,
        "files_touched": files,
        "diff_lines_added": added,
        "diff_lines_removed": removed,
        "test_file_touched": any(is_cheating_file(f) for f in files),
    }

    if result["test_file_touched"]:
        result["verdict"] = "disqualified"
        result["reason"] = "patch touches a test file or test config"
        return result

    worktree = ROOT / "worktrees" / f"grading-{short}-{agent}"
    tmp_agent = ROOT / "worktrees" / f".tmp-{short}-{agent}-agent.diff"
    tmp_test = ROOT / "worktrees" / f".tmp-{short}-{agent}-test.diff"

    def remove_worktree():
        run(["git", "-C", str(clone), "worktree", "remove", "--force", str(worktree)])
        run(["git", "-C", str(clone), "worktree", "prune"])
        # git leaves the folder behind if it was never (or no longer) a
        # registered worktree; clear it so the next worktree add works.
        if worktree.exists():
            shutil.rmtree(worktree)

    remove_worktree()
    try:
        code, out = run(["git", "-C", str(clone), "worktree", "add",
                         str(worktree), info["base_commit"]])
        if code != 0:
            result["verdict"] = "error"
            result["reason"] = "worktree add failed: " + out.strip()[-300:]
            return result

        if patch_file is not None:
            tmp_agent.write_text(patch_text)
            code, out = run(["git", "-C", str(worktree), "apply", str(tmp_agent)])
            if code != 0:
                result["verdict"] = "error"
                result["reason"] = "agent patch does not apply: " + out.strip()[-300:]
                return result

        tmp_test.write_text(info["test_patch"])
        code, out = run(["git", "-C", str(worktree), "apply", str(tmp_test)])
        if code != 0:
            result["verdict"] = "error"
            result["reason"] = "test patch does not apply: " + out.strip()[-300:]
            return result

        test_files = patch_files(info["test_patch"])
        start = time.time()
        try:
            code, out = run([str(python), "-m", "pytest", *test_files,
                             "-v", "--tb=no"], cwd=worktree,
                            timeout=TEST_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            result["verdict"] = "error"
            result["reason"] = "test run timed out"
            return result
        result["grading_time_s"] = round(time.time() - start, 1)

        status = {}
        for nodeid, st in re.findall(r"^(\S+::\S+)\s+(PASSED|FAILED|ERROR)",
                                     out, flags=re.M):
            status[short_name(nodeid)] = st

        def count(names):
            passed = sum(1 for n in names
                         if status.get(short_name(n)) == "PASSED")
            return {"passed": passed, "total": len(names)}

        result["fail_to_pass"] = count(info["fail_to_pass"])
        result["pass_to_pass_named"] = count(info["pass_to_pass"])
        ok = (result["fail_to_pass"]["passed"] == result["fail_to_pass"]["total"]
              and result["pass_to_pass_named"]["passed"]
              == result["pass_to_pass_named"]["total"])
        result["verdict"] = "resolved" if ok else "not_resolved"
        return result
    finally:
        remove_worktree()
        tmp_agent.unlink(missing_ok=True)
        tmp_test.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--patch", required=True,
                    help="path to a patch file, or NONE for the baseline")
    ap.add_argument("--agent", required=True)
    args = ap.parse_args()

    result = grade(args.task, args.patch, args.agent)

    short = args.task.split("__")[-1]
    out_path = ROOT / "results" / f"{short}-{args.agent}.json"
    merged = {}
    if out_path.exists():
        merged = json.loads(out_path.read_text())
    for stale in ("fail_to_pass", "pass_to_pass_named", "grading_time_s"):
        merged.pop(stale, None)
    old_agent = merged.get("agent")
    merged.update(result)
    if old_agent and old_agent != args.agent:
        merged["agent"] = old_agent
        merged["agent_key"] = args.agent
    out_path.write_text(json.dumps(merged, indent=2) + "\n")

    print(json.dumps(result, indent=2))
    print("verdict:", result["verdict"], "->", out_path.relative_to(ROOT))


if __name__ == "__main__":
    main()
