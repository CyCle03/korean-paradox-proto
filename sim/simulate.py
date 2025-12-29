from __future__ import annotations

import json
from typing import Dict, Iterable, List, Tuple

from .engine import is_bankrupt, is_riot, step
from .state import initial_state, serialize_state


def run_simulation(turns: int, rng) -> Tuple[List[Dict], Dict]:
    state = initial_state()
    log: List[Dict] = []
    bankruptcies = 0
    riots = 0
    support_total = 0.0

    for _ in range(turns):
        state, event = step(state, rng)
        if is_bankrupt(state):
            bankruptcies += 1
        if is_riot(state):
            riots += 1
        support_total += state.public_support

        log.append(
            {
                "state": serialize_state(state),
                "event": None if event is None else {
                    "id": event.id,
                    "title": event.title,
                    "actor": event.actor,
                },
            }
        )

    avg_support = support_total / max(turns, 1)
    summary = {
        "bankruptcies": bankruptcies,
        "riots": riots,
        "avg_public_support": round(avg_support, 2),
        "final_factions": state.factions,
    }
    return log, summary


def write_jsonl(path, records: Iterable[Dict]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
