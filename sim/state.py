from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict

FACTION_KEYS = ("royal", "bureaucrats", "warlords", "merchants", "clans")


@dataclass(frozen=True)
class State:
    turn: int
    stability: float
    legitimacy: float
    treasury: float
    food: float
    public_support: float
    revolt_risk: float
    factions: Dict[str, float]


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def normalize_factions(factions: Dict[str, float]) -> Dict[str, float]:
    return {key: clamp(factions.get(key, 50.0)) for key in FACTION_KEYS}


def initial_state() -> State:
    return State(
        turn=0,
        stability=62.0,
        legitimacy=58.0,
        treasury=55.0,
        food=60.0,
        public_support=57.0,
        revolt_risk=24.0,
        factions=normalize_factions(
            {
                "royal": 58.0,
                "bureaucrats": 52.0,
                "warlords": 41.0,
                "merchants": 48.0,
                "clans": 46.0,
            }
        ),
    )


def apply_deltas(state: State, **deltas: float) -> State:
    return replace(
        state,
        stability=clamp(state.stability + deltas.get("stability", 0.0)),
        legitimacy=clamp(state.legitimacy + deltas.get("legitimacy", 0.0)),
        treasury=clamp(state.treasury + deltas.get("treasury", 0.0)),
        food=clamp(state.food + deltas.get("food", 0.0)),
        public_support=clamp(state.public_support + deltas.get("public_support", 0.0)),
        revolt_risk=clamp(state.revolt_risk + deltas.get("revolt_risk", 0.0)),
    )


def apply_faction_deltas(state: State, updates: Dict[str, float]) -> State:
    factions = dict(state.factions)
    for key, delta in updates.items():
        if key not in factions:
            continue
        factions[key] = clamp(factions[key] + delta)
    return replace(state, factions=factions)


def serialize_state(state: State) -> Dict[str, float]:
    return {
        "turn": state.turn,
        "stability": round(state.stability, 2),
        "legitimacy": round(state.legitimacy, 2),
        "treasury": round(state.treasury, 2),
        "food": round(state.food, 2),
        "public_support": round(state.public_support, 2),
        "revolt_risk": round(state.revolt_risk, 2),
        "factions": {key: round(value, 2) for key, value in state.factions.items()},
    }
