from __future__ import annotations

from fastapi import FastAPI, HTTPException
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
