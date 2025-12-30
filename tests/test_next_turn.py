import json

from fastapi.testclient import TestClient

from app.main import app


def test_next_turn_advances_cursor(tmp_path):
    log_path = tmp_path / "run.jsonl"
    entries = []
    for turn in range(1, 6):
        entries.append(
            {
                "state": {
                    "turn": turn,
                    "stability": 50,
                    "legitimacy": 50,
                    "treasury": 50,
                    "food": 50,
                    "public_support": 50,
                    "revolt_risk": 10,
                    "factions": {
                        "royal": 50,
                        "bureaucrats": 50,
                        "warlords": 50,
                        "merchants": 50,
                        "clans": 50,
                    },
                    "actors": {"Chancellor": {"loyalty": 60, "ambition": 40, "influence": 50}},
                },
                "event": {
                    "id": f"event-{turn}",
                    "title": f"Event {turn}",
                    "actor": "Chancellor",
                    "cause_tags": ["riot"],
                    "severity": 2,
                    "stakeholders": ["Chancellor"],
                },
            }
        )
    with log_path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    client = TestClient(app)
    last_turns = []
    for _ in range(3):
        response = client.post(
            "/api/next_turn",
            json={
                "scenario": "baseline",
                "seed": 42,
                "turns": 5,
                "tail": 5,
                "log_path": str(log_path),
            },
        )
        assert response.status_code == 200
        payload = response.json()
        last_turns.append(payload["last_turn"])
        for key in ["state", "factions", "actors", "events", "error"]:
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

    assert last_turns == [1, 2, 3]
