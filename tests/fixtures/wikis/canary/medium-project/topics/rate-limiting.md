# Rate Limiting

## Overview
Orchid enforces rate limits on all inbound API requests using a sliding window
algorithm backed by Redis. Limits are configured per API key and per route.

## Details

### 2026-02-15 (session-or002)
The sliding window uses a 60-second window with per-key counters stored in
Redis as sorted sets. Each request increments the counter for the current
second and queries the sum across the trailing 60 seconds.

Default limits:
- Anonymous requests: 100 req/min
- Authenticated API keys: 1000 req/min
- Premium tier API keys: 10000 req/min

### 2026-02-20 (session-or001)
Route-level overrides: specific routes can have tighter limits than the
per-key default. The `/upload` route is capped at 10 req/min for all keys
to protect storage backends.

When a request exceeds the rate limit, Orchid returns HTTP 429 with a
`Retry-After` header indicating the number of seconds until the window
resets for that key.

## Sessions
> Source: [2026-02-15 session-or002]
> Source: [2026-02-20 session-or001]
