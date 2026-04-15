# Gateway

## Role
The Gateway is the Orchid entry point for all external API traffic. It handles
TLS termination, request authentication, rate limit enforcement, and request
routing to backend services. It is stateless except for the Redis connection
used for rate limit counters.

## Relationships
- [RateLimiter](RateLimiter.md) — delegates rate limit decisions
- [Router](Router.md) — delegates routing decisions
- [topics/tls-configuration](../topics/tls-configuration.md) — terminates TLS
- [topics/observability](../topics/observability.md) — emits traces and metrics

## Sessions
> Source: [2026-02-10 session-or003]
> Source: [2026-02-20 session-or001]
