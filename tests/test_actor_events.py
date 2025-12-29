from sim.events import EVENTS


def test_events_include_actor_field():
    for event in EVENTS:
        assert event.actor
