from __future__ import annotations

from typing import Dict, Iterable, Tuple


def compute_metrics(log: Iterable[Dict]) -> Dict[str, float]:
    min_support = 100.0
    revolt_total = 0.0
    turn_count = 0
    clamp_hits = 0

    for entry in log:
        state = entry["state"]
        support = state["public_support"]
        min_support = min(min_support, support)
        revolt_total += state["revolt_risk"]
        turn_count += 1

        for value in state["factions"].values():
            if value <= 0.0 or value >= 100.0:
                clamp_hits += 1

    avg_revolt = revolt_total / max(turn_count, 1)
    return {
        "min_public_support": round(min_support, 2),
        "avg_rebellion_risk": round(avg_revolt, 2),
        "faction_clamp_hits": clamp_hits,
    }
