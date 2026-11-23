"""Exporters: JSONL (for analysis/reporting), console, and Datadog via DogStatsD.

DatadogStatsdExporter speaks the DogStatsD wire protocol over UDP, so it works with
any Datadog Agent (default localhost:8125) without extra dependencies.
"""
from __future__ import annotations

import json
import socket
from pathlib import Path


class JsonlExporter:
    def __init__(self, path: str | Path = "traces.jsonl"):
        self.path = Path(path)

    def export(self, span) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(span.to_dict(), default=str) + "\n")


class ConsoleExporter:
    def export(self, span) -> None:
        print(f"[{span.status}] {span.kind}:{span.name} {span.latency_ms}ms "
              f"tokens={span.input_tokens}/{span.output_tokens} cost=${span.cost_usd:.5f}")


class DatadogStatsdExporter:
    """Emits metrics such as llm.latency_ms, llm.tokens.input, llm.cost_usd, llm.errors, llm.quality.*"""

    def __init__(self, host: str = "localhost", port: int = 8125, prefix: str = "llm", extra_tags: list[str] | None = None):
        self.addr, self.prefix = (host, port), prefix
        self.extra_tags = extra_tags or []
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sent: list[str] = []  # kept for testing/debugging

    def _tags(self, span) -> str:
        tags = [f"span:{span.name}", f"kind:{span.kind}", f"status:{span.status}",
                f"model:{span.model or 'none'}", f"service:{span.attributes.get('service', 'llm-app')}"]
        return "|#" + ",".join(tags + self.extra_tags)

    def _send(self, metric: str) -> None:
        self.sent.append(metric)
        try:
            self.sock.sendto(metric.encode(), self.addr)
        except OSError:
            pass  # observability must never break the app

    def export(self, span) -> None:
        tags, p = self._tags(span), self.prefix
        self._send(f"{p}.latency_ms:{span.latency_ms}|d{tags}")
        self._send(f"{p}.requests:1|c{tags}")
        if span.status == "error":
            self._send(f"{p}.errors:1|c{tags}")
        if span.input_tokens or span.output_tokens:
            self._send(f"{p}.tokens.input:{span.input_tokens}|c{tags}")
            self._send(f"{p}.tokens.output:{span.output_tokens}|c{tags}")
            self._send(f"{p}.cost_usd:{span.cost_usd}|c{tags}")
        for name, value in span.quality.items():
            self._send(f"{p}.quality.{name}:{value}|g{tags}")
