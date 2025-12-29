from __future__ import annotations

from dataclasses import replace
from typing import Optional, Tuple

from .events import Event, choose_event
from .state import State, apply_deltas, clamp


def balance_score(factions: dict[str, float]) -> float:
    values = list(factions.values())
    return max(values) - min(values)


def compute_turn_updates(state: State) -> State:
    balance = balance_score(state.factions)
    food_pressure = 50.0 - state.food

    treasury_delta = (state.factions["bureaucrats"] + state.factions["merchants"]) / 50.0
    treasury_delta -= balance / 60.0
    treasury_delta -= max(food_pressure, 0.0) / 25.0

    support_delta = (state.legitimacy - 50.0) / 18.0
    support_delta -= balance / 55.0
    support_delta -= max(food_pressure, 0.0) / 22.0

    stability_delta = (state.public_support - 50.0) / 20.0
    stability_delta -= balance / 65.0
    stability_delta -= max(food_pressure, 0.0) / 30.0

    revolt_delta = 0.0
    revolt_delta += max(0.0, 45.0 - state.public_support) / 20.0
    revolt_delta += max(0.0, state.factions["warlords"] - 55.0) / 18.0
    revolt_delta += max(0.0, 45.0 - state.food) / 16.0
    revolt_delta -= max(0.0, state.stability - 60.0) / 22.0

    return apply_deltas(
        state,
        treasury=treasury_delta,
        public_support=support_delta,
        stability=stability_delta,
        revolt_risk=revolt_delta,
    )


def is_bankrupt(state: State) -> bool:
    return state.treasury <= 0.0


def is_riot(state: State) -> bool:
    return state.public_support <= 30.0 and state.stability <= 40.0 and state.revolt_risk >= 60.0


def step(state: State, rng) -> Tuple[State, Optional[Event]]:
    updated = compute_turn_updates(state)
    updated = replace(updated, turn=state.turn + 1)
    updated = apply_actor_drift(updated)

    event = choose_event(updated, rng)
    if event is None:
        return updated, None

    choice = event.choose(rng)
    updated = event.apply(choice, updated)
    updated = apply_faction_soft_caps(state, updated)
    return updated, event


def apply_faction_soft_caps(previous: State, updated: State) -> State:
    factions = dict(updated.factions)
    for key, value in updated.factions.items():
        before = previous.factions.get(key, value)
        delta = value - before
        if delta <= 0:
            continue
        if before >= 95.0:
            delta *= 0.15
        elif before >= 85.0:
            delta *= 0.35
        factions[key] = clamp(before + delta)
    return replace(updated, factions=factions)


DECISION_DURATION = 10
DECISION_ID = "riot-policy"
DECISION_CAUSE_TAGS = ["riot", "security"]


def apply_decision_immediate(state: State, choice: str) -> State:
    if choice == "A":
        return apply_deltas(state, revolt_risk=-3.0, public_support=-1.5, stability=0.8)
    return apply_deltas(state, treasury=-1.2)


def apply_decision_tick(state: State, choice: str) -> State:
    if choice == "A":
        return apply_deltas(state, revolt_risk=0.3, stability=0.2)
    return apply_deltas(state, revolt_risk=-0.4, stability=0.2, treasury=-0.3)


def clamp_delta(value: float, limit: float = 2.0) -> float:
    return max(-limit, min(limit, value))


def apply_actor_drift(state: State) -> State:
    actors = {role: dict(stats) for role, stats in state.actors.items()}

    def adjust(role: str, loyalty: float, ambition: float, influence: float) -> None:
        stats = actors[role]
        stats["loyalty"] = clamp(stats["loyalty"] + clamp_delta(loyalty))
        stats["ambition"] = clamp(stats["ambition"] + clamp_delta(ambition))
        stats["influence"] = clamp(stats["influence"] + clamp_delta(influence))

    adjust(
        "Chancellor",
        loyalty=(state.stability - 50.0) / 30.0,
        ambition=(state.factions["bureaucrats"] - 50.0) / 35.0,
        influence=(state.legitimacy - 50.0) / 30.0,
    )
    adjust(
        "General",
        loyalty=(state.stability - 50.0) / 35.0 + (state.factions["warlords"] - 50.0) / 60.0,
        ambition=(state.factions["warlords"] - 50.0) / 30.0,
        influence=(state.revolt_risk - 50.0) / 30.0,
    )
    adjust(
        "Treasurer",
        loyalty=(state.treasury - 50.0) / 28.0,
        ambition=(50.0 - state.treasury) / 35.0,
        influence=(state.factions["merchants"] - 50.0) / 40.0,
    )
    adjust(
        "ClanHead",
        loyalty=(state.stability - 50.0) / 35.0 + (state.factions["clans"] - 50.0) / 60.0,
        ambition=(state.factions["clans"] - 50.0) / 28.0,
        influence=(state.public_support - 50.0) / 40.0,
    )
    adjust(
        "Spymaster",
        loyalty=(state.legitimacy - 50.0) / 35.0,
        ambition=(state.revolt_risk - 50.0) / 30.0,
        influence=(50.0 - state.public_support) / 40.0,
    )

    return replace(state, actors=actors)
