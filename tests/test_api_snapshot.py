import json

from fastapi.testclient import TestClient

from app.main import app


def test_api_snapshot_fields(tmp_path):
    log_path = tmp_path / "sample.jsonl"
    entries = [
        {
            "state": {
                "turn": 1,
                "stability": 55,
                "legitimacy": 50,
                "treasury": 40,
                "food": 60,
                "public_support": 45,
                "revolt_risk": 20,
                "factions": {"royal": 50, "bureaucrats": 50, "warlords": 50, "merchants": 50, "clans": 50},
                "actors": {"Chancellor": {"loyalty": 60, "ambition": 40, "influence": 50}},
            },
            "event": {
                "id": "minor-riot",
                "title": "소규모 폭동",
                "actor": "Chancellor",
                "cause_tags": ["riot", "security"],
                "severity": 2,
                "stakeholders": ["Chancellor"],
            },
        },
        {
            "state": {
                "turn": 2,
                "stability": 54,
                "legitimacy": 49,
                "treasury": 38,
                "food": 58,
                "public_support": 44,
                "revolt_risk": 22,
                "factions": {"royal": 49, "bureaucrats": 48, "warlords": 47, "merchants": 52, "clans": 51},
                "actors": {"Chancellor": {"loyalty": 61, "ambition": 41, "influence": 49}},
            },
            "event": None,
        },
    ]
    with log_path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    client = TestClient(app)
    response = client.post(
        "/api/snapshot",
        json={
            "scenario": "baseline",
            "seed": 1,
            "turns": 2,
            "tail": 10,
            "log_path": str(log_path),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    for key in ["state", "factions", "actors", "events"]:
        assert key in payload

    for event in payload["events"]:
        for field in [
            "turn",
            "id",
            "title",
            "actor",
            "severity",
            "cause_tags",
            "stakeholders",
        ]:
            assert field in event
