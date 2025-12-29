import json
import re

from ai.summarize import chronicle_summary, explain_summary


def test_rule_summaries_format(tmp_path):
    log_path = tmp_path / "sample.jsonl"
    entries = [
        {
            "state": {"turn": 1, "public_support": 50, "revolt_risk": 40},
            "event": {
                "id": "minor-riot",
                "title": "소규모 폭동",
                "actor": "Chancellor",
                "cause_tags": ["riot", "security"],
                "severity": 2,
                "stakeholders": ["Chancellor"],
            },
        },
        {
            "state": {"turn": 2, "public_support": 45, "revolt_risk": 55},
            "event": {
                "id": "trade-charter",
                "title": "상단의 특허",
                "actor": "Treasurer",
                "cause_tags": ["trade", "economy"],
                "severity": 2,
                "stakeholders": ["Treasurer"],
            },
        },
    ]
    with log_path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    explain = explain_summary("warlord", 7, 20, str(log_path))
    assert explain["mode"] == "rule"
    assert "\n" not in explain["text"]
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", explain["text"]) if s]
    assert len(sentences) == 3

    chronicle = chronicle_summary("warlord", 7, 120, str(log_path))
    assert chronicle["mode"] == "rule"
    lines = [line for line in chronicle["text"].splitlines() if line]
    assert 6 <= len(lines) <= 10
    assert all(line.startswith("- ") for line in lines)
