# Coordinator

## Role
The Coordinator is the central Skyhook service that accepts job submissions
from API clients, manages the JobQueue, issues authentication tokens to worker
nodes, and monitors overall system health. It is the only component with direct
write access to the PostgreSQL job store.

## Relationships
- [JobQueue](JobQueue.md) — owns and writes to the job queue
- [topics/worker-authentication](../topics/worker-authentication.md) — issues
  JWT tokens to workers via `/auth/token`
- [topics/job-scheduling](../topics/job-scheduling.md) — enforces scheduling
  policy when assigning jobs

## Sessions
> Source: [2026-03-05 session-sk002]
> Source: [2026-03-10 session-sk001]
