# Firm-wide exposure roll-up

`GET /api/firm/exposure` returns exposure across every fund at once. Human sessions only;
worker tokens get 403. Add `?include_broker=false` to skip the shared-account read.

Fund membership is honoured, the same as `GET /api/funds`: "firm-wide" means every fund the
caller is a member of, not every fund on the host. The payload says which in `scope`. The
legacy Team 4 board stays shared with everyone.

Proposed in D27. Code is `backend/app/firm.py` (pure aggregation) and
`backend/app/routes/firm.py` (the route). Tests: `backend/tests/test_firm_exposure.py`.

## Why a firm view exists

The desk policy, the fund mandate and the watchdog's order gate each reason about one
fund. Two things are therefore invisible to all of them.

**Capacity.** One shared Alpaca paper account backs every fund, and each fund's cash check
reads that same balance. Six funds can each claim $100,000 and each approve a book sized
to it against one $100,000 account.

**Correlated client positioning.** A name can sit inside every mandate's own limit while
every client holds it, so one issuer's drawdown reaches the whole book at once.

What this is *not*: if each fund holds a name at 8% of its own capital, the firm total is
also 8% of combined capital, not 48%. The signal is shared ownership and the size of the
firm total, not an amplified percentage.

## What counts as exposure

| Source | Counted as | Note |
|---|---|---|
| Recorded broker orders, net of sells | `committed` | Void statuses dropped; `unknown` and `submitting` excluded and listed under `uncertain_orders`, so totals are a lower bound |
| Newest strategy with a current human approval and backend PASS, priced at mandate capital | `approved` | Approval and test must both match the current policy hash |
| Registered or reviewed strategies | nothing | A proposal is never exposure; counted only as `proposed_strategies` |

Archived funds are excluded from firm capital; paused funds still count, because a paused
fund keeps its capital at risk. Nothing is simulated, assumed or carried forward.

## Findings

No firm-level threshold is invented. Every limit is either the account balance or a limit
a person already set in a mandate.

| Code | Severity | Limit used |
|---|---|---|
| `approved_exceeds_account` | critical | Approved books across funds vs the shared account's equity |
| `committed_exceeds_account` | critical | Recorded orders vs equity; means the per-fund logs no longer reconcile |
| `capacity_oversubscribed` | warn | Sum of active fund capital vs equity |
| `mandate_drift_position` | warn | A fund's own `max_position` |
| `mandate_drift_sector` | warn | A fund's own `max_sector` |
| `every_client_exposed` | warn | Every counted fund holds the name |
| `top_firm_position`, `top_firm_sector`, `cross_fund_overlap` | info | Reporting only, no threshold |
| `unclassified_symbols`, `unresolved_orders` | info / warn | Totals are incomplete or a lower bound |

An aggregate breach rule was deliberately left out. A firm fraction is a capital-weighted
average of the funds' own weights, so the like-for-like ceiling is the capital-weighted
average of their own limits; if every fund sits exactly at its limit the two are equal by
construction. The aggregate can exceed it only when some individual fund is already over
its own mandate, which is reported as drift. `permitted_fraction` is returned as that
reconciliation figure, not as a threshold.

## Gaps and handoffs

- Sector limits are now enforced upstream, so the drift findings are a backstop rather
  than the only check. `desk.check_allocation` applies the cash reserve and sector cap when
  a strategy is registered, and `paper.submit` and `synthesis/orders.py` apply them on
  projected holdings. Drift should therefore appear only when recorded orders move a fund
  past a limit it satisfied at registration, or when a mandate is tightened afterwards.
  `test_drift_finding_agrees_with_the_desk_allocation_check` pins the two to the same
  verdict on the same book.
- The sector map is `backend/app/wf/masking.py`'s `SECTORS`, reused rather than redefined so
  a firm total cannot disagree with a per-fund limit. It is a static label for the snapshot
  universe, not sourced market data and not a GICS licence. The gates fail closed on an
  unknown symbol, which is right before trading; this read-only report instead marks it
  `Unclassified`, excludes it from sector totals and names it in a finding, so a missing
  label cannot take the whole firm view down.
- Per-fund attribution of real holdings is limited by design: one shared account, no
  brokerage subledgers, so `committed` comes from each fund's own order log.
- Not done: no agent tool (would need a `roles.py` capability), no UI, and the live
  capacity check has not run against real Alpaca credentials from this machine.
- A roll-up is scoped to one person's memberships, so two advisors can see different firm
  totals. There is no account-wide view that crosses membership, by design.
