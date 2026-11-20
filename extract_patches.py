from datasets import load_dataset
ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
task = next(x for x in ds if x["instance_id"] == "sympy__sympy-11400")
open("tasks/sympy-11400-test_patch.diff", "w").write(task["test_patch"])
open("tasks/sympy-11400-gold_patch.diff", "w").write(task["patch"])
print("test_patch chars:", len(task["test_patch"]))
print("gold_patch chars:", len(task["patch"]))
