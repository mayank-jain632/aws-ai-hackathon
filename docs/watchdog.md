# Watchdog

The watchdog is the moderator half of lane 4 (D17, D19). It reviews every paper order before it reaches Alpaca, owns a firm-wide emergency stop, audits each fund's desk in the background, asks Bedrock for a second opinion on flagged trades, and feeds what it catches back to the other agents. Code: `backend/app/watchdog/`, routes in `backend/app/routes/watchdog.py`, canvas tools in `backend/worker/watchdog-tools.ts`.

## Where it sits

```text
executor submit_paper_order -> POST /api/internal/desk/order -> paper.submit
  -> account snapshot, open-order check
  -> watchdog review_order (16 rules, no LLM)   <- firm-wide stop, desk stop, fund pause
  -> existing adapter checks (exposure vs frozen target, fund capital, sector)
  -> desk.execution_checks again -> Alpaca paper
```

A block raises `ValueError("Watchdog blocked this order: ...")`. The order route records `paper_order_blocked`, and the executor sees the reason as its tool error. The verdict is final; no model can approve past it.

## Rules

| Rule | Blocks when |
|---|---|
| `emergency_stop` | Firm-wide stop, this fund's desk stop, or fund pause is on |
| `trading_permission` | Desk policy or fund mandate does not allow paper trading |
| `universe` | Ticker is outside the client's approved list |
| `known_ticker` | Ticker is not in the desk's price data |
| `backtest_pass` | A buy has no current backend PASS (sells that only cut risk are allowed) |
| `quantity_sanity` | Non-positive or NaN size, qty times price disagrees with notional, buy exceeds cash, sell exceeds holding |
| `order_size` | Over the per-order dollar limit, or one order is too large a share of equity for the risk band |
| `position_size` | Position after the trade exceeds the mandate's single-position cap |
| `concentration` | Three largest holdings after the trade exceed the risk band's combined cap |
| `drawdown` | Account is at its drawdown limit (buys only), or the strategy's tested drawdown is deeper than the client tolerates |
| `price_band` | A stated price is too far from the last close |
| `rapid_fire` | More than 5 orders in 60 seconds |
| `duplicate` | Same symbol, side and size within 5 minutes under a different order id |
| `wash_trade` | Opposite side of the same ticker already traded today |
| `turnover` | Today's traded value would exceed the risk band's daily cap |
| `daily_orders` | Over the mandate's daily order count |

Risk-band guardrails (`rules.GUARDRAILS`) are order-flow limits, not evaluation thresholds; a mandate field overrides them. Rules within 10% of a limit are reported as near misses without blocking. When several rules block, the most serious leads the reason.

To review an order outside `paper.submit`, use `review_order(WatchOrder, WatchMandate, WatchPortfolio) -> Verdict` and check `is_halted(desk)` first.

## Emergency stop

One flag across every fund, above each fund's desk stop. People trip and clear it; the monitor trips it on a runaway. Agents cannot clear it. It does not cancel orders a broker already accepted.

- `PUT /api/watchdog/halt` with `{"halted": true|false, "reason": "..."}` (worker tokens get 403)
- `GET /api/watchdog` or `GET /api/funds/{fund_id}/watchdog` for stop state, feedback, events and lessons

## Monitor

Runs every `WATCHDOG_INTERVAL_SECONDS` (default 60; 0 disables) over the board and every fund, and on demand through `POST /api/watchdog/audit`, `POST /api/funds/{fund_id}/watchdog/audit`, or the moderator's `watchdog_audit` tool. It flags more than 10 orders in 10 minutes (trips the stop), an agent with 3 blocked orders in 10 minutes (6 trips the stop), orders with an unknown broker outcome, holdings past the mandate, shorts, holdings outside the universe, and strategy memos that are missing, cite dates after the strategy cutoff (`assert_no_lookahead`), or changed after the strategy was frozen. Events are written beside the desk, mirrored to `workspace/watchdog/events.jsonl`, and logged on the desk as `watchdog_event`.

## Second opinion and lessons

Blocked and near-miss orders get a Bedrock Converse review through `run_structured` (`us.openai.gpt-5.6-luna`, no temperature): foul play or honest mistake, a plain explanation for the analyst, and a fix. With `MOCK_AGENTS=1`, no credentials, or a Bedrock error, a rule-based note stands in and its `source` says so.

Every verdict, desk-gate block, opinion and order outcome goes to `feedback.jsonl` beside the desk. It is distilled into `workspace/watchdog/LESSONS.md`, which strategy, executor and moderator agents read with `watchdog_lessons` (their instructions tell them to, before registering or ordering).

## Demo

Offline and repeatable, through the real backend routes with only the broker stubbed:

```sh
MOCK_AGENTS=1 uv run python scripts/watchdog_demo.py
```

It sets up a conservative client (Calder Family Trust, 25% position cap) with a strategy that passes a blind backtest on the real price snapshot. The executor's $40,000 MSFT buy is blocked on position size. An $8,000 buy goes through. A person trips the firm-wide stop, and orders in this fund and a second fund are both refused. The script ends by printing the lessons the agents will read.

On the hosted canvas, set a fund's desk policy and approve a strategy as `docs/agent-roles.md` describes, ask the executor for an oversized buy, then trip the stop with `PUT /api/watchdog/halt`.

## Not verified

A live Bedrock second opinion, a real Alpaca order through the gate, the registry listing in the built container, and a hosted rollout. All tests mock the broker; the Bedrock path is exercised with a stubbed `run_structured`. AgentCore Memory persistence (PRD P1) is not built; it would need an accepted decision for the new AWS resource.
