import json

from fastapi.testclient import TestClient

from app.main import app


def write_cursor(log_path, turn):
    cursor_path = log_path.with_suffix(log_path.suffix + ".cursor")
    cursor_path.write_text(str(turn), encoding="utf-8")


def test_set_budget(tmp_path):
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
                    "factions": {"royal": 50, "bureaucrats": 50, "warlords": 50, "merchants": 50, "clans": 50},
                    "actors": {"Chancellor": {"loyalty": 60, "ambition": 40, "influence": 50}},
                },
                "event": None,
            }
        )
    with log_path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    write_cursor(log_path, 5)

    client = TestClient(app)
    response = client.post(
        "/api/set_budget",
        json={
            "scenario": "baseline",
            "seed": 1,
            "turns": 5,
            "budget": {"security": 40, "economy": 40, "intel": 20},
            "log_path": str(log_path),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"]["budget"]["security"] == 40
    assert payload["state"]["budget"]["economy"] == 40
    assert payload["state"]["budget"]["intel"] == 20

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert any(
        json.loads(line).get("event", {}).get("id") == "budget_allocation"
        for line in lines
    )


def test_set_budget_requires_turn_boundary(tmp_path):
    log_path = tmp_path / "run.jsonl"
    entry = {
        "state": {
            "turn": 1,
            "stability": 50,
            "legitimacy": 50,
            "treasury": 50,
            "food": 50,
            "public_support": 50,
            "revolt_risk": 10,
            "factions": {"royal": 50, "bureaucrats": 50, "warlords": 50, "merchants": 50, "clans": 50},
            "actors": {"Chancellor": {"loyalty": 60, "ambition": 40, "influence": 50}},
        },
        "event": None,
    }
    log_path.write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")
    write_cursor(log_path, 1)

    client = TestClient(app)
    response = client.post(
        "/api/set_budget",
        json={
            "scenario": "baseline",
            "seed": 1,
            "turns": 1,
            "budget": {"security": 40, "economy": 40, "intel": 20},
            "log_path": str(log_path),
        },
    )
    assert response.status_code == 400
