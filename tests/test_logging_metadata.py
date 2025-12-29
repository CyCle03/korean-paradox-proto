import random

from sim.engine import step
from sim.events import CAUSE_TAGS
from sim.simulate import normalize_actor
from sim.state import ACTOR_ROLES, initial_state, serialize_state


def test_event_logs_include_metadata():
    rng = random.Random(9)
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
                    "cause_tags": event.cause_tags,
                    "severity": event.severity,
                    "stakeholders": event.stakeholders,
                },
            }
        )

    for entry in log:
        event = entry["event"]
        if event is None:
            continue
        assert event["actor"] in ACTOR_ROLES
        assert event["id"]
        assert 1 <= len(event["cause_tags"]) <= 3
        assert all(tag in CAUSE_TAGS for tag in event["cause_tags"])
        assert 1 <= event["severity"] <= 5
        assert len(event["stakeholders"]) <= 2
        assert all(name in ACTOR_ROLES for name in event["stakeholders"])
