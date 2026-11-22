"""MergeJudge compare view - rank agent arms per task from graded results.

Reads every results/*.json the scorer and runner wrote. For each task:
  1. Group runs into families: model family + scaffold, e.g.
     "Claude Sonnet · plan-first"; a record without a scaffold is direct.
     gold and none are controls: shown for reference, never ranked.
     Adversarial probe runs (probe_prompt: true) are not data and are
     skipped entirely.
  2. Pick one canonical run per (task, family): prefer a run with cost_usd
     recorded, otherwise the first by agent name.
  3. Rank canonical runs: resolved first, then fewest diff lines
     (added + removed), then lowest cost (missing cost sorts last).
Then a portfolio summary per family, plus an Oracle line that takes each
task's winner, and a reliability table: every run (repeats included) per
(task, family), with pass^k = C(resolved, k) / C(runs, k), and a 2x2
factorial grid per task (scaffold x model family) over every run.

Run from the project root:
  python3 src/compare.py
"""

import json
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTROLS = ("gold", "none")
LEGACY_FAMILY = {
    "claude": "Claude (default model)",
    "claude-e2e": "Claude (default model)",
    "claude-e2e2": "Claude (default model)",
}


def agent_name(record):
    # Hand-made records keep the arm name in agent_key, a label in agent.
    return record.get("agent_key") or record["agent"]


def model_family(record):
    config = record.get("agent_config")
    if config:
        lowered = config.lower()
        if "sonnet" in lowered:
            return "Claude Sonnet"
        if "default" in lowered:
            return "Claude (default model)"
        return config
    name = agent_name(record)
    return LEGACY_FAMILY.get(name, name)


def scaffold(record):
    return record.get("scaffold", "direct")


def family(record):
    return f"{model_family(record)} · {scaffold(record)}"


def diff_total(record):
    return record.get("diff_lines_added", 0) + record.get("diff_lines_removed", 0)


def rank_key(record):
    cost = record.get("cost_usd")
    return (record["verdict"] != "resolved", diff_total(record),
            cost is None, cost or 0, agent_name(record))


def fmt_counts(counts):
    return f"{counts['passed']}/{counts['total']}" if counts else "—"


def fmt_cost(cost):
    return f"${cost:.4f}" if cost is not None else "—"


def row(label, record):
    added = record.get("diff_lines_added", 0)
    removed = record.get("diff_lines_removed", 0)
    diff = f"+{added} / −{removed}" if added or removed else "—"
    time_s = record.get("agent_time_s")
    return (f"| {label} | {record['verdict']} "
            f"| {fmt_counts(record.get('fail_to_pass'))} "
            f"| {fmt_counts(record.get('pass_to_pass_named'))} "
            f"| {diff} | {f'{time_s}s' if time_s is not None else '—'} "
            f"| {fmt_cost(record.get('cost_usd'))} |")


def why_won(winner, runner_up):
    if winner["verdict"] != "resolved":
        return "no arm resolved the task"
    if runner_up is None:
        return "only arm run"
    if runner_up["verdict"] != "resolved":
        return "only arm that resolved"
    if diff_total(winner) != diff_total(runner_up):
        return (f"both resolved; smaller diff "
                f"({diff_total(winner)} vs {diff_total(runner_up)} lines)")
    return (f"both resolved with equal diffs; lower cost "
            f"({fmt_cost(winner.get('cost_usd'))} vs "
            f"{fmt_cost(runner_up.get('cost_usd'))})")


def canonical(runs):
    # Reliability repeats (-rN) never displace an existing canonical run.
    runs = [r for r in runs if r.get("repeat") is None] or runs
    with_cost = [r for r in runs if r.get("cost_usd") is not None]
    return sorted(with_cost or runs, key=agent_name)[0]


def main():
    records = [json.loads(p.read_text())
               for p in sorted((ROOT / "results").glob("*.json"))]
    records = [r for r in records if not r.get("probe_prompt")]
    tasks = sorted({r["task"] for r in records})

    winners = {}
    canon_by_family = {}  # family -> {task: canonical record}
    for task in tasks:
        runs = [r for r in records if r["task"] == task]
        controls = [r for r in runs if agent_name(r) in CONTROLS]
        by_family = {}
        for r in runs:
            if agent_name(r) not in CONTROLS:
                by_family.setdefault(family(r), []).append(r)
        ranked = sorted((canonical(rs) for rs in by_family.values()),
                        key=rank_key)

        print(f"## {task}\n")
        print("| Run | Verdict | FAIL_TO_PASS | PASS_TO_PASS | Diff | Time | Cost |")
        print("|---|---|---|---|---|---|---|")
        for i, r in enumerate(ranked, 1):
            canon_by_family.setdefault(family(r), {})[task] = r
            print(row(f"{i}. {family(r)} ({agent_name(r)})", r))
        for r in sorted(controls, key=agent_name):
            print(row(f"{agent_name(r)} (control)", r))

        if ranked:
            winner = ranked[0]
            winners[task] = winner
            runner_up = ranked[1] if len(ranked) > 1 else None
            print(f"\nWinner: {family(winner)} ({agent_name(winner)}) — "
                  f"{why_won(winner, runner_up)}\n")

    n = len(tasks)
    print("## Portfolio\n")
    print("| Family | Tasks resolved | Total cost |")
    print("|---|---|---|")
    for fam in sorted(canon_by_family):
        runs = canon_by_family[fam].values()
        resolved = sum(r["verdict"] == "resolved" for r in runs)
        print(f"| {fam} | {resolved}/{n} | {total_cost(runs)} |")
    resolved = sum(r["verdict"] == "resolved" for r in winners.values())
    print(f"| Oracle (per-task winner) | {resolved}/{n} "
          f"| {total_cost(winners.values())} |")

    reliability(records, tasks)
    factorial(records, tasks)


def pass_hat_k(runs, resolved, k):
    """Unbiased pass^k: chance k runs drawn without replacement all resolve."""
    return comb(resolved, k) / comb(runs, k)


def reliability(records, tasks):
    cells = {}  # (task, family) -> [resolved?, ...] over every run
    for r in records:
        if agent_name(r) not in CONTROLS:
            cells.setdefault((r["task"], family(r)), []).append(
                r["verdict"] == "resolved")
    max_runs = max(len(v) for v in cells.values())
    ks = range(1, max_runs + 1)

    print("\n## Reliability (all runs, pass^k)\n")
    print("| Task | Family | Runs | Resolved | "
          + " | ".join(f"pass^{k}" for k in ks) + " |")
    print("|---|---|---|---|" + "---|" * len(ks))
    for task, fam in sorted(cells):
        outcomes = cells[(task, fam)]
        n, c = len(outcomes), sum(outcomes)
        estimates = [f"{pass_hat_k(n, c, k):.3f}" if k <= n else "—"
                     for k in ks]
        print(f"| {task} | {fam} | {n} | {c} | " + " | ".join(estimates) + " |")


FACTORIAL_ROWS = ("direct", "plan-first")
FACTORIAL_COLS = ("Claude (default model)", "Claude Sonnet")


def factorial(records, tasks):
    print("\n## Factorial (scaffold x model, all runs)")
    for task in tasks:
        print(f"\n### {task}\n")
        print("| Scaffold | " + " | ".join(FACTORIAL_COLS) + " |")
        print("|---|" + "---|" * len(FACTORIAL_COLS))
        for scaf in FACTORIAL_ROWS:
            cells = []
            for fam in FACTORIAL_COLS:
                runs = [r for r in records if r["task"] == task
                        and agent_name(r) not in CONTROLS
                        and scaffold(r) == scaf and model_family(r) == fam]
                cells.append(factorial_cell(runs))
            print(f"| {scaf} | " + " | ".join(cells) + " |")


def factorial_cell(runs):
    if not runs:
        return "—"
    resolved = sum(r["verdict"] == "resolved" for r in runs)
    costs = [r["cost_usd"] for r in runs if r.get("cost_usd") is not None]
    if not costs:
        return f"{resolved}/{len(runs)} resolved, no cost recorded"
    note = (f" ({len(costs)} of {len(runs)} runs costed)"
            if len(costs) < len(runs) else "")
    return (f"{resolved}/{len(runs)} resolved, "
            f"mean {fmt_cost(sum(costs) / len(costs))}{note}")


def total_cost(runs):
    runs = list(runs)
    costs = [r["cost_usd"] for r in runs if r.get("cost_usd") is not None]
    missing = len(runs) - len(costs)
    text = f"${sum(costs):.4f}"
    return text + (f" ({missing} run(s) without cost)" if missing else "")


if __name__ == "__main__":
    main()
