from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from .state import State, apply_deltas, apply_faction_deltas


@dataclass(frozen=True)
class EventChoice:
    id: str
    label: str


@dataclass(frozen=True)
class Event:
    id: str
    title: str
    weight: float
    priority: int
    choices: List[EventChoice]
    condition: Callable[[State], bool]
    apply: Callable[[str, State], State]

    def choose(self, rng) -> str:
        return rng.choice(self.choices).id


def choose_event(state: State, rng) -> Optional[Event]:
    eligible = [event for event in EVENTS if event.condition(state)]
    if not eligible:
        return None

    max_priority = max(event.priority for event in eligible)
    top = [event for event in eligible if event.priority == max_priority]
    weights = [event.weight for event in top]
    total = sum(weights)
    pick = rng.random() * total
    upto = 0.0
    for event, weight in zip(top, weights):
        upto += weight
        if upto >= pick:
            return event
    return top[-1]


def event_granary(choice: str, state: State) -> State:
    if choice == "audit":
        state = apply_deltas(state, treasury=6, stability=2, legitimacy=1)
        return apply_faction_deltas(state, {"bureaucrats": 4, "merchants": -2})
    state = apply_deltas(state, treasury=-3, stability=-2, public_support=2)
    return apply_faction_deltas(state, {"merchants": 5, "bureaucrats": -3})


def event_border(choice: str, state: State) -> State:
    if choice == "reinforce":
        state = apply_deltas(state, treasury=-4, stability=2, food=-2)
        return apply_faction_deltas(state, {"warlords": 3, "royal": 2})
    state = apply_deltas(state, stability=-3, legitimacy=-2, public_support=-1)
    return apply_faction_deltas(state, {"warlords": 4, "royal": -3})


def event_reform(choice: str, state: State) -> State:
    if choice == "promote":
        state = apply_deltas(state, legitimacy=4, public_support=3)
        return apply_faction_deltas(state, {"bureaucrats": 4, "clans": -2})
    state = apply_deltas(state, stability=-2, legitimacy=-3)
    return apply_faction_deltas(state, {"clans": 3, "bureaucrats": -2})


def event_trade(choice: str, state: State) -> State:
    if choice == "open":
        state = apply_deltas(state, treasury=5, public_support=1)
        return apply_faction_deltas(state, {"merchants": 4, "warlords": -1})
    state = apply_deltas(state, treasury=-2, stability=2)
    return apply_faction_deltas(state, {"royal": 2, "merchants": -2})


def event_harvest(choice: str, state: State) -> State:
    if choice == "release":
        state = apply_deltas(state, food=8, public_support=3)
        return apply_faction_deltas(state, {"royal": 1, "clans": -1})
    state = apply_deltas(state, food=-2, treasury=4, public_support=-3)
    return apply_faction_deltas(state, {"clans": 2, "royal": -1})


def event_royal_guard(choice: str, state: State) -> State:
    if choice == "expand":
        state = apply_deltas(state, stability=3, treasury=-4)
        return apply_faction_deltas(state, {"royal": 4, "bureaucrats": -1})
    state = apply_deltas(state, stability=-2, legitimacy=-1)
    return apply_faction_deltas(state, {"bureaucrats": 2, "royal": -2})


def event_tax(choice: str, state: State) -> State:
    if choice == "raise":
        state = apply_deltas(state, treasury=6, public_support=-4, stability=-2)
        return apply_faction_deltas(state, {"bureaucrats": 2, "merchants": -2})
    state = apply_deltas(state, treasury=-3, public_support=3)
    return apply_faction_deltas(state, {"merchants": 2, "bureaucrats": -1})


def event_court_choice(choice: str, state: State) -> State:
    if choice == "conciliate":
        state = apply_deltas(state, legitimacy=2, stability=2)
        return apply_faction_deltas(state, {"clans": 3, "royal": -2})
    state = apply_deltas(state, legitimacy=-2, stability=-3)
    return apply_faction_deltas(state, {"royal": 3, "clans": -3})


def event_black_market(choice: str, state: State) -> State:
    if choice == "crackdown":
        state = apply_deltas(state, stability=2, public_support=-1)
        return apply_faction_deltas(state, {"bureaucrats": 2, "merchants": -3})
    state = apply_deltas(state, treasury=3, public_support=1)
    return apply_faction_deltas(state, {"merchants": 3, "bureaucrats": -1})


def event_famine_relief(choice: str, state: State) -> State:
    if choice == "mobilize":
        state = apply_deltas(state, food=6, treasury=-4, public_support=4)
        return apply_faction_deltas(state, {"bureaucrats": 2, "royal": 1})
    state = apply_deltas(state, food=-3, stability=-4, public_support=-4)
    return apply_faction_deltas(state, {"clans": 2, "royal": -2})


EVENTS: List[Event] = [
    Event(
        id="granary-crackdown",
        title="곡창의 균열",
        weight=1.2,
        priority=2,
        choices=[
            EventChoice(id="audit", label="감사단을 보내 세곡을 회수한다."),
            EventChoice(id="pardon", label="유출을 눈감고 상단과 타협한다."),
        ],
        condition=lambda state: state.turn == 1,
        apply=event_granary,
    ),
    Event(
        id="border-lords",
        title="변방의 성벽",
        weight=1.0,
        priority=1,
        choices=[
            EventChoice(id="reinforce", label="방어선을 강화한다."),
            EventChoice(id="delay", label="군량을 아끼고 방치한다."),
        ],
        condition=lambda state: state.factions["warlords"] >= 50,
        apply=event_border,
    ),
    Event(
        id="bureaucrat-reform",
        title="관료 개혁 요구",
        weight=1.1,
        priority=1,
        choices=[
            EventChoice(id="promote", label="개혁안을 수용한다."),
            EventChoice(id="reject", label="문벌의 힘을 보전한다."),
        ],
        condition=lambda state: state.factions["bureaucrats"] >= 55,
        apply=event_reform,
    ),
    Event(
        id="trade-charter",
        title="상단의 특허",
        weight=1.0,
        priority=1,
        choices=[
            EventChoice(id="open", label="개방을 허락한다."),
            EventChoice(id="limit", label="상단을 규제한다."),
        ],
        condition=lambda state: state.factions["merchants"] >= 50,
        apply=event_trade,
    ),
    Event(
        id="harvest-appeal",
        title="풍년 분배",
        weight=0.9,
        priority=1,
        choices=[
            EventChoice(id="release", label="곡물 창고를 연다."),
            EventChoice(id="tax", label="추가 세곡을 걷는다."),
        ],
        condition=lambda state: state.food >= 55,
        apply=event_harvest,
    ),
    Event(
        id="royal-guard",
        title="친위대 확충",
        weight=1.2,
        priority=2,
        choices=[
            EventChoice(id="expand", label="친위대를 확대한다."),
            EventChoice(id="delay", label="확충을 유예한다."),
        ],
        condition=lambda state: state.legitimacy <= 55,
        apply=event_royal_guard,
    ),
    Event(
        id="tax-reform",
        title="세제 개편",
        weight=1.1,
        priority=1,
        choices=[
            EventChoice(id="raise", label="세율을 올린다."),
            EventChoice(id="ease", label="세율을 낮춘다."),
        ],
        condition=lambda state: state.treasury <= 45,
        apply=event_tax,
    ),
    Event(
        id="court-petition",
        title="문벌 상소",
        weight=1.0,
        priority=2,
        choices=[
            EventChoice(id="conciliate", label="상소를 수용한다."),
            EventChoice(id="reject", label="왕권을 강조한다."),
        ],
        condition=lambda state: state.factions["clans"] >= 52 and state.stability < 60,
        apply=event_court_choice,
    ),
    Event(
        id="black-market",
        title="암시장 확산",
        weight=0.8,
        priority=1,
        choices=[
            EventChoice(id="crackdown", label="단속을 강화한다."),
            EventChoice(id="tolerate", label="거래를 묵인한다."),
        ],
        condition=lambda state: state.public_support < 55,
        apply=event_black_market,
    ),
    Event(
        id="famine-relief",
        title="기근 대응",
        weight=1.3,
        priority=3,
        choices=[
            EventChoice(id="mobilize", label="구휼과 군량 조달을 지시한다."),
            EventChoice(id="delay", label="지원을 늦춘다."),
        ],
        condition=lambda state: state.food < 40,
        apply=event_famine_relief,
    ),
]
