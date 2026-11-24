# Mergeability audit: closeout

The audit is closed after two failed judge calibrations. The pre-registered bar was at least 8/10 exact decision agreement with Dheeraj's maintainer labels, and no disagreement wider than one step.

| Round | Rubric | Exact agreement | Widest gap | Bar |
|---|---|---|---|---|
| 1 | v1 (`RUBRIC.md`) | 2/10 | 2 steps (2 packets) | not met |
| 2 | v2 (`RUBRIC-V2.md`) | 2/10 | 2 steps (3 packets) | not met |

Details are in [`CALIBRATION.md`](CALIBRATION.md) and [`CALIBRATION-V2.md`](CALIBRATION-V2.md).

## Systematic patterns

1. **Scale-usage mismatch.** The judge chose "merge with nits" 6 times in round 1 and 5 times in round 2. Dheeraj never used it. His decisions were binary: merge as-is or request changes.
2. **Change hygiene.** Dheeraj's request-changes reasons price change hygiene: visibility, documentation and care about breakage. v1 did not score these at all. v2 scored them imperfectly: it fixed RSSU4T, where the judge now asked for docs as Dheeraj did, and broke J0FZGM, where the judge now requested changes over a missing release note while Dheeraj merged as-is.
3. **Disagreement about defect reality.** On CDG3SS and 4CZXU7 the v2 judge named specific defects, answering criteria No, that the maintainer judged not real. No rubric wording can settle a disagreement about whether a defect exists.

## Conclusion

No mergeability numbers are published, because no calibrated judge exists. The remaining 14 packets stay ungraded by design.

Execution verdicts are machine-checkable. LLM opinion judging did not reproduce maintainer decisions in two blinded trials.

## Reproducibility

The key (`audit/key.json`, mapping each packet code to its run, task, stratum, arm and verdict) and the sampling script (`audit/sample.py`) are now public, so the draw is reproducible: running `python3 audit/sample.py` from the project root regenerates the same key and 24 packets byte for byte.
