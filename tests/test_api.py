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
    assert client.post("/api/checks", json={"incident_id": "AGA-BRC-5001:1:offside"}).status_code == 404
