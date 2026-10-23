"""The live feed in process (no Event Hubs): events flow to viewers and a VAR check starts the desk."""

import asyncio

from ruling.api import live
from ruling.api.checks import Checks
from ruling.api.live import LiveFeed, minute_of
from ruling.api.serialize import event_row
from ruling.api.store import MemoryStore
from ruling.sim import events as ev
from ruling.sim.cli import match_for_seed


class RecordingChecks(Checks):
    """Records the checks the feed starts instead of calling the model."""

    def __init__(self):
        super().__init__(MemoryStore())
        self.started = []

    def start(self, packet, auto_approve=False, drill=None):
        self.started.append(packet.incident_id)

        class Session:
            id = "test"
        return Session()


async def _collect(feed, until, timeout=60):
    seen = []

    async def watch():
        async for event in feed.follow(heartbeat=1.0):
            if event is not None:
                seen.append(event)
                if event["type"] == until:
                    return

    viewer = asyncio.create_task(watch())
    await asyncio.sleep(0)
    return viewer, seen


def test_minute_of_counts_the_second_half_from_45():
    e = ev.Event("m", 0, 2, 125.0, "AGA", None, ev.PASS, ev.SUCCESS, 0, 0, 0, 0)
    assert minute_of(e) == 47


def test_a_replayed_var_check_starts_a_desk_check():
    match = match_for_seed(5001)
    first_check = next(e for e in match.events if e.type == ev.VAR_CHECK)
    checks = RecordingChecks()

    async def run():
        feed = LiveFeed(checks)
        viewer, seen = await _collect(feed, "check_started")
        feed.play(match, speed=600, from_minute=minute_of(first_check))
        await asyncio.wait_for(viewer, timeout=60)
        feed.stop()
        return seen

    seen = asyncio.run(run())
    assert seen[-1]["type"] == "check_started" and checks.started
    assert any(e["type"] == "match_event" and e["event"]["type"] == ev.VAR_CHECK for e in seen)
    incident = next(i for i in match.incidents if i.id == checks.started[0])
    assert incident.event_index < first_check.index


def test_duplicates_and_leftovers_never_start_a_second_check():
    match = match_for_seed(5001)
    var_check = next(e for e in match.events if e.type == ev.VAR_CHECK)
    checks = RecordingChecks()
    feed = LiveFeed(checks)
    feed._matches[match.seed] = match
    feed.state["run"] = "now"

    def payload(run):
        return {"type": "match_event", "seed": match.seed, "match_id": match.id, "run": run, "score": [0, 0],
                "event": event_row(var_check)}

    feed._deliver(payload("now"))
    feed._deliver(payload("now"))  # Event Hubs delivers at least once: the same event again
    feed._deliver(payload("earlier"))  # still in the hub from an earlier replay
    assert len(checks.started) == 1 and feed.state["dropped"] == 2


def test_a_frozen_feed_is_called_stale_and_then_resumes(monkeypatch):
    monkeypatch.setattr(live, "STALE_AFTER", 0.5)
    monkeypatch.setattr(live, "WATCH_EVERY", 0.1)
    match = match_for_seed(5001)

    async def run():
        feed = LiveFeed(RecordingChecks())
        viewer, seen = await _collect(feed, "feed_resumed")
        feed.play(match, speed=600, from_minute=5)
        await asyncio.sleep(0.2)
        feed.stall(1.5)
        await asyncio.wait_for(viewer, timeout=30)
        feed.stop()
        return seen, feed.state

    seen, state = asyncio.run(run())
    kinds = [e["type"] for e in seen if e["type"] != "match_event"]
    assert kinds == ["feed_drill", "feed_stale", "feed_resumed"]
    assert seen[-1]["gap"] >= 1.0 and not state["stale"]


def test_replaying_mid_match_keeps_the_feed_running():
    match = match_for_seed(5001)

    async def run():
        feed = LiveFeed(RecordingChecks())
        feed.play(match, speed=60)
        await asyncio.sleep(0.1)
        feed.play(match, speed=60, from_minute=30)
        await asyncio.sleep(0.3)  # the first replay's clean-up has run by now
        state, kinds = dict(feed.state), [e["type"] for e in feed.log]
        feed.stop()
        return state, kinds

    state, kinds = asyncio.run(run())
    assert state["running"] and "feed_ended" not in kinds
