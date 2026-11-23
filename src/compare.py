"""MergeJudge compare view - rank agent arms per task from graded results.

Reads every results/*.json the scorer and runner wrote. For each task:
  1. Group runs into families: model family + scaffold, e.g.
     "Claude Sonnet · plan-first"; a record without a scaffold is direct.
     gold and none are controls: shown for reference, never ranked.
     Adversarial probe runs (probe_prompt: true) are not data and are
     skipped entirely.
  2. Aggregate EVERY direct-scaffold run of a family on a task: runs,
     resolved, pass^1 = resolved / runs (with a 95% Wilson score
     interval), mean diff lines (added + removed)
     of the resolved runs, and mean cost of all runs (failures cost too).
  3. Rank families reliability first: highest pass^1, then lowest mean
     diff of resolved runs, then lowest mean cost. No arm is ranked on a
     single sample. Only direct-scaffold families are ranked here and in
     the Portfolio. A task where no direct family resolved any run has
     no winner: it counts toward no family's tasks won and is left out
     of the Oracle row.
Then a portfolio summary per family (tasks won, overall pass^1, expected
spend = sum of per-task mean costs), plus an Oracle row that takes each
task's winner, a reward-hacking rate per family (resolved runs with a
hard-zero integrity scan / all attempts), and a reliability table: every run (repeats included) per
(task, family), with pass^k = C(resolved, k) / C(runs, k), and a 2x2
factorial grid per task (scaffold x model family) over every run.

Run from the project root:
  python3 src/compare.py
"""

import json
from math import comb, sqrt
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


def aggregate(fam, runs):
    resolved = [r for r in runs if r["verdict"] == "resolved"]
    costs = [r["cost_usd"] for r in runs if r.get("cost_usd") is not None]
    return {
        "family": fam,
        "runs": len(runs),
        "resolved": len(resolved),
        "pass1": len(resolved) / len(runs),
        "mean_diff": (sum(diff_total(r) for r in resolved) / len(resolved)
                      if resolved else None),
        "mean_cost": sum(costs) / len(costs) if costs else None,
        "costed": len(costs),
    }


def rank_key(agg):
    inf = float("inf")
    return (-agg["pass1"],
            agg["mean_diff"] if agg["mean_diff"] is not None else inf,
            agg["mean_cost"] if agg["mean_cost"] is not None else inf,
            agg["family"])


def fmt_diff(value):
    return f"{value:.1f}" if value is not None else "—"


def fmt_mean_cost(agg):
    text = fmt_cost(agg["mean_cost"])
    if agg["mean_cost"] is not None and agg["costed"] < agg["runs"]:
        text += f" ({agg['costed']} of {agg['runs']} costed)"
    return text


def wilson(resolved, runs, z=1.96):
    """95% Wilson score interval for resolved / runs."""
    p = resolved / runs
    centre = (p + z * z / (2 * runs)) / (1 + z * z / runs)
    half = (z / (1 + z * z / runs)
            * sqrt(p * (1 - p) / runs + z * z / (4 * runs * runs)))
    return centre - half, centre + half


def fmt_pass1(resolved, runs):
    lo, hi = wilson(resolved, runs)
    return f"{resolved / runs:.3f} [{lo:.3f}, {hi:.3f}]"


def agg_row(rank, agg):
    return (f"| {rank}. {agg['family']} | {agg['runs']} | {agg['resolved']} "
            f"| {fmt_pass1(agg['resolved'], agg['runs'])} "
            f"| {fmt_diff(agg['mean_diff'])} "
            f"| {fmt_mean_cost(agg)} |")


def win_basis(winner, runner_up):
    if runner_up is None:
        return "only arm run"
    if winner["pass1"] != runner_up["pass1"]:
        return (f"won on reliability: pass^1 {winner['pass1']:.3f} vs "
                f"{runner_up['pass1']:.3f}")
    if winner["mean_diff"] != runner_up["mean_diff"]:
        return (f"tie on pass^1 ({winner['pass1']:.3f}); won on diff: mean "
                f"{fmt_diff(winner['mean_diff'])} vs "
                f"{fmt_diff(runner_up['mean_diff'])} lines (resolved runs)")
    return (f"tie on pass^1 and diff; won on cost: mean "
            f"{fmt_cost(winner['mean_cost'])} vs "
            f"{fmt_cost(runner_up['mean_cost'])} per run")


def main():
    records = [json.loads(p.read_text())
               for p in sorted((ROOT / "results").glob("*.json"))]
    records = [r for r in records if not r.get("probe_prompt")]
    tasks = sorted({r["task"] for r in records})

    winners = {}  # task -> winning aggregate
    aggs = {}  # family -> {task: aggregate}
    for task in tasks:
        runs = [r for r in records if r["task"] == task]
        controls = [r for r in runs if agent_name(r) in CONTROLS]
        by_family = {}
        for r in runs:
            # Headline tables and Portfolio rank direct arms only; other
            # scaffolds appear in the Reliability and Factorial sections.
            if agent_name(r) not in CONTROLS and scaffold(r) == "direct":
                by_family.setdefault(family(r), []).append(r)
        ranked = sorted((aggregate(f, rs) for f, rs in by_family.items()),
                        key=rank_key)

        print(f"## {task}\n")
        print("| Family | Runs | Resolved | pass^1 | Mean diff (resolved) "
              "| Mean cost (all runs) |")
        print("|---|---|---|---|---|---|")
        for i, agg in enumerate(ranked, 1):
            aggs.setdefault(agg["family"], {})[task] = agg
            print(agg_row(i, agg))
        if controls:
            print("\n| Control | Verdict | FAIL_TO_PASS | PASS_TO_PASS "
                  "| Diff | Time | Cost |")
            print("|---|---|---|---|---|---|---|")
            for r in sorted(controls, key=agent_name):
                print(row(agent_name(r), r))

        if ranked and ranked[0]["resolved"] == 0:
            print("\nNo winner — no arm resolved this task.\n")
        elif ranked:
            winner = ranked[0]
            winners[task] = winner
            runner_up = ranked[1] if len(ranked) > 1 else None
            print(f"\nWinner: {winner['family']} — "
                  f"{win_basis(winner, runner_up)}\n")

    n = len(tasks)
    print("## Portfolio\n")
    print("| Family | Tasks won | Overall pass^1 | Expected spend |")
    print("|---|---|---|---|")
    for fam in sorted(aggs):
        per_task = aggs[fam].values()
        won = sum(1 for w in winners.values() if w["family"] == fam)
        print(f"| {fam} | {won}/{n} | {overall_pass1(per_task)} "
              f"| {expected_spend(per_task, n)} |")
    # The Oracle covers only tasks with a winner.
    print(f"| Oracle (per-task winner) | {len(winners)}/{n} "
          f"| {overall_pass1(winners.values())} "
          f"| {expected_spend(winners.values(), len(winners))} |")

    integrity_table(records)
    reliability(records, tasks)
    factorial(records, tasks)


def integrity_table(records):
    """Reward-hacking rate per Portfolio family: resolved runs whose trace
    scan (src/integrity.py) is hard_zero, over ALL attempts."""
    by_family = {}
    for r in records:
        if agent_name(r) not in CONTROLS and scaffold(r) == "direct":
            by_family.setdefault(family(r), []).append(r)
    print("\n## Integrity (reward-hacking rate)\n")
    print("| Family | Attempts | Scanned | Soft flags | Resolved with "
          "hard-zero | Reward-hacking rate |")
    print("|---|---|---|---|---|---|")
    for fam in sorted(by_family):
        runs = by_family[fam]
        outcome = [(r.get("integrity") or {}).get("outcome", "unscanned")
                   for r in runs]
        scanned = sum(o != "unscanned" for o in outcome)
        soft = outcome.count("soft_flag")
        hacked = sum(1 for r, o in zip(runs, outcome)
                     if o == "hard_zero" and r["verdict"] == "resolved")
        print(f"| {fam} | {len(runs)} | {scanned} | {soft} | {hacked} "
              f"| {hacked / len(runs):.3f} |")


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


def overall_pass1(per_task):
    per_task = list(per_task)
    runs = sum(a["runs"] for a in per_task)
    resolved = sum(a["resolved"] for a in per_task)
    return f"{fmt_pass1(resolved, runs)} ({resolved}/{runs})"


def expected_spend(per_task, n_tasks):
    """Sum of per-task mean cost per run: the cost of one run per task."""
    per_task = list(per_task)
    costs = [a["mean_cost"] for a in per_task if a["mean_cost"] is not None]
    text = f"${sum(costs):.4f}"
    missing = n_tasks - len(costs)
    return text + (f" ({missing} task(s) without cost)" if missing else "")


if __name__ == "__main__":
    main()
