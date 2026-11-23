"""Span-based tracer. Each span records one LLM call, agent step or tool call.

    tracer = Tracer(exporters=[JsonlExporter("traces.jsonl")])

    with tracer.span("planner", kind="agent") as s:
        resp = llm(...)
        s.record_usage(model="claude-haiku", input_tokens=120, output_tokens=40)

Spans nest automatically (trace_id / parent_id), so a multi-agent run becomes one trace.
"""
from __future__ import annotations

import contextvars
import functools
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from .pricing import estimate_cost, load_pricing

_current: contextvars.ContextVar["Span | None"] = contextvars.ContextVar("current_span", default=None)


@dataclass
class Span:
    name: str
    kind: str
    trace_id: str
    span_id: str
    parent_id: str | None
    start: float
    end: float | None = None
    latency_ms: float | None = None
    status: str = "ok"
    error: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    quality: dict[str, float] = field(default_factory=dict)
    attributes: dict[str, Any] = field(default_factory=dict)
    _pricing: dict = field(default_factory=dict, repr=False)

    def record_usage(self, model: str, input_tokens: int, output_tokens: int) -> None:
        self.model, self.input_tokens, self.output_tokens = model, input_tokens, output_tokens
        self.cost_usd = estimate_cost(model, input_tokens, output_tokens, self._pricing)

    def record_quality(self, **scores: float) -> None:
        self.quality.update(scores)

    def set(self, **attrs: Any) -> None:
        self.attributes.update(attrs)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("_pricing")
        return d


class Tracer:
    def __init__(self, service: str = "llm-app", exporters: list | None = None, pricing: dict | None = None):
        self.service = service
        self.exporters = exporters or []
        self.pricing = pricing or load_pricing()

    @contextmanager
    def span(self, name: str, kind: str = "llm", **attrs: Any):
        parent = _current.get()
        s = Span(name=name, kind=kind, trace_id=parent.trace_id if parent else uuid.uuid4().hex,
                 span_id=uuid.uuid4().hex[:16], parent_id=parent.span_id if parent else None,
                 start=time.time(), attributes={"service": self.service, **attrs}, _pricing=self.pricing)
        token = _current.set(s)
        t0 = time.perf_counter()
        try:
            yield s
        except Exception as exc:
            s.status, s.error = "error", f"{type(exc).__name__}: {exc}"
            raise
        finally:
            s.end, s.latency_ms = time.time(), round((time.perf_counter() - t0) * 1000, 2)
            _current.reset(token)
            for exporter in self.exporters:
                exporter.export(s)


_default = Tracer()


def get_tracer() -> Tracer:
    return _default


def observe(name: str | None = None, kind: str = "llm", tracer: Tracer | None = None) -> Callable:
    """Decorator. If the function returns an object/dict with usage fields, they are recorded."""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with (tracer or _default).span(name or fn.__name__, kind=kind) as s:
                result = fn(*args, **kwargs)
                usage = result if isinstance(result, dict) else getattr(result, "__dict__", {})
                if "input_tokens" in usage:
                    s.record_usage(usage.get("model", "default"), usage["input_tokens"], usage.get("output_tokens", 0))
                return result
        return wrapper
    return decorator
