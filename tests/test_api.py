import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from ruling.api.app import app
from ruling.desk.packet import HIDDEN


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    body = client.get("/api/health").json()
    assert body["ok"] is True


def test_demo_matches_are_the_development_seeds(client):
    matches = client.get("/api/matches").json()
    assert len(matches) == 20
    assert all(5001 <= m["seed"] <= 5020 for m in matches)
    assert matches[0]["home"]["name"] and matches[0]["incidents"] > 0


def test_held_out_matches_are_never_served(client):
    assert client.get("/api/matches/9001").status_code == 404


def test_match_detail_lists_incidents_without_ground_truth(client):
    detail = client.get("/api/matches/5001").json()
    assert detail["events"] and detail["players"]
    text = json.dumps(detail["incidents"])
    for field in HIDDEN:
        assert f'"{field}"' not in text


def test_frames_place_every_player(client):
    frame = client.get("/api/matches/5001/frames/100").json()
    assert len(frame["players"]) >= 20 and len(frame["ball"]) == 2
    assert client.get("/api/matches/5001/frames/999999").status_code == 404


def test_incident_detail_is_the_packet_the_desk_sees(client):
    incident_id = client.get("/api/matches/5001").json()["incidents"][0]["id"]
    detail = client.get(f"/api/incidents/{incident_id}").json()
    assert detail["packet"]["incident_id"] == incident_id
    text = json.dumps(detail)
    for field in HIDDEN:
        assert f'"{field}"' not in text


def test_unknown_checks_and_incidents_are_404(client):
    assert client.get("/api/checks/nope").status_code == 404
    assert client.get("/api/checks/nope/events").status_code == 404
    assert client.post("/api/checks/nope/decision", json={"decision": "approve"}).status_code == 404
    assert client.post("/api/checks/nope/translate", json={"language": "es"}).status_code == 404
    assert client.post("/api/checks", json={"incident_id": "AGA-BRC-5001:1:offside"}).status_code == 404


def test_a_drill_check_holds_and_is_never_stored(client):
    assert [d["id"] for d in client.get("/api/drills").json()] == [
        "tracking_dropout", "player_missing", "model_timeout", "wrong_draft"]
    incident_id = client.get("/api/matches/5003").json()["incidents"][0]["id"]
    assert client.post("/api/checks", json={"incident_id": incident_id, "drill": "nope"}).status_code == 422
    started = client.post("/api/checks", json={"incident_id": incident_id, "drill": "tracking_dropout"}).json()
    events = client.get(f"/api/checks/{started['check_id']}/events").text  # streams until the check ends
    assert '"type": "final"' in events
    case = client.get(f"/api/checks/{started['check_id']}").json()["case"]
    assert case["status"] == "held" and case["drill"] == "tracking_dropout"
    assert case["holding"].startswith("VAR check in progress") and case["verdict"] is None
    assert all(c["incident_id"] != incident_id for c in client.get("/api/cases").json())


def test_finished_checks_are_served_from_the_store_after_a_restart(client):
    held = {"check_id": "c0ffee000001", "incident_id": "MLA-HFW-5001:1:offside", "match_id": "MLA-HFW-5001",
            "status": "held", "holding": "VAR check in progress.", "drafts": None}
    asyncio.run(app.state.checks.store.save(held))  # the session itself is gone, as after a redeploy
    body = client.get("/api/checks/c0ffee000001").json()
    assert body["done"] and not body["awaiting_approval"] and body["case"]["status"] == "held"
    events = client.get("/api/checks/c0ffee000001/events").text
    assert json.loads(events.removeprefix("data: "))["type"] == "final"
    assert client.post("/api/checks/c0ffee000001/decision", json={"decision": "approve"}).status_code == 409
    assert client.post("/api/checks/c0ffee000001/translate", json={"language": "es"}).status_code == 409
    assert any(c["check_id"] == "c0ffee000001" for c in client.get("/api/cases?match_id=MLA-HFW-5001").json())
