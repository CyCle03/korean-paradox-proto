from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, List, Optional

from .state import State, apply_deltas, apply_faction_deltas

MINOR_RIOT_COOLDOWN_TURNS = 2
MAJOR_RIOT_COOLDOWN_TURNS = 6
MINOR_RIOT_BREACH_RISK = 75.0
MINOR_RIOT_BREACH_PROB = 0.15
CAUSE_TAGS = (
    "stability",
    "economy",
    "factions",
    "security",
    "intrigue",
    "food",
    "trade",
    "bureaucracy",
    "clan",
    "military",
    "riot",
)


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
    actor: str = "system"
    cause_tags: List[str] = field(default_factory=list)
    severity: int = 1
    stakeholders: List[str] = field(default_factory=list)

    def choose(self, rng) -> str:
        return rng.choice(self.choices).id


def choose_event(state: State, rng) -> Optional[Event]:
    eligible = [event for event in EVENTS if event.condition(state)]
    if not eligible:
        return None

    eligible = apply_riot_gate(eligible, state, rng)
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


def riot_condition(state: State) -> bool:
    return (
        state.public_support <= 30.0
        and state.stability <= 40.0
        and state.revolt_risk >= 60.0
        and state.turn >= state.riot_cooldown_until
    )


def minor_riot_condition(state: State) -> bool:
    return (
        state.public_support <= 45.0
        and state.stability <= 55.0
        and state.revolt_risk >= 55.0
    )


def apply_riot_gate(events: List[Event], state: State, rng) -> List[Event]:
    if state.turn >= state.riot_cooldown_until:
        return events

    gated: List[Event] = []
    for event in events:
        if event.id != "minor-riot":
            gated.append(event)
            continue
        if state.revolt_risk >= MINOR_RIOT_BREACH_RISK and rng.random() < MINOR_RIOT_BREACH_PROB:
            gated.append(event)
    return gated


def event_minor_riot(choice: str, state: State) -> State:
    _choice = choice
    state = apply_deltas(
        state,
        stability=-2,
        public_support=-3,
        revolt_risk=2,
        treasury=-1,
        legitimacy=-1,
    )
    return replace(state, riot_cooldown_until=state.turn + MINOR_RIOT_COOLDOWN_TURNS)


def event_major_riot(choice: str, state: State) -> State:
    _choice = choice
    state = apply_deltas(
        state,
        stability=5,
        public_support=7,
        revolt_risk=-20,
        treasury=-3,
        legitimacy=-1,
    )
    return replace(state, riot_cooldown_until=state.turn + MAJOR_RIOT_COOLDOWN_TURNS)


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


def event_chancellor(choice: str, state: State) -> State:
    if choice == "council":
        return apply_deltas(state, stability=0.5, legitimacy=0.5)
    return apply_deltas(state, stability=-0.5, legitimacy=-0.5)


def event_general(choice: str, state: State) -> State:
    if choice == "patrols":
        state = apply_deltas(state, stability=0.5, revolt_risk=-1, treasury=-0.5)
        return apply_faction_deltas(state, {"warlords": 0.5})
    state = apply_deltas(state, stability=-0.5, revolt_risk=0.5)
    return apply_faction_deltas(state, {"warlords": 0.5})


def event_treasurer(choice: str, state: State) -> State:
    if choice == "audit":
        return apply_deltas(state, treasury=1, public_support=-0.5)
    return apply_deltas(state, treasury=0.5, public_support=0.5)


def event_clan_head(choice: str, state: State) -> State:
    if choice == "pledge":
        state = apply_deltas(state, stability=0.5, public_support=0.5)
        return apply_faction_deltas(state, {"clans": 0.5, "royal": -0.5})
    state = apply_deltas(state, stability=-0.5, legitimacy=-0.5)
    return apply_faction_deltas(state, {"clans": 0.5})


def event_spymaster(choice: str, state: State) -> State:
    if choice == "reports":
        return apply_deltas(state, stability=0.5, revolt_risk=-1)
    return apply_deltas(state, stability=-0.5, revolt_risk=0.5)


EVENTS: List[Event] = [
    Event(
        id="minor-riot",
        title="소규모 폭동",
        weight=0.9,
        priority=3,
        choices=[
            EventChoice(id="contain", label="경비를 늘려 소요를 막는다."),
            EventChoice(id="appease", label="현장 조정을 통해 진정시킨다."),
        ],
        condition=minor_riot_condition,
        apply=event_minor_riot,
        actor="system",
        cause_tags=["riot", "security"],
        severity=2,
        stakeholders=[],
    ),
    Event(
        id="major-riot",
        title="대규모 폭동",
        weight=1.2,
        priority=4,
        choices=[
            EventChoice(id="contain", label="병력을 동원해 폭동을 진압한다."),
            EventChoice(id="appease", label="급히 민심을 달래며 진정시킨다."),
        ],
        condition=riot_condition,
        apply=event_major_riot,
        actor="system",
        cause_tags=["riot", "security"],
        severity=4,
        stakeholders=[],
    ),
    Event(
        id="chancellor-council",
        title="재상 회의",
        weight=0.2,
        priority=0,
        choices=[
            EventChoice(id="council", label="개혁 의제를 올려 합의를 만든다."),
            EventChoice(id="delay", label="논의를 미루고 현상 유지를 택한다."),
        ],
        condition=lambda state: (
            state.actors["Chancellor"]["influence"] >= 70
            and state.actors["Chancellor"]["loyalty"] >= 55
        ),
        apply=event_chancellor,
        actor="Chancellor",
        cause_tags=["bureaucracy", "stability"],
        severity=2,
        stakeholders=["Chancellor"],
    ),
    Event(
        id="general-patrols",
        title="장군의 순찰",
        weight=0.2,
        priority=0,
        choices=[
            EventChoice(id="patrols", label="도성을 순찰해 질서를 다잡는다."),
            EventChoice(id="standby", label="병력을 대기시켜 부담을 줄인다."),
        ],
        condition=lambda state: state.actors["General"]["ambition"] >= 70,
        apply=event_general,
        actor="General",
        cause_tags=["security", "military"],
        severity=2,
        stakeholders=["General"],
    ),
    Event(
        id="treasurer-audit",
        title="재정 감사",
        weight=0.2,
        priority=0,
        choices=[
            EventChoice(id="audit", label="지출을 엄격히 통제한다."),
            EventChoice(id="relief", label="지원을 유지하며 완충한다."),
        ],
        condition=lambda state: (
            state.actors["Treasurer"]["loyalty"] >= 70 and state.treasury <= 55
        ),
        apply=event_treasurer,
        actor="Treasurer",
        cause_tags=["economy", "bureaucracy"],
        severity=2,
        stakeholders=["Treasurer"],
    ),
    Event(
        id="clanhead-pledge",
        title="문벌의 충성",
        weight=0.2,
        priority=0,
        choices=[
            EventChoice(id="pledge", label="충성 서약을 받아낸다."),
            EventChoice(id="ignore", label="침묵 속 긴장을 두고 본다."),
        ],
        condition=lambda state: state.actors["ClanHead"]["influence"] >= 70,
        apply=event_clan_head,
        actor="ClanHead",
        cause_tags=["clan", "stability"],
        severity=2,
        stakeholders=["ClanHead"],
    ),
    Event(
        id="spymaster-reports",
        title="정보 보고",
        weight=0.2,
        priority=0,
        choices=[
            EventChoice(id="reports", label="잠복 정보를 바탕으로 정비한다."),
            EventChoice(id="overlook", label="위협을 과소평가한다."),
        ],
        condition=lambda state: state.actors["Spymaster"]["influence"] >= 70,
        apply=event_spymaster,
        actor="Spymaster",
        cause_tags=["intrigue", "security"],
        severity=2,
        stakeholders=["Spymaster"],
    ),
    Event(
        id="chancellor-faction-lean",
        title="재상의 중재",
        weight=0.2,
        priority=0,
        choices=[
            EventChoice(id="council", label="세력 간 균형을 강조한다."),
            EventChoice(id="delay", label="일정을 늦춰 변화를 피한다."),
        ],
        condition=lambda state: state.actors["Chancellor"]["loyalty"] <= 35,
        apply=event_chancellor,
        actor="Chancellor",
        cause_tags=["bureaucracy", "factions"],
        severity=2,
        stakeholders=["Chancellor"],
    ),
    Event(
        id="general-frontier",
        title="군단의 동향",
        weight=0.2,
        priority=0,
        choices=[
            EventChoice(id="patrols", label="군단을 분산 배치한다."),
            EventChoice(id="standby", label="병력을 한곳에 모은다."),
        ],
        condition=lambda state: (
            state.actors["General"]["influence"] >= 65 and state.factions["warlords"] >= 60
        ),
        apply=event_general,
        actor="General",
        cause_tags=["military", "security"],
        severity=2,
        stakeholders=["General"],
    ),
    Event(
        id="spymaster-whispers",
        title="밀담 소문",
        weight=0.2,
        priority=0,
        choices=[
            EventChoice(id="reports", label="소문을 통제한다."),
            EventChoice(id="overlook", label="흐름을 지켜본다."),
        ],
        condition=lambda state: state.actors["Spymaster"]["ambition"] >= 70,
        apply=event_spymaster,
        actor="Spymaster",
        cause_tags=["intrigue", "stability"],
        severity=2,
        stakeholders=["Spymaster"],
    ),
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
        actor="system",
        cause_tags=["economy", "food"],
        severity=3,
        stakeholders=[],
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
        actor="system",
        cause_tags=["military", "security"],
        severity=3,
        stakeholders=[],
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
        actor="system",
        cause_tags=["bureaucracy", "factions"],
        severity=3,
        stakeholders=[],
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
        actor="system",
        cause_tags=["trade", "economy"],
        severity=2,
        stakeholders=[],
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
        actor="system",
        cause_tags=["food", "economy"],
        severity=2,
        stakeholders=[],
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
        actor="system",
        cause_tags=["security", "factions"],
        severity=3,
        stakeholders=[],
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
        actor="system",
        cause_tags=["economy", "bureaucracy"],
        severity=3,
        stakeholders=[],
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
        actor="system",
        cause_tags=["clan", "factions"],
        severity=3,
        stakeholders=[],
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
        actor="system",
        cause_tags=["trade", "intrigue"],
        severity=2,
        stakeholders=[],
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
        actor="system",
        cause_tags=["food", "stability"],
        severity=4,
        stakeholders=[],
    ),
]
