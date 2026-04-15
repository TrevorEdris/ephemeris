# Router

## Role
The Router selects the backend service for a given inbound request based on
path prefixes and host headers. Routing rules are loaded from `orchid.routes.yaml`
and hot-reloaded within 5 seconds of file changes. The Router also implements
canary traffic splitting by `canary_weight` configuration.

## Relationships
- [Gateway](Gateway.md) — called by Gateway after rate limiting passes
- [topics/request-routing](../topics/request-routing.md) — routing rule format,
  match order, and canary routing behavior

## Sessions
> Source: [2026-02-12 session-or004]
> Source: [2026-02-22 session-or006]
