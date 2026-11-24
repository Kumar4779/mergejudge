# Mergeability audit rubric

> **Version 2.** Derived from the round-1 calibration disagreements recorded in `audit/CALIBRATION.md`. Version 1 is preserved unchanged in `audit/RUBRIC.md`.

Each packet holds a problem statement and a patch, nothing else. Judge the
patch as a maintainer of the project would on review. You do not know who or
what wrote it, or whether it passes the project's tests. Do not try to find
out.

Answer every criterion **Yes**, **No** or **Unknown**. Unknown is a valid and
expected answer. Use it when the packet does not give you enough to decide.
Examples: the fix depends on code the patch doesn't show, or you can't tell
whether a behaviour change is intended. Don't guess to avoid Unknown.

## (a) Addresses the issue

- **a1.** The patch changes the behaviour the problem statement describes. It doesn't only add a workaround, a warning or documentation.
- **a2.** The patch fixes the general case the issue describes, not only the specific example given.
- **a3.** Nothing the issue explicitly asks for is left undone.

## (b) Minimality and scope

- **b1.** Every changed file is needed for the fix, or is a change a maintainer would expect alongside it, such as a release note required by the project's conventions.
- **b2.** The patch has no unrelated edits: no refactors, reformatting, renames or drive-by fixes outside the issue.
- **b3.** The size of the change is proportionate to the problem. A reviewer would not ask for it to be cut down.

## (c) Code quality and fit with the codebase

- **c1.** The patch follows the surrounding code's idioms, naming and style.
- **c2.** It uses the project's existing helpers and patterns rather than re-implementing them.
- **c3.** It has no dead code, debugging leftovers, or comments that only narrate the change.
- **c4.** The logic is clear enough that a maintainer could own it without asking the author to explain.

## (d) Breakage risk beyond the named tests

- **d1.** Existing callers or users see no unintended change in behaviour: no altered defaults, signatures, return types or error types outside the fix.
- **d2.** Edge cases near the fix are handled or unaffected. Examples: empty input, None, other types, subclasses, other backends or platforms.
- **d3.** The patch introduces no performance, security or compatibility hazard a maintainer would flag.

## (f) Change hygiene

- **f1.** Where the project's conventions require documentation for this kind of change (new feature, new setting, changed default or other user-visible behavior), the patch includes it; a pure internal bug fix needs none.
- **f2.** A user-visible behavior change is announced where the project announces such changes (release notes or equivalent), or there is no user-visible change.
- **f3.** Where the change reaches beyond the reported issue (a broader code path, a changed default), the patch or its notes acknowledge the wider effect, so a reviewer can see the author noticed it.

## (e) Overall maintainer decision

Pick exactly one, and give a one-line reason:

| Decision | Meaning |
|---|---|
| **Merge as-is** | Would be merged without changes. |
| **Merge with nits** | Correct and in scope. Only cosmetic or trivial follow-ups. |
| **Request changes** | Right direction, but needs substantive revision before merging. |
| **Reject** | Wrong approach, does not address the issue, or does more harm than good. |

An Unknown in (a)–(d) does not force any particular decision. Make the call a
maintainer would make with the same information.

## Decision rules

- An Unknown on any criterion is not, by itself, grounds for Request changes or Reject. Request changes requires at least one named defect, missing piece, or criterion answered No.
- If the fix's mechanism is visible in the packet and matches the reported defect, inability to verify runtime behaviour from the packet alone is an Unknown, not a defect.
- Merge with nits is only for changes that are correct, complete and hygienic apart from cosmetic or trivial items. It is not a default answer for uncertainty.
