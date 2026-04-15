# Job Scheduling

## Overview
Skyhook schedules distributed jobs using a priority queue backed by PostgreSQL.
Jobs are claimed by worker nodes via a polling loop with configurable backoff.

## Details

### 2026-03-10 (session-sk001)
The scheduler assigns jobs to workers based on queue priority and worker
capacity tags. A job marked `priority: high` is always dequeued before
`priority: normal` jobs, regardless of insertion order.

Workers report their capacity tags at startup (e.g., `gpu`, `cpu-only`,
`large-memory`). The scheduler only assigns a job to a worker whose tags
satisfy the job's requirements.

### 2026-03-12 (session-sk003)
Retry policy: failed jobs are retried up to 3 times with exponential backoff
starting at 30 seconds. After 3 failures the job moves to the dead-letter
queue and an alert fires.

## Sessions
> Source: [2026-03-10 session-sk001]
> Source: [2026-03-12 session-sk003]
