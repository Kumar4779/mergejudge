"""MergeJudge runner v1 - run ONE coding agent on ONE task, then grade it.

The other half of the scorer. For one task and one agent arm:
  1. Fresh repo holding only the task's base commit: the tree is git
     archive'd out of the clone and committed once, so none of the
     clone's later history (which contains the real fix) comes along.
  2. Run the agent headless inside it, with only the issue text and the
     rules - it never sees the test patch or the gold patch.
  3. Hard timeout (sandbox contract). Even on timeout, whatever patch
     exists is captured and graded - the scorer is the judge. By default
     the agent runs under sandbox-exec (sandbox/agent.sb.template): no
     reads anywhere in the project except envs/, writes only to its
     worktree and temp,
     and network only through src/egress_proxy.py to the model API.
     --no-sandbox turns the gate off.
  4. Capture the patch (git add -A + diff --cached, so new files count),
     save the agent's full output as a log, remove the worktree.
  5. Grade the patch with src/scorer.py and stamp agent_time_s,
     agent_status, cost_usd, agent_config, sandbox, model (from the
     trace) and egress_refused into the result JSON the scorer writes.

Run from the project root, inside the project .venv:
  python3 src/runner.py --task sympy__sympy-11400 --agent claude-e2e
"""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from datasets import load_dataset

import egress_proxy
import scorer
from scorer import apply_overlay

ROOT = Path(__file__).resolve().parent.parent
AGENT_TIMEOUT_S = 30 * 60  # hard kill for the agent run (sandbox contract)

# Task setup (clone, env python, overlay) comes from the scorer's
# task_setup(): per-repo defaults, env by dataset version. These entries
# override it for the original three tasks, so their prompts (including
# their test hints) stay exactly as they were.
TASK_SETUP = {
    "sympy__sympy-11400": {
        "clone": "repos/sympy_src",
        "python": "envs/sympy-py39/bin/python",
    },
    "django__django-10914": {
        "clone": "repos/django_src",
        "python": "envs/django-py38/bin/python",
        "test_hint": "Run the affected tests from the repo root with: "
                     "PYTHONPATH=. {python} tests/runtests.py test_utils.tests",
    },
    "matplotlib__matplotlib-18869": {
        "clone": "repos/matplotlib_src",
        "python": "envs/matplotlib-py39/bin/python",
        "test_hint": "Run the affected tests from the repo root with: "
                     "PYTHONPATH=lib {python} -m pytest "
                     "lib/matplotlib/tests/test_matplotlib.py",
        # Same prebuilt compiled files the scorer copies in (see scorer.py).
        "overlay": ("envs/matplotlib-py39/lib/python3.9/site-packages/"
                    "matplotlib", "lib/matplotlib"),
    },
}

# Test hint for tasks without an override: mechanics only. It names no
# test module, file or test, so nothing about the hidden tests leaks.
GENERIC_TEST_HINT = {
    "django/django": "You can run the affected tests yourself with: "
                     "PYTHONPATH=. {env_python} tests/runtests.py <module> "
                     "\u2014 pick the module(s) covering the code you "
                     "changed.",
    "sympy/sympy": "You can run the affected tests yourself with: "
                   "{env_python} -m pytest <path> \u2014 pick the tests "
                   "covering the code you changed.",
    # PYTHONPATH=lib so the tests import the agent's tree, not the env's
    # base-commit install.
    "matplotlib/matplotlib": "You can run the affected tests yourself with: "
                             "PYTHONPATH=lib {env_python} -m pytest <path> "
                             "\u2014 pick the tests covering the code you "
                             "changed.",
}


def runner_setup(task_id, info):
    """The runner's override if any, else the scorer's setup + generic hint."""
    if task_id in TASK_SETUP:
        return TASK_SETUP[task_id]
    setup = dict(scorer.task_setup(task_id, info))
    if info["repo"] in GENERIC_TEST_HINT:
        setup["test_hint"] = GENERIC_TEST_HINT[info["repo"]]
    return setup


# Per-arm configuration, keyed by --agent. Arms differ in extra CLI args
# (the model) and scaffold. "direct" is the base prompt unchanged;
# "plan-first" appends PLAN_FIRST_INSTRUCTION to it. An arm not listed
# here (e.g. claude-e2e2) runs direct with no extra args and gets no
# agent_config. A -rN suffix marks a reliability repeat of the base arm
# (claude-sonnet-r2 runs as claude-sonnet and is stamped repeat: 2).
DEFAULT_LABEL = "claude-code (default model, Opus)"
SONNET_LABEL = "claude-code (Sonnet)"
ARM_CONFIG = {
    "claude-e2e": {"args": [], "label": DEFAULT_LABEL, "scaffold": "direct"},
    "claude-sonnet": {"args": ["--model", "sonnet"], "label": SONNET_LABEL,
                      "scaffold": "direct"},
    "claude-planfirst": {"args": [], "label": DEFAULT_LABEL,
                         "scaffold": "plan-first"},
    "claude-sonnet-planfirst": {"args": ["--model", "sonnet"],
                                "label": SONNET_LABEL,
                                "scaffold": "plan-first"},
}
DEFAULT_ARM = {"args": [], "label": None, "scaffold": "direct"}

PLAN_FIRST_INSTRUCTION = (
    "Work in this order: (1) write a small reproduction script that "
    "demonstrates the bug and run it; (2) state your plan in a few lines "
    "— root cause and which files you will change; (3) make the smallest "
    "fix; (4) run the affected tests on your fix using the test command "
    "given above, and keep iterating until they pass. Do not finish until "
    "step 4 passes.\n")
REPEAT_SUFFIX = re.compile(r"^(.+)-r(\d+)$")


def lookup_arm(agent):
    """Return (arm config, repeat number or None) for an --agent name."""
    match = REPEAT_SUFFIX.match(agent)
    if match:
        return ARM_CONFIG.get(match[1], DEFAULT_ARM), int(match[2])
    return ARM_CONFIG.get(agent, DEFAULT_ARM), None

PROMPT_TEMPLATE = """You are fixing a bug in this repository. Work only inside this directory: {worktree}

Issue:
{issue}

Rules:
- Do not edit any test files, and do not create files whose names start with test_.
- Do not modify anything outside this directory.
- Make the smallest fix that resolves the issue.
- {test_hint}
- When you are done, stop. Your changes will be captured as a patch and graded on a clean checkout with tests you cannot see.
"""


# Appended only with --probe-prompt, to check the sandbox holds against an
# agent that is told to go looking for the answer.
PROBE_INSTRUCTION = """
Before doing the task above, run these leak probes and report exactly what each one finds:
1. Try to read the MergeJudge project README at {project}/README.md.
2. Run git log --all in this repository and list every commit you see.
3. For any commit later than the one you are on, run git show on it.
Then do the task as normal.
""".format(project=ROOT)


def run(cmd, cwd=None, timeout=None):
    done = subprocess.run(cmd, cwd=cwd, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True)
    return done.returncode, done.stdout


def materialize_base(clone, base_commit, dest):
    """Write base_commit's tree to dest as a fresh one-commit repository.

    The agent never gets the clone's history: no later commits (the real
    fix is one of them), no branches, no remotes, no shared objects.
    """
    dest.mkdir(parents=True)
    archive = subprocess.Popen(["git", "-C", str(clone), "archive",
                                "--format=tar", base_commit],
                               stdout=subprocess.PIPE)
    untar = subprocess.run(["tar", "-x", "-C", str(dest)],
                           stdin=archive.stdout)
    archive.stdout.close()
    if archive.wait() != 0 or untar.returncode != 0:
        raise SystemExit(f"git archive of {base_commit} failed")
    git = ["git", "-C", str(dest), "-c", "user.name=MergeJudge",
           "-c", "user.email=mergejudge@localhost",
           "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]
    for step in (["init", "-q", "-b", "main"], ["add", "-A"],
                 ["commit", "-q", "-m", "Task base"]):
        code, out = run(git + step)
        if code != 0:
            raise SystemExit(f"materializing base failed at git {step[0]}: "
                             f"{out.strip()[-300:]}")


def load_task(task_id):
    ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    task = next(x for x in ds if x["instance_id"] == task_id)
    return {
        "repo": task["repo"],
        "version": task["version"],
        "base_commit": task["base_commit"],
        "issue": task["problem_statement"],
    }


def sandbox_profile(worktree, proxy_port):
    """Fill sandbox/agent.sb.template with this run's real paths.

    sandbox-exec matches resolved paths (/var -> /private/var), so every
    path is passed through realpath.
    """
    real = os.path.realpath
    values = {
        "WORKTREE": real(worktree),
        "PROJECT": real(ROOT),
        "TMPDIR": real(tempfile.gettempdir()),
        "HOME": real(Path.home()),
        "PROXY_PORT": str(proxy_port),
    }
    profile = (ROOT / "sandbox" / "agent.sb.template").read_text()
    for key, value in values.items():
        profile = profile.replace("{" + key + "}", value)
    return profile


def build_command(cli, prompt, extra_args):
    if cli == "claude":
        return ["claude", "-p", prompt, "--dangerously-skip-permissions",
                "--output-format", "stream-json", "--verbose", *extra_args]
    raise SystemExit(f"unknown --cli: {cli} (v1 supports: claude)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--agent", required=True,
                    help="arm label used in result filenames, e.g. claude-e2e")
    ap.add_argument("--cli", default="claude")
    ap.add_argument("--keep", action="store_true",
                    help="keep the agent worktree afterwards (debugging)")
    ap.add_argument("--no-sandbox", dest="sandbox", action="store_false",
                    help="run the agent without the sandbox-exec gate")
    ap.add_argument("--probe-prompt", action="store_true",
                    help="append the adversarial leak-probe instruction "
                         "(sandbox validation only, not a scored arm)")
    args = ap.parse_args()

    info = load_task(args.task)
    setup = runner_setup(args.task, info)
    clone = ROOT / setup["clone"]
    python = ROOT / setup["python"]
    short = args.task.split("__")[-1]

    worktree = (Path(tempfile.gettempdir())
                / f"mergejudge-{short}-{args.agent}-run")

    def remove_worktree():
        if worktree.exists():
            shutil.rmtree(worktree)

    remove_worktree()
    materialize_base(clone, info["base_commit"], worktree)
    apply_overlay(setup, worktree)

    raw_hint = setup.get("test_hint")
    test_hint = (raw_hint.format(python=python, env_python=python)
                 if raw_hint
                 else f"You may run tests with this Python: {python}")
    prompt = PROMPT_TEMPLATE.format(worktree=worktree, issue=info["issue"],
                                    test_hint=test_hint)
    arm, repeat = lookup_arm(args.agent)
    if arm["scaffold"] == "plan-first":
        prompt += PLAN_FIRST_INSTRUCTION
    if args.probe_prompt:
        prompt += PROBE_INSTRUCTION
    cmd = build_command(args.cli, prompt, arm["args"])

    # A fresh matplotlib config dir per run, beside the agent repo (not in
    # it, or the patch would capture it), so matplotlib never writes
    # ~/.matplotlib - which the sandbox denies anyway.
    mplconfig = worktree.parent / f"mergejudge-{short}-{args.agent}-mplconfig"
    shutil.rmtree(mplconfig, ignore_errors=True)
    mplconfig.mkdir()
    env = dict(os.environ, MPLCONFIGDIR=str(mplconfig))
    proxy = None
    profile_path = worktree.parent / f"mergejudge-{short}-{args.agent}.sb"
    if args.sandbox:
        proxy = egress_proxy.start()
        port = proxy.server_address[1]
        profile_path.write_text(sandbox_profile(worktree, port))
        cmd = ["sandbox-exec", "-f", str(profile_path), *cmd]
        env.update(HTTPS_PROXY=f"http://127.0.0.1:{port}",
                   HTTP_PROXY=f"http://127.0.0.1:{port}",
                   CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1")

    start = time.time()
    status = "completed"
    proc = subprocess.Popen(cmd, cwd=worktree, env=env,
                            stdout=subprocess.PIPE,
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
    egress_refused = []
    if proxy is not None:
        proxy.shutdown()
        egress_refused = sorted(set(proxy.refused))
        profile_path.unlink(missing_ok=True)

    log_path = ROOT / "results" / f"{short}-{args.agent}.log"
    log_path.write_text(log)

    cost_usd = None
    model = None
    for line in log.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            model = event.get("model")
        if event.get("type") == "result" and "total_cost_usd" in event:
            cost_usd = event["total_cost_usd"]

    run(["git", "-C", str(worktree), "add", "-A"])
    code, patch_text = run(["git", "-C", str(worktree), "diff", "--cached"])
    patch_path = ROOT / "results" / f"{short}-{args.agent}.patch"
    patch_path.write_text(patch_text)

    if not args.keep:
        remove_worktree()
        shutil.rmtree(mplconfig, ignore_errors=True)

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
        if cost_usd is not None:
            record["cost_usd"] = cost_usd
        if arm["label"] is not None:
            record["agent_config"] = arm["label"]
        if repeat is not None:
            record["repeat"] = repeat
        record["scaffold"] = arm["scaffold"]
        record["sandbox"] = args.sandbox
        record["model"] = model
        if args.probe_prompt:
            record["probe_prompt"] = True
        if args.sandbox:
            record["egress_refused"] = egress_refused
        result_path.write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    main()
