# KRX DART collector — current operation

This **public** repository runs DART collection and read-only financial-data
verification. All persisted financial statements and private stock analysis
stay in **private** `bottlework79/krx-stock-data`.

## Active GitHub Actions (manual only)

| Workflow | Purpose | Private DB writes |
| --- | --- | --- |
| `dart_direct_private_v2.yml` | Collect DART annual/quarterly JSON, check raw batch, merge into private `data/financial_statements_v2.pkl.gz`, commit private DB, then update public metadata ledger | Yes, only to the private repository |
| `verify_private_dart.yml` | Check out the *already persisted* private DB and private validation code on a public GitHub-hosted runner, run the audits without exposing raw records or row-level amounts | No |

Neither workflow has a push or schedule trigger. To run one: **Actions → select the workflow → Run workflow**.

## Data flow

1. Collection uses `collect_dart.py`, `select_history_batch.py`, `merge_private_v2.py`, and `build_dart_history.py`.
2. The public runner temporarily checks out private `krx-stock-data` with `PRIVATE_REPO_TOKEN`. It saves collected statements to the **private** v2 database and writes only collection *metadata* to this public repository.
3. Verification separately uses `verify_private_dart.py`: it temporarily checks out the same private repository and runs its existing `operations/` auditors. Only aggregate statuses and pass/fail stage names reach the **public** job log.
4. Existing raw DB, stock-price DB, scoring and technical screener remain private. The verification workflow never edits the DB or uploads private data as artifacts.

## Security

- Store `DART_API_KEY` and `PRIVATE_REPO_TOKEN` only in Actions secrets. **Never print or commit secrets.**
- The public runner can read the private repository during a run. Treat public-workflow changes as security-sensitive. Protect `main` and restrict who can change workflows.
- Current `PRIVATE_REPO_TOKEN` is shared with the collector and has write access to private storage. For verification, replace it eventually with a **separate read-only, private-repo-scoped token**, without weakening the collector's write workflow.
- Do not add `upload-artifact` for the private DB or print private-source traceback, ticker details, raw JSON, or amounts in public job logs.
- GitHub logs, cache and generated artifacts have different visibility and retention rules. Public repos must not be used as the storage location for private financial statements.

## Retired, removed paths

The old public pilot/legacy checkpoint, shard export and scope-probe workflows,
and the disabled private DART collector/checkpoint importer have been removed.
Do not use their former entry points. Old financial-data history is retained in
Git, while the current production-like handoff is direct **public runner →
private v2 DB**.

## Related

See `PERSISTENCE.md` for data and token handling. In the private repository,
`operations/verified_parent_profit.py` and related auditors remain necessary:
the public verification workflow **calls them from the temporary private checkout**.
