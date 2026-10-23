"""Persistent hourly fund wakeups inside the existing app process."""

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime, timedelta

HOUR = timedelta(hours=1)
AUTHORIZED_FUND = "8789dfb8011d462b"
logger = logging.getLogger(__name__)
WAKEUP = """Resume this saved fund's authorized research/evaluation workflow. This is an
hourly progress check, not a new investment mandate or permission to trade. Read the
current server mandate, mandate.md, fund-plan.md and the saved agent roster/threads.
Earlier document-only planning instructions are superseded by the current delegated
workflow. Verify what actually finished, reuse existing specialists, investigate
incomplete phases and continue useful independent work. Record dated evidence,
artifact paths, strategy/evaluation IDs, blockers and concrete next actions in
fund-plan.md. Distinguish the investment horizon from explicit evaluation dates.
In live paper mode an old saved historical cutoff is inactive; do not relabel live
research as historical evidence. For PAPER workflows, choose very low pass criteria as authorized and record them within the saved mandate
through the authorized backend tool, and freeze them before blind testing. Never
relax criteria after observing results. Report missing approvals or unsupported
enforcement and continue independent research; never invent prices, returns or approvals. Keep mandate, trading permissions, stop and human
approval gates unchanged. This wakeup does not authorize order submission.
"""


def now_utc():
    return datetime.now(UTC)


def busy(runtime):
    return any(
        agent.state.get("status") in {"running", "waiting", "monitoring"}
        or (getattr(agent, "task", None) is not None and not agent.task.done())
        for agent in runtime.agents.values()
    )


class FundScheduler:
    def __init__(self, store, clock=now_utc):
        self.store = store
        self.clock = clock
        self.lock = asyncio.Lock()
        self.task = None
        self.active_runs = {}
        changed = False
        now = clock()
        for fund_id, record in store.records.items():
            schedule = record.get("schedule")
            if schedule is None:
                # Explicit human authorization is limited to this existing fund.
                enabled = fund_id == AUTHORIZED_FUND and record["status"] == "active"
                record["schedule"] = self.new_schedule(
                    enabled, "Human instruction" if enabled else None
                )
                changed = True
            elif schedule.get("enabled"):
                if record["status"] != "active":
                    schedule.update(
                        enabled=False,
                        next_run_at=None,
                        last_result="Disabled: fund is not active",
                    )
                    changed = True
                elif (
                    not schedule.get("next_run_at")
                    or self.parse(schedule["next_run_at"]) <= now
                ):
                    schedule.update(
                        next_run_at=(now + HOUR).isoformat(),
                        last_result="Missed wakeup skipped after restart",
                    )
                    changed = True
        if changed:
            store.save()

    @staticmethod
    def parse(value):
        return datetime.fromisoformat(value).astimezone(UTC)

    def new_schedule(self, enabled=False, actor=None):
        now = self.clock()
        return {
            "enabled": enabled,
            "interval_seconds": 3600,
            "next_run_at": (now + HOUR).isoformat() if enabled else None,
            "last_run_at": None,
            "last_result": None,
            "authorized_by": actor,
            "authorized_at": now.isoformat() if enabled else None,
        }

    def view(self, fund_id):
        return dict(self.store.records[fund_id].get("schedule") or self.new_schedule())

    async def configure(self, fund_id, enabled, actor):
        async with self.lock:
            record = self.store.records[fund_id]
            if enabled and record["status"] != "active":
                raise ValueError("Resume the fund before enabling hourly wakeups")
            previous = self.view(fund_id)
            if enabled:
                # An idempotent enable does not postpone the next scheduled check.
                if not previous["enabled"]:
                    previous.update(
                        enabled=True,
                        next_run_at=(self.clock() + HOUR).isoformat(),
                        authorized_by=actor,
                        authorized_at=self.clock().isoformat(),
                        last_result="Hourly wakeups enabled",
                    )
            else:
                previous.update(
                    enabled=False,
                    next_run_at=None,
                    last_result="Hourly wakeups disabled",
                )
            record["schedule"] = previous
            self.store.save()
            if not enabled:
                await self.cancel_owned(fund_id)
            self.store.runtime(fund_id).publish()
            return self.view(fund_id)

    async def disable(self, fund_id, reason):
        await self.configure(fund_id, False, None)
        self.store.records[fund_id]["schedule"]["last_result"] = reason
        self.store.save()

    async def cancel_owned(self, fund_id):
        owned = self.active_runs.pop(fund_id, None)
        runtime = self.store.runtime(fund_id)
        if (
            owned is not None
            and runtime.agents["dexter"].task is owned
            and busy(runtime)
        ):
            await runtime.stop("dexter")

    async def tick(self):
        async with self.lock:
            now = self.clock()
            for fund_id, record in list(self.store.records.items()):
                schedule = record.get("schedule", {})
                if not schedule.get("enabled"):
                    continue
                if record["status"] != "active":
                    schedule.update(
                        enabled=False,
                        next_run_at=None,
                        last_result="Disabled: fund is not active",
                    )
                    self.store.save()
                    await self.cancel_owned(fund_id)
                    continue
                if (
                    not schedule.get("next_run_at")
                    or self.parse(schedule["next_run_at"]) > now
                ):
                    continue
                # Claim the next hour before dispatch: no queued catch-up work or retry flood.
                schedule["next_run_at"] = (now + HOUR).isoformat()
                runtime = self.store.runtime(fund_id)
                if busy(runtime):
                    schedule["last_result"] = "Skipped: agents are already working"
                else:
                    from backend.app.watchdog.halt import SWITCH

                    if SWITCH.state().get("halted"):
                        schedule["last_result"] = (
                            "Skipped: firm emergency stop is engaged"
                        )
                    else:
                        try:
                            await runtime.agents["dexter"].start(
                                WAKEUP, source="Hourly schedule"
                            )
                        except (ValueError, RuntimeError) as error:
                            schedule["last_result"] = f"Could not start: {error}"
                        else:
                            self.active_runs[fund_id] = runtime.agents["dexter"].task
                            schedule.update(
                                last_run_at=now.isoformat(),
                                last_result="Started saved Dexter",
                            )
                self.store.save()
                runtime.publish()

    async def run(self):
        while True:
            await asyncio.sleep(30)
            try:
                await self.tick()
            except Exception:
                # A single invalid worker/fund must not silently kill all schedules.
                logger.exception("Fund scheduler tick failed")

    def start(self):
        self.task = asyncio.create_task(self.run(), name="fund-hourly-wakeups")

    async def close(self):
        if self.task is not None:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
