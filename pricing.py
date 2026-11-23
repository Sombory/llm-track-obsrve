"""Token pricing used to estimate cost per call.

The values below are EXAMPLE placeholders (USD per 1K tokens). Always load the current
prices for your models and region (e.g. from the AWS Bedrock pricing page) via
`load_pricing("pricing.json")` before relying on cost figures.
"""
from __future__ import annotations

import json
from pathlib import Path

EXAMPLE_PRICING = {
    "default": {"input": 0.001, "output": 0.005},
    "mock-llm": {"input": 0.0, "output": 0.0},
}


def load_pricing(path: str | Path | None = None) -> dict:
    return json.loads(Path(path).read_text()) if path else dict(EXAMPLE_PRICING)


def estimate_cost(model: str, input_tokens: int, output_tokens: int, pricing: dict) -> float:
    p = pricing.get(model, pricing["default"])
    return round(input_tokens / 1000 * p["input"] + output_tokens / 1000 * p["output"], 6)
