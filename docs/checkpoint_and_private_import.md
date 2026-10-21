# Checkpoint retention and private import

## Current behavior
- The KRX snapshot is `data/krx_universe.json` (2,548 ticker codes). Update it explicitly when the private KRX price universe changes.
- The incremental pilot caches both `data/financial_statements.pkl.gz` and `data/unavailable_periods.json`.
- Previously unavailable historical reports are skipped on subsequent runs; current-year unavailable reports are rechecked.
- Each successful run uploads both files as a 30-day GitHub Actions artifact and saves a GitHub Actions cache snapshot.
- Cache is best-effort and can be evicted. Artifacts expire. **Neither is permanent storage.**
- The public Actions artifact is not private. Do not upload confidential financial calculations, API credentials, or private analysis outputs.

## Private merge (manual, offline)
1. Download a checkpoint artifact from a successful run.
2. Extract the artifact into a trusted local directory.
3. In the private `krx-stock-data` repository, run:
   `python operations/import_public_dart_checkpoint.py /trusted/path/financial_statements.pkl.gz`
4. Review reported duplicates and new entries.
5. Only after review run the same command with `--apply`.

The importer refuses records outside the private KRX universe, invalid record structures, and conflicting statement rows. It never overwrites an existing statement. **Never unpickle files from untrusted sources.**

## Pending production work
- Choose a licensed, access-controlled, durable storage location for source financial records.
- Automate verified import to the private repo without leaking private data or credentials.
- Add a checkpoint/restore integration test and full-batch performance tests.
- Confirm OpenDART redistribution terms before publishing collected raw financial data in a public artifact or repository.
