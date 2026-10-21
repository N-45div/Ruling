"""The live feed in process (no Event Hubs): events flow to viewers and a VAR check starts the desk."""

import asyncio

from ruling.api.checks import Checks
from ruling.api.live import LiveFeed, minute_of
from ruling.api.store import MemoryStore
from ruling.sim import events as ev
from ruling.sim.cli import match_for_seed


def test_minute_of_counts_the_second_half_from_45():
    e = ev.Event("m", 0, 2, 125.0, "AGA", None, ev.PASS, ev.SUCCESS, 0, 0, 0, 0)
    assert minute_of(e) == 47


def test_a_replayed_var_check_starts_a_desk_check():
    match = match_for_seed(5001)
    first_check = next(e for e in match.events if e.type == ev.VAR_CHECK)
    started = []

    class RecordingChecks(Checks):
        def start(self, packet, auto_approve=False):  # record instead of calling the model
            started.append(packet.incident_id)

            class Session:
                id = "test"
            return Session()

    async def run():
        feed = LiveFeed(RecordingChecks(MemoryStore()))
        seen = []

        async def watch():
            async for event in feed.follow(heartbeat=1.0):
                if event is None:
                    continue
                seen.append(event)
                if event["type"] == "check_started":
                    return

        viewer = asyncio.create_task(watch())
        await asyncio.sleep(0)
        feed.play(match, speed=600, from_minute=minute_of(first_check))
        await asyncio.wait_for(viewer, timeout=60)
        feed.stop()
        return seen

    seen = asyncio.run(run())
    assert seen[-1]["type"] == "check_started" and started
    assert any(e["type"] == "match_event" and e["event"]["type"] == ev.VAR_CHECK for e in seen)
    incident = next(i for i in match.incidents if i.id == started[0])
    assert incident.event_index < first_check.index
