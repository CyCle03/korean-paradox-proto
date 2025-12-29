from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ai.summarize import load_jsonl, resolve_log_path
from ai.summarize import chronicle_summary, explain_summary

app = FastAPI(title="Korean Paradox AI")


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
    tail: int = 60


def build_snapshot(scenario: str, seed: int, turns: int, tail: int):
    log_path = resolve_log_path(scenario, seed, None)
    if not log_path.exists():
        raise HTTPException(status_code=404, detail=f"Log not found: {log_path}")

    records = load_jsonl(log_path)
    if not records:
        raise HTTPException(status_code=404, detail="Log is empty")

    last_record = records[-1]
    last_state = last_record.get("state")
    last_turn = last_state.get("turn", 0) if isinstance(last_state, dict) else 0

    events = []
    cutoff = last_turn - max(tail, 1)
    for record in records:
        state = record.get("state", {})
        event = record.get("event")
        if not event:
            continue
        if state.get("turn", 0) <= cutoff:
            continue
        events.append(
            {
                "turn": state.get("turn", 0),
                "id": event.get("id"),
                "actor": event.get("actor"),
                "severity": event.get("severity"),
                "cause_tags": event.get("cause_tags", []),
                "stakeholders": event.get("stakeholders", []),
            }
        )

    factions = last_state.get("factions") if isinstance(last_state, dict) else None
    characters = None
    if isinstance(last_state, dict) and last_state.get("actors"):
        characters = [
            {"name": role, **stats} for role, stats in last_state.get("actors", {}).items()
        ]

    return {
        "log_path": str(log_path),
        "last_turn": last_turn,
        "state": last_state,
        "factions": factions,
        "characters": characters,
        "events": events,
    }


@app.post("/ai/explain")
async def explain(request: ExplainRequest):
    if request.scenario not in {"baseline", "famine", "deficit", "warlord"}:
        raise HTTPException(status_code=400, detail="Invalid scenario")
    return explain_summary(request.scenario, request.seed, request.turn_window, request.log_path)


@app.post("/ai/chronicle")
async def chronicle(request: ChronicleRequest):
    if request.scenario not in {"baseline", "famine", "deficit", "warlord"}:
        raise HTTPException(status_code=400, detail="Invalid scenario")
    return chronicle_summary(request.scenario, request.seed, request.turns, request.log_path)


@app.post("/api/snapshot")
async def snapshot(request: SnapshotRequest):
    if request.scenario not in {"baseline", "famine", "deficit", "warlord"}:
        raise HTTPException(status_code=400, detail="Invalid scenario")
    return build_snapshot(request.scenario, request.seed, request.turns, request.tail)


@app.post("/api/run")
async def run_snapshot(request: SnapshotRequest):
    if request.scenario not in {"baseline", "famine", "deficit", "warlord"}:
        raise HTTPException(status_code=400, detail="Invalid scenario")
    from scripts.run_sim import run_with_scenario

    log, _summary = run_with_scenario(request.turns, __import__("random").Random(request.seed), request.scenario)
    out_path = resolve_log_path(request.scenario, request.seed, None)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    from sim.simulate import write_jsonl

    write_jsonl(out_path, log)
    return build_snapshot(request.scenario, request.seed, request.turns, request.tail)


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
          </div>
          <div class="status">
            public_support / rebellion_risk / treasury / stability<br />
            <span id="state-status">로그/상태 로딩 필요</span>
          </div>
        </section>

        <section class="panel">
          <h2>Feed</h2>
          <div class="dramatic-card">
            <h3>드라마틱 요약</h3>
            <div class="mode" id="mode">mode: -</div>
            <pre id="result">결과가 여기에 표시된다.</pre>
          </div>
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
      const result = document.getElementById("result");
      const mode = document.getElementById("mode");
      const stateStatus = document.getElementById("state-status");
      const feed = document.getElementById("feed");
      const factions = document.getElementById("factions");
      const actors = document.getElementById("actors");

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

      async function callApi(url, body) {
        mode.textContent = "mode: ...";
        result.textContent = "요청 중...";
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
          mode.textContent = `mode: ${data.mode || "-"}`;
          result.textContent = data.text || "(empty)";
        } catch (err) {
          mode.textContent = "mode: error";
          result.textContent = `에러: ${err.message}`;
        }
      }

      function updateSnapshot(data) {
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

        feed.innerHTML = "";
        if (!data.events || data.events.length === 0) {
          feed.innerHTML = "<div class='feed-item'>최근 이벤트 없음</div>";
        } else {
          data.events.forEach((event) => {
            const tags = (event.cause_tags || []).join(", ");
            const line = document.createElement("div");
            line.className = "feed-item";
            line.textContent = `T${event.turn} · ${event.id} · ${event.actor} · S${event.severity} · ${tags}`;
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
        if (!data.characters || data.characters.length === 0) {
          actors.innerHTML = "<div class='actor'>인물 데이터 로딩 필요</div>";
        } else {
          data.characters.forEach((actor) => {
            const card = document.createElement("div");
            card.className = "actor";
            card.textContent = `${actor.name} · loyalty ${actor.loyalty} · ambition ${actor.ambition} · influence ${actor.influence}`;
            actors.appendChild(card);
          });
        }
      }

      document.getElementById("explain").addEventListener("click", (event) => {
        event.preventDefault();
        const data = payload();
        callApi("/ai/explain", {
          scenario: data.scenario,
          seed: data.seed,
          turn_window: data.turn_window,
          log_path: null,
        });
      });

      document.getElementById("chronicle").addEventListener("click", (event) => {
        event.preventDefault();
        const data = payload();
        callApi("/ai/chronicle", {
          scenario: data.scenario,
          seed: data.seed,
          turns: data.turns,
          log_path: null,
        });
      });

      async function runSnapshot(url) {
        const data = payload();
        try {
          const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              scenario: data.scenario,
              seed: data.seed,
              turns: data.turns,
              tail: 60,
            }),
          });
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }
          const snapshot = await response.json();
          updateSnapshot(snapshot);
        } catch (err) {
          stateStatus.textContent = `에러: ${err.message}`;
        }
      }

      document.getElementById("load").addEventListener("click", (event) => {
        event.preventDefault();
        runSnapshot("/api/snapshot");
      });

      document.getElementById("run").addEventListener("click", (event) => {
        event.preventDefault();
        runSnapshot("/api/run");
      });
    </script>
  </body>
</html>
"""
