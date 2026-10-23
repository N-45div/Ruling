"""Live VAR checks: run the desk workflow in the background and stream every step.

A check pauses at human approval and waits for a decision from the desk UI (or approves
itself when asked to). Any number of viewers can follow one check; a late viewer gets
the steps so far first. Finished case files go to the store.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict

from ..desk.packet import CheckPacket
from ..desk.workflow import APPROVE, CaseFile, Step, build, listen, run_within, unlisten
from .serialize import case_dict
from .store import Store


class CheckSession:
    def __init__(self, packet: CheckPacket, store: Store, drill: str | None = None):
        self.id = uuid.uuid4().hex[:12]
        self.packet = packet
        self.store = store
        self.drill = drill
        self.workflow = build()
        self.events: list[dict] = []
        self.case: CaseFile | None = None
        self.request_id: str | None = None
        self.done = False
        self._viewers: list[asyncio.Queue] = []

    # ---- events ------------------------------------------------------------------------

    def _push(self, kind: str, **data) -> None:
        event = {"type": kind, "check_id": self.id, **data}
        self.events.append(event)
        for queue in self._viewers:
            queue.put_nowait(event)

    def _on_step(self, case: CaseFile, step: Step) -> None:
        self.case = case
        self._push("step", step=asdict(step), case=case_dict(case))

    async def follow(self, heartbeat: float = 15.0):
        """Every event so far, then new ones as they happen; None is a heartbeat."""
        queue: asyncio.Queue = asyncio.Queue()
        # No await between the snapshot and registering, so nothing is missed or repeated.
        backlog = list(self.events)
        self._viewers.append(queue)
        try:
            for event in backlog:
                yield event
            if self.done:
                return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=heartbeat)
                except asyncio.TimeoutError:
                    yield None
                    continue
                yield event
                if event["type"] in ("final", "error"):
                    return
        finally:
            self._viewers.remove(queue)

    # ---- running -----------------------------------------------------------------------

    async def run(self, auto_approve: bool = False) -> None:
        self._push("started", incident_id=self.packet.incident_id)
        try:
            listen(self.id, self._on_step)
            result = await run_within(self.workflow, CaseFile(self.packet, listener=self.id, drill=self.drill))
            if isinstance(result, CaseFile):  # held at the deadline
                await self._finish(result)
            else:
                await self._settle(result, auto_approve)
        except Exception as exc:  # the desk must never leave a viewer waiting
            self.done = True
            unlisten(self.id)
            self._push("error", message=f"{type(exc).__name__}: {exc}"[:300])

    async def decide(self, decision: str) -> None:
        if not self.request_id:
            raise ValueError("this check is not waiting for approval")
        request_id, self.request_id = self.request_id, None
        result = await self.workflow.run(responses={request_id: decision})
        await self._settle(result, auto_approve=False)

    async def _finish(self, case: CaseFile) -> None:
        self.case, self.done = case, True
        unlisten(self.id)
        if not self.drill:  # drills never become case files
            await self.store.save({"check_id": self.id, **case_dict(case)})
        self._push("final", case=case_dict(case))

    async def _settle(self, result, auto_approve: bool) -> None:
        outputs = result.get_outputs()
        if outputs:
            await self._finish(outputs[-1])
            return
        self.request_id = result.get_request_info_events()[0].request_id
        self._push("awaiting_approval", case=case_dict(self.case))
        if auto_approve:
            await self.decide(APPROVE)


class Checks:
    def __init__(self, store: Store):
        self.store = store
        self.sessions: dict[str, CheckSession] = {}
        self._tasks: set[asyncio.Task] = set()

    def start(self, packet: CheckPacket, auto_approve: bool = False, drill: str | None = None) -> CheckSession:
        session = CheckSession(packet, self.store, drill)
        self.sessions[session.id] = session
        task = asyncio.create_task(session.run(auto_approve))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return session

    def decide(self, session: CheckSession, decision: str) -> None:
        task = asyncio.create_task(session.decide(decision))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
