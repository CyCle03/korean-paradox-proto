from __future__ import annotations

import json
from collections import deque

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
    seed: int = 42
    turns: int = 120


def error_response(status_code: int, message: str):
    return JSONResponse(status_code=status_code, content={"error": message})


def cursor_path_for(path):
    return path.with_suffix(path.suffix + ".cursor")


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


def build_snapshot(scenario: str, seed: int, turns: int, tail: int, log_path: str | None):
    path = resolve_log_path(scenario, seed, log_path)
    if not path.exists():
        return None, (404, f"Log not found: {path}")

    cursor = read_cursor(path)
    scan, _unused, error = scan_log(path, tail, cursor)
    if error:
        return None, error

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

    last_state = scan["last_state_cursor"] if cursor is not None else scan["last_state_overall"]
    if cursor is not None and last_state is None:
        return None, (404, "Cursor out of range")

    last_turn = cursor if cursor is not None else (last_state.get("turn", 0) if isinstance(last_state, dict) else 0)
    factions = last_state.get("factions") if isinstance(last_state, dict) else None
    actors = last_state.get("actors") if isinstance(last_state, dict) else None

    return (
        {
            "log_path": str(path),
            "last_turn": last_turn,
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
    return explain_summary(request.scenario, request.seed, request.turn_window, request.log_path)


@app.post("/ai/chronicle")
async def chronicle(request: ChronicleRequest):
    if request.scenario not in VALID_SCENARIOS:
        return error_response(400, "Invalid scenario")
    return chronicle_summary(request.scenario, request.seed, request.turns, request.log_path)


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
    from scripts.run_sim import run_with_scenario
    from sim.simulate import run_simulation, write_jsonl

    rng = __import__("random").Random(request.seed)
    if request.scenario == "baseline":
        log, _summary = run_simulation(request.turns, rng)
    else:
        log, _summary = run_with_scenario(request.turns, rng, request.scenario)

    out_path = resolve_log_path(request.scenario, request.seed, None)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_path, log)
    write_cursor(out_path, 1 if log else 0)
    snapshot_data, error = build_snapshot(
        request.scenario, request.seed, request.turns, 200, None
    )
    if error:
        status_code, message = error
        return error_response(status_code, message)
    return snapshot_data


@app.post("/api/next_turn")
async def next_turn(request: SnapshotRequest):
    if request.scenario not in VALID_SCENARIOS:
        return error_response(400, "Invalid scenario")
    path = resolve_log_path(request.scenario, request.seed, request.log_path)
    if not path.exists():
        return error_response(404, f"Log not found: {path}")

    cursor = read_cursor(path)
    if cursor is None:
        cursor = 0

    scan, _unused, error = scan_log(path, request.tail, None)
    if error:
        status_code, message = error
        return error_response(status_code, message)
    last_turn_overall = scan["last_turn_overall"]
    if cursor >= last_turn_overall:
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

      function payload() {
        const data = new FormData(form);
        return {
          scenario: data.get("scenario"),
          seed: Number(data.get("seed")),
          turn_window: Number(data.get("turn_window")),
          turns: Number(data.get("turns")),
          log_path: null,
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

      function setButtonState(button, running) {
        if (!button) {
          return;
        }
        button.disabled = running;
        button.textContent = running ? "Running..." : "Next Turn ▶";
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

      function updateSnapshot(data) {
        setError(data.error || null);
        const state = data.state || {};
        const support = state.public_support ?? null;
        const risk = state.revolt_risk ?? null;
        const treasury = state.treasury ?? null;
        const stability = state.stability ?? null;
        if (support === null) {
          stateStatus.textContent = "로그/상태 로딩 필요";
        } else {
          stateStatus.textContent = `public_support ${support} · rebellion_risk ${risk} · treasury ${treasury} · stability ${stability}`;
        }

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
          data.events.forEach((event) => {
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
      }

      document.getElementById("explain").addEventListener("click", (event) => {
        event.preventDefault();
        const data = payload();
        callAi("/ai/explain", {
          scenario: data.scenario,
          seed: data.seed,
          turn_window: data.turn_window,
          log_path: null,
        }, explainMode, explainResult);
      });

      document.getElementById("chronicle").addEventListener("click", (event) => {
        event.preventDefault();
        const data = payload();
        callAi("/ai/chronicle", {
          scenario: data.scenario,
          seed: data.seed,
          turns: data.turns,
          log_path: null,
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
          updateSnapshot(snapshot);
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
          log_path: null,
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

      nextTurnButton.addEventListener("click", async (event) => {
        event.preventDefault();
        const data = payload();
        setButtonState(nextTurnButton, true);
        try {
          const response = await fetch("/api/next_turn", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              scenario: data.scenario,
              seed: data.seed,
              turns: data.turns,
              tail: 200,
              log_path: null,
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
          setButtonState(nextTurnButton, false);
        }
      });
    </script>
  </body>
</html>
"""
