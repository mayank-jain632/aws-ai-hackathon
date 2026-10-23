# Sushruth · Lane 4b: firm-wide exposure roll-up

Updated 14:15 by Claude Code

**Nothing from this lane is on `main`.** The work is on branch `sushruth/firm-exposure`,
held there by Sushruth's decision rather than merged, so under D31 it is not in the demo.
It was briefly on main at `4599ad5` and `2bb325f` and was reverted in `5b42f19`. No code
on `main` depends on it and no file on `main` is claimed by it.

- What it is, what is verified and what is not: D27, plus the branch's own copy of this
  file and `docs/firm-exposure.md`.
- Re-landing it needs a revert of the revert, not a rebase. The original commits are
  ancestors of `main`, so `git rebase main` drops the whole feature and leaves an empty
  diff.
- Last checked against `main` at `70f8c7c`: the branch still applies, nothing it reads has
  changed, and the suite is 386 passed with it against 370 on `main` alone.

**Blocked, or need from someone**
- Nothing outstanding on `main` from this lane. Requests to other lanes are recorded on the
  branch and apply only if the team decides to merge it.

**Files I am working in right now**
- On `main`: this file only.
