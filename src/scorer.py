"""MergeJudge scorer v2 - grade one agent patch for one SWE-bench task.

The recipe (proven by hand on sympy-11400 on 2026-11-19, on
django-10914 on 2026-11-21 and on matplotlib-18869 on 2026-11-22):
  1. Fresh worktree at the task's base commit (clean checkout).
  2. Anti-cheat: a patch touching a test file or test config is
     disqualified before any test runs.
  3. Apply the agent patch, then the task's test patch.
  4. Run the grading tests with the task's own Python env, using the
     repo's own test strategy (pytest, or Django's runtests.py),
     collecting every test's result by name.
  5. Verdict from the NAMED tests only. Write the result JSON.

The scorer never imports the target repo - it drives git and the test
runner from outside, so tests run in a process the agent cannot touch.

Run from the project root, inside the project .venv:
  python3 src/scorer.py --task sympy__sympy-11400 --patch results/sympy-11400-claude.patch --agent claude
  python3 src/scorer.py --task django__django-10914 --patch tasks/django-10914-gold_patch.diff --agent gold
  python3 src/scorer.py --task django__django-10914 --patch NONE --agent none
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from datasets import load_dataset

ROOT = Path(__file__).resolve().parent.parent
TEST_TIMEOUT_S = 5 * 60  # same test timeout as src/runner.py

# What the dataset cannot tell us: where the repo is cloned here, which
# Python can run its tests, and which test strategy the repo uses.
# Per-repo defaults cover any task of that repo, with the env picked by
# the task's dataset version; a TASK_SETUP entry overrides them for one
# task (and is the only way to set up repos without defaults).
REPO_SETUP = {
    "django/django": {
        "clone": "repos/django_src",
        "strategy": "django",
        "python_by_version": {
            "3.0": "envs/django-py38/bin/python",
            "3.1": "envs/django31-py38/bin/python",
        },
    },
    "sympy/sympy": {
        "clone": "repos/sympy_src",
        "strategy": "pytest",
        # Python 3.9 + mpmath 1.3.0 + pytest serves both the 1.0 and 1.1
        # version bands (base commits 2016-2017).
        "python_by_version": {
            "1.0": "envs/sympy-py39/bin/python",
            "1.1": "envs/sympy-py39/bin/python",
        },
    },
    "scikit-learn/scikit-learn": {
        "clone": "repos/scikit-learn_src",
        "strategy": "pytest",
        # x86_64 env under Rosetta (see ci/build_env.sh). The worktree's
        # sklearn/ has no compiled extensions; copy in the ones the env
        # built from the base commit, as for matplotlib.
        "overlay": ("envs/scikit-learn-py37/lib/python3.7/site-packages/"
                    "sklearn", "sklearn"),
        "python_by_version": {
            "0.20": "envs/scikit-learn-py37/bin/python",
        },
    },
}

TASK_SETUP = {
    "django__django-10914": {
        "clone": "repos/django_src",
        "python": "envs/django-py38/bin/python",
        "strategy": "django",
    },
    "matplotlib__matplotlib-18869": {
        "clone": "repos/matplotlib_src",
        "python": "envs/matplotlib-py39/bin/python",
        "strategy": "pytest",
        # Tests must import the patched worktree's lib/, which has no
        # compiled extensions; copy in the ones the env built from the
        # base commit (plus the generated _version.py). All gitignored.
        "pythonpath": "lib",
        "overlay": ("envs/matplotlib-py39/lib/python3.9/site-packages/"
                    "matplotlib", "lib/matplotlib"),
    },
}

OVERLAY_PATTERNS = ("*.so", "_version.py")


def apply_overlay(setup, worktree):
    """Copy a task's prebuilt compiled files into a fresh worktree."""
    if "overlay" not in setup:
        return
    src, dest = ROOT / setup["overlay"][0], worktree / setup["overlay"][1]
    for pattern in OVERLAY_PATTERNS:
        for f in src.rglob(pattern):
            target = dest / f.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)

CONFIG_NAMES = {"conftest.py", "pytest.ini", "tox.ini", "setup.cfg"}

DJANGO_STATUS = {"ok": "PASSED", "FAIL": "FAILED",
                 "ERROR": "ERROR", "skipped": "SKIPPED"}


def run(cmd, cwd=None, timeout=None, env=None):
    done = subprocess.run(cmd, cwd=cwd, timeout=timeout, env=env,
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
        "repo": task["repo"],
        "version": task["version"],
        "base_commit": task["base_commit"],
        "fail_to_pass": as_list(task["FAIL_TO_PASS"]),
        "pass_to_pass": as_list(task["PASS_TO_PASS"]),
        "test_patch": task["test_patch"],
    }


def task_setup(task_id, info):
    """Per-task override if there is one, else the repo's defaults."""
    if task_id in TASK_SETUP:
        return TASK_SETUP[task_id]
    repo = REPO_SETUP.get(info["repo"])
    if repo is None:
        raise SystemExit(f"no setup for {task_id}: add a TASK_SETUP entry "
                         f"or REPO_SETUP defaults for {info['repo']}")
    python = repo["python_by_version"].get(info["version"])
    if python is None:
        raise SystemExit(f"no env for {info['repo']} version "
                         f"{info['version']} ({task_id}); add one to "
                         f"REPO_SETUP python_by_version")
    setup = {k: v for k, v in repo.items() if k != "python_by_version"}
    setup["python"] = python
    return setup


def short_name(test_name):
    return test_name.split("::")[-1]


def django_label(test_file):
    # tests/test_utils/tests.py -> test_utils.tests
    parts = list(Path(test_file).parts)
    if parts and parts[0] == "tests":
        parts = parts[1:]
    parts[-1] = Path(parts[-1]).stem
    return ".".join(parts)


DJANGO_TEST = re.compile(r"(\S+) \(([\w.]+)\) \.\.\. ")
DJANGO_RESULT = re.compile(r"(ok|FAIL|ERROR|skipped)(?!\w)")
DJANGO_NAME_ONLY = re.compile(r"(\S+) \(([\w.]+)\)\s*$")


def parse_django(out):
    """Parse runtests.py --verbosity 2 output into {name: status}.

    Most lines are 'test_name (module.Class) ... ok'. A test with a
    docstring prints its name alone on one line and the docstring with
    the result on the next, so a name-only line is carried forward to
    the next result line. Keys match the dataset's FAIL_TO_PASS /
    PASS_TO_PASS format exactly: 'test_name (module.Class)'. Because the
    dataset lists some Django tests by docstring instead, a docstring-style
    test is recorded under both its test-name key and its docstring key.

    A test that fails inside a subTest prints no status at all, so the
    next test's output runs onto the same line:
    'test_a (m.C) ... test_b (m.C) ... ok'. Every test on a line is
    parsed: each name takes the status token right after its ' ... ', and
    a name followed directly by another name gets none (it did not pass).
    """
    status = {}
    pending = None
    for line in out.splitlines():
        pos = 0
        if (pending is not None and not DJANGO_TEST.match(line)
                and not DJANGO_NAME_ONLY.match(line)):
            # The docstring line of a docstring-style test.
            m = re.match(r"^(.*?) \.\.\. ", line)
            if m and DJANGO_TEST.match(line, m.end()):
                # It printed no status; the next test runs on.
                pending = None
                pos = m.end()
            else:
                m = re.match(r"^(.*?) \.\.\. (ok|FAIL|ERROR|skipped)", line)
                if m:
                    status[pending] = DJANGO_STATUS[m.group(2)]
                    status[m.group(1)] = DJANGO_STATUS[m.group(2)]
                    pending = None
                continue
        finished = False  # a status token ended this line's chain
        while m := DJANGO_TEST.match(line, pos):
            pending = None
            result = DJANGO_RESULT.match(line, m.end())
            if result:
                status[f"{m.group(1)} ({m.group(2)})"] = \
                    DJANGO_STATUS[result.group(1)]
                finished = True
                break
            pos = m.end()  # no status: the next test starts right here
        if not finished:
            m = DJANGO_NAME_ONLY.match(line, pos)
            if m:
                pending = f"{m.group(1)} ({m.group(2)})"
    return status


def grade(task_id, patch_path, agent):
    info = load_task(task_id)
    setup = task_setup(task_id, info)
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

    if patch_file is not None and patch_text.strip() == "":
        patch_file = None  # an empty patch grades exactly like NONE

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
        run(["git", "-C", str(clone), "worktree", "remove", "--force",
             str(worktree)])
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
            code, out = run(["git", "-C", str(worktree), "apply",
                             str(tmp_agent)])
            if code != 0:
                result["verdict"] = "error"
                result["reason"] = ("agent patch does not apply: "
                                     + out.strip()[-300:])
                return result

        tmp_test.write_text(info["test_patch"])
        code, out = run(["git", "-C", str(worktree), "apply", str(tmp_test)])
        if code != 0:
            result["verdict"] = "error"
            result["reason"] = ("test patch does not apply: "
                                 + out.strip()[-300:])
            return result

        start = time.time()
        try:
            if setup["strategy"] == "django":
                labels = [django_label(f)
                          for f in patch_files(info["test_patch"])]
                env = dict(os.environ, PYTHONPATH=".")
                code, out = run([str(python), "tests/runtests.py",
                                 "--verbosity", "2", *labels],
                                cwd=worktree, timeout=TEST_TIMEOUT_S,
                                env=env)
                status = parse_django(out)
                key = lambda name: name
            else:
                test_files = patch_files(info["test_patch"])
                apply_overlay(setup, worktree)
                env = (dict(os.environ, PYTHONPATH=setup["pythonpath"])
                       if "pythonpath" in setup else None)
                code, out = run([str(python), "-m", "pytest", *test_files,
                                 "-v", "--tb=no"], cwd=worktree,
                                timeout=TEST_TIMEOUT_S, env=env)
                status = {}
                for nodeid, st in re.findall(
                        r"^(\S+::\S+)\s+(PASSED|FAILED|ERROR)",
                        out, flags=re.M):
                    status[short_name(nodeid)] = st
                key = short_name
        except subprocess.TimeoutExpired:
            result["verdict"] = "error"
            result["reason"] = "test run timed out"
            return result
        result["grading_time_s"] = round(time.time() - start, 1)

        def count(names):
            passed = sum(1 for n in names
                         if status.get(key(n)) == "PASSED")
            return {"passed": passed, "total": len(names)}

        result["fail_to_pass"] = count(info["fail_to_pass"])
        result["pass_to_pass_named"] = count(info["pass_to_pass"])
        ok = (result["fail_to_pass"]["passed"]
              == result["fail_to_pass"]["total"]
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
