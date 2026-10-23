"""Firm-level exposure route. Human-only, and read-only across every fund."""

import httpx
from fastapi import APIRouter, HTTPException, Request

from backend.app.desk import desk_for
from backend.app.firm import fund_exposure, roll_up
from backend.app.paper import account_snapshot
from backend.app.routes.desk import human

router = APIRouter(tags=["firm"])


def collect(store) -> list[dict]:
    return [
        fund_exposure(fund_id, record, desk_for(store.runtime(fund_id)).state)
        for fund_id, record in list(store.records.items())
    ]


@router.get("/api/firm/exposure")
def exposure(request: Request, include_broker: bool = True) -> dict:
    """Exposure across all funds, optionally compared with the shared paper account."""
    human(request)
    store = getattr(request.app.state, "funds", None)
    if store is None:
        raise HTTPException(503, "Fund store is not ready yet")
    equity: float | None = None
    note: str | None = None
    if include_broker:
        # A missing or unreachable broker must not fail the exposure view; the capacity
        # check is simply reported as unavailable.
        try:
            equity = float(account_snapshot()["account"]["equity"])
        except httpx.HTTPError:
            note = "Shared paper account request failed, so the capacity check is unavailable."
        except (ValueError, KeyError, TypeError) as error:
            note = f"Shared paper account unavailable, so the capacity check is unavailable: {error}"
    return {**roll_up(collect(store), equity), "broker_note": note}
