# NFR-0010. Gate releases on a smoke test against real dependencies

## Attribute

Operations / release engineering.

## Description

Before a release is considered verified, the built `runner` image
shall be run against real Postgres, Redis, S3, and Keycloak, with
`/health/ready` polled (5s interval, 5s timeout, 30 retries, 150s
start period) until it reports healthy.

## Source

Operators/SRE; release engineering. Implemented in `compose.yml`
(repo root), invoked from `.github/workflows/release.yml`.

## Verification

CI fails the release workflow if the smoke-test stack's
`/health/ready` polling doesn't succeed within the configured
retries.
