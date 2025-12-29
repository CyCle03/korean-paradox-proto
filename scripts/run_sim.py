from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ai.summarize import compact_events, rule_explain
from sim.engine import (
    DECISION_CAUSE_TAGS,
    DECISION_DURATION,
    DECISION_ID,
    apply_decision_immediate,
    apply_decision_tick,
    is_bankrupt,
    is_riot,
    step,
)
from sim.metrics import compute_metrics
from sim.simulate import run_simulation, write_jsonl
from sim.state import ACTOR_ROLES, initial_state, serialize_state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Korean Paradox simulation runner")
    parser.add_argument("--turns", type=int, default=120, help="Number of turns to simulate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--out", type=str, default="logs/run.jsonl", help="Output JSONL path")
    parser.add_argument(
        "--scenario",
        type=str,
        default="baseline",
        choices=["baseline", "famine", "deficit", "warlord"],
        help="Scenario preset for initial conditions",
    )
    return parser.parse_args()


def run_with_scenario(turns: int, rng, scenario: str) -> Tuple[List[Dict], Dict]:
    state = initial_state(scenario)
    log: List[Dict] = []
    bankruptcies = 0
    riots = 0
    support_total = 0.0
    decision_choice: str | None = None
    decision_remaining = 0

    for _ in range(turns):
        if decision_remaining > 0 and decision_choice:
            state = apply_decision_tick(state, decision_choice)
            decision_remaining -= 1

        state, event = step(state, rng)
        if is_bankrupt(state):
            bankruptcies += 1
        if is_riot(state):
            riots += 1
        support_total += state.public_support

        record = {
            "state": serialize_state(state),
            "event": None
            if event is None
            else {
                "id": event.id,
                "title": event.title,
                "actor": event.actor if event.actor in ACTOR_ROLES else "Chancellor",
                "cause_tags": event.cause_tags,
                "severity": event.severity,
                "stakeholders": event.stakeholders,
            },
        }

        if decision_choice is None and (
            is_riot(state) or state.revolt_risk >= 55.0
        ):
            windowed = log[-20:] + [record]
            rule_explain(compact_events(windowed), windowed)
            decision_choice = "A" if rng.random() < 0.5 else "B"
            state = apply_decision_immediate(state, decision_choice)
            decision_remaining = DECISION_DURATION
            record["decision_id"] = DECISION_ID
            record["choice"] = decision_choice
            record["actor"] = "Chancellor"
            record["cause_tags"] = DECISION_CAUSE_TAGS

        log.append(record)

    avg_support = support_total / max(turns, 1)
    summary = {
        "bankruptcies": bankruptcies,
        "riots": riots,
        "avg_public_support": round(avg_support, 2),
        "final_factions": state.factions,
    }
    return log, summary


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)
    if args.scenario == "baseline":
        log, summary = run_simulation(args.turns, rng)
    else:
        log, summary = run_with_scenario(args.turns, rng, args.scenario)

    summary.update(compute_metrics(log))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_path, log)

    print("Simulation summary")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
