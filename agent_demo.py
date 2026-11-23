"""Simulates a multi-agent run (planner -> tools -> reporter) and writes traces.jsonl.

    python examples/agent_demo.py && python -m llmobs.report traces.jsonl
"""
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from llmobs import ConsoleExporter, JsonlExporter, Tracer  # noqa: E402
from llmobs.quality import groundedness  # noqa: E402

tracer = Tracer(service="agent-demo", exporters=[JsonlExporter("traces.jsonl"), ConsoleExporter()])
random.seed(1)


def fake_llm(span, model="default", tin=(200, 900), tout=(30, 250), fail_rate=0.03):
    time.sleep(random.uniform(0.01, 0.05))
    if random.random() < fail_rate:
        raise TimeoutError("model timeout")
    span.record_usage(model, random.randint(*tin), random.randint(*tout))


for i in range(25):
    try:
        with tracer.span("orchestrator", kind="agent", run=i):
            with tracer.span("planner", kind="llm") as s:
                fake_llm(s)
            with tracer.span("sql_tool", kind="tool"):
                time.sleep(random.uniform(0.005, 0.02))
            with tracer.span("reporter", kind="llm") as s:
                fake_llm(s, tin=(600, 1500), tout=(150, 400))
                s.record_quality(groundedness=groundedness("churn rate is higher in emerging segment",
                                                           "emerging segment churn rate 31%"))
    except TimeoutError:
        pass
