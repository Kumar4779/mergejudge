import sys

from datasets import load_dataset

instance_id = sys.argv[1]
short = instance_id.split("__")[-1]
ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
task = next(x for x in ds if x["instance_id"] == instance_id)
open(f"tasks/{short}-test_patch.diff", "w").write(task["test_patch"])
open(f"tasks/{short}-gold_patch.diff", "w").write(task["patch"])
print("test_patch chars:", len(task["test_patch"]))
print("gold_patch chars:", len(task["patch"]))
