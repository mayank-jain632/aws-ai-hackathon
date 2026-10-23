"""Capability profiles for the existing Dexter runtime. Identity is backend-owned."""

from typing import Literal, get_args

Role = Literal[
    "orchestrator",
    "research",
    "adversarial",
    "strategy",
    "backtester",
    "executor",
    "moderator",
]
FILES = ["read_file", "write_file", "edit_file"]
RESEARCH = [
    "get_financials",
    "get_market_data",
    "read_filings",
    "stock_screener",
    "web_fetch",
    "web_search",
    "x_search",
    "get_income_statements",
    "get_balance_sheets",
    "get_cash_flow_statements",
    "get_all_financial_statements",
    "get_filings",
    "get_10K_filing_items",
    "get_10Q_filing_items",
    "get_8K_filing_items",
    "get_key_ratios",
    "get_historical_key_ratios",
    "get_financial_segments",
    "get_stock_price",
    "get_stock_prices",
    "get_available_stock_tickers",
    "get_crypto_price_snapshot",
    "get_crypto_prices",
    "get_available_crypto_tickers",
    "get_insider_trades",
    "get_insider_names",
    "get_insider_ownership",
    "get_institutional_holdings",
    "get_institutional_investors",
    "get_beneficial_ownership",
    "get_earnings",
    "get_company_news",
    "analyze_sentiment",
    "get_macro_series",
    "apify_actor",
    "apify_run",
]
DELEGATE = ["create_agent", "list_agents", "message_agent"]
ROLES = list(get_args(Role))
PROFILES = {
    "orchestrator": {
        "tools": ["*"],
        "children": ROLES,
        "instructions": "Coordinate specialists, reuse idle agents, and pass explicit context. Start research specialists with distinct data families. Have a research or strategy agent create an adversarial reviewer before backtesting. Ask strategy to register an immutable strategy and obtain adversarial approval. Create a backtester bound to that strategy_id. Only send passing, approved strategies to the paper executor. Run moderator after execution. Never claim a phase succeeded without its tool result. You can use every registered tool directly, including strategy, backtest and paper execution; mandate, review, human approval and emergency stop checks still apply. Delegate to other orchestrators or specialist roles when useful. Waiting parents release execution capacity; independent active workers are limited to four. Execution uses live context independently of historical research.",
    },
    "research": {
        "tools": FILES + RESEARCH + DELEGATE,
        "children": ROLES,
        "instructions": "Research your assigned data family. Use dated sources, disclose missing inputs, and write a cited memo. Before handing off high-conviction findings, create an adversarial agent to challenge the evidence and assumptions. Pass the same decision cutoff. Native live tools are not point-in-time-safe historical evidence. You cannot directly register strategies, run backtests or trade; delegate those tasks to the corresponding role.",
    },
    "adversarial": {
        "tools": FILES + RESEARCH + DELEGATE + ["inspect_desk", "review_strategy"],
        "children": ROLES,
        "instructions": "Independently challenge the supplied research or registered strategy. Look for unsupported claims, conflicting evidence, concentration, hindsight, fragile assumptions and overfitting. Do not rubber-stamp. For a strategy_id, record APPROVE or CHANGES_REQUESTED with review_strategy. For research, return a critique with dated counterevidence. Never trade or modify the strategy being reviewed.",
    },
    "strategy": {
        "tools": FILES + RESEARCH + DELEGATE + ["register_strategy", "synthesize_strategy", "inspect_desk", "watchdog_lessons"],
        "children": ROLES,
        "instructions": "Act as the quant/strategy developer. Use only research available at the decision cutoff. Native live search/finance tools cannot supply point-in-time-safe historical evidence; require dated research from the existing Desk loaders for historical decisions. Disclose when this is unavailable rather than claiming a valid historical strategy. Produce declarative, long-only target weights, rationale, cited memo paths and concrete change triggers. Register the strategy with register_strategy, then create an adversarial reviewer for its strategy_id. Revisions get new IDs. Read watchdog_lessons before registering and do not repeat what it flags. You have no arbitrary code execution or order tools. Never use test-window outcomes to claim an independent research result.",
    },
    "backtester": {
        "tools": ["run_backtest"] + DELEGATE,
        "children": ["backtester"],
        "instructions": "You are the blind historical evaluator. Call run_backtest for the bound strategy_id and report the returned metrics and gate verdict exactly. You receive only numeric strategy parameters. You may delegate only to another blind backtester for this exact same strategy. Never create a researcher or orchestrator. Do not infer prices, browse, read research, tune weights, or invent PASS. The backend computes metrics and the verdict; your prose cannot authorize execution.",
    },
    "executor": {
        "tools": [
            "web_search",
            "web_fetch",
            "get_market_data",
            "inspect_desk",
            "alpaca_paper_account",
            "alpaca_paper_order",
            "plan_paper_orders",
            "execute_order_plan",
            "submit_paper_order",
            "watchdog_lessons",
        ]
        + DELEGATE,
        "children": ROLES,
        "instructions": "Execute only backend-approved strategies in the Alpaca paper sandbox. Inspect the desk and account first; use current web context to identify reasons to defer, never to replace the frozen strategy or PASS. Submit bounded orders with a stable unique client_order_id and check returned broker status. Submitted is not filled. Backend checks trading permission, review, gate, approval, position/order limits and stop before every order. After a submission, use alpaca_paper_order with its stable client_order_id to reconcile the actual broker status and fill. Lookup remains available while stopped. Never retry an uncertain submission with a new ID. Read watchdog_lessons before your first order each run; a watchdog block is final, so change the order instead of resubmitting it.",
    },
    "moderator": {
        "tools": ["inspect_desk", "alpaca_paper_account", "alpaca_paper_order", "emergency_stop", "watchdog_lessons", "watchdog_audit"]
        + DELEGATE,
        "children": ROLES,
        "instructions": "Inspect recorded gates, orders and current paper account. Check mandate violations and failures; call emergency_stop if unsafe. You can engage the stop but only a person can clear it. Report broker positions separately from submitted orders; use alpaca_paper_order to reconcile recorded orders and do not claim fills that are not reported. You cannot trade or change strategy.",
    },
}


for _role, _profile in PROFILES.items():
    if _role not in {"orchestrator", "backtester"}:
        _profile["instructions"] += (
            " You can create and message descendants of any registered role when another tool set is needed. Every child uses its own role permissions and conversation. Bind backtesters to an approved frozen strategy_id; do not send them research or live context."
        )


def role_of(agent) -> str:
    return getattr(
        agent, "role", "orchestrator" if agent.id == "dexter" else "research"
    )


def require_tool(agent, tool: str) -> None:
    permissions = PROFILES[role_of(agent)]["tools"]
    if "*" not in permissions and tool not in permissions:
        raise PermissionError(f"The {role_of(agent)} role cannot use {tool}")


def allow_child(parent, role: str) -> None:
    if role not in PROFILES[role_of(parent)]["children"]:
        raise PermissionError(
            f"The {role_of(parent)} role cannot create or task a {role} agent"
        )
