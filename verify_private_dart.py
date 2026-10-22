"""Verify the private DART DB on a PUBLIC runner without publishing private data.

Run only from a trusted workflow_dispatch or a temporary owner-authored smoke
test. The private repo is checked out to the runner but never committed to this
public repo. All private subprocess output (including exceptions, tracebacks,
ticker lists, account amounts, and full raw audit diagnostics) is suppressed.

ONLY report aggregate counts, including failures by named phase. Detailed
review stays in the private source tree for the duration of the job; it is
never uploaded as a public artifact or printed in a public Actions log.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PRIVATE = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).parent)) / "private"
DATABASE = PRIVATE / "data" / "financial_statements_v2.pkl.gz"
SUMMARY = PRIVATE / "dart_results" / "verified_calculation" / "parent_net_income_annual_summary.json"
QUARTERLY_SUMMARY = PRIVATE / "dart_results" / "verified_calculation" / "parent_profit_quarterly_ttm_summary.json"

# The commands intentionally call the existing reviewed PRIVATE repository
# scripts: no raw data or private analysis logic is copied into this public repo.
STEPS = (
    ("Account profit scope", ("-m", "operations.audit_dart_json_profit")),
    ("Original account codes", ("-m", "operations.audit_hwacheon_profit_codes")),
    ("Quarterly field structure", ("-m", "operations.audit_quarterly_profit_fields")),
    ("Annual account cross-check", ("-m", "operations.audit_account_codes_cross_year")),
    ("Proposal validation tests", ("-m", "unittest", "discover", "-s", "test", "-p", "test_parent_profit_mapping.py")),
    ("Verified mapping proposals", ("-m", "operations.propose_missing_parent_mappings")),
    ("Calculation mapping tests", ("-m", "unittest", "discover", "-s", "test", "-p", "test_verified_parent_profit.py")),
    ("Remaining account mapping tests", ("-m", "unittest", "discover", "-s", "test", "-p", "test_remaining_parent_mappings.py")),
    ("Annual parent net income calculation", ("-m", "operations.calculate_verified_parent_profit")),
    ("Unresolved annual account diagnosis", ("-m", "operations.diagnose_unresolved_parent_profit")),
    ("Original account diagnosis", ("-m", "operations.diagnose_missing_parent_raw")),
    ("Quarterly and TTM regression tests", ("-m", "unittest", "discover", "-s", "test", "-p", "test_quarterly_parent_profit.py")),
    ("Quarterly and TTM calculation view", ("-m", "operations.calculate_quarterly_parent_profit")),
)

# Only known, non-sensitive result categories are allowed in public logs.
ALLOWED_STATUSES = (
    "standard",
    "verified_nonstandard",
    "verified_nonstandard_cross_year",
    "verified_nonstandard_two_equations",
    "missing_unverified",
    "suspected_wrong_minority_code_manual_review",
    "restated_comparative_conflict_manual_review",
    "ambiguous_multiple_financial_payloads",
    "ambiguous_standard",
)



# Independent aggregate-only categories for the quarterly and TTM view.
ALLOWED_QUARTER_STATES = (
    "standard_parent", "missing_standard_owner", "ambiguous_owner_amounts",
    "ambiguous_multiple_financial_payloads", "missing_q1_fields",
    "q1_from_explicit_ytd", "q1_from_explicit_quarter",
    "q1_quarter_ytd_disagreement", "quarter_ytd_arithmetic_disagreement",
    "ytd_only", "quarter_only",
)
ALLOWED_Q4_STATES = (
    "missing_q3_ytd_or_annual", "unverified_annual_owner_profit",
    "future_comparative_filing_date_unknown", "mixed_statement_scope_blocked",
    "annual_minus_q3_verified_ytd",
)
ALLOWED_TTM_STATES = (
    "missing_or_unverified_current_ytd", "missing_prior_year_quarter_or_annual",
    "missing_or_unverified_prior_amount", "mixed_statement_scope_blocked",
    "future_comparative_filing_date_unknown", "calculated_from_verified_ytd",
    "unverified_annual_owner_profit", "verified_annual",
)


def print_quarterly_summary():
    source = json.loads(QUARTERLY_SUMMARY.read_text(encoding="utf-8"))
    for label, statuses, count_key, allowed in (
        ("QUARTERLY", source.get("quarterly_by_status"),
         "quarterly_periods", ALLOWED_QUARTER_STATES),
        ("Q4", source.get("q4_by_status"), "q4_periods", ALLOWED_Q4_STATES),
        ("TTM", source.get("ttm_by_status"), "ttm_periods", ALLOWED_TTM_STATES),
    ):
        total = source.get(count_key)
        if type(total) is not int or total < 0 or not isinstance(statuses, dict):
            raise RuntimeError(f"Unusable aggregate quarterly report ({label})")
        if any(k not in allowed or type(v) is not int or v < 0
               for k, v in statuses.items()):
            raise RuntimeError(f"Unrecognized aggregate quarterly state ({label})")
        if sum(statuses.values()) != total:
            raise RuntimeError(f"Nonbalancing aggregate quarterly states ({label})")
        print(f"VERIFICATION_{label}_PERIODS={total}")
        for status in allowed:
            if status in statuses:
                print(f"VERIFICATION_{label}_{status.upper()}={statuses[status]}")
    if source.get("database_modified") is not False or source.get("score_modified") is not False:
        raise RuntimeError("Quarterly verification attempted a forbidden write")
    if source.get("historical_backtest_ready") is not False:
        raise RuntimeError("Quarterly future filing dates have not been validated")

def run_private_phase(name, args):
    # Do NOT stream private stdout/stderr to a publicly visible job log.
    # A new public workflow run's logs and artifacts can be read by anyone.
    completed = subprocess.run(
        (sys.executable, *args),
        cwd=PRIVATE,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=240,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"Private validation phase failed ({name}, exit {completed.returncode})")
    print(f"PASS: {name}", flush=True)


def print_safe_summary():
    data = json.loads(SUMMARY.read_text(encoding="utf-8"))
    total = data.get("annual_periods")
    statuses = data.get("by_status")
    if type(total) is not int or total < 0 or not isinstance(statuses, dict):
        raise RuntimeError("Invalid verification summary (details intentionally hidden)")
    # Block unexpected keys to avoid reflecting untrusted or private strings.
    if any(k not in ALLOWED_STATUSES or type(v) is not int or v < 0
           for k, v in statuses.items()):
        raise RuntimeError("Unrecognized verification summary (details intentionally hidden)")
    if sum(statuses.values()) != total:
        raise RuntimeError("Verification counts do not balance (details intentionally hidden)")
    print(f"VERIFICATION_TOTAL_ANNUAL_PERIODS={total}")
    for status in ALLOWED_STATUSES:
        if status in statuses:
            print(f"VERIFICATION_{status.upper()}={statuses[status]}")
    print("RESULTS_REMAIN_PRIVATE=True")
    print("PRIVATE_DATABASE_MODIFIED=False")


def main():
    if not DATABASE.is_file():
        raise RuntimeError("Private input database unavailable (no contents displayed)")
    if not (PRIVATE / "operations" / "verified_parent_profit.py").is_file():
        raise RuntimeError("Private verification source missing")
    for name, args in STEPS:
        run_private_phase(name, args)
    print_safe_summary()
    print_quarterly_summary()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        # Raised messages are constructed from *fixed* stage names and
        # error codes, not raw inputs, private values, or subprocess output.
        print(f"PUBLIC_RUNNER_VERIFICATION_FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
