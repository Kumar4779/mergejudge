"""MergeJudge bulk ingestion - pin new SWE-bench Lite tasks, validation-gated.

For a repo and a count, take the next instances of that repo in dataset
order that are not already pinned in tasks/tasks.json, and for each:
  1. Write the same per-task files the manual extraction produced
     (extract_task.py / extract_patches.py): tasks/<short>-issue.txt,
     tasks/<short>-test_patch.diff, tasks/<short>-gold_patch.diff.
  2. Register it in tasks/tasks.json ({"instance_id", "repo"}).
  3. Gate it through src/scorer.py, unchanged: the gold patch must be
     resolved and the empty patch (NONE) not_resolved. Setup comes from
     the scorer's per-repo defaults - no per-task entries.
A task failing the gate is quarantined: removed from tasks.json, its
files (and gate results) moved to tasks/quarantine/ with a NOTE naming
the failure.

Run from the project root, inside the project .venv:
  python3 src/ingest_tasks.py --repo django/django --count 10
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from datasets import load_dataset

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "tasks"
TASKS_JSON = TASKS / "tasks.json"
QUARANTINE = TASKS / "quarantine"


def read_pinned():
    return json.loads(TASKS_JSON.read_text())


def write_pinned(entries):
    entries = sorted(entries, key=lambda e: e["instance_id"])
    lines = ",\n".join(f"  {json.dumps(e)}" for e in entries)
    TASKS_JSON.write_text(f"[\n{lines}\n]\n")


def task_files(short):
    return [TASKS / f"{short}-{suffix}" for suffix in
            ("issue.txt", "test_patch.diff", "gold_patch.diff")]


def write_task(record):
    short = record["instance_id"].split("__")[-1]
    issue, test_patch, gold_patch = task_files(short)
    issue.write_text(record["problem_statement"])
    test_patch.write_text(record["test_patch"])
    gold_patch.write_text(record["patch"])
    return short


def grade(task_id, patch, agent):
    """Run the scorer CLI; return its result record (or None)."""
    done = subprocess.run([sys.executable, str(ROOT / "src" / "scorer.py"),
                           "--task", task_id, "--patch", patch,
                           "--agent", agent], cwd=ROOT,
                          capture_output=True, text=True)
    short = task_id.split("__")[-1]
    path = ROOT / "results" / f"{short}-{agent}.json"
    if done.returncode != 0 or not path.exists():
        return {"verdict": "error",
                "reason": (done.stdout + done.stderr).strip()[-300:]}
    return json.loads(path.read_text())


def counts(record, key):
    c = record.get(key)
    return f"{c['passed']}/{c['total']}" if c else "—"


def gate(task_id, short):
    """Return None if the task passes, else a one-line failure reason."""
    gold = grade(task_id, f"tasks/{short}-gold_patch.diff", "gold")
    none = grade(task_id, "NONE", "none")
    print(f"  gold: {gold['verdict']} F2P {counts(gold, 'fail_to_pass')} "
          f"P2P {counts(gold, 'pass_to_pass_named')} | none: "
          f"{none['verdict']} F2P {counts(none, 'fail_to_pass')}")
    problems = []
    if gold["verdict"] != "resolved":
        problems.append(f"gold patch {gold['verdict']} (FAIL_TO_PASS "
                        f"{counts(gold, 'fail_to_pass')}, PASS_TO_PASS "
                        f"{counts(gold, 'pass_to_pass_named')})"
                        + (f": {gold['reason']}" if gold.get("reason") else ""))
    if none["verdict"] != "not_resolved":
        problems.append(f"empty patch {none['verdict']} (FAIL_TO_PASS "
                        f"{counts(none, 'fail_to_pass')})"
                        + (f": {none['reason']}" if none.get("reason") else ""))
    return "; ".join(problems) or None


def quarantine(entries, task_id, short, reason):
    QUARANTINE.mkdir(exist_ok=True)
    moved = task_files(short) + [ROOT / "results" / f"{short}-{a}.json"
                                 for a in ("gold", "none")]
    for f in moved:
        if f.exists():
            shutil.move(str(f), QUARANTINE / f.name)
    (QUARANTINE / f"{short}-NOTE.txt").write_text(
        f"{task_id} failed the ingestion validation gate.\n{reason}\n")
    return [e for e in entries if e["instance_id"] != task_id]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="e.g. django/django")
    ap.add_argument("--count", type=int, required=True)
    args = ap.parse_args()

    entries = read_pinned()
    pinned = {e["instance_id"] for e in entries}
    quarantined = {p.name[:-len("-NOTE.txt")]
                   for p in QUARANTINE.glob("*-NOTE.txt")}
    ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    new = [x for x in ds if x["repo"] == args.repo
           and x["instance_id"] not in pinned
           and x["instance_id"].split("__")[-1] not in quarantined]
    new = new[:args.count]
    print(f"ingesting {len(new)} {args.repo} task(s)")

    passed, failed = [], []
    for record in new:
        task_id = record["instance_id"]
        short = write_task(record)
        entries.append({"instance_id": task_id, "repo": record["repo"]})
        write_pinned(entries)
        print(f"{task_id} (version {record['version']})")
        reason = gate(task_id, short)
        if reason is None:
            passed.append(task_id)
        else:
            entries = quarantine(entries, task_id, short, reason)
            write_pinned(entries)
            failed.append((task_id, reason))
            print(f"  QUARANTINED: {reason}")

    print(f"\n{len(passed)}/{len(new)} passed the gate")
    for task_id, reason in failed:
        print(f"  quarantined {task_id}: {reason}")


if __name__ == "__main__":
    main()
