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

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

PRIVATE = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).parent)) / "private"
DATABASE = PRIVATE / "data" / "financial_statements_v2.pkl.gz"
SUMMARY = PRIVATE / "dart_results" / "verified_calculation" / "parent_net_income_annual_summary.json"
QUARTERLY_SUMMARY = PRIVATE / "dart_results" / "verified_calculation" / "parent_profit_quarterly_ttm_summary.json"
TRIAGE_SUMMARY = PRIVATE / "dart_results" / "quarterly_triage" / "quarterly_parent_review_summary.json"
VALUATION_SUMMARY = PRIVATE / "dart_results" / "verified_valuation" / "verified_ttm_valuation_summary.json"
FILING_EVIDENCE = PRIVATE / "data" / "dart_filing_evidence.json"
FINANCIAL_SCORE_SUMMARY = PRIVATE / "dart_results" / "financial_score_pilot" / "financial_score_summary.json"

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
    ("Quarterly discrepancy triage regression tests", ("-m", "unittest", "discover", "-s", "test", "-p", "test_quarterly_parent_triage.py")),
    ("Diagnose quarterly account and amount discrepancies", ("-m", "operations.diagnose_quarterly_parent_discrepancies")),
    ("TTM valuation bridge regression tests", ("-m", "unittest", "discover", "-s", "test", "-p", "test_verified_ttm_valuation.py")),
    ("Current-only TTM PER snapshot tests", ("-m", "unittest", "discover", "-s", "test", "-p", "test_current_ttm_per_snapshot.py")),
    ("Current-only PER snapshot without market network calls", ("-m", "operations.current_ttm_per_snapshot")),
    ("Existing market cap integration regression tests", ("-m", "unittest", "discover", "-s", "test", "-p", "test_existing_market_cap_bridge.py")),  # Includes original-filing-only safety checks
    ("DART filing dates and receipts regression tests", ("-m", "unittest", "discover", "-s", "test", "-p", "test_dart_filing_evidence.py")),
    ("Original filing owner table parser tests", ("-m", "unittest", "discover", "-s", "test", "-p", "test_original_dart_owner_table.py")),
    ("Original filing isolated table context tests", ("-m", "unittest", "discover", "-s", "test", "-p", "test_original_dart_table_context.py")),
    ("Original DART document parser offline tests", ("-m", "unittest", "discover", "-s", "test", "-p", "test_original_dart_document.py")),
    ("Validate date-gated TTM valuation bridge", ("-m", "operations.calculate_verified_ttm_valuation")),
    ("DART financial score pilot regression tests", ("-m", "unittest", "discover", "-s", "test", "-p", "test_dart_financial_score_pilot.py")),
    ("Calculate read-only DART financial score pilot", ("-m", "operations.score_verified_dart_financials")),
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

# Explicit fixed categories only. Do not reflect private row labels or values.
TRIAGE_STATES = frozenset({
    "missing_standard_owner",
    "quarter_ytd_arithmetic_disagreement",
    "q1_quarter_ytd_disagreement",
})
TRIAGE_CATEGORIES = frozenset({
    "nonstandard_two_field_attribution_candidate",
    "nonstandard_partial_or_ambiguous_equation",
    "standard_owner_code_without_usable_numbers",
    "nonstandard_owner_label_without_balanced_equation",
    "nonstandard_minority_label_only",
    "no_recognized_owner_attribution",
    "parent_only_arithmetic_conflict_total_reconciles",
    "parent_and_total_arithmetic_conflict",
    "parent_arithmetic_conflict_total_inconclusive",
    "prior_owner_components_unavailable",
    "q1_three_month_cumulative_disagreement",
})
PER_STATES = frozenset({
    "unverified_ttm_profit",
    "nonpositive_ttm_profit",
    "missing_dated_market_cap_and_filing_evidence",
    "ambiguous_market_cap_evidence",
    "unapproved_market_cap_source",
    "invalid_market_cap",
    "missing_dated_filing_evidence",
    "quote_before_financial_disclosure",
    "quote_after_requested_asof_date",
    "quote_stale_relative_to_filing",
    "provisional_per_external_evidence_not_authenticated",
})

def safe_int(value):
    return type(value) is int and value >= 0

def print_triage_summary():
    info = json.loads(TRIAGE_SUMMARY.read_text(encoding="utf-8"))
    total = info.get("total_review_cases")
    by_status, by_category = info.get("by_original_status"), info.get("by_category")
    if not safe_int(total) or not isinstance(by_status, dict) or not isinstance(by_category, dict):
        raise RuntimeError("Unusable quarterly triage summary")
    if any(k not in TRIAGE_STATES or not safe_int(v) for k,v in by_status.items()):
        raise RuntimeError("Unexpected quarterly triage status")
    if any(
        not safe_int(v) or len(k.split("/")) != 2 or
        k.split("/")[0] not in TRIAGE_STATES or
        k.split("/")[1] not in TRIAGE_CATEGORIES
        for k,v in by_category.items()
    ):
        raise RuntimeError("Unexpected quarterly triage category")
    if sum(by_status.values()) != total or sum(by_category.values()) != total:
        raise RuntimeError("Quarterly triage counts do not balance")
    if info.get("auto_mapped") != 0 or info.get("private_db_modified") is not False:
        raise RuntimeError("Quarterly audit violated read-only policy")
    print(f"VERIFICATION_QUARTERLY_TRIAGE_TOTAL={total}")
    for kind in sorted(TRIAGE_STATES):
        print(f"VERIFICATION_TRIAGE_{kind.upper()}={by_status.get(kind,0)}")
    for category in sorted(TRIAGE_CATEGORIES):
        number = sum(v for key,v in by_category.items() if key.split("/")[1] == category)
        if number:
            print(f"VERIFICATION_TRIAGE_CAUSE_{category.upper()}={number}")

def print_valuation_summary():
    info = json.loads(VALUATION_SUMMARY.read_text(encoding="utf-8"))
    total = info.get("ttm_periods")
    statuses = info.get("per_by_status")
    if not safe_int(total) or not isinstance(statuses, dict):
        raise RuntimeError("Unusable valuation summary")
    if any(k not in PER_STATES or not safe_int(v) for k,v in statuses.items()):
        raise RuntimeError("Unexpected valuation status")
    if sum(statuses.values()) != total:
        raise RuntimeError("Valuation counts do not balance")
    if info.get("database_modified") is not False or info.get("financial_score_modified") is not False:
        raise RuntimeError("Valuation bridge violated read-only policy")
    if info.get("historical_backtest_ready") is not False:
        raise RuntimeError("Prematurely marked valuation as backtest ready")
    if info.get("provided_market_cap_evidence_rows") != 0:
        raise RuntimeError("Public verification must not load nonpublic quote evidence")
    if info.get("per_calculable_provisional") != 0:
        raise RuntimeError("Public verifier must withhold unevidenced PER")
    positive = info.get("positive_verified_ttm")
    yoy = info.get("yoy_calculable")
    if not safe_int(positive) or not safe_int(yoy) or positive > total or yoy > total:
        raise RuntimeError("Invalid TTM quality counts")
    official = info.get("official_first_filings")
    reconciled = info.get("verified_financial_versions")
    metadata = info.get("official_metadata_periods")
    if not all(safe_int(k) for k in (official, reconciled, metadata)):
        raise RuntimeError("Invalid official filing-date count")
    if reconciled > official or official > metadata:
        raise RuntimeError("Invalid official filing evidence coverage")
    print(f"VERIFICATION_OFFICIAL_FILING_METADATA={metadata}")
    print(f"VERIFICATION_ORIGINAL_FILING_RECEIPTS={official}")
    print(f"VERIFICATION_RECONCILED_FINANCIAL_VERSIONS={reconciled}")
    print(f"VERIFICATION_TTM_VALUATION_PERIODS={total}")
    print(f"VERIFICATION_TTM_POSITIVE_NET={positive}")
    print(f"VERIFICATION_TTM_YOY_CALCULATED={yoy}")
    print("VERIFICATION_TTM_PER_WITHOUT_PRICE_EVIDENCE=0")

def check_private_filing_evidence():
    if not FILING_EVIDENCE.exists():
        print("VERIFICATION_FILING_EVIDENCE_NOT_YET_COLLECTED=True")
        return
    sidecar = json.loads(FILING_EVIDENCE.read_text(encoding="utf-8"))
    if sidecar.get("schema_version") != 1 or not isinstance(sidecar.get("entries"), dict):
        raise RuntimeError("Invalid private filing evidence")
    if (sidecar.get("financial_rows_version_verified") is not False
            or sidecar.get("historical_backtest_ready") is not False):
        raise RuntimeError("Filing evidence incorrectly asserts historical data validation")
    count = 0
    for key, item in sidecar["entries"].items():
        if not isinstance(item, dict):
            raise RuntimeError("Invalid private filing entry")
        keyparts = key.split("|")
        if len(keyparts) != 3 or keyparts != [
                str(item.get("ticker")), str(item.get("year")), str(item.get("report"))]:
            raise RuntimeError("Private filing identity mismatch")
        if (item.get("financial_rows_version_verified") is not False
                or item.get("historical_backtest_ready") is not False):
            raise RuntimeError("Historical financial row provenance not established")
        status = item.get("status")
        if status not in ("first_unamended_filing_found",
                          "no_unamended_original_filing", "ambiguous_first_filing_date"):
            raise RuntimeError("Unknown filing evidence status")
        if status == "first_unamended_filing_found":
            receipt = str(item.get("filing_receipt") or "")
            date = str(item.get("filing_date") or "")
            if not (len(receipt) == 14 and receipt.isascii() and receipt.isdecimal()):
                raise RuntimeError("Invalid private receipt evidence")
            try:
                parsed = dt.date.fromisoformat(date)
            except ValueError:
                raise RuntimeError("Invalid private filing date") from None
            if parsed.isoformat() != date:
                raise RuntimeError("Noncanonical private filing date")
            count += 1
    valuation = json.loads(VALUATION_SUMMARY.read_text(encoding="utf-8"))
    if (valuation.get("official_first_filings") != count
            or valuation.get("official_metadata_periods") != len(sidecar["entries"])):
        raise RuntimeError("Filing receipt coverage differs between private sidecar and valuation summary")
    print(f"VERIFICATION_FIRST_DART_FILINGS_MATCHED={count}")
    print(f"VERIFICATION_DART_FILING_SIDECAR_ENTRIES={len(sidecar['entries'])}")
    print("VERIFICATION_FIRST_FILING_DOES_NOT_VALIDATE_HISTORICAL_VALUES=True")

def print_financial_score_summary():
    data = json.loads(FINANCIAL_SCORE_SUMMARY.read_text(encoding="utf-8"))
    count = data.get("companies")
    scored = data.get("provisional_scored")
    withheld = data.get("withheld_insufficient_coverage")
    if not all(safe_int(v) for v in (count, scored, withheld)):
        raise RuntimeError("Invalid DART score aggregate counts")
    if scored + withheld != count or data.get("total_weight") != 100:
        raise RuntimeError("DART financial score aggregate does not balance")
    if data.get("valuation_weight_neutral") != 15 or data.get("minimum_verified_weight_for_score") != 50:
        raise RuntimeError("Unexpected research financial scoring definition")
    if any(data.get(k) is not False for k in (
        "price_db_modified", "financial_db_modified",
        "existing_financial_score_modified", "technical_rank_modified",
        "historical_backtest_ready"
    )):
        raise RuntimeError("Research score must not modify production data or rankings")
    print(f"VERIFICATION_FINANCIAL_SCORE_COMPANIES={count}")
    print(f"VERIFICATION_FINANCIAL_SCORE_PROVISIONAL={scored}")
    print(f"VERIFICATION_FINANCIAL_SCORE_WITHHELD={withheld}")
    print("VERIFICATION_FINANCIAL_VALUATION_NEUTRAL_WEIGHT=15")
    print("VERIFICATION_TECHNICAL_RANKINGS_UNCHANGED=True")


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
        if name == "Original filing owner table parser tests":
            import re
            # Capture only known fixture test identifiers. Never print source
            # traceback, amount, ticker, filing receipt or assertion diff.
            diagnostic = subprocess.run(
                (sys.executable, "-m", "unittest", "discover", "-s", "test",
                 "-p", "test_original_dart_owner_table.py"),
                cwd=PRIVATE, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=45, check=False,
            )
            allowed = {
                "test_krw_row_exact_match_is_candidate_only",
                "test_rounded_millions_do_not_equal_won",
                "test_different_table_with_same_number_not_owner_candidate",
                "test_comprehensive_or_minority_label_excluded",
                "test_multiple_owner_rows_ambiguous",
                "test_unknown_unit_is_not_approved",
                "test_negative_parentheses",
                "test_audit_preserves_no_auto_approval",
                "test_original_dart_owner_table",
            }
            failures = sorted(set(
                re.findall(r"(?:FAIL|ERROR): (test_[A-Za-z0-9_]+)", diagnostic.stderr.decode("utf-8", errors="replace"))
            ) & allowed)
            if failures:
                print("PUBLIC_SAFE_FAILING_UNIT_TESTS=" + ",".join(failures), flush=True)
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
    print_triage_summary()
    print_valuation_summary()
    check_private_filing_evidence()
    print_financial_score_summary()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        # Raised messages are constructed from *fixed* stage names and
        # error codes, not raw inputs, private values, or subprocess output.
        print(f"PUBLIC_RUNNER_VERIFICATION_FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
