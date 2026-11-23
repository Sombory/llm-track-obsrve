"""Auto-instrumentation for Amazon Bedrock's Converse API."""
from __future__ import annotations

from .tracer import Tracer, get_tracer


def instrument_bedrock(client, tracer: Tracer | None = None):
    """Wrap a boto3 bedrock-runtime client so every converse() call is traced."""
    tracer = tracer or get_tracer()
    original = client.converse

    def traced_converse(**kwargs):
        with tracer.span("bedrock.converse", kind="llm", model_id=kwargs.get("modelId")) as s:
            resp = original(**kwargs)
            usage = resp.get("usage", {})
            s.record_usage(kwargs.get("modelId", "default"), usage.get("inputTokens", 0), usage.get("outputTokens", 0))
            s.set(stop_reason=resp.get("stopReason"))
            return resp

    client.converse = traced_converse
    return client
