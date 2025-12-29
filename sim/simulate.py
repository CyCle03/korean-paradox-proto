from __future__ import annotations

import json
from typing import Dict, Iterable, List, Tuple

from ai.summarize import compact_events, rule_explain
from .engine import (
    DECISION_CAUSE_TAGS,
    DECISION_DURATION,
    DECISION_ID,
    apply_decision_immediate,
    apply_decision_tick,
    is_bankrupt,
    is_riot,
    step,
)
from .state import ACTOR_ROLES, initial_state, serialize_state


def run_simulation(turns: int, rng) -> Tuple[List[Dict], Dict]:
    state = initial_state()
    log: List[Dict] = []
    bankruptcies = 0
    riots = 0
    support_total = 0.0
    decision_choice: str | None = None
    decision_remaining = 0

    for _ in range(turns):
        if decision_remaining > 0 and decision_choice:
            state = apply_decision_tick(state, decision_choice)
            decision_remaining -= 1

        state, event = step(state, rng)
        if is_bankrupt(state):
            bankruptcies += 1
        if is_riot(state):
            riots += 1
        support_total += state.public_support

        record = {
            "state": serialize_state(state),
            "event": None
            if event is None
            else {
                "id": event.id,
                "title": event.title,
                "actor": normalize_actor(event.actor),
                "cause_tags": event.cause_tags,
                "severity": event.severity,
                "stakeholders": event.stakeholders,
            },
        }

        if decision_choice is None and (
            is_riot(state) or state.revolt_risk >= 55.0
        ):
            windowed = log[-20:] + [record]
            rule_explain(compact_events(windowed), windowed)
            decision_choice = "A" if rng.random() < 0.5 else "B"
            state = apply_decision_immediate(state, decision_choice)
            decision_remaining = DECISION_DURATION
            record["decision_id"] = DECISION_ID
            record["choice"] = decision_choice
            record["actor"] = "Chancellor"
            record["cause_tags"] = DECISION_CAUSE_TAGS

        log.append(record)

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


def normalize_actor(actor: str) -> str:
    return actor if actor in ACTOR_ROLES else "Chancellor"
