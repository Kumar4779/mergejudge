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
  sympy-modern)  # Fresh-slice sympy tasks (post-cutoff, current sympy
                 # master): a modern band, not the 1.0-era envs/sympy-py39.
                 # hypothesis: required by current sympy/conftest.py.
    py_version="3.12"
    packages=("mpmath==1.3.0" "pytest==9.2.0" "hypothesis==6.170.17")
    ;;
  scikit-learn-py37)
    # scikit-learn 0.20-era tasks. This env is x86_64 under Rosetta: the
    # 0.20-era stack (Python 3.7, numpy 1.16, scipy 1.2) predates Apple
    # Silicon and has no arm64 builds. uv no longer ships Python 3.7, so
    # the interpreter comes from conda-forge osx-64 (self-contained); the
    # rest are PyPI x86_64 wheels. setuptools 40.6.3 because current
    # setuptools rejects the 2017 flat layout. scikit-learn itself is
    # built from repos/scikit-learn_src at the task's base commit, against
    # the installed numpy; the scorer copies its compiled .so files into
    # each grading worktree.
    base_commit="b90661d6a46aa3619d3eec94d5281f5888add501"
    env="$PWD/envs/$name"
    CONDA_SUBDIR=osx-64 conda create -y -q -p "$env" -c conda-forge \
      --override-channels python=3.7 pip
    uv pip install -q --python "$env/bin/python" numpy==1.16.6 \
      scipy==1.2.3 pytest==3.10.1 Cython==0.28.5 setuptools==40.6.3
    build="$PWD/worktrees/sklearn-build"
    git -C repos/scikit-learn_src worktree add -q --detach "$build" \
      "$base_commit"
    (cd "$build" && "$env/bin/python" -m pip install -q \
      --no-build-isolation --no-deps .)
    git -C repos/scikit-learn_src worktree remove --force "$build"
    echo "Built envs/$name (Python 3.7, x86_64): scikit-learn @ $base_commit"
    exit 0
    ;;
  astropy-py39)
    # astropy 4.3-band tasks (base commits from early 2022), native arm64.
    # Pins resolved with --exclude-newer 2022-03-04, the day after the
    # astropy-12907 base commit; Cython 0.29.22 is the base commit's own
    # build pin, and pytest-astropy-header 0.2.0 is excluded by its
    # setup.cfg. Resolved: numpy 1.22.2, pyerfa 2.0.0.1, PyYAML 6.0,
    # packaging 21.3, setuptools 60.9.3, setuptools_scm 6.4.2,
    # extension-helpers 0.1, pytest 7.0.1, pytest-astropy 0.9.0,
    # pytest-astropy-header 0.1.2, hypothesis 6.39.1. astropy itself is
    # built from repos/astropy_src at the base commit; the scorer copies
    # its compiled .so files and _version.py into each grading worktree.
    base_commit="d16bfe05a744909de4b27f5875fe0d4ed41ce607"
    env="$PWD/envs/$name"
    uv venv -q --allow-existing --python 3.9 "$env"
    uv pip install -q --python "$env/bin/python" --exclude-newer 2022-03-04 \
      "numpy==1.22.*" "pyerfa>=2.0" "PyYAML>=3.13" "packaging>=19.0" \
      "setuptools<61" "setuptools_scm>=6.2" wheel cython==0.29.22 \
      extension-helpers "pytest<7.1" "pytest-astropy>=0.9" \
      "pytest-astropy-header!=0.2.0"
    build="$PWD/worktrees/astropy-build"
    git -C repos/astropy_src worktree add -q --detach "$build" "$base_commit"
    (cd "$build" && uv pip install -q --python "$env/bin/python" \
      --no-build-isolation --no-deps .)
    git -C repos/astropy_src worktree remove --force "$build"
    echo "Built envs/$name (Python 3.9): astropy @ $base_commit"
    exit 0
    ;;
  *)
    echo "No env recipe for $name" >&2
    exit 1
    ;;
esac

uv venv -q --allow-existing --python "$py_version" "envs/$name"
uv pip install -q --python "envs/$name/bin/python" "${packages[@]}"
echo "Built envs/$name (Python $py_version): ${packages[*]}"
