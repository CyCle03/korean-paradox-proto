from __future__ import annotations

import argparse
import csv
import random
import statistics
from pathlib import Path
from typing import Dict, List

from sim.engine import is_bankrupt, is_riot, step
from sim.metrics import compute_metrics
from sim.state import initial_state, serialize_state

SCENARIOS = ("baseline", "famine", "deficit", "warlord")
METRIC_KEYS = (
    "riots",
    "bankruptcies",
    "avg_public_support",
    "avg_rebellion_risk",
    "min_public_support",
    "faction_clamp_hits",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed sweep for scenario validation")
    parser.add_argument("--turns", type=int, default=120, help="Turns per run")
    parser.add_argument("--seeds", nargs=2, type=int, default=[0, 99], help="Seed range")
    parser.add_argument("--out", type=str, default="out", help="Output directory")
    return parser.parse_args()


def run_once(turns: int, seed: int, scenario: str) -> Dict:
    rng = random.Random(seed)
    state = initial_state(scenario)
    log: List[Dict] = []
    bankruptcies = 0
    riots = 0
    support_total = 0.0

    for _ in range(turns):
        state, event = step(state, rng)
        if is_bankrupt(state):
            bankruptcies += 1
        if is_riot(state):
            riots += 1
        support_total += state.public_support
        log.append(
            {
                "state": serialize_state(state),
                "event": None if event is None else {"id": event.id, "title": event.title},
            }
        )

    metrics = compute_metrics(log)
    avg_support = support_total / max(turns, 1)
    return {
        "seed": seed,
        "riots": riots,
        "bankruptcies": bankruptcies,
        "avg_public_support": round(avg_support, 2),
        "avg_rebellion_risk": metrics["avg_rebellion_risk"],
        "min_public_support": metrics["min_public_support"],
        "faction_clamp_hits": metrics["faction_clamp_hits"],
        "collapsed": int(
            metrics["min_public_support"] == 0.0 and metrics["avg_rebellion_risk"] >= 70.0
        ),
    }


def write_csv(path: Path, rows: List[Dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: List[Dict]) -> Dict[str, Dict[str, float]]:
    summary: Dict[str, Dict[str, float]] = {}
    for key in METRIC_KEYS:
        values = [row[key] for row in rows]
        summary[key] = {
            "mean": round(statistics.mean(values), 2),
            "std": round(statistics.pstdev(values), 2),
        }
    collapse_rate = sum(row["collapsed"] for row in rows) / max(len(rows), 1)
    summary["collapse_rate"] = {"mean": round(collapse_rate, 2), "std": 0.0}
    return summary


def print_summary(summaries: Dict[str, Dict[str, Dict[str, float]]]) -> None:
    print("Scenario Summary")
    for scenario, stats in summaries.items():
        print(f"- {scenario}")
        for key in METRIC_KEYS:
            metric = stats[key]
            print(f"  {key}: mean={metric['mean']}, std={metric['std']}")
        collapse = stats["collapse_rate"]["mean"]
        print(f"  collapse_rate: {collapse}")


def main() -> None:
    args = parse_args()
    start_seed, end_seed = args.seeds
    seeds = range(start_seed, end_seed + 1)
    out_dir = Path(args.out)

    summaries: Dict[str, Dict[str, Dict[str, float]]] = {}
    for scenario in SCENARIOS:
        rows = [run_once(args.turns, seed, scenario) for seed in seeds]
        write_csv(out_dir / f"{scenario}.csv", rows)
        summaries[scenario] = summarize(rows)

    print_summary(summaries)


if __name__ == "__main__":
    main()
