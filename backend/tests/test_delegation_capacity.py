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


def test_late_parallel_requests_reacquire_parent_only_once(controlled_board):
    manager, processes, _ = controlled_board

    async def exercise():
        root = manager.agents["dexter"]
        await root.start("Coordinate")
        await until(lambda: "dexter" in processes)
        # Three independent workers fill the remaining capacity.
        for _ in range(3):
            await manager.slots.acquire()

        async def first_request():
            async with manager.delegating(root):
                # A queued worker takes the slot released by this parent.
                await manager.slots.acquire()

        first = asyncio.create_task(first_request())
        await until(
            lambda: (
                root.pending_delegations == 0
                and not root.holds_slot
                and manager.slots._value == 0
            )
        )

        async def late_request():
            async with manager.delegating(root):
                pass

        late = asyncio.create_task(late_request())
        await asyncio.sleep(0)
        manager.slots.release()
        manager.slots.release()
        await asyncio.gather(first, late)
        assert root.holds_slot
        assert manager.slots._value == 1
        processes["dexter"].finish()
        await root.task
        manager.slots.release()
        manager.slots.release()
        assert manager.slots._value == 4

    asyncio.run(exercise())


def test_background_children_timer_wait_and_completion_wakeup(controlled_board):
    manager, processes, _ = controlled_board

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
            root = manager.agents["dexter"]
            await root.start("Supervise")
            await until(lambda: "dexter" in processes)
            response = await client.post("/api/internal/agents/create", headers=auth(manager, "dexter"), json={"name": "Async", "task": "Research", "wait_for_result": False})
            assert response.status_code == 200 and response.json()["background"]
            aid = response.json()["id"]
            await until(lambda: aid in processes)
            waiting = asyncio.create_task(client.post("/api/internal/agents/wait", headers=auth(manager, "dexter"), json={"seconds": 3600, "agent_ids": [aid]}))
            await until(lambda: root.waiting_until is not None and not root.holds_slot)
            assert root.state["status"] == "running" and root.snapshot()["waitingForAgents"]
            processes[aid].finish()
            result = await asyncio.wait_for(waiting, timeout=1)
            assert result.json()["reason"] == "agent_finished"
            assert root.holds_slot and root.waiting_until is None
            timer = await client.post("/api/internal/agents/wait", headers=auth(manager, "dexter"), json={"seconds": 0.01})
            assert timer.json()["reason"] == "timer" and root.holds_slot
            await manager.close()
            assert manager.slots._value == 4

    asyncio.run(exercise())


def test_stop_long_timer_and_queued_reacquisition_are_prompt(controlled_board):
    manager, processes, _ = controlled_board

    async def exercise():
        root = manager.agents["dexter"]
        await root.start("Wait")
        await until(lambda: "dexter" in processes)
        timer = asyncio.create_task(manager.wait_for_agents(root, 3600, []))
        await until(lambda: root.waiting_until is not None and not root.holds_slot)
        await asyncio.wait_for(root.stop(), timeout=0.5)
        with pytest.raises(ValueError, match="cancelled"):
            await asyncio.wait_for(timer, timeout=0.5)
        assert manager.slots._value == 4
        await root.start("Wait for capacity")
        await until(lambda: root.holds_slot)
        # Fill every slot, including the one the timer releases, before it returns.
        timer = asyncio.create_task(manager.wait_for_agents(root, 0.01, []))
        await until(lambda: not root.holds_slot)
        for _ in range(4):
            await manager.slots.acquire()
        await until(lambda: root.pending_delegations == 0)
        await asyncio.wait_for(root.stop(), timeout=0.5)
        await asyncio.wait_for(timer, timeout=0.5)
        for _ in range(4):
            manager.slots.release()
        assert manager.slots._value == 4

    asyncio.run(exercise())


def test_thread_read_is_bounded_paginated_and_fund_private(controlled_board, tmp_path, monkeypatch):
    manager, _, _ = controlled_board
    other = runtime.AgentManager(root=tmp_path / "other-fund")
    sibling = runtime.LocalAgent(manager, "sibling", "Sibling", "dexter", "research")
    blind = runtime.LocalAgent(manager, "blind", "Blind", "dexter", "backtester")
    manager.agents.update(sibling=sibling, blind=blind)
    other.agents["secret-agent"] = runtime.LocalAgent(other, "secret-agent", "Secret", "dexter", "research")
    sibling.state["messages"] = [{"id": str(i), "role": "assistant", "text": str(i) + "x" * 1000} for i in range(30)]
    root = manager.agents["dexter"]
    before = list(root.state["messages"])

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
            result = await client.get("/api/internal/agents/sibling/thread?limit=3&max_chars=200", headers=auth(manager, "dexter"))
            assert result.status_code == 200
            page = result.json()
            assert [m["id"] for m in page["messages"]] == ["27", "28", "29"]
            assert sum(len(m["text"]) for m in page["messages"]) <= 200
            assert page["next_cursor"] == 27 and any(m["truncated"] for m in page["messages"])
            previous = await client.get("/api/internal/agents/sibling/thread?cursor=27&limit=3", headers=auth(manager, "dexter"))
            assert previous.json()["messages"][-1]["id"] == "26"
            assert root.state["messages"] == before
            assert (await client.get("/api/internal/agents/secret-agent/thread", headers=auth(manager, "dexter"))).status_code == 404
            assert (await client.get("/api/internal/agents/sibling/thread", headers=auth(other, "dexter"))).status_code == 403
            for action, body in [("wait", {"seconds": 0.01}), ("result", {"agent_id": "sibling"})]:
                assert (await client.post("/api/internal/agents/" + action, headers=auth(manager, "blind"), json=body)).status_code == 403
            assert (await client.get("/api/internal/agents/sibling/thread", headers=auth(manager, "blind"))).status_code == 403
            assert (await client.get("/api/internal/agents/sibling/thread?limit=100", headers=auth(manager, "dexter"))).status_code == 422
            assert (await client.post("/api/internal/agents/wait", headers=auth(manager, "dexter"), json={"seconds": 3601})).status_code == 422

    asyncio.run(exercise())


def test_persisted_result_reader_has_no_private_state_or_symlink_escape(controlled_board, tmp_path):
    manager, _, _ = controlled_board
    root = manager.agents["dexter"]
    result_dir = root.local / ".dexter" / "tool-results"
    result_dir.mkdir(parents=True)
    result_file = result_dir / "real-call.txt"
    result_file.write_text("Actual tool response " * 100)
    root.state_path.write_text("PRIVATE STATE")
    listed = manager.read_tool_result("dexter")
    assert listed["files"] == [".dexter/tool-results/real-call.txt"]
    page = manager.read_tool_result("dexter", str(result_file), limit=20)
    assert page["content"] == "Actual tool response "[:20] and page["next_offset"] == 20
    assert manager.read_tool_result("dexter", page["path"], offset=20, limit=21)["content"] == result_file.read_text()[20:41]
    for path in [str(root.state_path), "../agents/secret/state.json", ".dexter/tool-results/../scratchpad/private.json"]:
        with pytest.raises(ValueError, match="Only persisted"):
            manager.read_tool_result("dexter", path)
    outside = tmp_path / "outside.txt"
    outside.write_text("OTHER FUND")
    link = result_dir / "escape.txt"
    link.symlink_to(outside)
    with pytest.raises(ValueError, match="Only persisted"):
        manager.read_tool_result("dexter", str(link))
    with pytest.raises(ValueError, match="not found"):
        manager.read_tool_result("dexter", ".dexter/tool-results/invented.txt")


def test_full_tree_graph_reports_objectives_and_explicit_blocker(controlled_board):
    manager, processes, _ = controlled_board

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
            root = manager.agents["dexter"]
            await root.start("Supervise the full tree")
            await until(lambda: "dexter" in processes)
            child = await manager.create("dexter", "Research", "Find dated evidence")
            await until(lambda: child.id in processes)
            result = await client.post("/api/internal/agents/progress", headers=auth(manager, child.id), json={"phase": "Research", "status": "blocked", "blocker": "Provider credential is unavailable", "artifacts": ["memo.md"]})
            assert result.status_code == 200
            graph = (await client.get("/api/internal/agents", headers=auth(manager, "dexter"))).json()["agents"]
            node = next(a for a in graph if a["id"] == child.id)
            assert node["parentId"] == "dexter" and node["objective"] == "Find dated evidence"
            assert node["workflow"]["blocker"] == "Provider credential is unavailable"
            processes[child.id].finish()
            await child.task
            assert child.snapshot()["lifecycle"] == "blocked"
            assert child.state["progress"]["complete"] is False
            await manager.close()

    asyncio.run(exercise())


def test_roster_over_sixteen_creates_executor_queues_and_cancels(controlled_board):
    manager, processes, peaks = controlled_board

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            root = manager.agents["dexter"]
            await root.start("Coordinate a large existing fund roster")
            await until(lambda: "dexter" in processes)
            created = []
            for index in range(20):
                child = await manager.create(
                    "dexter", f"Specialist {index}", "Inspect and prepare authorized work",
                    "executor" if index == 19 else "research",
                )
                created.append(child)
            await until(lambda: len(processes) == 4)
            assert len(manager.agents) == 21
            assert created[-1].role == "executor"
            assert created[-1].snapshot()["queued"]
            assert max(peaks) == 4
            assert sum(a.holds_slot for a in manager.agents.values()) == 4
            assert sum(a.snapshot()["queued"] for a in created) == 17
            catalog = (await client.get("/api/agent-roles")).json()
            assert catalog["max_agents"] is None
            assert catalog["max_active_runs"] == 4
            await asyncio.wait_for(manager.stop("dexter"), timeout=1)
            assert all(a.state["status"] == "stopped" for a in manager.agents.values())
            assert all(not a.holds_slot for a in manager.agents.values())
            assert manager.slots._value == 4
            reloaded = runtime.AgentManager(root=manager.root)
            assert len(reloaded.agents) == 21
            assert reloaded.agents[created[-1].id].role == "executor"

    asyncio.run(exercise())
