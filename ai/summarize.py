from __future__ import annotations

import json
import os
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib import request

from .prompts import CHRONICLE_SYSTEM, CHRONICLE_USER, EXPLAIN_SYSTEM, EXPLAIN_USER
from .mappings import CAUSE_TAG_KR


def resolve_log_path(scenario: str, seed: int, log_path: Optional[str]) -> Path:
    if log_path:
        return Path(log_path)

    base = Path("logs")
    if scenario == "baseline":
        candidates = [base / f"run_{seed}.jsonl", base / "run.jsonl"]
    else:
        candidates = [base / f"run_{scenario}_{seed}.jsonl", base / f"run_{scenario}.jsonl"]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[-1]


def load_jsonl(path: Path) -> List[Dict]:
    records: List[Dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            records.append(json.loads(line))
    return records


def extract_events(records: Iterable[Dict]) -> List[Dict]:
    return [record for record in records if record.get("event")]


def filter_recent(records: List[Dict], window: int) -> List[Dict]:
    if not records:
        return []
    last_turn = max(record.get("state", {}).get("turn", 0) for record in records)
    threshold = last_turn - max(window, 1)
    return [record for record in records if record.get("state", {}).get("turn", 0) > threshold]


def filter_turns(records: List[Dict], turns: int) -> List[Dict]:
    limit = max(turns, 1)
    return [record for record in records if record.get("state", {}).get("turn", 0) <= limit]


def compact_events(records: Iterable[Dict]) -> List[Dict]:
    compact: List[Dict] = []
    for record in records:
        event = record.get("event")
        if not event:
            continue
        compact.append(
            {
                "turn": record.get("state", {}).get("turn", 0),
                "id": event.get("id"),
                "actor": event.get("actor"),
                "severity": event.get("severity"),
                "cause_tags": event.get("cause_tags", []),
                "stakeholders": event.get("stakeholders", []),
            }
        )
    return compact


def build_context(events: List[Dict]) -> str:
    lines = []
    for event in events:
        tags = ",".join(event.get("cause_tags", []))
        stakeholders = ",".join(event.get("stakeholders", []))
        lines.append(
            f"id={event.get('id')} actor={event.get('actor')} severity={event.get('severity')} "
            f"tags={tags} stakeholders={stakeholders}"
        )
    return "\n".join(lines)


def rule_explain(events: List[Dict], records: List[Dict]) -> str:
    tags = Counter(tag for event in events for tag in event.get("cause_tags", []))
    tag_list = [item for item, _count in tags.most_common(2)]
    tone = explain_tone(events, records)
    max_sev = max([event.get("severity", 1) for event in events] or [1])

    if tag_list:
        tag_names = [CAUSE_TAG_KR.get(tag, tag) for tag in tag_list]
        if len(tag_names) == 1:
            cause_sentence = f"{tone} 단계에서 {tag_names[0]}의 균열이 불씨로 솟는다."
        else:
            cause_sentence = (
                f"{tone} 단계에서 {tag_names[0]}와 {tag_names[1]}의 균열이 동시에 흔들린다."
            )
    else:
        cause_sentence = f"{tone} 단계이지만 원인을 압축하기엔 사건 기록이 너무 희미하다."

    actor_counts = Counter(event.get("actor") for event in events if event.get("actor"))
    top_actor = actor_counts.most_common(1)[0][0] if actor_counts else "미상"
    actor_sentence = f"{tone}의 칼날을 쥔 결정적 행위자는 {top_actor}이며 심각도 {max_sev}의 충돌을 부른다."

    if tone == "붕괴 직전":
        risk_sentence = "다음 충돌은 억제선을 넘어 파국으로 떨어질 조짐이다."
    elif tone == "위기":
        risk_sentence = "다음 충돌이 이어지면 파국의 문턱을 넘을 조짐이다."
    else:
        risk_sentence = "조짐은 약하지만 방치하면 파국의 문턱으로 치달을 조짐이다."

    return " ".join([cause_sentence, actor_sentence, risk_sentence])


def explain_tone(events: List[Dict], records: List[Dict]) -> str:
    avg_rebellion = (
        statistics.mean(record.get("state", {}).get("revolt_risk", 0.0) for record in records)
        if records
        else 0.0
    )
    max_sev = max([event.get("severity", 1) for event in events] or [1])
    if max_sev >= 5 or avg_rebellion >= 75:
        return "붕괴 직전"
    if max_sev >= 4 or avg_rebellion >= 60:
        return "위기"
    return "주의"


def rule_chronicle(events: List[Dict]) -> str:
    lines: List[str] = []
    ordered_events = sorted(events, key=lambda event: event.get("turn", 0))
    prioritized = [event for event in ordered_events if event.get("severity", 1) >= 3]
    if not prioritized:
        prioritized = ordered_events

    for event in prioritized[:6]:
        tags = ", ".join(event.get("cause_tags", []))
        actor = event.get("actor", "system")
        event_id = event.get("id", "unknown")
        lines.append(
            f"- [S{event.get('severity')}] {actor} 주도로 {event_id} 사건이 기록되었고 태그는 {tags}다."
        )

    while len(lines) < 6:
        lines.append("- 특별한 변동 없이 경과를 관찰했다.")

    return "\n".join(lines[:10])


def call_openai(messages: List[Dict], model: str) -> Optional[str]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
    }

    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]
    except Exception:
        return None


def normalize_explain(text: str) -> Optional[str]:
    cleaned = " ".join(text.split())
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", cleaned) if s]
    if len(sentences) < 3:
        return None
    return " ".join(sentences[:3])


def normalize_chronicle(text: str) -> Optional[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    normalized = []
    for line in lines:
        normalized.append(line if line.startswith("- ") else f"- {line}")
    if not (6 <= len(normalized) <= 10):
        return None
    return "\n".join(normalized)


def explain_summary(
    scenario: str, seed: int, turn_window: int, log_path: Optional[str]
) -> Dict[str, str]:
    path = resolve_log_path(scenario, seed, log_path)
    records = load_jsonl(path)
    windowed = filter_recent(records, turn_window)
    event_records = extract_events(windowed)
    events = compact_events(event_records)

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    context = build_context(events)
    messages = [
        {"role": "system", "content": EXPLAIN_SYSTEM},
        {"role": "user", "content": EXPLAIN_USER.format(events=context)},
    ]
    response = call_openai(messages, model)
    if response:
        normalized = normalize_explain(response)
        if normalized:
            return {"mode": "llm", "text": normalized}

    rule_text = rule_explain(events, windowed)
    return {"mode": "rule", "text": rule_text}


def chronicle_summary(
    scenario: str, seed: int, turns: int, log_path: Optional[str]
) -> Dict[str, str]:
    path = resolve_log_path(scenario, seed, log_path)
    records = load_jsonl(path)
    limited = filter_turns(records, turns)
    event_records = extract_events(limited)
    events = compact_events(event_records)

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    context = build_context(events)
    messages = [
        {"role": "system", "content": CHRONICLE_SYSTEM},
        {"role": "user", "content": CHRONICLE_USER.format(events=context)},
    ]
    response = call_openai(messages, model)
    if response:
        normalized = normalize_chronicle(response)
        if normalized:
            return {"mode": "llm", "text": normalized}

    rule_text = rule_chronicle(events)
    return {"mode": "rule", "text": rule_text}
