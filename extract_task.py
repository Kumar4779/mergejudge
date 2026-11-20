from datasets import load_dataset

ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
task = next(x for x in ds if x["instance_id"] == "sympy__sympy-11400")
print("repo:", task["repo"])
print("base_commit:", task["base_commit"])
print("FAIL_TO_PASS:", task["FAIL_TO_PASS"])
print("PASS_TO_PASS:", task["PASS_TO_PASS"])
open("tasks/sympy-11400-issue.txt", "w").write(task["problem_statement"])
print("Issue saved to tasks/sympy-11400-issue.txt")
