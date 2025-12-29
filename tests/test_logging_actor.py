import random

from sim.engine import step
from sim.simulate import normalize_actor
from sim.state import ACTOR_ROLES, initial_state, serialize_state


def test_actor_logged_for_warlord_events():
    rng = random.Random(7)
    state = initial_state("warlord")
    log = []

    for _ in range(50):
        state, event = step(state, rng)
        log.append(
            {
                "state": serialize_state(state),
                "event": None
                if event is None
                else {
                    "id": event.id,
                    "title": event.title,
                    "actor": normalize_actor(event.actor),
                },
            }
        )

    for entry in log:
        event = entry["event"]
        if event is None:
            continue
        assert "actor" in event
        assert event["actor"] in ACTOR_ROLES
        assert "id" in event
