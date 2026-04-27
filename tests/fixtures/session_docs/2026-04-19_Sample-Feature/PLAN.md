# Plan — Sample Feature

## Target files

- `auth/reset.go` — new endpoint
- `migrations/001_password_reset_tokens.sql` — new table

## Steps

1. Add migration.
2. Implement endpoint.
3. Wire to router.

## Risks

- Token leak via logs.

## Verification

- `go test ./auth/...`
