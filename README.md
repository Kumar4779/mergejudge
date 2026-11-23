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
| matplotlib__matplotlib-18869 | none (baseline) | not_resolved | 0/4 | 3/3 | — | — | — |
| matplotlib__matplotlib-18869 | gold (human fix) | resolved | 4/4 | 3/3 | +51 / −16 | — | — |
| matplotlib__matplotlib-18869 | claude-e2e (runner) | resolved | 4/4 | 3/3 | +58 / −17 | 45.4s | $0.2255 |
| matplotlib__matplotlib-18869 | claude-sonnet (runner) | resolved | 4/4 | 3/3 | +30 / −0 | 13.8s | $0.0730 |

Every row is a JSON record in `results/`, with the agent's patch and trace log beside it. Gold is the dataset's human fix; none is the no-patch baseline control.

## Best-of-N: the first judged comparison

MergeJudge exists to judge *between* agents, so the second arm matters more than the second task. Two Claude configurations now run every task — the default model (Opus) and Sonnet — with identical prompts and rules. `src/compare.py` ranks them per task over every direct run each arm has made: highest pass^1 (resolved runs / runs) first, then smallest mean diff of the resolved runs, then lowest mean cost per run (failed runs cost money too). Gold and none are reference controls, never competitors.

Ranking uses every run, reliability first: on matplotlib a single canonical run would have crowned an arm that resolves only half its runs, so no arm is ranked on one sample again.

### django__django-10914

| Family | Runs | Resolved | pass^1 | Mean diff (resolved) | Mean cost (all runs) |
|---|---|---|---|---|---|
| 1. Claude Sonnet · direct | 6 | 6 | 1.000 | 2.0 | $0.0662 |
| 2. Claude (default model) · direct | 4 | 4 | 1.000 | 16.5 | $0.2113 |

**Winner: Claude Sonnet · direct** — tie on pass^1 (1.000); won on diff: mean 2.0 vs 16.5 lines (resolved runs). All six of Sonnet's patches are line-for-line the human gold fix, at about a third of the cost; every default-model patch also edited two or three docs files the gold fix never touched.

### django__django-10924

| Family | Runs | Resolved | pass^1 | Mean diff (resolved) | Mean cost (all runs) |
|---|---|---|---|---|---|
| 1. Claude Sonnet · direct | 4 | 4 | 1.000 | 2.0 | $0.0577 |
| 2. Claude (default model) · direct | 4 | 4 | 1.000 | 12.8 | $0.1421 |

**Winner: Claude Sonnet · direct** — tie on pass^1 (1.000); won on diff: mean 2.0 vs 12.8 lines (resolved runs).

### django__django-11001

| Family | Runs | Resolved | pass^1 | Mean diff (resolved) | Mean cost (all runs) |
|---|---|---|---|---|---|
| 1. Claude Sonnet · direct | 4 | 4 | 1.000 | 2.0 | $0.0635 |
| 2. Claude (default model) · direct | 4 | 4 | 1.000 | 2.0 | $0.1236 |

**Winner: Claude Sonnet · direct** — tie on pass^1 and diff; won on cost: mean $0.0635 vs $0.1236 per run.

### django__django-11019

| Family | Runs | Resolved | pass^1 | Mean diff (resolved) | Mean cost (all runs) |
|---|---|---|---|---|---|
| 1. Claude (default model) · direct | 4 | 4 | 1.000 | 83.5 | $0.2868 |
| 2. Claude Sonnet · direct | 4 | 3 | 0.750 | 77.0 | $0.1111 |

**Winner: Claude (default model) · direct** — won on reliability: pass^1 1.000 vs 0.750.

### django__django-11039

| Family | Runs | Resolved | pass^1 | Mean diff (resolved) | Mean cost (all runs) |
|---|---|---|---|---|---|
| 1. Claude Sonnet · direct | 4 | 4 | 1.000 | 2.8 | $0.0581 |
| 2. Claude (default model) · direct | 4 | 4 | 1.000 | 5.0 | $0.1241 |

**Winner: Claude Sonnet · direct** — tie on pass^1 (1.000); won on diff: mean 2.8 vs 5.0 lines (resolved runs).

### django__django-11049

| Family | Runs | Resolved | pass^1 | Mean diff (resolved) | Mean cost (all runs) |
|---|---|---|---|---|---|
| 1. Claude Sonnet · direct | 4 | 4 | 1.000 | 2.0 | $0.0645 |
| 2. Claude (default model) · direct | 4 | 4 | 1.000 | 2.0 | $0.1869 |

**Winner: Claude Sonnet · direct** — tie on pass^1 and diff; won on cost: mean $0.0645 vs $0.1869 per run.

### django__django-11099

| Family | Runs | Resolved | pass^1 | Mean diff (resolved) | Mean cost (all runs) |
|---|---|---|---|---|---|
| 1. Claude Sonnet · direct | 4 | 4 | 1.000 | 4.0 | $0.0537 |
| 2. Claude (default model) · direct | 4 | 4 | 1.000 | 4.0 | $0.1119 |

**Winner: Claude Sonnet · direct** — tie on pass^1 and diff; won on cost: mean $0.0537 vs $0.1119 per run.

### django__django-11133

| Family | Runs | Resolved | pass^1 | Mean diff (resolved) | Mean cost (all runs) |
|---|---|---|---|---|---|
| 1. Claude Sonnet · direct | 4 | 4 | 1.000 | 2.0 | $0.0534 |
| 2. Claude (default model) · direct | 4 | 4 | 1.000 | 4.0 | $0.1190 |

**Winner: Claude Sonnet · direct** — tie on pass^1 (1.000); won on diff: mean 2.0 vs 4.0 lines (resolved runs).

### django__django-11179

| Family | Runs | Resolved | pass^1 | Mean diff (resolved) | Mean cost (all runs) |
|---|---|---|---|---|---|
| 1. Claude Sonnet · direct | 4 | 4 | 1.000 | 1.0 | $0.0532 |
| 2. Claude (default model) · direct | 4 | 4 | 1.000 | 1.0 | $0.1138 |

**Winner: Claude Sonnet · direct** — tie on pass^1 and diff; won on cost: mean $0.0532 vs $0.1138 per run.

### django__django-11283

| Family | Runs | Resolved | pass^1 | Mean diff (resolved) | Mean cost (all runs) |
|---|---|---|---|---|---|
| 1. Claude (default model) · direct | 4 | 4 | 1.000 | 30.2 | $0.1716 |
| 2. Claude Sonnet · direct | 4 | 0 | 0.000 | — | $0.0625 |

**Winner: Claude (default model) · direct** — won on reliability: pass^1 1.000 vs 0.000.

### django__django-11422

| Family | Runs | Resolved | pass^1 | Mean diff (resolved) | Mean cost (all runs) |
|---|---|---|---|---|---|
| 1. Claude Sonnet · direct | 4 | 4 | 1.000 | 10.5 | $0.0674 |
| 2. Claude (default model) · direct | 4 | 4 | 1.000 | 10.8 | $0.1197 |

**Winner: Claude Sonnet · direct** — tie on pass^1 (1.000); won on diff: mean 10.5 vs 10.8 lines (resolved runs).

### django__django-11564

| Family | Runs | Resolved | pass^1 | Mean diff (resolved) | Mean cost (all runs) |
|---|---|---|---|---|---|
| 1. Claude Sonnet · direct | 4 | 4 | 1.000 | 21.2 | $0.1203 |
| 2. Claude (default model) · direct | 4 | 4 | 1.000 | 31.5 | $0.1869 |

**Winner: Claude Sonnet · direct** — tie on pass^1 (1.000); won on diff: mean 21.2 vs 31.5 lines (resolved runs).

### matplotlib__matplotlib-18869

| Family | Runs | Resolved | pass^1 | Mean diff (resolved) | Mean cost (all runs) |
|---|---|---|---|---|---|
| 1. Claude (default model) · direct | 4 | 4 | 1.000 | 76.0 | $0.2192 |
| 2. Claude Sonnet · direct | 4 | 2 | 0.500 | 30.0 | $0.0836 |

**Winner: Claude (default model) · direct** — won on reliability: pass^1 1.000 vs 0.500. Both failing Sonnet runs mishandled the same case: a `.post` version must count as a development build of the *next* release.

### sympy__sympy-11400

| Family | Runs | Resolved | pass^1 | Mean diff (resolved) | Mean cost (all runs) |
|---|---|---|---|---|---|
| 1. Claude (default model) · direct | 7 | 7 | 1.000 | 14.0 | $0.1898 (5 of 7 costed) |
| 2. Claude Sonnet · direct | 4 | 0 | 0.000 | — | $0.0836 |

**Winner: Claude (default model) · direct** — won on reliability: pass^1 1.000 vs 0.000. Every Sonnet patch added a sinc rewrite but no Relational support, and both target tests failed every time.

### Portfolio view

| Family | Tasks won | Overall pass^1 | Expected spend |
|---|---|---|---|
| Claude (default model) · direct | 4/14 | 1.000 (59/59) | $2.3068 |
| Claude Sonnet · direct | 10/14 | 0.810 (47/58) | $0.9989 |
| Oracle (per-task winner) | 14/14 | 1.000 (61/61) | $1.5256 |

There is no best arm — the winner depends on the task. The default model resolved every one of its runs (59/59, pass^1 1.000) yet won only 4 of 14 tasks; Sonnet won the other 10 at an overall pass^1 of 0.810 (47/58). Its failures are concentrated on four tasks: it never resolved sympy-11400 or django-11283 (0/4 each), resolved matplotlib-18869 in 2 of 4 runs and django-11019 in 3 of 4, and resolved every run on the other ten. Picking the winner per task keeps pass^1 at 1.000 for $1.5256 expected spend, about two-thirds of always-default's $2.3068. That gap between "always one agent" and "the right agent per task" is what AgentRouter is being built to capture — and every run above is its future training data. (Aggregates cover every direct run of each arm; probe runs are excluded.)

The oracle figure is an expected spend, not a measured bill: the sum over tasks of each task's winning arm's mean cost per run — what one run per task costs a router that always picks the winner, the target a router aims at. Running both arms once on every task has an expected spend of $3.3057.

### Scaffold experiment: plan-first vs direct (2x2 factorial)

Two scaffolds x two models, every cell repeated. Plan-first arms had to reproduce the bug, state a plan, fix, then run the affected tests and iterate before finishing.

| Task | Scaffold | Default model | Sonnet |
|---|---|---|---|
| django-10914 | direct | 4/4 resolved, mean $0.2113 | 6/6 resolved, mean $0.0662 |
| django-10914 | plan-first | 3/3 resolved, mean $0.2182 | 3/3 resolved, mean $0.0986 |
| sympy-11400 | direct | 7/7 resolved, mean $0.1898 | 0/4 resolved, mean $0.0836 |
| sympy-11400 | plan-first | 3/3 resolved, mean $0.1610 | 0/3 resolved, mean $0.0663 |

- No outcome changed in any cell. On these tasks the model was the deciding variable; the scaffold was not.
- Self-testing has a coverage ceiling: plan-first Sonnet ran the visible sympy tests (30 passed) and stopped — but the visible suite does not cover the hidden cases, and its output was still not valid C. An agent grading itself with tests it can see is the same trap as an agent grading itself at all.
- Plan-first taxed the cheap arm: Sonnet's django patches gained docs edits (+2/-2 to +7/-9 instead of the gold +1/-1), cost about 50% more, and took about 3x longer — for the same verdict.

## What the results actually say

- **Reliability belongs to the task, not the model.** Across 14 tasks the cheap arm is perfect on ten, deterministically wrong on two (0/4 on sympy-11400 and django-11283) and intermittent on two (2/4 on matplotlib-18869, 3/4 on django-11019) — which is precisely what makes routing possible: a judge that knows the task can hold the expensive arm's reliability at two-thirds of its cost.
- **Test-pass is not mergeable.** On django-10914 the agent resolved the task (+12 / −12) but also edited three documentation files the one-line gold fix never touched. The tests can't see that; a reviewer would. MergeJudge records diff size on every run so the difference is visible instead of vibes.
- **Convergence is not cheating — and we can prove which.** The sympy agent's patch matched a hand-produced patch line-for-line. The stream-json audit trace shows why: 4 tool calls, all inside its own worktree, no access to the saved answers. sympy-11400 is a well-known upstream fix; SWE-bench training-data contamination is a documented caveat that applies to every number here.
- **Not every agent checks its own work — and checking doesn't save them.** Sonnet's direct runs edit and stop without running a single test on their fix; the default model usually runs the visible tests. The plan-first arms were forced to self-test and it changed no outcome: on sympy the visible tests passed while the hidden grading tests still failed. Self-verification is bounded by the coverage of the tests the agent can see.

## Threat model and limitations

- Agent runs execute under `sandbox-exec`: network is denied except a local proxy that only forwards to `api.anthropic.com`, the project tree is read-denied except `envs/`, and each agent repo is materialized as a single-commit, history-cut checkout of the task's base commit. An adversarial probe run that tried to read the answers found nothing.
- Costs are API-equivalent estimates from the agent's own trace (`total_cost_usd`) on a Claude Pro subscription — useful for comparisons, not an invoice.
- n = 14 tasks. These are verified results, not statistics. pass^k, held-out tasks, and confidence intervals arrive with scale, or not at all.

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

## Run MergeJudge in your CI

```yaml
- uses: actions/checkout@v4
- uses: Kumar4779/mergejudge@v1
  with:
    task: sympy__sympy-11400
    patch: path/to/agent.patch
```

The check grades the patch against the task's real tests on a clean checkout and fails unless the task resolves, including when the patch touches a test file. The Action is self-tested on `sympy__sympy-11400`, `django__django-10914` and `matplotlib__matplotlib-18869`; the scorer itself grades all 14 tasks locally.

## Roadmap

- Dataset scale-up in progress: 20 gradeable tasks (django 12, sympy 7, matplotlib 1), rebalancing toward ~30 across repos.
- scikit-learn-10297 and astropy-12907 extraction still remaining.
- Confidence intervals and a private holdout slice as the dataset grows.
- A second *vendor* arm (Codex or Cursor CLI) once an API key exists.
- AgentRouter once the verified-outcome count supports it.
