from __future__ import annotations

import argparse
import random
from pathlib import Path

from ai.summarize import compact_events, explain_tone, rule_chronicle, rule_explain
from sim.engine import step
from sim.simulate import normalize_actor
from sim.state import initial_state, serialize_state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI summary demo runner")
    parser.add_argument("--scenario", type=str, default="baseline")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--turns", type=int, default=120)
    parser.add_argument("--out", type=str, default="out/demo_report.md")
    return parser.parse_args()


def window_records(records, window: int) -> list[dict]:
    if not records:
        return []
    return records[-max(window, 1) :]


def build_event_log(event) -> dict:
    if event is None:
        return None
    return {
        "id": event.id,
        "title": event.title,
        "actor": normalize_actor(event.actor),
        "cause_tags": event.cause_tags,
        "severity": event.severity,
        "stakeholders": event.stakeholders,
    }


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)
    state = initial_state(args.scenario)

    records: list[dict] = []
    auto_turns: list[int] = []
    forced_turns: list[int] = []
    explain_calls: list[dict] = []
    called_turns: set[int] = set()
    forced_triggered = False
    window = 20

    for _ in range(args.turns):
        state, event = step(state, rng)
        record = {
            "state": serialize_state(state),
            "event": build_event_log(event),
        }
        records.append(record)

        current_turn = record["state"]["turn"]
        if event is not None and event.severity >= 3 and current_turn not in called_turns:
            windowed = window_records(records, window)
            text = rule_explain(compact_events(windowed), windowed)
            explain_calls.append({"turn": current_turn, "mode": "auto", "text": text})
            auto_turns.append(current_turn)
            called_turns.add(current_turn)

        if not forced_triggered:
            windowed = window_records(records, window)
            tone = explain_tone(compact_events(windowed), windowed)
            if tone == "붕괴 직전":
                if current_turn not in called_turns:
                    text = rule_explain(compact_events(windowed), windowed)
                    explain_calls.append({"turn": current_turn, "mode": "forced", "text": text})
                    called_turns.add(current_turn)
                forced_turns.append(current_turn)
                forced_triggered = True

    chronicle = rule_chronicle(compact_events(records))

    report_lines = [
        "# Demo Report",
        "",
        f"- Scenario: {args.scenario}",
        f"- Seed: {args.seed}",
        f"- Turns: {args.turns}",
        f"- Auto explain turns: {auto_turns}",
        f"- Forced explain turns: {forced_turns}",
        "",
        "## Explain Results",
    ]

    if explain_calls:
        for entry in explain_calls:
            report_lines.append(f"- Turn {entry['turn']} ({entry['mode']}): {entry['text']}")
    else:
        report_lines.append("- No explain calls were triggered.")

    report_lines.extend(["", "## Chronicle", chronicle])

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(report_lines), encoding="utf-8")


if __name__ == "__main__":
    main()
