# JobQueue

## Role
JobQueue is the PostgreSQL-backed priority queue that holds all pending and
in-progress Skyhook jobs. It is the single source of truth for job state.
Workers poll the JobQueue to claim work; the coordinator inserts new jobs on
behalf of API callers.

## Relationships
- [Coordinator](Coordinator.md) — inserts jobs and monitors queue depth
- [topics/job-scheduling](../topics/job-scheduling.md) — describes scheduling
  policy and retry behavior

## Sessions
> Source: [2026-03-10 session-sk001]
