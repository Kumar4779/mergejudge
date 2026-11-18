"""MergeJudge runner v0.1 - run ONE coding agent on ONE task, safely."""
import subprocess
from pathlib import Path

AGENT_TIMEOUT_S = 30 * 60   # hard kill for the agent run (sandbox contract)
TEST_TIMEOUT_S = 5 * 60     # hard kill for the test run

def make_worktree(repo: Path, dest: Path) -> Path:
    subprocess.run(["git", "-C", str(repo), "worktree", "add", str(dest)], check=True)
    return dest

if __name__ == "__main__":
    print(f"agent timeout: {AGENT_TIMEOUT_S // 60} min | test timeout: {TEST_TIMEOUT_S // 60} min")
    print("runner skeleton OK")
