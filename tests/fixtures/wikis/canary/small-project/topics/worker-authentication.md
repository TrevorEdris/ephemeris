# Worker Authentication

## Overview
Skyhook worker nodes authenticate to the coordinator using short-lived JWT
tokens. Tokens are issued at worker startup and refreshed automatically before
expiry.

## Details

### 2026-03-05 (session-sk002)
The coordinator exposes a `/auth/token` endpoint. Workers call this endpoint
with a pre-shared bootstrap secret (set via environment variable
`SKYHOOK_BOOTSTRAP_SECRET`). The endpoint returns a JWT with a 15-minute TTL
and a list of granted capabilities.

Workers must refresh the token when fewer than 2 minutes remain on the current
TTL. A refresh failure causes the worker to stop accepting new jobs and
complete any in-flight jobs before shutting down gracefully.

### 2026-03-08 (session-sk004)
Token rotation: the coordinator rotates the signing key every 24 hours. Old
tokens signed with the previous key remain valid for their full TTL. Tokens
signed with keys older than 48 hours are rejected.

## Sessions
> Source: [2026-03-05 session-sk002]
> Source: [2026-03-08 session-sk004]
