from __future__ import annotations

from dataclasses import replace
from typing import Optional, Tuple

from .events import Event, choose_event
from .state import State, apply_deltas


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

    event = choose_event(updated, rng)
    if event is None:
        return updated, None

    choice = event.choose(rng)
    updated = event.apply(choice, updated)
    return updated, event
