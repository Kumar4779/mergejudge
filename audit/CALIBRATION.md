# Judge calibration: fresh-subagent grading vs Dheeraj's labels

## Method

- **Grading.** Each of the 10 calibration packets was graded by its own fresh subagent. The subagent's only input was the text of `audit/RUBRIC.md` plus the text of that one packet, passed inline, with an instruction not to use any tools. Each subagent made no tool call except returning its report. None was given another packet, the labels, the key, any results file, or git history. It answered a1–d3 with Yes, No or Unknown, then gave the (e) decision and a one-line reason. All 10 gradings are reproduced verbatim in `audit/judge-labels-calibration.md`.
- **Comparison.** `audit/labels-dheeraj.md` was opened only after all 10 gradings were written. The comparison is at decision level only, because Dheeraj labelled decisions and his criteria tables are blank by design.
- **Distance.** Distance is measured in steps on the scale merge as-is < merge with nits < request changes < reject. A positive distance means the judge was stricter than Dheeraj.

## Pre-registered bar

At least **8/10 exact decision agreement**, and **no disagreement wider than one step**.

## Result: bar not met

Exact agreement is **2/10**. Two disagreements are two steps wide.

| Packet | Judge decision | Dheeraj decision | Distance |
|---|---|---|---|
| DERB1N | Merge with nits | Merge as-is | +1 |
| IUGYPE | Merge with nits | Request changes | −1 |
| 31BYPI | Merge as-is | Merge as-is | 0 |
| BCCT5Y | Merge with nits | Request changes | −1 |
| HYJZ9X | Merge as-is | Merge as-is | 0 |
| CDG3SS | Request changes | Merge as-is | +2 |
| J0FZGM | Merge with nits | Merge as-is | +1 |
| RSSU4T | Merge with nits | Request changes | −1 |
| 4CZXU7 | Request changes | Merge as-is | +2 |
| QXTPUZ | Merge with nits | Request changes | −1 |

Observations on the table:

- **No consistent direction.** The judge was stricter on 4 packets and more lenient on 4.
- **Dheeraj never used merge with nits.** The judge used it 6 times.
- **The −1 cases name similar concerns.** In the four packets where Dheeraj requested changes and the judge chose merge with nits, the judge's reasons name missing tests, docs or a changelog entry. Dheeraj's reasons point at similar concerns, for example "add some documentation". So the two may differ partly in where they draw the line between a nit and a requested change.
- **The +2 cases involve doubts about correctness.** Both are sympy patches where the judge doubted the fix was complete or correct and Dheeraj chose merge as-is.

These are observations on 10 packets, not conclusions.

## Caveats

1. **Dheeraj's labels are decision-level only.** They were given in a plain-language walkthrough on 2026-11-23, with technical Q&A on request. There are no criterion-level labels to compare against, and the reasons are short or absent.
2. **The parent session built the sample, so fresh subagents did the grading.** The parent session knows the key, meaning which run, arm and verdict sits behind each code. It also typed Dheeraj's decisions into `labels-dheeraj.md` in the previous step, so it knew them before grading began. None of that reached the graders: each subagent's input was the rubric and one packet, with no tool use.
