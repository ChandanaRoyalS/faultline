"""Faultline's own telemetry (T6.6): the agent's trace beside the outage it is investigating.

Two seams, one rule. `tracing` puts a span on every model call, tool call, backend read and
investigation; `metrics` (piece 3) exposes queue depth, in-flight investigations and latency at
`/metrics`. **Both are no-ops until something asks** - the SDKs live behind the `observability`
extra, `make check` never imports them, and a process that sets no `OTEL_EXPORTER_OTLP_ENDPOINT`
gets spans that cost a dictionary lookup and export nothing.

The design note is `docs/design/t6.6-self-observability.md`.
"""
