#!/usr/bin/env bash
# Build a task test env by name, for envs selected through the scorer's
# per-repo defaults (REPO_SETUP python_by_version). Envs live in the
# gitignored envs/; this file is the record of how each one is built.
#
# Usage, from the project root:
#   bash ci/build_env.sh django31-py38
set -euo pipefail

name="$1"

case "$name" in
  django-py38)   # Django 3.0 tasks
    py_version="3.8"
    packages=("pytz==2026.6" "sqlparse==0.5.5")
    ;;
  django31-py38) # Django 3.1 tasks: as django-py38, plus asgiref, which
                 # Django 3.1 requires (unpinned in its setup.py). 3.2.2 is
                 # the newest release before the 3.1-era base commits.
    py_version="3.8"
    packages=("pytz==2026.6" "sqlparse==0.5.5" "asgiref==3.2.2")
    ;;
  *)
    echo "No env recipe for $name" >&2
    exit 1
    ;;
esac

uv venv -q --allow-existing --python "$py_version" "envs/$name"
uv pip install -q --python "envs/$name/bin/python" "${packages[@]}"
echo "Built envs/$name (Python $py_version): ${packages[*]}"
