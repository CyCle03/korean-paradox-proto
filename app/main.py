from __future__ import annotations

import json
import os
import tempfile
from collections import deque
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from ai.summarize import resolve_log_path
from ai.summarize import chronicle_summary, explain_summary

app = FastAPI(title="Korean Paradox AI")
VALID_SCENARIOS = {"baseline", "famine", "deficit", "warlord"}


class ExplainRequest(BaseModel):
    scenario: str
    seed: int = 42
    turn_window: int = 20
    log_path: str | None = None


class ChronicleRequest(BaseModel):
    scenario: str
    seed: int = 42
    turns: int = 120
    log_path: str | None = None


class SnapshotRequest(BaseModel):
    scenario: str
    seed: int = 42
    turns: int = 120
    tail: int = 200
    log_path: str | None = None


class RunRequest(BaseModel):
    scenario: str
    seed: int
    turns: int


class PendingDecisionRequest(BaseModel):
    scenario: str
    seed: int = 42
    turns: int = 120
    tail: int = 20
    log_path: str | None = None


class DecisionRequest(BaseModel):
    scenario: str
    seed: int
    turns: int
    decision_id: str
    choice: str
    log_path: str | None = None


class BudgetRequest(BaseModel):
    scenario: str
    seed: int = 42
    turns: int = 120
    budget: dict[str, int]
    log_path: str | None = None


def error_response(status_code: int, message: str):
    return JSONResponse(status_code=status_code, content={"error": message})


def cursor_path_for(path):
    return Path(str(path) + ".cursor")


def read_cursor(path):
    cursor_path = cursor_path_for(path)
    if not cursor_path.exists():
        return None
    try:
        return int(cursor_path.read_text(encoding="utf-8").strip() or 0)
    except ValueError:
        return None


def write_cursor(path, cursor):
    cursor_path = cursor_path_for(path)
    cursor_path.write_text(str(cursor), encoding="utf-8")


def meta_path_for(path):
    return path.with_suffix(path.suffix + ".meta.json")


def max_turn_path_for(path):
    return Path(str(path) + ".maxturn")


def candidate_log_paths(scenario: str, seed: int) -> list[Path]:
    base = Path("logs")
    if scenario == "baseline":
        return [base / f"run_{seed}.jsonl", base / "run.jsonl"]
    return [base / f"run_{scenario}_{seed}.jsonl", base / f"run_{scenario}.jsonl"]


def resolve_run_path(scenario: str, seed: int, turns: int, log_path: str | None) -> Path:
    if log_path:
        return Path(log_path)
    return resolve_log_path(scenario, seed, None)


def read_meta(path):
    meta_path = meta_path_for(path)
    if not meta_path.exists():
        return {"decisions": [], "budget": None}
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"decisions": [], "budget": None}
    data.setdefault("decisions", [])
    data.setdefault("budget", None)
    return data


def write_meta(path, meta):
    meta_path = meta_path_for(path)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def read_max_turn(path, fallback):
    max_path = max_turn_path_for(path)
    if max_path.exists():
        try:
            return int(max_path.read_text(encoding="utf-8").strip())
        except ValueError:
            return fallback
    return fallback


def write_max_turn(path, max_turn):
    max_path = max_turn_path_for(path)
    max_path.write_text(str(max_turn), encoding="utf-8")


def clamp_value(value, minimum=0.0, maximum=100.0):
    return max(minimum, min(maximum, value))


def apply_delta(state, key, delta):
    if key not in state:
        return
    state[key] = round(clamp_value(state[key] + delta), 2)


def apply_decision_modifiers(state, cursor, decisions):
    if cursor is None:
        return
    for decision in decisions:
        turn = decision.get("turn")
        duration = decision.get("duration", 0)
        immediate = decision.get("immediate", {})
        modifier = decision.get("modifier", {})
        delayed = decision.get("delayed")

        if turn == cursor:
            for key, delta in immediate.items():
                apply_delta(state, key, delta)

        if duration and turn is not None and turn < cursor <= turn + duration:
            for key, delta in modifier.items():
                apply_delta(state, key, delta)

        if delayed and turn is not None:
            delay = delayed.get("delay", 0)
            if cursor == turn + delay:
                for key, delta in delayed.get("effects", {}).items():
                    apply_delta(state, key, delta)


def budget_effects(budget):
    security = budget.get("security", 0)
    economy = budget.get("economy", 0)
    intel = budget.get("intel", 0)
    effects = {
        "revolt_risk": -0.04 * security,
        "treasury": (-0.02 * security) + (0.04 * economy),
        "public_support": 0.02 * economy,
    }
    return effects, intel


def apply_budget_modifiers(state, cursor, budget):
    if cursor is None or not budget:
        return 0
    turn = budget.get("turn")
    if turn is None:
        return 0
    if not (turn < cursor <= turn + 5):
        return 0
    effects, intel = budget_effects(budget)
    for key, delta in effects.items():
        apply_delta(state, key, delta)
    return intel


def adjust_event_severity(events, intel):
    if not events:
        return
    reduction = 0
    if intel >= 50:
        reduction = 1
    if reduction == 0:
        return
    for event in events:
        severity = event.get("severity")
        if isinstance(severity, (int, float)):
            event["severity"] = max(1, int(round(severity - reduction)))


def cursor_log_view(path, cursor):
    if cursor is None:
        return None
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl", mode="w", encoding="utf-8")
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                state = record.get("state", {})
                turn = state.get("turn", 0) if isinstance(state, dict) else 0
                if turn <= cursor:
                    temp.write(line)
    finally:
        temp.close()
    return temp.name


def scan_log(path, tail, cursor):
    last_state_overall = None
    last_state_cursor = None
    tail_buffer = deque(maxlen=max(int(tail), 1))
    has_records = False
    last_turn_overall = 0

    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                has_records = True
                state = record.get("state")
                state_turn = None
                if isinstance(state, dict):
                    last_state_overall = state
                    if state.get("turn") is not None:
                        last_turn_overall = state.get("turn")
                    state_turn = state.get("turn")
                elif isinstance(last_state_overall, dict):
                    state_turn = last_state_overall.get("turn")
                if state_turn is None:
                    state_turn = 0

                if cursor is None or state_turn <= cursor:
                    if isinstance(state, dict):
                        last_state_cursor = state
                    elif isinstance(last_state_overall, dict) and state_turn <= cursor:
                        last_state_cursor = last_state_overall
                    tail_buffer.append({"event": record.get("event"), "turn": state_turn})
    except json.JSONDecodeError:
        return None, None, (400, "Invalid JSONL record")

    if not has_records:
        return None, None, (404, "Log is empty")

    return (
        {
            "last_state_overall": last_state_overall,
            "last_state_cursor": last_state_cursor,
            "last_turn_overall": last_turn_overall,
            "tail_buffer": list(tail_buffer),
        },
        None,
        None,
    )


DECISION_SPECS = {
    "riot_response": {
        "title": "폭동 대응",
        "choices": [
            {"id": "hardline", "label": "강경 진압"},
            {"id": "conciliate", "label": "유화 정책"},
        ],
        "duration": 10,
    },
    "scandal_management": {
        "title": "스캔들 관리",
        "choices": [
            {"id": "conceal", "label": "은폐"},
            {"id": "disclose", "label": "공개"},
        ],
        "duration": 10,
    },
}

COOLDOWN_TURNS = 10


def decision_effects(decision_id, choice):
    if decision_id == "riot_response":
        if choice == "hardline":
            return {
                "immediate": {"revolt_risk": -6, "public_support": -3},
                "modifier": {"stability": 1, "legitimacy": -0.5},
                "duration": 10,
            }
        if choice == "conciliate":
            return {
                "immediate": {"revolt_risk": -3, "treasury": -5},
                "modifier": {"public_support": 1},
                "duration": 10,
            }
    if decision_id == "scandal_management":
        if choice == "conceal":
            return {
                "immediate": {"legitimacy": -2, "revolt_risk": -2},
                "modifier": {},
                "duration": 10,
                "delayed": {"delay": 10, "effects": {"public_support": -3}},
            }
        if choice == "disclose":
            return {
                "immediate": {"public_support": 2, "treasury": -3},
                "modifier": {"legitimacy": 0.5},
                "duration": 10,
            }
    return None


def append_event_record(path, state, event):
    record = {"state": state, "event": event}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def ensure_event_objects(path):
    records = []
    needs_rewrite = False
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("event") is None:
                    record["event"] = {}
                    needs_rewrite = True
                records.append(record)
    except json.JSONDecodeError:
        return (400, "Invalid JSONL record")
    if not needs_rewrite:
        return None
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    os.replace(temp_path, path)
    return None


def decision_logged_in_turn(events, decision_id):
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("type") == "decision" and event.get("id") == decision_id:
            return True
    return False


def scan_decision_context(path, cursor, decision_id):
    current_events = []
    last_decision_turn = None
    has_records = False
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                has_records = True
                state = record.get("state")
                if not isinstance(state, dict):
                    continue
                state_turn = state.get("turn")
                if state_turn is None:
                    continue
                if state_turn == cursor:
                    event = record.get("event")
                    if isinstance(event, dict):
                        current_events.append(event)
                if state_turn <= cursor:
                    event = record.get("event") or {}
                    if event.get("type") == "decision" and event.get("id") == decision_id:
                        last_decision_turn = state_turn
    except json.JSONDecodeError:
        return None, None, (400, "Invalid JSONL record")
    if not has_records:
        return None, None, (404, "Log is empty")
    return current_events, last_decision_turn, None


def check_pending_decision(state, current_events, turn, last_riot_turn):
    if not isinstance(state, dict) or turn is None:
        return None
    if decision_logged_in_turn(current_events, "riot_response"):
        return None
    if decision_logged_in_turn(current_events, "scandal_management"):
        return None
    if last_riot_turn is not None and (turn - last_riot_turn) <= COOLDOWN_TURNS:
        return None

    revolt_risk = state.get("revolt_risk", 0)
    security_trigger = False
    for event in current_events:
        tags = event.get("cause_tags", []) or []
        severity = event.get("severity", 0) or 0
        if "security" in tags and severity >= 3:
            security_trigger = True
            break

    if revolt_risk >= 40 or security_trigger:
        return "riot_response"

    for event in current_events:
        tags = event.get("cause_tags", []) or []
        actor = event.get("actor")
        if actor == "Spymaster" and ("intel" in tags or "politics" in tags):
            return "scandal_management"

    return None


def pending_decision_for(path, tail, cursor_override=None):
    cursor = cursor_override if cursor_override is not None else read_cursor(path)
    if cursor is None:
        return None, None, (404, "Cursor not initialized")
    scan, _unused, error = scan_log(path, tail, cursor)
    if error:
        return None, None, error
    state = scan["last_state_cursor"]
    current_events, last_riot_turn, error = scan_decision_context(path, cursor, "riot_response")
    if error:
        return None, None, error
    decision_id = check_pending_decision(state, current_events, cursor, last_riot_turn)
    return decision_id, cursor, None


def build_snapshot(scenario: str, seed: int, turns: int, tail: int, log_path: str | None):
    path = resolve_run_path(scenario, seed, turns, log_path)
    if not path.exists():
        return None, (404, f"Log not found: {path}")

    cursor = read_cursor(path)
    scan, _unused, error = scan_log(path, tail, cursor)
    if error:
        return None, error
    max_turn = read_max_turn(path, scan["last_turn_overall"])

    events = []
    for item in scan["tail_buffer"]:
        event = item.get("event")
        if not event:
            continue
        events.append(
            {
                "turn": item.get("turn") or 0,
                "id": event.get("id"),
                "title": event.get("title"),
                "actor": event.get("actor"),
                "severity": event.get("severity"),
                "cause_tags": event.get("cause_tags", []),
                "stakeholders": event.get("stakeholders", []),
            }
        )

    meta = read_meta(path)
    last_state = scan["last_state_cursor"] if cursor is not None else scan["last_state_overall"]
    if cursor is not None and last_state is None:
        return None, (404, "Cursor out of range")

    if isinstance(last_state, dict):
        effective_state = dict(last_state)
        decisions = meta.get("decisions", [])
        apply_decision_modifiers(effective_state, cursor, decisions)
        intel = apply_budget_modifiers(effective_state, cursor, meta.get("budget"))
        if meta.get("budget"):
            effective_state["budget"] = meta.get("budget")
        last_state = effective_state
        if intel:
            adjust_event_severity(events, intel)

    last_turn = cursor if cursor is not None else (last_state.get("turn", 0) if isinstance(last_state, dict) else 0)
    factions = last_state.get("factions") if isinstance(last_state, dict) else None
    actors = last_state.get("actors") if isinstance(last_state, dict) else None

    return (
        {
            "log_path": str(path),
            "last_turn": last_turn,
            "cursor": cursor,
            "max_turn": max_turn,
            "state": last_state,
            "factions": factions,
            "actors": actors,
            "events": events,
            "error": None,
        },
        None,
    )


@app.post("/ai/explain")
async def explain(request: ExplainRequest):
    if request.scenario not in VALID_SCENARIOS:
        return error_response(400, "Invalid scenario")
    path = resolve_run_path(request.scenario, request.seed, 0, request.log_path)
    if not path.exists():
        return error_response(404, f"Log not found: {path}")
    cursor = read_cursor(path)
    temp_path = cursor_log_view(path, cursor)
    try:
        return explain_summary(
            request.scenario,
            request.seed,
            request.turn_window,
            temp_path or str(path),
        )
    finally:
        if temp_path:
            os.unlink(temp_path)


@app.post("/ai/chronicle")
async def chronicle(request: ChronicleRequest):
    if request.scenario not in VALID_SCENARIOS:
        return error_response(400, "Invalid scenario")
    path = resolve_run_path(request.scenario, request.seed, request.turns, request.log_path)
    if not path.exists():
        return error_response(404, f"Log not found: {path}")
    cursor = read_cursor(path)
    temp_path = cursor_log_view(path, cursor)
    try:
        return chronicle_summary(
            request.scenario,
            request.seed,
            request.turns,
            temp_path or str(path),
        )
    finally:
        if temp_path:
            os.unlink(temp_path)


@app.post("/api/snapshot")
async def snapshot(request: SnapshotRequest):
    if request.scenario not in VALID_SCENARIOS:
        return error_response(400, "Invalid scenario")
    snapshot_data, error = build_snapshot(
        request.scenario, request.seed, request.turns, request.tail, request.log_path
    )
    if error:
        status_code, message = error
        return error_response(status_code, message)
    return snapshot_data


@app.post("/api/run")
async def run_snapshot(request: RunRequest):
    if request.scenario not in VALID_SCENARIOS:
        return error_response(400, "Invalid scenario")
    if request.turns < 2:
        return error_response(400, "turns must be >= 2")
    from scripts.run_sim import run_with_scenario
    from sim.simulate import run_simulation, write_jsonl

    rng = __import__("random").Random(request.seed)
    if request.scenario == "baseline":
        log, _summary = run_simulation(request.turns, rng)
    else:
        log, _summary = run_with_scenario(request.turns, rng, request.scenario)

    out_path = resolve_run_path(request.scenario, request.seed, request.turns, None)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    cursor_path = cursor_path_for(out_path)
    if cursor_path.exists():
        cursor_path.unlink()
    meta_path = meta_path_for(out_path)
    if meta_path.exists():
        meta_path.unlink()
    max_path = max_turn_path_for(out_path)
    if max_path.exists():
        max_path.unlink()
    write_jsonl(out_path, log)
    write_cursor(out_path, 1 if log else 0)
    write_meta(out_path, {"decisions": [], "budget": None})
    write_max_turn(out_path, request.turns)
    snapshot_data, error = build_snapshot(
        request.scenario, request.seed, request.turns, 200, None
    )
    if error:
        status_code, message = error
        return error_response(status_code, message)
    return snapshot_data


@app.post("/api/pending_decision")
async def pending_decision(request: PendingDecisionRequest):
    if request.scenario not in VALID_SCENARIOS:
        return error_response(400, "Invalid scenario")
    path = Path(request.log_path) if request.log_path else resolve_run_path(
        request.scenario, request.seed, request.turns, None
    )
    if not path.exists():
        return error_response(404, f"Log not found: {path}")
    decision_id, cursor, error = pending_decision_for(path, request.tail)
    if error:
        status_code, message = error
        return error_response(status_code, message)
    if not decision_id:
        return {"pending": False, "decision": None, "error": None}
    spec = DECISION_SPECS[decision_id]
    return {
        "pending": True,
        "decision": {
            "id": decision_id,
            "title": spec["title"],
            "choices": spec["choices"],
            "turn": cursor,
        },
        "error": None,
    }


@app.post("/api/decide")
async def decide(request: DecisionRequest):
    if request.scenario not in VALID_SCENARIOS:
        return error_response(400, "Invalid scenario")
    if request.decision_id not in DECISION_SPECS:
        return error_response(400, "Invalid decision_id")
    effects = decision_effects(request.decision_id, request.choice)
    if not effects:
        return error_response(400, "Invalid choice")

    path = resolve_run_path(request.scenario, request.seed, request.turns, request.log_path)
    if not path.exists():
        return error_response(404, f"Log not found: {path}")
    cursor = read_cursor(path)
    if cursor is None:
        return error_response(404, "Cursor not initialized")
    current_events, _last_decision_turn, error = scan_decision_context(
        path, cursor, request.decision_id
    )
    if error:
        status_code, message = error
        return error_response(status_code, message)
    if decision_logged_in_turn(current_events, request.decision_id):
        snapshot_data, error = build_snapshot(
            request.scenario, request.seed, request.turns, 200, str(path)
        )
        if error:
            status_code, message = error
            return error_response(status_code, message)
        return snapshot_data

    decision_id, cursor, error = pending_decision_for(path, 20, cursor_override=cursor)
    if error:
        status_code, message = error
        return error_response(status_code, message)
    if decision_id != request.decision_id:
        return error_response(400, "No pending decision")

    error = ensure_event_objects(path)
    if error:
        status_code, message = error
        return error_response(status_code, message)

    scan, _unused, error = scan_log(path, 5, cursor)
    if error:
        status_code, message = error
        return error_response(status_code, message)
    state = scan["last_state_cursor"]
    if not isinstance(state, dict):
        return error_response(404, "State not found")

    state_snapshot = dict(state)
    state_snapshot["turn"] = cursor
    cause_tags = ["security", "policy"] if request.decision_id == "riot_response" else ["intel", "politics"]
    stakeholders = ["Chancellor", "General"] if request.decision_id == "riot_response" else ["Spymaster", "Chancellor"]
    event = {
        "type": "decision",
        "id": request.decision_id,
        "title": DECISION_SPECS[request.decision_id]["title"],
        "choice": request.choice,
        "actor": "Chancellor",
        "cause_tags": cause_tags,
        "severity": 3,
        "stakeholders": stakeholders,
        "effects": effects,
        "duration": effects.get("duration", 0),
    }
    if request.decision_id == "riot_response":
        event["meta"] = {"cooldown_until": cursor + COOLDOWN_TURNS}
    append_event_record(path, state_snapshot, event)

    meta = read_meta(path)
    meta["decisions"].append(
        {
            "turn": cursor,
            "id": request.decision_id,
            "choice": request.choice,
            "immediate": effects.get("immediate", {}),
            "modifier": effects.get("modifier", {}),
            "duration": effects.get("duration", 0),
            "delayed": effects.get("delayed"),
        }
    )
    write_meta(path, meta)

    snapshot_data, error = build_snapshot(
        request.scenario, request.seed, request.turns, 200, str(path)
    )
    if error:
        status_code, message = error
        return error_response(status_code, message)
    return snapshot_data


@app.post("/api/set_budget")
async def set_budget(request: BudgetRequest):
    if request.scenario not in VALID_SCENARIOS:
        return error_response(400, "Invalid scenario")
    path = resolve_run_path(request.scenario, request.seed, request.turns, request.log_path)
    if not path.exists():
        return error_response(404, f"Log not found: {path}")
    cursor = read_cursor(path)
    if cursor is None:
        return error_response(404, "Cursor not initialized")
    if cursor % 5 != 0:
        return error_response(400, "Budget can be set every 5 turns")

    budget = request.budget or {}
    required_keys = {"security", "economy", "intel"}
    if set(budget.keys()) != required_keys:
        return error_response(400, "Invalid budget keys")
    if sum(budget.values()) != 100:
        return error_response(400, "Budget must sum to 100")

    meta = read_meta(path)
    meta["budget"] = {
        "security": int(budget["security"]),
        "economy": int(budget["economy"]),
        "intel": int(budget["intel"]),
        "turn": cursor,
    }
    write_meta(path, meta)

    error = ensure_event_objects(path)
    if error:
        status_code, message = error
        return error_response(status_code, message)

    scan, _unused, error = scan_log(path, 5, cursor)
    if error:
        status_code, message = error
        return error_response(status_code, message)
    state = scan["last_state_cursor"]
    if not isinstance(state, dict):
        return error_response(404, "State not found")

    event = {
        "type": "budget",
        "id": "budget_allocation",
        "title": "예산 배분",
        "actor": "Chancellor",
        "cause_tags": ["policy", "economy"],
        "severity": 2,
        "stakeholders": ["Treasurer"],
        "allocation": budget,
        "duration": 5,
    }
    append_event_record(path, state, event)

    snapshot_data, error = build_snapshot(
        request.scenario, request.seed, request.turns, 200, request.log_path
    )
    if error:
        status_code, message = error
        return error_response(status_code, message)
    return snapshot_data


@app.post("/api/next_turn")
async def next_turn(request: SnapshotRequest):
    if request.scenario not in VALID_SCENARIOS:
        return error_response(400, "Invalid scenario")
    path = resolve_run_path(request.scenario, request.seed, request.turns, request.log_path)
    if not path.exists():
        return error_response(404, f"Log not found: {path}")

    cursor = read_cursor(path)
    if cursor is None:
        cursor = 0

    pending_id, _cursor, error = pending_decision_for(path, 20, cursor_override=cursor)
    if error:
        status_code, message = error
        return error_response(status_code, message)
    if pending_id:
        return error_response(400, "Decision required")

    scan, _unused, error = scan_log(path, request.tail, None)
    if error:
        status_code, message = error
        return error_response(status_code, message)
    max_turn = read_max_turn(path, scan["last_turn_overall"])
    if cursor >= max_turn:
        return error_response(400, "No more turns available")

    new_cursor = cursor + 1
    write_cursor(path, new_cursor)
    snapshot_data, error = build_snapshot(
        request.scenario, request.seed, request.turns, request.tail, request.log_path
    )
    if error:
        status_code, message = error
        return error_response(status_code, message)
    return snapshot_data


@app.get("/", response_class=HTMLResponse)
async def demo_page():
    return """
<!doctype html>
<html lang="ko">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>게임형 요약 데모</title>
    <style>
      :root { color-scheme: dark; }
      body { font-family: "Space Grotesk", "Segoe UI", sans-serif; background: #0f1116; color: #e9e3d6; margin: 0; }
      .wrap { max-width: 1280px; margin: 0 auto; padding: 28px 24px 48px; }
      header { display: flex; justify-content: space-between; align-items: baseline; gap: 16px; margin-bottom: 20px; }
      h1 { font-size: 1.6rem; margin: 0; letter-spacing: 0.02em; }
      p { margin: 4px 0 0; color: #a6a09a; }
      .grid { display: grid; grid-template-columns: 1fr 2.2fr 1fr; gap: 16px; }
      .panel { background: #171a21; border: 1px solid #2a2f3a; border-radius: 14px; padding: 16px; min-height: 200px; }
      .panel h2 { margin: 0 0 12px; font-size: 1rem; color: #f1c40f; text-transform: uppercase; letter-spacing: 0.12em; }
      form { display: grid; gap: 12px; }
      label { display: grid; gap: 6px; font-size: 0.85rem; color: #cfc6b5; }
      select, input { padding: 8px 10px; border-radius: 8px; border: 1px solid #323847; background: #0f1116; color: #e9e3d6; }
      .actions { margin-top: 12px; display: flex; gap: 10px; flex-wrap: wrap; }
      button { padding: 10px 16px; border-radius: 999px; border: none; cursor: pointer; font-weight: 600; }
      .primary { background: #b13c2b; color: #fff; }
      .secondary { background: #30405a; color: #dfe7f5; }
      .status { margin-top: 16px; padding: 12px; border-radius: 10px; border: 1px dashed #3a4152; color: #8e8a85; font-size: 0.85rem; }
      .dramatic-card { background: #11141b; border: 1px solid #433026; border-radius: 16px; padding: 18px; margin-bottom: 16px; }
      .dramatic-card h3 { margin: 0 0 8px; font-size: 1.1rem; }
      .mode { font-size: 0.8rem; color: #b59d7d; margin-bottom: 8px; }
      pre { white-space: pre-wrap; margin: 0; font-family: inherit; }
      .decision-card { background: #121826; border: 1px solid #3a4152; border-radius: 14px; padding: 14px; margin-bottom: 16px; display: none; }
      .decision-card h4 { margin: 0 0 6px; font-size: 1rem; color: #f1c40f; }
      .decision-card p { margin: 0 0 10px; color: #b9b2a4; font-size: 0.85rem; }
      .decision-actions { display: flex; gap: 8px; flex-wrap: wrap; }
      .decision-actions button { border-radius: 999px; padding: 8px 14px; font-size: 0.85rem; }
      .error-card { background: #201317; border: 1px solid #5b2d32; color: #f3c6c2; padding: 12px; border-radius: 12px; margin-bottom: 12px; display: none; }
      .state-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
      .state-item { background: #12151d; border: 1px solid #2a2f3a; border-radius: 10px; padding: 8px 10px; display: flex; justify-content: space-between; font-size: 0.85rem; color: #d4c8ba; }
      .state-item strong { color: #f1c40f; font-weight: 600; }
      .feed { display: grid; gap: 10px; }
      .feed-item { background: #131722; border: 1px solid #2b3240; border-radius: 10px; padding: 10px; font-size: 0.85rem; color: #cfc6b5; }
      .bars { display: grid; gap: 10px; }
      .bar { display: grid; gap: 6px; font-size: 0.8rem; }
      .bar span { display: flex; justify-content: space-between; color: #bdb4a5; }
      .bar-track { background: #0f1116; border-radius: 999px; overflow: hidden; border: 1px solid #2b3240; }
      .bar-fill { height: 8px; background: #5f7a4a; width: 50%; }
      .actors { margin-top: 12px; display: grid; gap: 8px; font-size: 0.85rem; }
      .actor { background: #12161f; border: 1px solid #2a2f3a; border-radius: 10px; padding: 8px; }
      .budget-card { margin-top: 16px; background: #121826; border: 1px solid #2a2f3a; border-radius: 12px; padding: 12px; }
      .budget-card h3 { margin: 0 0 10px; font-size: 0.95rem; color: #f1c40f; text-transform: uppercase; letter-spacing: 0.08em; }
      .budget-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
      .budget-row label { flex: 1; font-size: 0.8rem; color: #cfc6b5; }
      .budget-row input { width: 70px; }
      .budget-actions { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
      .budget-status { font-size: 0.8rem; color: #b9b2a4; }
      @media (max-width: 1000px) { .grid { grid-template-columns: 1fr; } }
    </style>
  </head>
  <body>
    <div class="wrap">
      <header>
        <div>
          <h1>게임형 요약 데모</h1>
          <p>로그 기반 요약을 게임 화면처럼 확인한다.</p>
        </div>
      </header>

      <div class="grid">
        <section class="panel">
          <h2>State</h2>
          <form id="controls">
            <label>
              Scenario
              <select name="scenario">
                <option value="baseline">baseline</option>
                <option value="famine">famine</option>
                <option value="deficit">deficit</option>
                <option value="warlord" selected>warlord</option>
              </select>
            </label>
            <label>
              Seed
              <input type="number" name="seed" value="42" />
            </label>
            <label>
              Turn Window (Explain)
              <input type="number" name="turn_window" value="20" />
            </label>
            <label>
              Turns (Chronicle)
              <input type="number" name="turns" value="120" />
            </label>
          </form>
          <div class="actions">
            <button class="primary" id="explain">Explain (Dramatic)</button>
            <button class="secondary" id="chronicle">Chronicle</button>
            <button class="secondary" id="load">Load</button>
            <button class="secondary" id="run">Run</button>
            <button class="secondary" id="next-turn">Next Turn ▶</button>
          </div>
          <div class="status">
            public_support / rebellion_risk / treasury / stability<br />
            <span id="state-status">로그/상태 로딩 필요</span>
          </div>
          <div class="state-grid" id="state-grid">
            <div class="state-item"><span>Turn</span><strong>-</strong></div>
            <div class="state-item"><span>Stability</span><strong>-</strong></div>
            <div class="state-item"><span>Legitimacy</span><strong>-</strong></div>
            <div class="state-item"><span>Treasury</span><strong>-</strong></div>
            <div class="state-item"><span>Food</span><strong>-</strong></div>
            <div class="state-item"><span>Support</span><strong>-</strong></div>
            <div class="state-item"><span>Revolt Risk</span><strong>-</strong></div>
          </div>
        </section>

        <section class="panel">
          <h2>Feed</h2>
          <div class="dramatic-card">
            <h3>드라마틱 요약</h3>
            <div class="mode" id="explain-mode">mode: -</div>
            <pre id="explain-result">결과가 여기에 표시된다.</pre>
          </div>
          <div class="dramatic-card">
            <h3>연대기 요약</h3>
            <div class="mode" id="chronicle-mode">mode: -</div>
            <pre id="chronicle-result">결과가 여기에 표시된다.</pre>
          </div>
          <div class="decision-card" id="decision-card">
            <h4 id="decision-title">결단 필요</h4>
            <p id="decision-desc">선택을 내려야 다음 턴으로 진행된다.</p>
            <div class="decision-actions" id="decision-actions"></div>
          </div>
          <div class="error-card" id="error-card">에러 메시지</div>
          <div class="feed" id="feed">
            <div class="feed-item">turn · event.id · actor · severity · cause_tags</div>
          </div>
        </section>

        <section class="panel">
          <h2>Factions</h2>
          <div class="bars" id="factions">
            <div class="bar">
              <span>왕권 <em>50%</em></span>
              <div class="bar-track"><div class="bar-fill" style="width: 50%"></div></div>
            </div>
            <div class="bar">
              <span>관료 <em>50%</em></span>
              <div class="bar-track"><div class="bar-fill" style="width: 50%"></div></div>
            </div>
            <div class="bar">
              <span>군벌 <em>50%</em></span>
              <div class="bar-track"><div class="bar-fill" style="width: 50%"></div></div>
            </div>
            <div class="bar">
              <span>상인 <em>50%</em></span>
              <div class="bar-track"><div class="bar-fill" style="width: 50%"></div></div>
            </div>
            <div class="bar">
              <span>문벌 <em>50%</em></span>
              <div class="bar-track"><div class="bar-fill" style="width: 50%"></div></div>
            </div>
          </div>
          <div class="actors" id="actors">
            <div class="actor">Chancellor · loyalty/ambition/influence (placeholder)</div>
            <div class="actor">General · loyalty/ambition/influence (placeholder)</div>
            <div class="actor">Treasurer · loyalty/ambition/influence (placeholder)</div>
            <div class="actor">ClanHead · loyalty/ambition/influence (placeholder)</div>
            <div class="actor">Spymaster · loyalty/ambition/influence (placeholder)</div>
          </div>
          <div class="budget-card">
            <h3>Budget</h3>
            <div class="budget-row">
              <label for="budget-security">Security</label>
              <input id="budget-security" type="number" min="0" max="100" value="34" />
            </div>
            <div class="budget-row">
              <label for="budget-economy">Economy</label>
              <input id="budget-economy" type="number" min="0" max="100" value="33" />
            </div>
            <div class="budget-row">
              <label for="budget-intel">Intel</label>
              <input id="budget-intel" type="number" min="0" max="100" value="33" />
            </div>
            <div class="budget-actions">
              <button class="secondary" id="budget-save">Set Budget</button>
              <span class="budget-status" id="budget-status">턴 경계에서만 편집 가능</span>
            </div>
          </div>
        </section>
      </div>
    </div>

    <script>
      const form = document.getElementById("controls");
      const explainResult = document.getElementById("explain-result");
      const explainMode = document.getElementById("explain-mode");
      const chronicleResult = document.getElementById("chronicle-result");
      const chronicleMode = document.getElementById("chronicle-mode");
      const errorCard = document.getElementById("error-card");
      const stateStatus = document.getElementById("state-status");
      const stateGrid = document.getElementById("state-grid");
      const feed = document.getElementById("feed");
      const factions = document.getElementById("factions");
      const actors = document.getElementById("actors");
      const nextTurnButton = document.getElementById("next-turn");
      const decisionCard = document.getElementById("decision-card");
      const decisionTitle = document.getElementById("decision-title");
      const decisionDesc = document.getElementById("decision-desc");
      const decisionActions = document.getElementById("decision-actions");
      const budgetSecurity = document.getElementById("budget-security");
      const budgetEconomy = document.getElementById("budget-economy");
      const budgetIntel = document.getElementById("budget-intel");
      const budgetSave = document.getElementById("budget-save");
      const budgetStatus = document.getElementById("budget-status");
      let nextTurnRunning = false;
      let nextTurnLocked = false;
      let lastDecisionExplainTurn = null;
      let currentLogPath = null;
      let currentCursor = null;
      let currentMaxTurn = null;

      function payload() {
        const data = new FormData(form);
        return {
          scenario: data.get("scenario"),
          seed: Number(data.get("seed")),
          turn_window: Number(data.get("turn_window")),
          turns: Number(data.get("turns")),
          log_path: currentLogPath,
        };
      }

      function setError(message) {
        if (message) {
          errorCard.textContent = `에러: ${message}`;
          errorCard.style.display = "block";
        } else {
          errorCard.textContent = "";
          errorCard.style.display = "none";
        }
      }

      function refreshNextTurnButton() {
        if (!nextTurnButton) {
          return;
        }
        if (nextTurnRunning) {
          nextTurnButton.disabled = true;
          nextTurnButton.textContent = "Running...";
          return;
        }
        if (
          currentCursor !== null &&
          currentMaxTurn !== null &&
          currentCursor >= currentMaxTurn
        ) {
          nextTurnButton.disabled = true;
          nextTurnButton.textContent = "End";
          return;
        }
        if (nextTurnLocked) {
          nextTurnButton.disabled = true;
          nextTurnButton.textContent = "결단 필요";
          return;
        }
        nextTurnButton.disabled = false;
        nextTurnButton.textContent = "Next Turn ▶";
      }

      function setNextTurnRunning(running) {
        nextTurnRunning = running;
        refreshNextTurnButton();
      }

      function setNextTurnLock(locked) {
        nextTurnLocked = locked;
        refreshNextTurnButton();
      }

      async function callAi(url, body, targetMode, targetResult) {
        targetMode.textContent = "mode: ...";
        targetResult.textContent = "요청 중...";
        try {
          const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }
          const data = await response.json();
          targetMode.textContent = `mode: ${data.mode || "-"}`;
          targetResult.textContent = data.text || "(empty)";
        } catch (err) {
          targetMode.textContent = "mode: error";
          targetResult.textContent = `에러: ${err.message}`;
        }
      }

      function setBudgetInputs(enabled) {
        budgetSecurity.disabled = !enabled;
        budgetEconomy.disabled = !enabled;
        budgetIntel.disabled = !enabled;
        budgetSave.disabled = !enabled;
      }

      function updateBudgetUI(state) {
        const budget = state && state.budget ? state.budget : { security: 34, economy: 33, intel: 33 };
        budgetSecurity.value = budget.security ?? 0;
        budgetEconomy.value = budget.economy ?? 0;
        budgetIntel.value = budget.intel ?? 0;

        const turn = state ? state.turn : null;
        const canEdit = Number.isInteger(turn) && turn % 5 === 0;
        setBudgetInputs(canEdit);
        const total = Number(budgetSecurity.value) + Number(budgetEconomy.value) + Number(budgetIntel.value);
        if (turn === null || turn === undefined) {
          budgetStatus.textContent = "상태 로딩 필요";
        } else if (canEdit) {
          budgetStatus.textContent = `합계 ${total} / 100`;
        } else {
          budgetStatus.textContent = `다음 편집: 5턴마다 (합계 ${total})`;
        }
      }

      function renderDecisionCard(decision) {
        if (!decision) {
          decisionCard.style.display = "none";
          decisionActions.innerHTML = "";
          return;
        }
        decisionCard.style.display = "block";
        decisionTitle.textContent = decision.title || "결단 필요";
        decisionDesc.textContent = "선택을 내려야 다음 턴으로 진행된다.";
        decisionActions.innerHTML = "";
        decision.choices.forEach((choice, index) => {
          const button = document.createElement("button");
          button.className = index === 0 ? "primary" : "secondary";
          button.textContent = choice.label || choice.id;
          button.addEventListener("click", (event) => {
            event.preventDefault();
            sendDecision(decision.id, choice.id);
          });
          decisionActions.appendChild(button);
        });
      }

      function setDecisionButtonsDisabled(disabled) {
        const buttons = decisionActions.querySelectorAll("button");
        buttons.forEach((button) => {
          button.disabled = disabled;
        });
      }

      async function fetchPendingDecision() {
        const data = payload();
        try {
          const turns = currentMaxTurn ?? data.turns;
          const response = await fetch("/api/pending_decision", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              scenario: data.scenario,
              seed: data.seed,
              turns: turns,
              tail: 20,
              log_path: data.log_path,
            }),
          });
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }
          const pending = await response.json();
          if (pending.pending) {
            setNextTurnLock(true);
            renderDecisionCard(pending.decision);
            if (pending.decision && pending.decision.turn !== lastDecisionExplainTurn) {
              lastDecisionExplainTurn = pending.decision.turn;
              callAi("/ai/explain", {
                scenario: data.scenario,
                seed: data.seed,
                turn_window: data.turn_window,
                log_path: data.log_path,
              }, explainMode, explainResult);
            }
          } else {
            setNextTurnLock(false);
            renderDecisionCard(null);
          }
        } catch (err) {
          setError(err.message);
        }
      }

      async function sendDecision(decisionId, choice) {
        const data = payload();
        setDecisionButtonsDisabled(true);
        setNextTurnLock(true);
        try {
          const turns = currentMaxTurn ?? data.turns;
          const response = await fetch("/api/decide", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              scenario: data.scenario,
              seed: data.seed,
              turns: turns,
              decision_id: decisionId,
              choice: choice,
              log_path: data.log_path,
            }),
          });
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }
          const snapshot = await response.json();
          updateSnapshot(snapshot);
          setNextTurnLock(false);
          renderDecisionCard(null);
        } catch (err) {
          setError(err.message);
        } finally {
          setDecisionButtonsDisabled(false);
        }
      }

      function updateSnapshot(data, checkPending) {
        setError(data.error || null);
        if (data.log_path) {
          currentLogPath = data.log_path;
        }
        const state = data.state || {};
        const support = state.public_support ?? null;
        const risk = state.revolt_risk ?? null;
        const treasury = state.treasury ?? null;
        const stability = state.stability ?? null;
        const cursor = data.cursor ?? null;
        const maxTurn = data.max_turn ?? null;
        currentCursor = cursor;
        currentMaxTurn = maxTurn;
        if (support === null) {
          stateStatus.textContent = "로그/상태 로딩 필요";
        } else {
          const cursorText =
            cursor !== null && maxTurn !== null ? ` · cursor ${cursor}/${maxTurn}` : "";
          stateStatus.textContent = `public_support ${support} · rebellion_risk ${risk} · treasury ${treasury} · stability ${stability}${cursorText}`;
        }
        refreshNextTurnButton();

        updateBudgetUI(state);

        const stateItems = [
          ["Turn", state.turn],
          ["Stability", state.stability],
          ["Legitimacy", state.legitimacy],
          ["Treasury", state.treasury],
          ["Food", state.food],
          ["Support", state.public_support],
          ["Revolt Risk", state.revolt_risk],
        ];
        stateGrid.innerHTML = "";
        stateItems.forEach(([label, value]) => {
          const item = document.createElement("div");
          item.className = "state-item";
          item.innerHTML = `<span>${label}</span><strong>${value ?? "-"}</strong>`;
          stateGrid.appendChild(item);
        });

        feed.innerHTML = "";
        if (!data.events || data.events.length === 0) {
          feed.innerHTML = "<div class='feed-item'>최근 이벤트 없음</div>";
        } else {
          const sortedEvents = [...data.events].sort((a, b) => (a.turn ?? 0) - (b.turn ?? 0));
          sortedEvents.forEach((event) => {
            const tags = (event.cause_tags || []).join(", ");
            const title = event.title || event.id || "unknown";
            const line = document.createElement("div");
            line.className = "feed-item";
            line.textContent = `T${event.turn} · ${title} · ${event.actor} · S${event.severity} · ${tags}`;
            feed.appendChild(line);
          });
        }

        const factionData = data.factions || {};
        const factionLabels = [
          ["royal", "왕권"],
          ["bureaucrats", "관료"],
          ["warlords", "군벌"],
          ["merchants", "상인"],
          ["clans", "문벌"],
        ];
        factions.innerHTML = "";
        factionLabels.forEach(([key, label]) => {
          const value = factionData[key] ?? null;
          const percent = value === null ? 0 : Math.max(0, Math.min(100, value));
          const bar = document.createElement("div");
          bar.className = "bar";
          bar.innerHTML = `
            <span>${label} <em>${value === null ? "-" : Math.round(percent) + "%"}</em></span>
            <div class="bar-track"><div class="bar-fill" style="width: ${percent}%"></div></div>
          `;
          factions.appendChild(bar);
        });

        actors.innerHTML = "";
        const actorData = data.actors || {};
        const actorEntries = Object.entries(actorData);
        if (actorEntries.length === 0) {
          actors.innerHTML = "<div class='actor'>인물 데이터 로딩 필요</div>";
        } else {
          actorEntries.forEach(([name, stats]) => {
            const card = document.createElement("div");
            card.className = "actor";
            card.textContent = `${name} · loyalty ${stats.loyalty} · ambition ${stats.ambition} · influence ${stats.influence}`;
            actors.appendChild(card);
          });
        }
        if (checkPending) {
          fetchPendingDecision();
        }
      }

      document.getElementById("explain").addEventListener("click", (event) => {
        event.preventDefault();
        const data = payload();
        callAi("/ai/explain", {
          scenario: data.scenario,
          seed: data.seed,
          turn_window: data.turn_window,
          log_path: data.log_path,
        }, explainMode, explainResult);
      });

      document.getElementById("chronicle").addEventListener("click", (event) => {
        event.preventDefault();
        const data = payload();
        callAi("/ai/chronicle", {
          scenario: data.scenario,
          seed: data.seed,
          turns: data.turns,
          log_path: data.log_path,
        }, chronicleMode, chronicleResult);
      });

      async function runSnapshot(url, body) {
        const data = payload();
        try {
          const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body(data)),
          });
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }
          const snapshot = await response.json();
          updateSnapshot(snapshot, true);
        } catch (err) {
          setError(err.message);
        }
      }

      document.getElementById("load").addEventListener("click", (event) => {
        event.preventDefault();
        runSnapshot("/api/snapshot", (data) => ({
          scenario: data.scenario,
          seed: data.seed,
          turns: data.turns,
          tail: 200,
          log_path: data.log_path,
        }));
      });

      document.getElementById("run").addEventListener("click", (event) => {
        event.preventDefault();
        runSnapshot("/api/run", (data) => ({
          scenario: data.scenario,
          seed: data.seed,
          turns: data.turns,
        }));
      });

      budgetSave.addEventListener("click", async (event) => {
        event.preventDefault();
        const data = payload();
        const budget = {
          security: Number(budgetSecurity.value),
          economy: Number(budgetEconomy.value),
          intel: Number(budgetIntel.value),
        };
        const total = budget.security + budget.economy + budget.intel;
        if (total !== 100) {
          setError("Budget must sum to 100");
          return;
        }
        budgetSave.disabled = true;
        try {
          const response = await fetch("/api/set_budget", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              scenario: data.scenario,
              seed: data.seed,
              turns: data.turns,
              budget: budget,
              log_path: data.log_path,
            }),
          });
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }
          const snapshot = await response.json();
          updateSnapshot(snapshot);
        } catch (err) {
          setError(err.message);
        } finally {
          budgetSave.disabled = false;
        }
      });

      nextTurnButton.addEventListener("click", async (event) => {
        event.preventDefault();
        const data = payload();
        setNextTurnRunning(true);
        try {
          const response = await fetch("/api/next_turn", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              scenario: data.scenario,
              seed: data.seed,
              turns: data.turns,
              tail: 200,
              log_path: data.log_path,
            }),
          });
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }
          const snapshot = await response.json();
          updateSnapshot(snapshot, true);
        } catch (err) {
          setError(err.message);
        } finally {
          setNextTurnRunning(false);
        }
      });

      refreshNextTurnButton();
    </script>
  </body>
</html>
"""
