# Decision Log

## [2026-02-20] Rate limiting at the gateway layer, not per-service

**Decision:** Rate limiting is enforced by the Orchid API gateway for all
inbound requests. Individual backend services do not implement their own rate
limiting.

**Rationale:** Centralizing rate limiting in the gateway eliminates duplicate
configuration and ensures consistent behavior across all services. Backend
services can trust that any request reaching them has already passed rate
checks.

**Session:** > Source: [2026-02-20 session-or001]

---

## [2026-02-15] Use Redis for rate limit counters

**Decision:** Orchid stores rate limit counters in Redis with a 60-second
sliding window. Redis was chosen over in-memory counters for multi-instance
deployments.

**Rationale:** In-memory counters do not work when the gateway runs as multiple
replicas. Redis provides atomic increment operations and TTL-based expiry that
map cleanly to the sliding window algorithm.

**Session:** > Source: [2026-02-15 session-or002]

---

## [2026-02-10] TLS termination at the gateway boundary

**Decision:** TLS is terminated at the Orchid gateway. Traffic between Orchid
and backend services uses mTLS within the cluster.

**Rationale:** External TLS termination at the gateway simplifies certificate
management for backend services. mTLS inside the cluster provides mutual
authentication without exposing services to the public internet directly.

**Session:** > Source: [2026-02-10 session-or003]
