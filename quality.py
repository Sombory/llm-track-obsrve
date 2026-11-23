"""Cheap, deterministic quality checks to attach to spans. Swap in LLM-as-judge for production."""
from __future__ import annotations

import json
import re


def groundedness(answer: str, context: str) -> float:
    words = set(re.findall(r"[a-z]{4,}", answer.lower()))
    ctx = set(re.findall(r"[a-z]{4,}", context.lower()))
    return round(len(words & ctx) / max(len(words), 1), 3)


def is_valid_json(text: str) -> float:
    try:
        json.loads(text)
        return 1.0
    except (ValueError, TypeError):
        return 0.0


def refusal(answer: str) -> float:
    return float(bool(re.search(r"\b(i can't|i cannot|i don't know|not able to)\b", answer.lower())))
