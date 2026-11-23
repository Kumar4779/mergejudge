#!/usr/bin/env bash
# Recreate, on a fresh CI machine, what a task needs before src/scorer.py
# can grade it: the task's repo at its base commit, and the task's test
# Python env. Locally both live in gitignored repos/ and envs/.
#
# Clone path, env path, repo and base commit come from the scorer itself
# (TASK_SETUP and the SWE-bench record); only the env recipe - Python
# version, packages, and how to fetch/build - is listed here, matching
# the local env exactly.
#
# Usage, from the project root with .venv set up:
#   bash ci/setup_task.sh sympy__sympy-11400
set -euo pipefail

task="$1"
fetch="base"   # base: the base commit only; history: all commits + tags
build="none"   # matplotlib: build + install the repo itself from base

case "$task" in
  sympy__sympy-11400)
    py_version="3.9"
    packages=("mpmath==1.3.0" "pytest==8.4.2")
    ;;
  django__django-10914)
    py_version="3.8"
    packages=("pytz==2026.6" "sqlparse==0.5.5")
    ;;
  matplotlib__matplotlib-18869)
    py_version="3.9"
    packages=("numpy==1.21.6" "pytest==6.2.5" "pyparsing==2.4.7"
              "pillow==8.3.2" "cycler==0.10.0" "kiwisolver==1.3.2"
              "python-dateutil==2.8.2"
              # build requirements, installed first: no build isolation
              "setuptools==59.8.0" "wheel==0.48.0" "setuptools-scm==6.4.2"
              "setuptools-scm-git-archive==1.4.1" "certifi")
    # setuptools_scm derives the version (3.5.0.dev1324+g...) from tags
    # and history, so fetch those; file contents still come on demand.
    fetch="history"
    build="matplotlib"
    ;;
  *)
    echo "::error::No CI setup recipe for $task yet (supported:" \
         "sympy__sympy-11400, django__django-10914," \
         "matplotlib__matplotlib-18869)"
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

# Safe to re-run (e.g. the action used twice in one job): an existing
# clone that already has the base commit is reused.
if git -C "$clone" cat-file -e "$base_commit^{commit}" 2>/dev/null; then
  :
elif [ "$fetch" = history ]; then
  git clone -q --filter=blob:none --no-checkout \
    "https://github.com/$repo.git" "$clone"
else
  # Only the base commit is needed: grading worktrees check it out.
  git init -q "$clone"
  git -C "$clone" fetch -q --depth 1 "https://github.com/$repo.git" "$base_commit"
fi

env_python="$PWD/$env_python"  # absolute: the build step changes directory
env_dir="$(dirname "$(dirname "$env_python")")"
uv venv -q --allow-existing --python "$py_version" "$env_dir"
uv pip install -q --python "$env_python" "${packages[@]}"

if [ "$build" = matplotlib ] && ! "$env_python" -c "import matplotlib.ft2font" 2>/dev/null; then
  # Plain (non-editable) install of the base-commit tree into the env's
  # site-packages, which is where the scorer's overlay step copies the
  # compiled extensions from. matplotlib enables LTO by default, which
  # leaves its bundled FreeType as bitcode that does not link: turn it off.
  build_tree="worktrees/$(basename "$clone")-build"
  git -C "$clone" worktree add -q --detach "$PWD/$build_tree" "$base_commit"
  (cd "$build_tree" &&
   CFLAGS=-fno-lto CXXFLAGS=-fno-lto LDFLAGS=-fno-lto \
     uv pip install -q --python "$env_python" --no-build-isolation .)
  git -C "$clone" worktree remove --force "$PWD/$build_tree"
  "$env_python" -c "import matplotlib, matplotlib.ft2font; print('built matplotlib', matplotlib.__version__)"
fi

echo "Set up $task: $clone @ ${base_commit:0:10}, $env_dir (Python $py_version)"
