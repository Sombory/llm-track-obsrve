import json

import pytest

from llmobs import DatadogStatsdExporter, JsonlExporter, Tracer, observe
from llmobs.bedrock import instrument_bedrock
from llmobs.report import load, render_html, summarize


class Collect:
    def __init__(self):
        self.spans = []

    def export(self, span):
        self.spans.append(span)


def test_nested_spans_share_trace_and_cost_is_estimated():
    c = Collect()
    t = Tracer(exporters=[c], pricing={"default": {"input": 1.0, "output": 2.0}})
    with t.span("agent", kind="agent"):
        with t.span("llm") as s:
            s.record_usage("default", 1000, 500)
    child, parent = c.spans
    assert child.trace_id == parent.trace_id and child.parent_id == parent.span_id
    assert child.cost_usd == pytest.approx(2.0)
    assert child.latency_ms >= 0


def test_errors_are_recorded_and_reraised():
    c = Collect()
    t = Tracer(exporters=[c])
    with pytest.raises(ValueError):
        with t.span("boom"):
            raise ValueError("bad")
    assert c.spans[0].status == "error" and "bad" in c.spans[0].error


def test_observe_decorator_reads_usage():
    c = Collect()
    t = Tracer(exporters=[c])

    @observe("call", tracer=t)
    def call():
        return {"model": "default", "input_tokens": 10, "output_tokens": 5}

    call()
    assert c.spans[0].input_tokens == 10


def test_datadog_exporter_emits_dogstatsd_lines():
    dd = DatadogStatsdExporter(port=9)  # discard port, nothing listening
    t = Tracer(exporters=[dd])
    with t.span("reporter") as s:
        s.record_usage("default", 100, 20)
        s.record_quality(groundedness=0.9)
    metrics = "\n".join(dd.sent)
    assert "llm.latency_ms:" in metrics and "|d|#" in metrics
    assert "llm.tokens.input:100|c" in metrics and "llm.quality.groundedness:0.9|g" in metrics


def test_bedrock_instrumentation():
    class FakeClient:
        def converse(self, **kw):
            return {"usage": {"inputTokens": 42, "outputTokens": 7}, "stopReason": "end_turn"}

    c = Collect()
    client = instrument_bedrock(FakeClient(), Tracer(exporters=[c]))
    client.converse(modelId="m1", messages=[])
    assert c.spans[0].input_tokens == 42 and c.spans[0].attributes["stop_reason"] == "end_turn"


def test_report(tmp_path):
    path = tmp_path / "t.jsonl"
    t = Tracer(exporters=[JsonlExporter(path)])
    for _ in range(3):
        with t.span("llm") as s:
            s.record_usage("default", 100, 50)
    df = load(path)
    assert summarize(df).loc["llm", "calls"] == 3
    assert "LLM Observability Report" in render_html(df)
    json.loads(path.read_text().splitlines()[0])
