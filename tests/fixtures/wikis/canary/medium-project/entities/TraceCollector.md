# TraceCollector

## Role
TraceCollector is the Orchid component responsible for OpenTelemetry trace
propagation. It reads the `traceparent` header from inbound requests, generates
root spans when none is present, and injects the propagated trace context into
upstream requests forwarded to backend services.

## Relationships
- [Gateway](Gateway.md) — TraceCollector runs as middleware within Gateway
- [topics/observability](../topics/observability.md) — describes tracing,
  metrics, and access log format

## Sessions
> Source: [2026-02-25 session-or007]
