# Session — Sample Feature

## Goal

Add password reset flow.

### Prompt 1
> Add password reset flow to the auth module.

- Surveyed auth module.
- Drafted PLAN.

### Prompt 2
> Implement.

- Implemented `/auth/reset` endpoint.

## Decisions

- 2026-04-19 — Use one-time tokens with 1-hour TTL, not session reuse.
