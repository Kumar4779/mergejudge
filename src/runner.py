"""MergeJudge runner v1 - run ONE coding agent on ONE task, then grade it.

The other half of the scorer. For one task and one agent arm:
  1. Fresh worktree at the task's base commit (clean checkout).
  2. Run the agent headless inside it, with only the issue text and the
     rules - it never sees the test patch or the gold patch.
  3. Hard timeout (sandbox contract). Even on timeout, whatever patch
     exists is captured and graded - the scorer is the judge.
  4. Capture the patch (git add -A + diff --cached, so new files count),
     save the agent's full output as a log, remove the worktree.
  5. Grade the patch with src/scorer.py and stamp agent_time_s and
     agent_status into the result JSON the scorer writes.

Run from the project root, inside the project .venv:
  python3 src/runner.py --task sympy__sympy-11400 --agent claude-e2e
"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from datasets import load_dataset

ROOT = Path(__file__).resolve().parent.parent
AGENT_TIMEOUT_S = 30 * 60  # hard kill for the agent run (sandbox contract)

# Same per-task facts as the scorer: where the repo is cloned here, and
# which Python can run its tests. One entry per task.
TASK_SETUP = {
    "sympy__sympy-11400": {
        "clone": "repos/sympy_src",
        "python": "envs/sympy-py39/bin/python",
    },
}

PROMPT_TEMPLATE = """You are fixing a bug in this repository. Work only inside this directory: {worktree}

Issue:
{issue}

Rules:
- Do not edit any test files, and do not create files whose names start with test_.
- Do not modify anything outside this directory.
- Make the smallest fix that resolves the issue.
- You may run tests with this Python: {python}
- When you are done, stop. Your changes will be captured as a patch and graded on a clean checkout with tests you cannot see.
"""


def run(cmd, cwd=None, timeout=None):
    done = subprocess.run(cmd, cwd=cwd, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True)
    return done.returncode, done.stdout


def load_task(task_id):
    ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    task = next(x for x in ds if x["instance_id"] == task_id)
    return {
        "base_commit": task["base_commit"],
        "issue": task["problem_statement"],
    }


def build_command(cli, prompt):
    if cli == "claude":
        return ["claude", "-p", prompt, "--dangerously-skip-permissions",
                "--output-format", "stream-json", "--verbose"]
    raise SystemExit(f"unknown --cli: {cli} (v1 supports: claude)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--agent", required=True,
                    help="arm label used in result filenames, e.g. claude-e2e")
    ap.add_argument("--cli", default="claude")
    ap.add_argument("--keep", action="store_true",
                    help="keep the agent worktree afterwards (debugging)")
    args = ap.parse_args()

    info = load_task(args.task)
    setup = TASK_SETUP[args.task]
    clone = ROOT / setup["clone"]
    python = ROOT / setup["python"]
    short = args.task.split("__")[-1]

    worktree = (Path(tempfile.gettempdir())
                / f"mergejudge-{short}-{args.agent}-run")

    def remove_worktree():
        run(["git", "-C", str(clone), "worktree", "remove", "--force",
             str(worktree)])
        run(["git", "-C", str(clone), "worktree", "prune"])
        if worktree.exists():
            shutil.rmtree(worktree)

    remove_worktree()
    code, out = run(["git", "-C", str(clone), "worktree", "add",
                     str(worktree), info["base_commit"]])
    if code != 0:
        print("worktree add failed:", out.strip()[-300:])
        sys.exit(1)

    prompt = PROMPT_TEMPLATE.format(worktree=worktree, issue=info["issue"],
                                    python=python)
    cmd = build_command(args.cli, prompt)

    start = time.time()
    status = "completed"
    proc = subprocess.Popen(cmd, cwd=worktree, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            start_new_session=True)
    try:
        log, _ = proc.communicate(timeout=AGENT_TIMEOUT_S)
        if proc.returncode != 0:
            status = f"exit-{proc.returncode}"
    except subprocess.TimeoutExpired:
        status = "timeout"
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        log, _ = proc.communicate()
    log = log or ""
    agent_time_s = round(time.time() - start, 1)

    log_path = ROOT / "results" / f"{short}-{args.agent}.log"
    log_path.write_text(log)

    run(["git", "-C", str(worktree), "add", "-A"])
    code, patch_text = run(["git", "-C", str(worktree), "diff", "--cached"])
    patch_path = ROOT / "results" / f"{short}-{args.agent}.patch"
    patch_path.write_text(patch_text)

    if not args.keep:
        remove_worktree()

    print(f"agent {args.agent}: status={status} time={agent_time_s}s "
          f"patch_lines={len(patch_text.splitlines())} log={log_path.name}")

    code, out = run([sys.executable, str(ROOT / "src" / "scorer.py"),
                     "--task", args.task, "--patch", str(patch_path),
                     "--agent", args.agent], cwd=ROOT)
    print(out)

    result_path = ROOT / "results" / f"{short}-{args.agent}.json"
    if result_path.exists():
        record = json.loads(result_path.read_text())
        record["agent_time_s"] = agent_time_s
        record["agent_status"] = status
        result_path.write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    main()
