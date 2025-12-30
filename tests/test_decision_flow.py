import json

from fastapi.testclient import TestClient

from app.main import app


def write_cursor(log_path, turn):
    cursor_path = log_path.with_suffix(log_path.suffix + ".cursor")
    cursor_path.write_text(str(turn), encoding="utf-8")


def test_decision_flow_riot_response(tmp_path):
    log_path = tmp_path / "run.jsonl"
    entries = [
        {
            "state": {
                "turn": 1,
                "stability": 55,
                "legitimacy": 50,
                "treasury": 40,
                "food": 60,
                "public_support": 45,
                "revolt_risk": 45,
                "factions": {"royal": 50, "bureaucrats": 50, "warlords": 50, "merchants": 50, "clans": 50},
                "actors": {"Chancellor": {"loyalty": 60, "ambition": 40, "influence": 50}},
            },
            "event": None,
        }
    ]
    with log_path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    write_cursor(log_path, 1)

    client = TestClient(app)
    pending = client.post(
        "/api/pending_decision",
        json={
            "scenario": "baseline",
            "seed": 1,
            "turns": 1,
            "tail": 20,
            "log_path": str(log_path),
        },
    )
    assert pending.status_code == 200
    pending_payload = pending.json()
    assert pending_payload["pending"] is True
    assert pending_payload["decision"]["id"] == "riot_response"

    decided = client.post(
        "/api/decide",
        json={
            "scenario": "baseline",
            "seed": 1,
            "turns": 1,
            "decision_id": "riot_response",
            "choice": "hardline",
            "log_path": str(log_path),
        },
    )
    assert decided.status_code == 200
    payload = decided.json()
    for key in ["state", "factions", "actors", "events", "error"]:
        assert key in payload

    pending_after = client.post(
        "/api/pending_decision",
        json={
            "scenario": "baseline",
            "seed": 1,
            "turns": 1,
            "tail": 20,
            "log_path": str(log_path),
        },
    )
    assert pending_after.status_code == 200
    assert pending_after.json()["pending"] is False

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert any(
        json.loads(line).get("event", {}).get("id") == "riot_response"
        for line in lines
    )


def test_decision_flow_scandal_management(tmp_path):
    log_path = tmp_path / "run.jsonl"
    entries = [
        {
            "state": {
                "turn": 1,
                "stability": 55,
                "legitimacy": 50,
                "treasury": 40,
                "food": 60,
                "public_support": 45,
                "revolt_risk": 10,
                "factions": {"royal": 50, "bureaucrats": 50, "warlords": 50, "merchants": 50, "clans": 50},
                "actors": {"Spymaster": {"loyalty": 60, "ambition": 40, "influence": 50}},
            },
            "event": {
                "id": "spy-whisper",
                "title": "첩보의 속삭임",
                "actor": "Spymaster",
                "cause_tags": ["intel"],
                "severity": 2,
                "stakeholders": ["Spymaster"],
            },
        }
    ]
    with log_path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    write_cursor(log_path, 1)

    client = TestClient(app)
    pending = client.post(
        "/api/pending_decision",
        json={
            "scenario": "baseline",
            "seed": 1,
            "turns": 1,
            "tail": 20,
            "log_path": str(log_path),
        },
    )
    assert pending.status_code == 200
    pending_payload = pending.json()
    assert pending_payload["pending"] is True
    assert pending_payload["decision"]["id"] == "scandal_management"

    decided = client.post(
        "/api/decide",
        json={
            "scenario": "baseline",
            "seed": 1,
            "turns": 1,
            "decision_id": "scandal_management",
            "choice": "conceal",
            "log_path": str(log_path),
        },
    )
    assert decided.status_code == 200
    payload = decided.json()
    assert payload["error"] is None
