"""Backfill OpenDART official periodic filing dates into PRIVATE metadata only.

Run in public GitHub Actions with a temporary private checkout. NEVER upload
the private DB, filing evidence rows, or list responses as public artifacts.
Print aggregate counters only. Do not overwrite statement rows or any scores.

OpenDART /api/list.json is official for rcept_no / rcept_dt. One query per
company (plus pagination), and strict calendar-year filing type matching.
Correction/amendment or competing filings: record evidence for human review,
but refuse using the earliest date as proof the archived JSON was available
at that time.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import os
import pickle
import re
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests

API = "https://opendart.fss.or.kr/api/list.json"
REPORT_FOR_MONTH = {("사업보고서", "12"): "annual",
                    ("반기보고서", "06"): "half",
                    ("분기보고서", "03"): "q1",
                    ("분기보고서", "09"): "q3"}
TITLE = re.compile(
    r"^\\s*(?P<prefix>(?:\\[[^]]+\\]\\s*)*)"
    r"(?P<kind>사업보고서|반기보고서|분기보고서)"
    r"\\s*\\(\\s*(?P<year>\\d{4})\\s*\\.\\s*(?P<month>\\d{2})\\s*\\)"
)
RECEIPT = re.compile(r"\\d{14}")
CORP = re.compile(r"\\d{8}")
TICKER = re.compile(r"\\d{6}")
KEY_PATTERN = re.compile(r"\\d{6}\\|\\d{4}\\|(annual|q1|half|q3)\\|CFS")


def filing_identity(record):
    """Match only ordinary calendar-year statements, no unknown fiscal ends."""
    title = str(record.get("report_nm") or "")
    match = TITLE.match(title)
    if not match:
        return None
    year = int(match["year"])
    report = REPORT_FOR_MONTH.get((match["kind"], match["month"]))
    if not report or not 2000 <= year <= 2100:
        return None
    receipt = str(record.get("rcept_no") or "")
    filed = str(record.get("rcept_dt") or "")
    if not RECEIPT.fullmatch(receipt) or not re.fullmatch(r"\\d{8}", filed):
        return None
    try:
        day = dt.datetime.strptime(filed, "%Y%m%d").date()
    except ValueError:
        return None
    if day.year < year or day > dt.date.today():
        return None
    # Correction markers, even if one row appears, cannot attest original
    # financial value availability at initial filing date.
    amended = bool(match["prefix"].strip()) or "정정" in title or "첨부추가" in title
    return (year, report), {
        "filing_date": day.isoformat(),
        "filing_receipt": receipt,
        "amended": amended,
    }


def classify_filing_records(records, ticker, corp, wanted):
    """Only return coarse, typed evidence for periods actually in private DB."""
    selected = defaultdict(dict)
    for record in records:
        if str(record.get("corp_code") or "") != corp:
            continue
        stock_code = str(record.get("stock_code") or "").strip()
        if stock_code and stock_code != ticker:
            continue
        identified = filing_identity(record)
        if identified is None:
            continue
        (year, report), observation = identified
        key = f"{ticker}|{year}|{report}|CFS"
        if key not in wanted:
            continue
        selected[key][observation["filing_receipt"]] = observation

    out = {}
    for key in sorted(wanted):
        observations = sorted(selected.get(key, {}).values(),
                              key=lambda x: (x["filing_date"], x["filing_receipt"]))
        if not observations:
            out[key] = {"status": "filing_not_found"}
        elif len(observations) == 1 and not observations[0]["amended"]:
            out[key] = {
                "status": "single_unamended_filing",
                "filing_date": observations[0]["filing_date"],
                "filing_receipt": observations[0]["filing_receipt"],
            }
        else:
            out[key] = {
                "status": "amended_or_multiple_filings_review",
                "filing_count": len(observations),
                "earliest_filing_date": observations[0]["filing_date"],
                "latest_filing_date": observations[-1]["filing_date"],
                "earliest_filing_receipt": observations[0]["filing_receipt"],
                "latest_filing_receipt": observations[-1]["filing_receipt"],
            }
    return out


def fetch_periodic_list(session, api_key, corp, *, earliest, latest, max_pages=20):
    """Fail closed if pagination not complete; never silently trust partial data."""
    response_rows = []
    for page in range(1, max_pages + 1):
        params = {"crtfc_key": api_key, "corp_code": corp,
                  "bgn_de": earliest.strftime("%Y%m%d"),
                  "end_de": latest.strftime("%Y%m%d"),
                  "pblntf_ty": "A", "last_reprt_at": "N",
                  "page_count": 100, "page_no": page,
                  "sort": "date", "sort_mth": "asc"}
        response = session.get(API, params=params, timeout=(10, 45))
        response.raise_for_status()
        data = response.json()
        status = str(data.get("status"))
        if status == "013":
            return []
        if status != "000":
            raise RuntimeError("OpenDART periodic list retrieval failed; no metadata will be saved")
        rows = data.get("list")
        if not isinstance(rows, list):
            raise RuntimeError("Unexpected OpenDART periodic list format")
        response_rows.extend(rows)
        try:
            total_pages = int(data["total_page"])
        except (KeyError, TypeError, ValueError):
            raise RuntimeError("Unknown DART pagination; refuse partial list") from None
        if page >= total_pages:
            return response_rows
        time.sleep(0.2)
    raise RuntimeError("OpenDART page cap reached; refuse incomplete metadata")


def load_private_periods(path):
    with gzip.open(path, "rb") as handle:
        database = pickle.load(handle)
    if not isinstance(database, dict):
        raise ValueError("Unexpected trusted private financial DB format")
    corp_for_ticker = {}
    periods = defaultdict(set)
    for item in database.values():
        if not isinstance(item, dict) or item.get("fs_div") != "CFS":
            continue
        ticker = str(item.get("ticker") or "").strip()
        corp = str(item.get("corp_code") or "").strip()
        year, report = item.get("year"), item.get("report")
        if not TICKER.fullmatch(ticker) or not CORP.fullmatch(corp):
            continue
        if type(year) is not int or report not in {"annual", "q1", "half", "q3"}:
            continue
        if ticker in corp_for_ticker and corp_for_ticker[ticker] != corp:
            raise ValueError("Conflicting corporate identities in private DB")
        corp_for_ticker[ticker] = corp
        periods[ticker].add(f"{ticker}|{year}|{report}|CFS")
    return corp_for_ticker, periods


def load_existing(path):
    if not path.exists():
        return {"schema_version": 1, "source": "OpenDART_periodic_list",
                "entries": {}}
    result = json.loads(path.read_text(encoding="utf-8"))
    if (result.get("schema_version") != 1
            or result.get("source") != "OpenDART_periodic_list"
            or not isinstance(result.get("entries"), dict)
            or any(not KEY_PATTERN.fullmatch(k) for k in result["entries"])):
        raise ValueError("Invalid existing private filing evidence ledger")
    return result


def save_atomic(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     delete=False, suffix=".tmp") as handle:
        temp = Path(handle.name)
        json.dump(obj, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\\n")
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def collect(db_path, dest, *, api_key, limit=2, tickers=None, session=None):
    corp_codes, periods = load_private_periods(db_path)
    ledger = load_existing(dest)
    all_tickers = sorted(corp_codes)
    if tickers is not None:
        requested = set(tickers)
        if any(not TICKER.fullmatch(t) for t in requested):
            raise ValueError("Invalid stock code in selection")
        all_tickers = [t for t in all_tickers if t in requested]
    # Backfill incomplete tickers; do not needlessly repeat successful ones.
    pending = [t for t in all_tickers if any(
        key not in ledger["entries"]
        for key in periods[t]
    )]
    selected = pending[:limit]
    owned = session or requests.Session()
    summary = Counter()
    updates = {}
    for ticker in selected:
        wanted = periods[ticker]
        years = [int(k.split("|")[1]) for k in wanted]
        # include late amendments of the oldest year, through current day
        start = dt.date(min(years), 1, 1)
        try:
            rows = fetch_periodic_list(owned, api_key, corp_codes[ticker],
                                       earliest=start, latest=dt.date.today())
        except (requests.RequestException, RuntimeError) as exc:
            raise RuntimeError("OpenDART query failed; private filing ledger remains unchanged") from None
        observed = classify_filing_records(rows, ticker, corp_codes[ticker], wanted)
        updates.update(observed)
        summary.update(v["status"] for v in observed.values())
        summary["companies_scanned"] += 1
    if updates:
        ledger["entries"].update(updates)
        save_atomic(dest, ledger)
    summary["private_periods_with_corp_code"] = sum(map(len, periods.values()))
    summary["total_ledger_entries"] = len(ledger["entries"])
    summary["changed_periods"] = len(updates)
    summary["private_db_modified"] = 0
    return dict(summary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--tickers", default=None,
                        help="Optional comma-delimited private ticker subset")
    args = parser.parse_args()
    if not 1 <= args.limit <= 10:
        parser.error("limit must be 1..10")
    token = os.environ.get("DART_API_KEY")
    if not token:
        parser.error("Missing DART_API_KEY secret")
    ticker_list = args.tickers.split(",") if args.tickers else None
    totals = collect(args.private_db, args.output, api_key=token,
                     limit=args.limit, tickers=ticker_list)
    print("DART_FILING_EVIDENCE_SUMMARY=" + json.dumps(totals, sort_keys=True))


if __name__ == "__main__":
    main()
