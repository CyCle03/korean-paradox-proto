from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

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


@app.get("/", response_class=HTMLResponse)
async def demo_page():
    return """
<!doctype html>
<html lang="ko">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>AI 요약 데모</title>
    <style>
      body { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; background: #f6f3ee; color: #1d1b16; margin: 0; }
      .wrap { max-width: 960px; margin: 0 auto; padding: 32px 24px 48px; }
      header { display: flex; justify-content: space-between; align-items: baseline; gap: 16px; }
      h1 { font-size: 1.8rem; margin: 0 0 8px; }
      p { margin: 0; color: #564c41; }
      form { margin-top: 24px; display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }
      label { display: grid; gap: 6px; font-size: 0.85rem; }
      select, input { padding: 8px 10px; border-radius: 8px; border: 1px solid #cbbba7; background: #fff; }
      .actions { margin-top: 16px; display: flex; gap: 12px; flex-wrap: wrap; }
      button { padding: 10px 16px; border-radius: 999px; border: none; cursor: pointer; font-weight: 600; }
      .primary { background: #8c3a24; color: #fff; }
      .secondary { background: #d9c3a4; color: #1d1b16; }
      .output { margin-top: 24px; background: #fff; border-radius: 12px; padding: 16px; border: 1px solid #e2d3c0; }
      .mode { font-size: 0.8rem; color: #6c5b49; margin-bottom: 8px; }
      pre { white-space: pre-wrap; margin: 0; font-family: inherit; }
    </style>
  </head>
  <body>
    <div class="wrap">
      <header>
        <div>
          <h1>AI 요약 데모</h1>
          <p>scenario, seed, turn 범위를 지정해 요약을 확인한다.</p>
        </div>
      </header>

      <form id="controls">
        <label>
          Scenario
          <select name="scenario">
            <option value="baseline">baseline</option>
            <option value="famine">famine</option>
            <option value="deficit">deficit</option>
            <option value="warlord">warlord</option>
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
      </div>

      <section class="output">
        <div class="mode" id="mode">mode: -</div>
        <pre id="result">결과가 여기에 표시된다.</pre>
      </section>
    </div>

    <script>
      const form = document.getElementById("controls");
      const result = document.getElementById("result");
      const mode = document.getElementById("mode");

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
    </script>
  </body>
</html>
"""
