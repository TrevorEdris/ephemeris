# Observability

## Overview
Orchid emits request traces via OpenTelemetry, exposes Prometheus metrics on
`:9090/metrics`, and writes structured access logs to stdout in JSON format.

## Details

### 2026-02-25 (session-or007)
Trace propagation: Orchid reads the `traceparent` header from inbound requests
and forwards it to backend services. If no `traceparent` is present, Orchid
generates a new root span.

Prometheus metrics exposed:
- `orchid_requests_total{route, status_class}` — counter
- `orchid_request_duration_seconds{route}` — histogram (p50/p95/p99)
- `orchid_rate_limit_rejections_total{api_key_tier}` — counter
- `orchid_upstream_errors_total{service, error_type}` — counter

### 2026-02-27 (session-or008)
Access logs include: timestamp, request ID, method, path, upstream service,
HTTP status, duration_ms, and api_key_id (hashed). No PII is logged.

## Sessions
> Source: [2026-02-25 session-or007]
> Source: [2026-02-27 session-or008]
