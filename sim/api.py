from __future__ import annotations

import random
from typing import Optional

from fastapi import FastAPI, Query

from .engine import is_bankrupt, is_riot, step
from .simulate import run_simulation
from .state import initial_state, serialize_state

app = FastAPI(title="Korean Paradox Prototype")

_rng = random.Random(42)
_state = initial_state()


def _reset(seed: Optional[int] = None) -> None:
    global _rng
    global _state
    if seed is not None:
        _rng = random.Random(seed)
    _state = initial_state()


@app.get("/state")
async def get_state():
    return {"state": serialize_state(_state)}


@app.post("/step")
async def step_state():
    global _state
    _state, event = step(_state, _rng)
    return {
        "state": serialize_state(_state),
        "event": None if event is None else {"id": event.id, "title": event.title},
        "bankrupt": is_bankrupt(_state),
        "riot": is_riot(_state),
    }


@app.post("/run")
async def run_state(
    turns: int = Query(120, ge=1, le=500),
    seed: Optional[int] = Query(None),
):
    if seed is not None:
        _reset(seed)
    log, summary = run_simulation(turns, _rng)
    return {"summary": summary, "log": log}
