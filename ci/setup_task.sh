#!/usr/bin/env bash
# Recreate, on a fresh CI machine, what a task needs before src/scorer.py
# can grade it: the task's repo at its base commit, and the task's test
# Python env. Locally both live in gitignored repos/ and envs/.
#
# Clone path, env path, repo and base commit come from the scorer itself
# (TASK_SETUP and the SWE-bench record); only the env recipe - Python
# version and packages, matching the local env - is listed here.
#
# Usage, from the project root with .venv set up:
#   bash ci/setup_task.sh sympy__sympy-11400
set -euo pipefail

task="$1"

case "$task" in
  sympy__sympy-11400)
    py_version="3.9"
    packages=("mpmath==1.3.0" "pytest==8.4.2")
    ;;
  *)
    echo "::error::No CI setup recipe for $task yet (supported: sympy__sympy-11400)"
    exit 1
    ;;
esac

read -r clone env_python repo base_commit < <(.venv/bin/python - "$task" <<'PY'
import sys
sys.path.insert(0, "src")
import scorer
from datasets import load_dataset

task = sys.argv[1]
setup = scorer.TASK_SETUP[task]
record = next(x for x in load_dataset("princeton-nlp/SWE-bench_Lite",
                                      split="test")
              if x["instance_id"] == task)
print(setup["clone"], setup["python"], record["repo"], record["base_commit"])
PY
)

# Only the base commit is needed: grading worktrees check it out.
git init -q "$clone"
git -C "$clone" fetch -q --depth 1 "https://github.com/$repo.git" "$base_commit"

env_dir="$(dirname "$(dirname "$env_python")")"
uv venv -q --python "$py_version" "$env_dir"
uv pip install -q --python "$env_python" "${packages[@]}"

echo "Set up $task: $clone @ ${base_commit:0:10}, $env_dir (Python $py_version)"
