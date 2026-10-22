# Persistence and privacy — current architecture

## Durable storage

The source of truth is **private** `bottlework79/krx-stock-data`:
`data/financial_statements_v2.pkl.gz`.

The public `dart_direct_private_v2.yml` job temporarily checks out the
private repository, collects a small DART batch, merges only trusted incoming
records, commits the private v2 DB, then rebuilds a public metadata-only
collection ledger. The private DB is **not** copied into the public Git tree,
cache or artifact.

A public-runner checkout is ephemeral; the data stays in private storage once
the job finishes. Avoid saving secrets in runner output, logs, files or caches.

## Validation of persisted data

`verify_private_dart.yml` runs manually in the public repo. It checks out
the currently persisted private financial database and its matching validation
code, runs the private auditors, then emits only aggregate pass/fail counts.
There are no public validation artifacts and no database writes.

Private-source code is executed in the same temporary runner environment:
treat changes to the public verification workflow and runner script as
security-sensitive. In particular, the workflow currently uses the collector's
existing `PRIVATE_REPO_TOKEN`; a dedicated **read-only** token is preferable.

## Operations

The collection workflow is **workflow_dispatch-only**. The read-only
verification workflow also runs automatically on pushes that change **only**
its workflow or verifier script, not on collection metadata updates. Neither
workflow has a schedule, and the private stock-price screener is separate.
The private stock-price screener has its own separate schedule and is not
moved to this repository.

The original pilot/cache/checkpoint import workflows have been retired.
Their history remains recoverable from Git history; they are not an active
source of stored records. Do not publish private financial DB files, source
rows or full audit details in this public repo.
