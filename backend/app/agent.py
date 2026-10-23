"""One local Dexter process, with persistent conversation and workspace files."""

import asyncio
import json
import os
import platform
import secrets
import shutil
import signal
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values

from backend.app.models import choices, select_model
from backend.app.roles import PROFILES, allow_child

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / ".local/agent"
DEXTER_SOURCE = Path(os.environ.get("DEXTER_SOURCE_DIR", ROOT / ".local/dexter"))


def now():
    return datetime.now(UTC).isoformat()


def environment():
    env = os.environ.copy()
    env.update(
        {k: v for k, v in dotenv_values(ROOT / ".env.local").items() if v is not None}
    )
    # Hosted workers use the instance role. Local workers use the workshop profile.
    if env.get("AWS_CREDENTIAL_MODE") == "role":
        for key in (
            "AWS_PROFILE",
            "AWS_DEFAULT_PROFILE",
            "AWS_SHARED_CREDENTIALS_FILE",
            "AWS_CONFIG_FILE",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
        ):
            env.pop(key, None)
        env["LANGSMITH_TRACING"] = "false"
        return env
    # Only the dedicated workshop files, not personal AWS profiles.
    env.update(
        AWS_SHARED_CREDENTIALS_FILE=os.getenv(
            "AWS_SHARED_CREDENTIALS_FILE",
            str(Path.home() / ".aws/aws-hackathon-2026.credentials"),
        ),
        AWS_CONFIG_FILE=os.getenv(
            "AWS_CONFIG_FILE", str(Path.home() / ".aws/aws-hackathon-2026.config")
        ),
        AWS_PROFILE="aws-hackathon-2026",
        AWS_REGION=env.get("AWS_REGION", "us-east-1"),
        LANGSMITH_TRACING="false",
    )
    for key in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AWS_ROLE_ARN",
    ):
        env.pop(key, None)
    return env


def bun_binary():
    system = {"Darwin": "darwin", "Linux": "linux"}[platform.system()]
    arch = "aarch64" if platform.machine() in {"arm64", "aarch64"} else "x64"
    for prefix in (ROOT, ROOT / "backend/worker"):
        candidate = prefix / f"node_modules/@oven/bun-{system}-{arch}/bin/bun"
        if candidate.exists():
            return str(candidate)
    if binary := shutil.which("bun"):
        return binary
    raise RuntimeError("Bun is missing. Rebuild the local sandbox.")


class LocalAgent:
    def __init__(
        self,
        manager,
        agent_id="dexter",
        name="Dexter",
        parent_id=None,
        role=None,
        model=None,
    ):
        self.manager = manager
        self.id = agent_id
        self.name = name
        self.parent_id = parent_id
        self.role = role or ("orchestrator" if agent_id == "dexter" else "research")
        if self.role not in PROFILES:
            raise ValueError("Unknown agent role")
        self.local = (
            manager.root / "agent"
            if agent_id == "dexter"
            else manager.root / "agents" / agent_id
        )
        self.workspace = manager.root / "workspace"
        self.state_path = self.local / "state.json"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.local.mkdir(parents=True, exist_ok=True)
        self.local.chmod(0o700)
        self.migrate_workspace()
        self.state = (
            json.loads(self.state_path.read_text())
            if self.state_path.exists()
            else {"messages": [], "activity": []}
        )
        # Older releases did not persist a choice. Migrate their Luna default.
        saved_model = self.state.get("model")
        if saved_model == "us.openai.gpt-5.6-luna":
            saved_model = None
        self.model = select_model(
            self.role,
            requested=model,
            inherited=saved_model or environment().get("MAIN_AGENT_MODEL"),
        )
        self.state["model"] = self.model
        if self.state.get("status") == "running":
            self.state["status"] = "stopped"
        self.state.setdefault("status", "idle")
        self.process = None
        self.task = None
        self.lock = asyncio.Lock()
        self.cancelled = False
        self.holds_slot = False
        self.pending_delegations = 0

    def migrate_workspace(self):
        legacy = self.local / "workspace"
        if not legacy.exists():
            return
        for source in legacy.rglob("*"):
            if (
                not source.is_file()
                or source.is_symlink()
                or ".dexter" in source.relative_to(legacy).parts
            ):
                continue
            target = self.workspace / source.relative_to(legacy)
            if target.exists():
                if target.read_bytes() == source.read_bytes():
                    continue
                target = target.with_name(f"{self.id}-{target.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.move(str(source), str(target))

    def files(self):
        return sorted(
            str(p.relative_to(self.workspace))
            for p in self.workspace.rglob("*")
            if p.is_file()
            and not p.is_symlink()
            and ".dexter" not in p.relative_to(self.workspace).parts
        )[:200]

    def snapshot(self):
        return {
            "id": self.id,
            "parentId": self.parent_id,
            "role": self.role,
            "waitingForAgents": self.pending_delegations > 0,
            "queued": self.state["status"] == "running"
            and not self.holds_slot
            and not self.pending_delegations,
            "tools": PROFILES[self.role]["tools"],
            "name": self.name,
            "status": self.state["status"],
            "model": self.model,
            "modelChoices": choices(self.role),
            "messages": self.state["messages"],
            "activity": self.state["activity"],
            "files": self.files(),
            "workspace": str(self.workspace.relative_to(ROOT))
            if self.workspace.is_relative_to(ROOT)
            else "workspace",
        }

    def publish(self):
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state))
        temporary.replace(self.state_path)
        self.manager.publish()

    def activity(self, label, detail="", kind="info"):
        self.state["activity"].append(
            {
                "id": uuid4().hex,
                "time": now(),
                "label": label,
                "detail": detail[:12000],
                "kind": kind,
            }
        )
        self.state["activity"] = self.state["activity"][-100:]

    async def set_model(self, model):
        async with self.lock:
            if self.task and not self.task.done():
                raise ValueError("Stop the agent before changing its model")
            self.model = select_model(self.role, requested=model)
            self.state["model"] = self.model
            self.activity("Model selected", self.model)
            self.publish()

    async def start(self, prompt, source="You"):
        async with self.lock:
            if self.task and not self.task.done():
                raise ValueError(
                    f"{self.name} is already running. Stop it before sending another message."
                )
            if self.manager.paused:
                raise ValueError(
                    "This fund is paused. Resume it before starting agents."
                )
            bun_binary()
            if not (DEXTER_SOURCE / ".revision").exists():
                raise RuntimeError("Dexter source is missing. Run npm run setup:agent.")
            if self.role == "backtester":
                from backend.app.desk import desk_for

                record = desk_for(self.manager).strategy(
                    self.state.get("strategy_id", "")
                )
                prompt = (
                    "Call run_backtest and report its exact result. Frozen numeric strategy: "
                    + json.dumps(
                        {
                            "strategy_id": record["id"],
                            "weights": record["weights"],
                            "cutoff": record["cutoff"],
                            "end": record["end"],
                        }
                    )
                )
            history = []
            for message in self.state["messages"]:
                if message["role"] == "user":
                    history.append({"query": message["text"], "answer": ""})
                elif history and message["role"] == "assistant":
                    history[-1]["answer"] = message["text"]
            history = (
                [turn for turn in history if turn["answer"]][-8:]
                if self.role != "backtester"
                else []
            )
            self.state["messages"].append(
                {"id": uuid4().hex, "role": "user", "text": prompt, "source": source}
            )
            self.state["status"] = "running"
            self.cancelled = False
            self.activity("Run started")
            self.publish()
            self.task = asyncio.create_task(self.run(prompt, history))

    async def run(self, prompt, history):
        completed = False
        try:
            if self.manager.slots.locked():
                self.activity("Queued for a worker slot")
                self.publish()
            await self.manager.slots.acquire()
            self.holds_slot = True
            if self.cancelled:
                self.state["status"] = "stopped"
                return
            self.process = await asyncio.create_subprocess_exec(
                bun_binary(),
                "--tsconfig-override",
                str(DEXTER_SOURCE / "tsconfig.json"),
                str(ROOT / "backend/worker/run.ts"),
                cwd=self.workspace,
                env={
                    **environment(),
                    "AGENT_CONTROL_TOKEN": self.manager.token,
                    "LOCAL_AGENT_ID": self.id,
                    "LOCAL_AGENT_NAME": "Historical evaluator"
                    if self.role == "backtester"
                    else self.name,
                    "LOCAL_AGENT_ROLE": self.role,
                    "LOCAL_AGENT_MODEL": self.model,
                    "AGENT_ALLOWED_TOOLS": json.dumps(PROFILES[self.role]["tools"]),
                    "AGENT_ROLE_INSTRUCTIONS": PROFILES[self.role]["instructions"],
                    "DEXTER_STATE_DIR": str(self.local / ".dexter"),
                },
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
                limit=4 * 1024 * 1024,
            )
            if self.cancelled:
                os.killpg(self.process.pid, signal.SIGTERM)
            payload = json.dumps(
                {
                    "prompt": prompt,
                    "history": history,
                    "files": [] if self.role == "backtester" else self.files(),
                    "context": ""
                    if self.role == "backtester"
                    else self.manager.context,
                }
            ).encode()
            self.process.stdin.write(payload)
            await self.process.stdin.drain()
            self.process.stdin.close()
            # Drain stderr concurrently so a verbose dependency cannot block the worker.
            stderr_task = asyncio.create_task(self.process.stderr.read())
            async for line in self.process.stdout:
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                kind = event.get("type")
                if kind == "tool_start":
                    self.activity(
                        event.get("tool", "Tool started"),
                        json.dumps(event.get("args", {})),
                        "tool",
                    )
                elif kind == "tool_end":
                    self.activity(
                        f"{event.get('tool', 'Tool')} completed",
                        event.get("result", ""),
                        "success",
                    )
                elif kind == "tool_error":
                    self.activity(
                        event.get("tool", "Tool failed"),
                        event.get("error", "Tool error"),
                        "error",
                    )
                elif kind == "error":
                    raise RuntimeError(
                        event.get("error") or event.get("message") or "Agent error"
                    )
                elif kind == "done":
                    answer = event.get("answer", "")
                    if answer.startswith("Error:"):
                        raise RuntimeError(answer)
                    if answer.startswith("Reached maximum iterations"):
                        raise RuntimeError(answer)
                    if answer:
                        self.state["messages"].append(
                            {"id": uuid4().hex, "role": "assistant", "text": answer}
                        )
                    self.activity(
                        "Run completed",
                        f"{event.get('iterations', 0)} model turns",
                        "success",
                    )
                    completed = True
                else:
                    continue
                self.publish()
            code = await self.process.wait()
            stderr = (await stderr_task).decode(errors="replace")
            if code and not self.cancelled:
                raise RuntimeError(stderr[-3000:] or "Dexter exited before finishing")
            self.state["status"] = (
                "stopped" if self.cancelled else "idle" if completed else "error"
            )
            if self.cancelled:
                self.activity("Run stopped")
            elif not completed:
                self.activity("Run ended without a result", kind="error")
        except asyncio.CancelledError:
            self.state["status"] = "stopped"
            self.activity("Run stopped")
        except (OSError, RuntimeError, ValueError) as error:
            self.state["status"] = "stopped" if self.cancelled else "error"
            self.activity(
                "Run stopped" if self.cancelled else "Run failed", str(error), "error"
            )
        finally:
            if self.process and self.process.returncode is None:
                os.killpg(self.process.pid, signal.SIGKILL)
                await self.process.wait()
            self.process = None
            if self.holds_slot:
                self.holds_slot = False
                self.manager.slots.release()
            self.publish()

    async def stop(self):
        self.cancelled = True
        if self.process and self.process.returncode is None:
            os.killpg(self.process.pid, signal.SIGTERM)
        if self.task and not self.task.done():
            if self.process is None and not self.holds_slot:
                self.task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(self.task), timeout=3)
            except asyncio.CancelledError:
                self.state["status"] = "stopped"
                self.publish()
            except TimeoutError:
                if self.process and self.process.returncode is None:
                    os.killpg(self.process.pid, signal.SIGKILL)
                await self.task


class AgentManager:
    """Local workers share a workspace and keep separate conversations."""

    def __init__(self, root=None):
        self.root = Path(root) if root else ROOT / ".local"
        self.context = ""
        self.paused = False
        self.token = secrets.token_urlsafe(32)
        self.subscribers = set()
        self.lock = asyncio.Lock()
        self.slots = asyncio.Semaphore(4)
        self.registry = self.root / "agents.json"
        self.layout_file = self.root / "layout.json"
        self.layout = (
            json.loads(self.layout_file.read_text())
            if self.layout_file.exists()
            else {}
        )
        self.agents = {"dexter": LocalAgent(self)}
        if self.registry.exists():
            for item in json.loads(self.registry.read_text()):
                self.agents[item["id"]] = LocalAgent(
                    self, item["id"], item["name"], item["parentId"], item.get("role")
                )

        from backend.app.desk import Desk

        self.desk = Desk(self)

    def snapshot(self):
        return {
            "agents": [a.snapshot() for a in self.agents.values()],
            "positions": self.layout,
            "viewers": len(self.subscribers),
        }

    def publish(self):
        snapshot = self.snapshot()
        for queue in self.subscribers:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(snapshot)

    def ancestors(self, agent_id):
        found = set()
        while agent_id:
            found.add(agent_id)
            agent_id = self.agents[agent_id].parent_id
        return found

    @asynccontextmanager
    async def delegating(self, caller):
        """Yield the parent's active slot while Dexter waits for delegated tools.

        Multiple tool calls from one model turn share one suspended parent. Only
        the final returning request reacquires its slot before the next model call.
        """
        caller.pending_delegations += 1
        if caller.holds_slot:
            caller.holds_slot = False
            self.slots.release()
        caller.publish()
        try:
            yield
        finally:
            caller.pending_delegations -= 1
            if caller.pending_delegations == 0 and self.worker_alive(caller):
                await self.slots.acquire()
                if (
                    self.worker_alive(caller)
                    and caller.pending_delegations == 0
                    and not caller.holds_slot
                ):
                    caller.holds_slot = True
                else:
                    self.slots.release()
            caller.publish()

    @staticmethod
    def worker_alive(agent):
        return (
            not agent.cancelled
            and agent.process is not None
            and agent.process.returncode is None
        )

    async def create(
        self, parent_id, name, task, role="research", strategy_id=None, model=None
    ):
        async with self.lock:
            parent = self.agents[parent_id]
            allow_child(parent, role)
            if parent.role == "backtester":
                bound = parent.state.get("strategy_id")
                if strategy_id not in (None, bound):
                    raise PermissionError(
                        "Blind delegates must evaluate the parent's frozen strategy"
                    )
                strategy_id = bound
            if len(self.agents) >= 16:
                raise ValueError(
                    "This board supports up to sixteen agents; reuse idle specialists."
                )
            if role == "backtester":
                from backend.app.desk import desk_for

                desk = desk_for(self)
                desk.strategy(strategy_id)
                if (
                    desk.state["reviews"].get(strategy_id, {}).get("verdict")
                    != "APPROVE"
                ):
                    raise ValueError(
                        "Create an adversarial reviewer and obtain approval before blind evaluation"
                    )
            child = LocalAgent(
                self,
                uuid4().hex[:12],
                name.strip(),
                parent_id,
                role,
                select_model(role, requested=model, inherited=parent.model),
            )
            if role == "backtester":
                child.state["strategy_id"] = strategy_id
            self.agents[child.id] = child
            try:
                await child.start(task, self.agents[parent_id].name)
            except (ValueError, RuntimeError):
                self.agents.pop(child.id)
                raise
            temporary = self.registry.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(
                    [
                        {
                            "id": a.id,
                            "name": a.name,
                            "parentId": a.parent_id,
                            "role": a.role,
                        }
                        for a in self.agents.values()
                        if a.id != "dexter"
                    ]
                )
            )
            temporary.replace(self.registry)
            self.agents[parent_id].activity(
                "Agent created", f"{child.name}: {task}", "tool"
            )
            self.agents[parent_id].publish()
            return child

    async def result(self, child):
        if child.task:
            try:
                await asyncio.shield(child.task)
            except asyncio.CancelledError:
                if not child.cancelled:
                    raise
        answer = ""
        for message in reversed(child.state["messages"]):
            if message["role"] == "user":
                break
            if message["role"] == "assistant":
                answer = message["text"]
                break
        return {
            "id": child.id,
            "name": child.name,
            "status": child.state["status"],
            "model": child.model,
            "answer": answer,
            "files": child.files(),
        }

    async def stop(self, agent_id):
        descendants = [
            a for a in self.agents.values() if agent_id in self.ancestors(a.id)
        ]
        await asyncio.gather(*(a.stop() for a in reversed(descendants)))

    async def close(self):
        await asyncio.gather(*(a.stop() for a in self.agents.values()))
