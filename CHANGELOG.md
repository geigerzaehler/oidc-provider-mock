# Changes

## Unreleased

- Suppress deprecation warnings introduced in Authlib v1.6.

## v0.2.4 - 2025-04-19

- Suppress exception logging on client errors in token endpoint.
- Use correct error code "invalid_grant" when refresh token is not valid.

## v0.2.3 - 2025-04-18

- Add HTTP endpoint to revoke all tokens for a user.

## v0.2.2 - 2025-04-14

- Set initial focus to `sub` input in authorization form.

## v0.2.1 - 2025-03-20

- Add required `httpx` production dependency.
