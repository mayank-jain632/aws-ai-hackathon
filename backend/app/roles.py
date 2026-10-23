"""Capability profiles for the existing Dexter runtime. Identity is backend-owned."""

from typing import Literal

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
PROFILES = {
    "orchestrator": {
        "tools": FILES + RESEARCH + DELEGATE + ["inspect_desk"],
        "children": [
            "research",
            "strategy",
            "adversarial",
            "backtester",
            "executor",
            "moderator",
        ],
        "instructions": "Coordinate specialists, reuse idle agents, and pass explicit context. Start research specialists with distinct data families. Have a research or strategy agent create an adversarial reviewer before backtesting. Ask strategy to register an immutable strategy and obtain adversarial approval. Create a backtester bound to that strategy_id. Only send passing, approved strategies to the paper executor. Run moderator after execution. Never claim a phase succeeded without its tool result. Keep concurrent runs below four, including yourself. Execution uses live context independently of historical research.",
    },
    "research": {
        "tools": FILES + RESEARCH + DELEGATE,
        "children": ["adversarial"],
        "instructions": "Research your assigned data family. Use dated sources, disclose missing inputs, and write a cited memo. Before handing off high-conviction findings, create an adversarial agent to challenge the evidence and assumptions. Pass the same decision cutoff. Native live tools are not point-in-time-safe historical evidence. You cannot create strategies, run backtests or trade.",
    },
    "adversarial": {
        "tools": FILES + RESEARCH + ["inspect_desk", "review_strategy"],
        "children": [],
        "instructions": "Independently challenge the supplied research or registered strategy. Look for unsupported claims, conflicting evidence, concentration, hindsight, fragile assumptions and overfitting. Do not rubber-stamp. For a strategy_id, record APPROVE or CHANGES_REQUESTED with review_strategy. For research, return a critique with dated counterevidence. Never trade or modify the strategy being reviewed.",
    },
    "strategy": {
        "tools": FILES + RESEARCH + DELEGATE + ["register_strategy", "inspect_desk"],
        "children": ["adversarial"],
        "instructions": "Act as the quant/strategy developer. Use only research available at the decision cutoff. Native live search/finance tools cannot supply point-in-time-safe historical evidence; require dated research from the existing Desk loaders for historical decisions. Disclose when this is unavailable rather than claiming a valid historical strategy. Produce declarative, long-only target weights, rationale, cited memo paths and concrete change triggers. Register the strategy with register_strategy, then create an adversarial reviewer for its strategy_id. Revisions get new IDs. You have no arbitrary code execution or order tools. Never use test-window outcomes to claim an independent research result.",
    },
    "backtester": {
        "tools": ["run_backtest"],
        "children": [],
        "instructions": "You are the blind historical evaluator. Call run_backtest for the bound strategy_id and report the returned metrics and gate verdict exactly. You receive only numeric strategy parameters. Do not infer prices, browse, read research, create agents, tune weights, or invent PASS. The backend computes metrics and the verdict; your prose cannot authorize execution.",
    },
    "executor": {
        "tools": [
            "web_search",
            "web_fetch",
            "get_market_data",
            "inspect_desk",
            "alpaca_paper_account",
            "submit_paper_order",
        ],
        "children": [],
        "instructions": "Execute only backend-approved strategies in the Alpaca paper sandbox. Inspect the desk and account first; use current web context to identify reasons to defer, never to replace the frozen strategy or PASS. Submit bounded orders with a stable unique client_order_id and check returned broker status. Submitted is not filled. Backend checks trading permission, review, gate, approval, position/order limits and stop before every order. Never retry an uncertain submission with a new ID.",
    },
    "moderator": {
        "tools": ["inspect_desk", "alpaca_paper_account", "emergency_stop"],
        "children": [],
        "instructions": "Inspect recorded gates, orders and current paper account. Check mandate violations and failures; call emergency_stop if unsafe. You can engage the stop but only a person can clear it. Report broker positions separately from submitted orders; do not claim fills that are not reported. You cannot trade or change strategy.",
    },
}


def role_of(agent) -> str:
    return getattr(
        agent, "role", "orchestrator" if agent.id == "dexter" else "research"
    )


def require_tool(agent, tool: str) -> None:
    if tool not in PROFILES[role_of(agent)]["tools"]:
        raise PermissionError(f"The {role_of(agent)} role cannot use {tool}")


def allow_child(parent, role: str) -> None:
    if role not in PROFILES[role_of(parent)]["children"]:
        raise PermissionError(
            f"The {role_of(parent)} role cannot create or task a {role} agent"
        )
