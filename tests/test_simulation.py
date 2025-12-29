import random
from dataclasses import replace

from sim.engine import is_bankrupt, is_riot
from sim.events import EVENTS
from sim.simulate import run_simulation
from sim.state import initial_state


def test_reproducibility_with_seed():
    rng_a = random.Random(42)
    rng_b = random.Random(42)

    log_a, summary_a = run_simulation(8, rng_a)
    log_b, summary_b = run_simulation(8, rng_b)

    assert log_a == log_b
    assert summary_a == summary_b


def test_values_clamped_to_range():
    rng = random.Random(7)
    log, _summary = run_simulation(50, rng)

    for entry in log:
        state = entry["state"]
        for key in ("stability", "legitimacy", "treasury", "food", "public_support", "revolt_risk"):
            assert 0.0 <= state[key] <= 100.0
        for value in state["factions"].values():
            assert 0.0 <= value <= 100.0


def test_event_apply_is_consistent():
    event = next(item for item in EVENTS if item.id == "granary-crackdown")
    state = initial_state()

    updated = event.apply("audit", state)

    assert updated.treasury == state.treasury + 6
    assert updated.stability == state.stability + 2
    assert updated.legitimacy == state.legitimacy + 1
    assert updated.factions["bureaucrats"] == state.factions["bureaucrats"] + 4
    assert updated.factions["merchants"] == state.factions["merchants"] - 2


def test_bankruptcy_and_riot_conditions():
    state = initial_state()
    bankrupt_state = replace(state, treasury=0)
    riot_state = replace(state, public_support=25, stability=35, revolt_risk=65)

    assert is_bankrupt(bankrupt_state)
    assert is_riot(riot_state)


def test_simulation_runs_120_turns():
    rng = random.Random(1)
    log, _summary = run_simulation(120, rng)

    assert len(log) == 120
