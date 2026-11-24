# Judge calibration, round 2: rubric v2

## Method

- **Same set-up as round 1** (`audit/CALIBRATION.md`), on the same 10 calibration packets.
- **Grading.** Each packet was graded by its own fresh subagent. The subagent's only input was the verbatim text of `audit/RUBRIC-V2.md` and the verbatim text of that one packet, passed inline. A fixed reply-format instruction listed the answer lines a1–d3, f1–f3, e and Reason, and told the subagent not to use any tools. That instruction is identical to round 1's apart from the f1–f3 lines. Each subagent made no tool call except returning its report. None was given labels, the key, other packets, results files, git history, or anything this session knows. All 10 gradings are reproduced verbatim in `audit/judge-labels-calibration-v2.md`.
- **Comparison.** `audit/labels-dheeraj.md` was opened for the round-2 comparison only after all 10 v2 gradings were written. The comparison is at decision level.
- **Distance.** Distance is measured in steps on the scale merge as-is < merge with nits < request changes < reject. A positive distance means the judge was stricter than Dheeraj.

## What v2 changes, and the round-1 disagreement each change addresses

| v2 change | Round-1 disagreements it was aimed at |
|---|---|
| f1: documentation where the project's conventions require it | IUGYPE and RSSU4T. Dheeraj requested changes over documentation and visibility ("make sure people see the change", "add some documentation"); the judge chose merge with nits. |
| f2: user-visible change announced in release notes or equivalent | IUGYPE and QXTPUZ. Dheeraj requested changes; the judge treated a missing changelog entry as a nit. |
| f3: wider effect acknowledged | BCCT5Y. Dheeraj requested changes ("ensure that it does not break anything"); the judge chose merge with nits. |
| Rule: an Unknown alone is not grounds for request changes or reject | CDG3SS and 4CZXU7. The judge requested changes partly on unverified doubts; Dheeraj chose merge as-is (+2 each). |
| Rule: if the mechanism is visible and matches the defect, an unverifiable runtime effect is an Unknown, not a defect | 4CZXU7. The judge's round-1 reason rested on what the generic path "likely" computes. Also CDG3SS. |
| Rule: merge with nits is not a default for uncertainty | DERB1N and J0FZGM. The judge chose merge with nits; Dheeraj chose merge as-is (+1 each). |

## Pre-registered bar (same as round 1)

At least **8/10 exact decision agreement**, and **no disagreement wider than one step**.

## Result: bar not met

Exact agreement is **2/10**, the same as round 1. Three disagreements are two steps wide; round 1 had two.

| Packet | Dheeraj | Round 1 judge (v1) | Distance | Round 2 judge (v2) | Distance |
|---|---|---|---|---|---|
| DERB1N | Merge as-is | Merge with nits | +1 | Merge with nits | +1 |
| IUGYPE | Request changes | Merge with nits | −1 | Merge with nits | −1 |
| 31BYPI | Merge as-is | Merge as-is | 0 | Merge as-is | 0 |
| BCCT5Y | Request changes | Merge with nits | −1 | Merge with nits | −1 |
| HYJZ9X | Merge as-is | Merge as-is | 0 | Merge with nits | +1 |
| CDG3SS | Merge as-is | Request changes | +2 | Request changes | +2 |
| J0FZGM | Merge as-is | Merge with nits | +1 | Request changes | +2 |
| RSSU4T | Request changes | Merge with nits | −1 | Request changes | 0 |
| 4CZXU7 | Merge as-is | Request changes | +2 | Request changes | +2 |
| QXTPUZ | Request changes | Merge with nits | −1 | Merge with nits | −1 |

What changed between rounds:

- **One packet moved into agreement.** On RSSU4T the judge answered f1 and f2 No and requested changes for missing docs, matching Dheeraj.
- **Two packets moved away.** On HYJZ9X the judge went from merge as-is to merge with nits, citing a missing test and topic doc. On J0FZGM it went from merge with nits to request changes, answering f2 and f3 No for a missing release note and an unacknowledged side effect.
- **The two +2 cases did not move.** On CDG3SS and 4CZXU7 the judge now answered criteria No, rather than relying on Unknowns. That puts its request-changes decisions inside v2's decision rules: they name defects. The disagreement with Dheeraj is about whether those defects are real, which the rubric cannot settle.
- **Hygiene cut both ways.** The new criteria pulled the judge toward request changes where Dheeraj also requested changes (RSSU4T). They also pulled it there where Dheeraj merged (J0FZGM).

These are observations on 10 packets, not conclusions.

## Caveats

1. **Standing caveat.** v2 was revised using these same 10 packets' disagreements. Passing here would have been necessary but not sufficient. Before the remaining packets are graded, the rubric must be validated on held-out packets against fresh labels from Dheeraj.
2. **Round-1 caveats still apply.** Dheeraj's labels are decision-level only, given in a plain-language walkthrough with technical Q&A on request. The parent session built the sample, wrote v2, and has seen both label sets. None of that reached the graders, whose input was file text only.
