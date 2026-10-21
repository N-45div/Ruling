"""The live match feed: a match is replayed through Azure Event Hubs, and every VAR check in
it starts the desk on its own.

The producer publishes each match event to the hub, paced by match time at the chosen
speed. The consumer reads the hub and fans events out to every viewer; when a VAR check
arrives it starts a desk check for that incident, which then waits for a person to
approve the messages. Without Event Hubs (on a laptop) the feed is delivered in process.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque

from ..desk.packet import packet_for
from ..sim import events as ev
from .checks import Checks
from .serialize import event_row

MAX_GAP = 3.0  # seconds of real time any single pause may take, so stoppages do not stall a demo


def minute_of(e: ev.Event) -> int:
    return (0 if e.period == 1 else 45) + int(e.second // 60)


class LiveFeed:
    def __init__(self, checks: Checks, namespace: str | None = None, hub: str | None = None):
        self.checks, self.namespace, self.hub = checks, namespace, hub
        self.log: deque[dict] = deque(maxlen=400)
        self.state = {"seed": None, "match_id": None, "speed": None, "running": False, "clock": None,
                      "transport": "event_hubs" if hub else "in_process"}
        self._viewers: list[asyncio.Queue] = []
        self._matches: dict[int, ev.Match] = {}
        self._producer: asyncio.Task | None = None
        self._consumer: asyncio.Task | None = None

    # ---- lifecycle ---------------------------------------------------------------------

    def start_consumer(self) -> None:
        if self.hub and not self._consumer:
            self._consumer = asyncio.create_task(self._consume())

    async def close(self) -> None:
        for task in (self._producer, self._consumer):
            if task:
                task.cancel()

    def play(self, match: ev.Match, speed: float, from_minute: int = 0) -> None:
        if self._producer and not self._producer.done():
            self._producer.cancel()
        start = next((i for i, e in enumerate(match.events) if minute_of(e) >= from_minute), 0)
        self._matches[match.seed] = match
        self.state.update(seed=match.seed, match_id=match.id, speed=speed, running=True)
        self._producer = asyncio.create_task(self._produce(match, speed, start))

    def stop(self) -> None:
        if self._producer:
            self._producer.cancel()
        self.state["running"] = False

    # ---- producing and consuming -------------------------------------------------------

    async def _produce(self, match: ev.Match, speed: float, start: int) -> None:
        producer = None
        if self.hub:
            from azure.eventhub import EventData
            from azure.eventhub.aio import EventHubProducerClient
            from azure.identity.aio import DefaultAzureCredential

            producer = EventHubProducerClient(fully_qualified_namespace=self.namespace, eventhub_name=self.hub,
                                              credential=DefaultAzureCredential())
        goals = {g.index: g.team for g in match.goals()}
        previous = None
        try:
            for e in match.events[start:]:
                if previous is not None:
                    gap = e.second - previous.second if e.period == previous.period else 2.0
                    await asyncio.sleep(max(0.0, min(gap / speed, MAX_GAP)))
                score = [sum(1 for i, t in goals.items() if i <= e.index and t == side)
                         for side in (match.home, match.away)]
                payload = {"type": "match_event", "seed": match.seed, "match_id": match.id, "score": score,
                           "event": event_row(e)}
                if producer:
                    batch = await producer.create_batch(partition_key=match.id)
                    batch.add(EventData(json.dumps(payload)))
                    await producer.send_batch(batch)
                else:
                    self._deliver(payload)
                previous = e
        finally:
            self.state["running"] = False
            if producer:
                await producer.close()
            self._broadcast({"type": "feed_ended", "match_id": match.id})

    async def _consume(self) -> None:
        from azure.eventhub.aio import EventHubConsumerClient
        from azure.identity.aio import DefaultAzureCredential

        client = EventHubConsumerClient(fully_qualified_namespace=self.namespace, eventhub_name=self.hub,
                                        consumer_group="$Default", credential=DefaultAzureCredential())

        async def on_event(partition_context, event):
            if event is not None:
                self._deliver(json.loads(event.body_as_str()))

        async with client:
            await client.receive(on_event=on_event, starting_position="@latest")

    # ---- fan-out -----------------------------------------------------------------------

    def _broadcast(self, payload: dict) -> None:
        self.log.append(payload)
        for queue in self._viewers:
            queue.put_nowait(payload)

    def _deliver(self, payload: dict) -> None:
        self.state["clock"] = payload["event"]["clock"]
        self._broadcast(payload)
        if payload["event"]["type"] == ev.VAR_CHECK:
            self._start_check(payload)

    def _start_check(self, payload: dict) -> None:
        match = self._matches.get(payload["seed"])
        if match is None:
            return
        index = payload["event"]["i"]
        earlier = [i for i in match.incidents if i.event_index < index]
        if not earlier:
            return
        incident = max(earlier, key=lambda i: i.event_index)
        session = self.checks.start(packet_for(match, incident), auto_approve=False)
        self._broadcast({"type": "check_started", "check_id": session.id, "incident_id": incident.id,
                         "category": incident.category, "clock": payload["event"]["clock"],
                         "match_id": match.id})

    async def follow(self, heartbeat: float = 15.0):
        """New feed events as they happen; None is a heartbeat."""
        queue: asyncio.Queue = asyncio.Queue()
        self._viewers.append(queue)
        try:
            while True:
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=heartbeat)
                except asyncio.TimeoutError:
                    yield None
        finally:
            self._viewers.remove(queue)
