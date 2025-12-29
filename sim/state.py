from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict

FACTION_KEYS = ("royal", "bureaucrats", "warlords", "merchants", "clans")
ACTOR_ROLES = ("Chancellor", "General", "Treasurer", "ClanHead", "Spymaster")


@dataclass(frozen=True)
class State:
    turn: int
    stability: float
    legitimacy: float
    treasury: float
    food: float
    public_support: float
    revolt_risk: float
    riot_cooldown_until: int
    factions: Dict[str, float]
    actors: Dict[str, Dict[str, float]]


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def normalize_factions(factions: Dict[str, float]) -> Dict[str, float]:
    return {key: clamp(factions.get(key, 50.0)) for key in FACTION_KEYS}


def normalize_actors(actors: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    normalized: Dict[str, Dict[str, float]] = {}
    for role in ACTOR_ROLES:
        stats = actors.get(role, {})
        normalized[role] = {
            "loyalty": clamp(stats.get("loyalty", 50.0)),
            "ambition": clamp(stats.get("ambition", 50.0)),
            "influence": clamp(stats.get("influence", 50.0)),
        }
    return normalized


SCENARIOS = {
    "baseline": {},
    "famine": {
        "stability": 45.0,
        "legitimacy": 50.0,
        "treasury": 48.0,
        "food": 25.0,
        "public_support": 40.0,
        "revolt_risk": 45.0,
        "factions": {
            "royal": 52.0,
            "bureaucrats": 50.0,
            "warlords": 48.0,
            "merchants": 45.0,
            "clans": 50.0,
        },
    },
    "deficit": {
        "stability": 58.0,
        "legitimacy": 56.0,
        "treasury": 20.0,
        "food": 55.0,
        "public_support": 54.0,
        "revolt_risk": 32.0,
        "factions": {
            "royal": 56.0,
            "bureaucrats": 48.0,
            "warlords": 42.0,
            "merchants": 42.0,
            "clans": 46.0,
        },
    },
    "warlord": {
        "stability": 55.0,
        "legitimacy": 52.0,
        "treasury": 50.0,
        "food": 55.0,
        "public_support": 50.0,
        "revolt_risk": 40.0,
        "factions": {
            "royal": 45.0,
            "bureaucrats": 50.0,
            "warlords": 70.0,
            "merchants": 46.0,
            "clans": 52.0,
        },
    },
}


def initial_state(scenario: str = "baseline") -> State:
    base_state = State(
        turn=0,
        stability=62.0,
        legitimacy=58.0,
        treasury=55.0,
        food=60.0,
        public_support=57.0,
        revolt_risk=24.0,
        riot_cooldown_until=0,
        factions=normalize_factions(
            {
                "royal": 58.0,
                "bureaucrats": 52.0,
                "warlords": 41.0,
                "merchants": 48.0,
                "clans": 46.0,
            }
        ),
        actors=normalize_actors(
            {
                "Chancellor": {"loyalty": 56.0, "ambition": 52.0, "influence": 58.0},
                "General": {"loyalty": 50.0, "ambition": 54.0, "influence": 52.0},
                "Treasurer": {"loyalty": 55.0, "ambition": 50.0, "influence": 54.0},
                "ClanHead": {"loyalty": 48.0, "ambition": 56.0, "influence": 55.0},
                "Spymaster": {"loyalty": 53.0, "ambition": 57.0, "influence": 58.0},
            }
        ),
    )
    overrides = SCENARIOS.get(scenario)
    if overrides is None:
        raise ValueError(f"Unknown scenario: {scenario}")

    if not overrides:
        return base_state

    factions_override = overrides.get("factions", {})
    factions = normalize_factions({**base_state.factions, **factions_override})
    return replace(
        base_state,
        stability=overrides.get("stability", base_state.stability),
        legitimacy=overrides.get("legitimacy", base_state.legitimacy),
        treasury=overrides.get("treasury", base_state.treasury),
        food=overrides.get("food", base_state.food),
        public_support=overrides.get("public_support", base_state.public_support),
        revolt_risk=overrides.get("revolt_risk", base_state.revolt_risk),
        riot_cooldown_until=overrides.get("riot_cooldown_until", base_state.riot_cooldown_until),
        factions=factions,
        actors=normalize_actors({**base_state.actors, **overrides.get("actors", {})}),
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
        "riot_cooldown_until": state.riot_cooldown_until,
        "factions": {key: round(value, 2) for key, value in state.factions.items()},
        "actors": {
            role: {key: round(value, 2) for key, value in stats.items()}
            for role, stats in state.actors.items()
        },
    }
