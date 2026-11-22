# MergeJudge

**Trust no patch you haven't tested.** MergeJudge grades coding-agent patches the only way that counts: by applying them to a clean checkout and running the real tests — never by trusting the agent's own report.

Coding agents will happily tell you "all tests pass" in an environment where the grading tests don't even exist. MergeJudge separates the two jobs that benchmarks too often blur: the agent proposes, an independent verifier disposes. A human approves the winner; nothing auto-merges.

## How it works

1. **Run** (`src/runner.py`) — the agent gets a fresh git worktree at the task's base commit, in a temp directory outside the project tree, with only the issue text and the rules. It never sees the test patch or the gold patch. A 30-minute hard timeout kills the agent's whole process group. The run's full tool-call trace is logged, and the patch, wall-clock time, and API-equivalent cost are captured.
2. **Grade** (`src/scorer.py`) — on a *separate* clean checkout, the scorer applies the agent's patch, then the hidden test patch, and runs the repo's own test strategy (pytest, or Django's `runtests.py`). The verdict comes from the task's named FAIL_TO_PASS / PASS_TO_PASS tests only — never from raw file counts, and never from the agent's claims.
3. **Anti-cheat** — a patch that touches a test file or test config, *including deleting one*, is disqualified before any test runs. Re-grading can never leave stale counts behind: a failed or disqualified re-grade replaces the record's numbers instead of inheriting them.

## Results so far (SWE-bench Lite)

| Task | Run | Verdict | FAIL_TO_PASS | PASS_TO_PASS | Diff | Agent time | Cost |
|---|---|---|---|---|---|---|---|
| sympy__sympy-11400 | none (baseline) | not_resolved | 0/2 | 29/29 | — | — | — |
| sympy__sympy-11400 | gold (human fix) | resolved | 2/2 | 29/29 | +14 / −0 | — | — |
| sympy__sympy-11400 | claude (manual) | resolved | 2/2 | 29/29 | +14 / −0 | ~41s | — |
| sympy__sympy-11400 | claude-e2e (runner) | resolved | 2/2 | 29/29 | +14 / −0 | 24.4s | — |
| sympy__sympy-11400 | claude-e2e2 (audited) | resolved | 2/2 | 29/29 | +14 / −0 | 26.4s | $0.2156 |
| sympy__sympy-11400 | claude-sonnet (runner) | not_resolved | 0/2 | 29/29 | +8 / −0 | 8.8s | $0.0837 |
| django__django-10914 | none (baseline) | not_resolved | 0/1 | 98/98 | — | — | — |
| django__django-10914 | gold (human fix) | resolved | 1/1 | 98/98 | +1 / −1 | — | — |
| django__django-10914 | claude-e2e (runner) | resolved | 1/1 | 98/98 | +12 / −12 | 35.7s | $0.2247 |
| django__django-10914 | claude-sonnet (runner) | resolved | 1/1 | 98/98 | +1 / −1 | 7.3s | $0.0762 |

Every row is a JSON record in `results/`, with the agent's patch and trace log beside it. Gold is the dataset's human fix; none is the no-patch baseline control.

## Best-of-N: the first judged comparison

MergeJudge exists to judge *between* agents, so the second arm matters more than the second task. Two Claude configurations now run every task — the default model (Opus) and Sonnet — with identical prompts and rules. `src/compare.py` ranks them per task: resolved first, then smaller diff, then lower cost. Gold and none are reference controls, never competitors.

### django__django-10914

| Run | Verdict | FAIL_TO_PASS | PASS_TO_PASS | Diff | Time | Cost |
|---|---|---|---|---|---|---|
| Claude Sonnet | resolved | 1/1 | 98/98 | +1 / −1 | 7.3s | $0.0762 |
| Claude (default model) | resolved | 1/1 | 98/98 | +12 / −12 | 35.7s | $0.2247 |

**Winner: Sonnet** — both resolved; Sonnet's patch is line-for-line the human gold fix, at a third of the cost and without the three docs files the default model's patch also edited.

### sympy__sympy-11400

| Run | Verdict | FAIL_TO_PASS | PASS_TO_PASS | Diff | Time | Cost |
|---|---|---|---|---|---|---|
| Claude (default model) | resolved | 2/2 | 29/29 | +14 / −0 | 26.4s | $0.2156 |
| Claude Sonnet | not_resolved | 0/2 | 29/29 | +8 / −0 | 8.8s | $0.0837 |

**Winner: the default model** — the only arm that resolved. Sonnet's patch added a sinc rewrite but no Relational support, and both target tests still failed.

### Portfolio view

| Strategy | Tasks resolved | Total cost |
|---|---|---|
| Always default model | 2/2 | $0.4403 |
| Always Sonnet | 1/2 | $0.1599 |
| Oracle (per-task winner) | 2/2 | $0.2918 |

There is no best arm — the winner depends on the task. Picking the winner per task matches the strongest single arm's quality (2/2) for about two-thirds of its cost, while the cheapest arm alone is cheap precisely because it fails half the time. That gap between "always one agent" and "the right agent per task" is what AgentRouter is being built to capture — and every row above is its future training data. (Canonical run per family shown; the default model has resolved sympy in 3 of 3 runs so far — manual, e2e, and the audited e2e2.)

The oracle figure counts only the winning runs — it is the lower bound a router aims at; running every arm on both tasks cost $0.6002 in total.

## What the results actually say

- **Test-pass is not mergeable.** On django-10914 the agent resolved the task (+12 / −12) but also edited three documentation files the one-line gold fix never touched. The tests can't see that; a reviewer would. MergeJudge records diff size on every run so the difference is visible instead of vibes.
- **Convergence is not cheating — and we can prove which.** The sympy agent's patch matched a hand-produced patch line-for-line. The stream-json audit trace shows why: 4 tool calls, all inside its own worktree, no access to the saved answers. sympy-11400 is a well-known upstream fix; SWE-bench training-data contamination is a documented caveat that applies to every number here.
- **Agents don't check their own work.** The audited sympy run edited the file and stopped — it never ran a single test on its fix. Whether an arm self-tests is a recorded dimension for future comparisons.

## Threat model and limitations

- Agent isolation is currently *procedural*: isolated temp worktree, prompt rules, and a complete tool-call audit log for every run. It is not yet OS-enforced; `sandbox-exec` isolation is the agreed gate before the dataset is scaled, because a determined agent with filesystem access could still wander.
- Costs are API-equivalent estimates from the agent's own trace (`total_cost_usd`) on a Claude Pro subscription — useful for comparisons, not an invoice.
- n = 2 tasks. These are verified results, not statistics. pass^k, held-out tasks, and confidence intervals arrive with scale, or not at all.

## Run it yourself

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install datasets
# Grade the gold patch for a task (needs the task's clone + env; see TASK_SETUP in src/scorer.py):
python3 src/scorer.py --task django__django-10914 --patch tasks/django-10914-gold_patch.diff --agent gold
# Run an agent end-to-end and grade it:
python3 src/runner.py --task django__django-10914 --agent claude-e2e
```

## Roadmap

- Remaining pinned tasks: astropy-12907, matplotlib-18869, scikit-learn-10297 — same recipe: extract, hand-validate both directions, then automated runs.
- A second *vendor* arm (Codex or Cursor CLI), so the competition crosses providers, not just models.
- OS-level sandboxing, then dataset scale-up from 5 to ~30 tasks.
- AgentRouter: a router trained on MergeJudge's verified outcomes — Bradley–Terry arm rankings plus a P(resolved) model with calibrated abstention and a cost–quality Pareto frontier. The dataset this repo produces is its training set.
