"""Firm-level exposure route. Human-only, and read-only across every fund."""

import httpx
from fastapi import APIRouter, HTTPException, Request

from backend.app.desk import desk_for
from backend.app.firm import fund_exposure, roll_up
from backend.app.paper import account_snapshot
from backend.app.routes.desk import human

router = APIRouter(tags=["firm"])


def collect(store, visible=None) -> list[dict]:
    """Per-fund exposure for the funds the caller may see. `visible` filters by fund id."""
    return [
        fund_exposure(fund_id, record, desk_for(store.runtime(fund_id)).state)
        for fund_id, record in list(store.records.items())
        if visible is None or visible(fund_id)
    ]


@router.get("/api/firm/exposure")
def exposure(request: Request, include_broker: bool = True) -> dict:
    """Exposure across the caller's funds, optionally compared with the paper account."""
    human(request)
    store = getattr(request.app.state, "funds", None)
    if store is None:
        raise HTTPException(503, "Fund store is not ready yet")
    # Fund membership is enforced on /api/funds, so the firm view must honour it too:
    # "firm-wide" means every fund this person is a member of, not every fund on the host.
    sharing = getattr(request.app.state, "sharing", None)
    email = getattr(request.state, "user", "local")
    visible = (lambda fund_id: sharing.can_access(fund_id, email)) if sharing else None
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
    return {
        **roll_up(collect(store, visible), equity),
        "broker_note": note,
        "scope": f"funds {email} is a member of" if sharing else "every fund on this host",
    }
