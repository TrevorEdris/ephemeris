# Discovery — Sample Feature

## Findings

- Auth module uses bcrypt for hashing.
- No reset-token table exists yet.

## Gaps

- Need migration for `password_reset_tokens` table.
- No email send infra.

## Open questions

- TTL: 15min, 1hr, or 24hr?
