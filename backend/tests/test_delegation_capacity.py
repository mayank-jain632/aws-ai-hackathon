"""Actual runtime/HTTP handoffs with controllable worker processes, no model I/O."""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from backend.app import agent as runtime
from backend.app.main import app


class FakeOutput:
    def __init__(self):
        self.queue = asyncio.Queue()

    def __aiter__(self):
        return self

    async def __anext__(self):
        value = await self.queue.get()
        if value is None:
            raise StopAsyncIteration
        return value


class FakeProcess:
    def __init__(self, agent_id, pid):
        self.agent_id = agent_id
        self.pid = pid
        self.returncode = None
        self.stdout = FakeOutput()
        self.ended = asyncio.Event()
        self.payload = b""
        self.stdin = SimpleNamespace(
            write=self.write, drain=self.drain, close=lambda: None
        )
        self.stderr = SimpleNamespace(read=self.read_stderr)

    def write(self, value):
        self.payload += value

    async def drain(self):
        pass

    async def read_stderr(self):
        return b""

    async def wait(self):
        await self.ended.wait()
        return self.returncode

    def finish(self):
        if self.returncode is not None:
            return
        self.returncode = 0
        self.stdout.queue.put_nowait(
            json.dumps(
                {"type": "done", "answer": "completed", "iterations": 1}
            ).encode()
            + b"\n"
        )
        self.stdout.queue.put_nowait(None)
        self.ended.set()


async def until(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0.001)


@pytest.fixture
def controlled_board(tmp_path, monkeypatch):
    manager = runtime.AgentManager(root=tmp_path / "state")
    source = tmp_path / "source"
    source.mkdir()
    (source / ".revision").write_text("test")
    monkeypatch.setattr(runtime, "DEXTER_SOURCE", source)
    monkeypatch.setattr(runtime, "bun_binary", lambda: "bun")
    monkeypatch.setattr(app.state, "manager", manager, raising=False)
    monkeypatch.delattr(app.state, "funds", raising=False)
    monkeypatch.delenv("APP_ACCESS_PASSWORD", raising=False)
    processes = {}
    peaks = []

    async def spawn(*args, **kwargs):
        aid = kwargs["env"]["LOCAL_AGENT_ID"]
        process = FakeProcess(aid, len(processes) + 100)
        processes[aid] = process
        peaks.append(sum(agent.holds_slot for agent in manager.agents.values()))
        assert peaks[-1] <= 4
        return process

    monkeypatch.setattr(runtime.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(
        runtime.os,
        "killpg",
        lambda pid, sig: next(p for p in processes.values() if p.pid == pid).finish(),
    )
    return manager, processes, peaks


def auth(manager, aid):
    return {"X-Agent-Token": manager.token, "X-Agent-ID": aid}


async def create(client, manager, parent, role="research"):
    result = await client.post(
        "/api/internal/agents/create",
        headers=auth(manager, parent),
        json={"role": role, "name": role, "task": "Perform specialist work"},
    )
    assert result.status_code == 200, result.text
    return result.json()


def test_sibling_nested_handoffs_bound_slots_and_cancel_queued(controlled_board):
    manager, processes, peaks = controlled_board

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            root = manager.agents["dexter"]
            await root.start("Coordinate work")
            await until(lambda: "dexter" in processes)
            requests = [
                asyncio.create_task(create(client, manager, "dexter")) for _ in range(3)
            ]
            await until(lambda: len(processes) == 4)
            assert root.pending_delegations == 3 and not root.holds_slot
            children = [a for a in manager.agents.values() if a.parent_id == "dexter"]
            parent = children[0]
            nested = [
                asyncio.create_task(create(client, manager, parent.id, "adversarial"))
                for _ in range(2)
            ]
            await until(lambda: len(processes) == 6)
            assert parent.pending_delegations == 2 and not parent.holds_slot
            assert sum(a.holds_slot for a in manager.agents.values()) == 4
            queued = await manager.create(
                "dexter", "Queued", "Wait for capacity", "strategy"
            )
            await asyncio.sleep(0)
            assert queued.process is None and queued.snapshot()["queued"]
            await asyncio.wait_for(queued.stop(), timeout=0.5)
            assert queued.state["status"] == "stopped"
            assert queued.id not in processes
            grandchildren = [
                a for a in manager.agents.values() if a.parent_id == parent.id
            ]
            processes[grandchildren[0].id].finish()
            await until(lambda: parent.pending_delegations == 1)
            assert not parent.holds_slot
            processes[grandchildren[1].id].finish()
            await asyncio.gather(*nested)
            assert parent.holds_slot and parent.pending_delegations == 0
            for child in children:
                processes[child.id].finish()
            await asyncio.gather(*requests)
            assert root.holds_slot and root.pending_delegations == 0
            assert sum(a.holds_slot for a in manager.agents.values()) == 1
            processes["dexter"].finish()
            await root.task
            assert manager.slots._value == 4
            roster = json.loads(manager.registry.read_text())
            assert len(roster) == 6 and max(peaks) == 4
            assert root.snapshot()["status"] == "idle"
        await manager.close()

    asyncio.run(exercise())


def test_stop_waiting_branch_releases_every_slot(controlled_board):
    manager, processes, _ = controlled_board

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            root = manager.agents["dexter"]
            await root.start("Delegate")
            await until(lambda: "dexter" in processes)
            child_request = asyncio.create_task(create(client, manager, "dexter"))
            await until(lambda: len(processes) == 2)
            child = next(a for a in manager.agents.values() if a.parent_id == "dexter")
            nested_request = asyncio.create_task(
                create(client, manager, child.id, "strategy")
            )
            await until(lambda: len(processes) == 3)
            assert not root.holds_slot and not child.holds_slot
            await asyncio.wait_for(manager.stop("dexter"), timeout=1)
            await asyncio.gather(child_request, nested_request)
            assert all(a.state["status"] == "stopped" for a in manager.agents.values())
            assert all(not a.holds_slot for a in manager.agents.values())
            assert manager.slots._value == 4

    asyncio.run(exercise())


def test_cancel_before_worker_coroutine_starts_has_result(controlled_board):
    manager, processes, _ = controlled_board

    async def exercise():
        child = await manager.create(
            "dexter", "Cancel immediately", "No model work", "research"
        )
        await child.stop()
        result = await manager.result(child)
        assert result["status"] == "stopped"
        assert child.id not in processes
        assert manager.slots._value == 4

    asyncio.run(exercise())
