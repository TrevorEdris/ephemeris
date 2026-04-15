# Decision Log

## [2026-03-10] Use PostgreSQL for persistent job state

**Decision:** All Skyhook job records are stored in PostgreSQL, not in Redis or
an in-memory store.

**Rationale:** Job state must survive service restarts. Redis would require
persistence configuration and adds operational complexity. PostgreSQL already
exists in the stack for user accounts.

**Session:** > Source: [2026-03-10 session-sk001]

---

## [2026-03-05] Authenticate workers with short-lived JWT tokens

**Decision:** Worker nodes authenticate to the Skyhook coordinator using
short-lived JWT tokens (15-minute TTL) issued at worker startup.

**Rationale:** Long-lived API keys increase blast radius on credential leak.
Short-lived tokens limit exposure without requiring complex certificate
infrastructure.

**Session:** > Source: [2026-03-05 session-sk002]
