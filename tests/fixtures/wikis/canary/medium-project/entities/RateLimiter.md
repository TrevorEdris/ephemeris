# RateLimiter

## Role
RateLimiter enforces per-key and per-route request quotas using a sliding
window algorithm backed by Redis. It is called synchronously on every inbound
request before routing. Requests that exceed the limit are rejected with
HTTP 429.

## Relationships
- [Gateway](Gateway.md) — invokes RateLimiter on each request
- [topics/rate-limiting](../topics/rate-limiting.md) — documents the algorithm,
  limits by tier, and route overrides

## Sessions
> Source: [2026-02-15 session-or002]
