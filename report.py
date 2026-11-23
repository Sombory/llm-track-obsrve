"""Aggregate a traces.jsonl file and render a self-contained HTML dashboard.

    python -m llmobs.report traces.jsonl --html report.html
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

import pandas as pd


def load(path: str | Path) -> pd.DataFrame:
    return pd.DataFrame([json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()])


def summarize(df: pd.DataFrame, by: str = "name") -> pd.DataFrame:
    g = df.groupby(by)
    out = pd.DataFrame({
        "calls": g.size(),
        "p50_ms": g.latency_ms.quantile(0.5),
        "p95_ms": g.latency_ms.quantile(0.95),
        "error_rate": g.status.apply(lambda s: (s == "error").mean()),
        "input_tokens": g.input_tokens.sum(),
        "output_tokens": g.output_tokens.sum(),
        "cost_usd": g.cost_usd.sum(),
    })
    return out.round({"p50_ms": 1, "p95_ms": 1, "error_rate": 3, "cost_usd": 5}).sort_values("calls", ascending=False)


def _bars(series: pd.Series, unit: str) -> str:
    peak = max(series.max(), 1e-9)
    rows = "".join(
        f'<div class="row"><span class="lbl">{html.escape(str(k))}</span>'
        f'<span class="bar" style="width:{v / peak * 100:.1f}%"></span><span class="val">{v:,.1f}{unit}</span></div>'
        for k, v in series.items())
    return f'<div class="bars">{rows}</div>'


def render_html(df: pd.DataFrame) -> str:
    s = summarize(df)
    traces = df.trace_id.nunique()
    kpis = [("Traces", f"{traces}"), ("Spans", f"{len(df)}"),
            ("p95 latency", f"{df.latency_ms.quantile(.95):,.0f} ms"),
            ("Error rate", f"{(df.status == 'error').mean():.1%}"),
            ("Tokens", f"{int(df.input_tokens.sum() + df.output_tokens.sum()):,}"),
            ("Est. cost", f"${df.cost_usd.sum():,.4f}")]
    kpi_html = "".join(f'<div class="kpi"><div class="k">{k}</div><div class="v">{v}</div></div>' for k, v in kpis)
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LLM Observability Report</title><style>
body{{font-family:system-ui,sans-serif;margin:24px;color:#1b2430;background:#f7f9fc}}
h1{{font-size:22px}} h2{{font-size:16px;margin-top:28px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px}}
.kpi{{background:#fff;border:1px solid #e3e8ef;border-radius:8px;padding:12px}} .k{{color:#5b6573;font-size:12px}} .v{{font-size:20px;font-weight:600}}
.bars .row{{display:flex;align-items:center;gap:8px;margin:4px 0}} .lbl{{width:160px;font-size:13px}}
.bar{{height:14px;background:#1f4e79;border-radius:3px;display:inline-block}} .val{{font-size:12px;color:#5b6573}}
table{{border-collapse:collapse;background:#fff;font-size:13px;width:100%}} td,th{{border:1px solid #e3e8ef;padding:6px 8px;text-align:right}} th:first-child,td:first-child{{text-align:left}}
</style></head><body><h1>LLM Observability Report</h1><div class="kpis">{kpi_html}</div>
<h2>p95 latency by span</h2>{_bars(s.p95_ms, " ms")}
<h2>Estimated cost by span (USD)</h2>{_bars(s.cost_usd * 1000, " m$")}
<h2>Summary</h2>{s.to_html()}</body></html>"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("traces")
    ap.add_argument("--html", default="report.html")
    args = ap.parse_args()
    frame = load(args.traces)
    print(summarize(frame).to_string())
    Path(args.html).write_text(render_html(frame), encoding="utf-8")
    print(f"\nHTML report written to {args.html}")
