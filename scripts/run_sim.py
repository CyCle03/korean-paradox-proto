from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from sim.simulate import run_simulation, write_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Korean Paradox simulation runner")
    parser.add_argument("--turns", type=int, default=120, help="Number of turns to simulate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--out", type=str, default="logs/run.jsonl", help="Output JSONL path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)
    log, summary = run_simulation(args.turns, rng)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_path, log)

    print("Simulation summary")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
