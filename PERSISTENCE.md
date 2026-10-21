# Collection persistence and privacy

The public pilot workflow uses a versioned GitHub Actions cache with a unique key per run and a restore prefix. This avoids immutable-key staleness. Cache retention is finite and eviction is possible; it is NOT a permanent database.

The pilot also uploads a short-lived artifact even if the collector exits with an error, provided the database file exists. The artifact may be accessible to users with repository access and should not contain secrets. It is not a substitute for durable storage.

## Durable destination: private analysis repository

A separate private repository should receive a validated, versioned, checksummed financial database through a narrowly scoped GitHub token or GitHub App. Do not put a private repository write token in a public workflow until its permissions, allowed actions, and destination are reviewed. Never print a token.

Before enabling permanent collection:
1. Confirm redistribution conditions for DART source data and avoid public raw DB publication until approved.
2. Create a private-only data import endpoint or a restricted fine-grained token with contents write only on the private repository.
3. Store the credential in public repository Actions secrets; do not expose it in logs or source.
4. Validate checksum, schema, source universe and record counts on the private side before replacement.
5. Test one tiny batch, rollback, then resume.

The public repository's KRX universe is a snapshot of 2,548 public ticker identifiers from the existing private price database. Refresh it when the private price universe changes. The public pilot does not modify the private database.
