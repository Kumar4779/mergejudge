import sys

from datasets import load_dataset

instance_id = sys.argv[1]
short = instance_id.split("__")[-1]
ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
task = next(x for x in ds if x["instance_id"] == instance_id)
print("repo:", task["repo"])
print("base_commit:", task["base_commit"])
print("FAIL_TO_PASS:", task["FAIL_TO_PASS"])
print("PASS_TO_PASS:", task["PASS_TO_PASS"])
open(f"tasks/{short}-issue.txt", "w").write(task["problem_statement"])
print(f"Issue saved to tasks/{short}-issue.txt")
