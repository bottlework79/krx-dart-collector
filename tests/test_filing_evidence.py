"""Offline proof that official DART list results match correct filing periods.

No DART API key, external calls, or private DB needed.
"""
import datetime as dt
import unittest
from unittest.mock import Mock

from collect_filing_evidence import (
    filing_identity, classify_filing_records, fetch_periodic_list,
    collect,
)


def filing(kind="사업보고서", year=2024, month="12",
           name_prefix="", rcept="20250331000123", date="20250331",
           stock="123456", corp="00123456"):
    return {"report_nm": f"{name_prefix}{kind} ({year}.{month})",
            "rcept_no": rcept, "rcept_dt": date,
            "stock_code": stock, "corp_code": corp}


class FilingMetadataTests(unittest.TestCase):
    def test_annual_name_is_fiscal_year_not_filing_year(self):
        match = filing_identity(filing())
        self.assertEqual(match[0], (2024, "annual"))
        self.assertEqual(match[1]["filing_date"], "2025-03-31")

    def test_quarter_and_half_labels(self):
        for kind, month, expected in (
            ("분기보고서", "03", "q1"),
            ("분기보고서", "09", "q3"),
            ("반기보고서", "06", "half"),
        ):
            with self.subTest(month=month):
                match = filing_identity(filing(kind, 2024, month))
                self.assertEqual(match[0], (2024, expected))

    def test_nondecember_fiscal_and_unrecognized_period_block(self):
        self.assertIsNone(filing_identity(filing(month="09", kind="사업보고서")))
        self.assertIsNone(filing_identity(filing(month="12", kind="분기보고서")))

    def test_correction_marker_flags_even_single_record(self):
        item = filing(name_prefix="[기재정정] ")
        classification = classify_filing_records(
            [item], "123456", "00123456", {"123456|2024|annual|CFS"}
        )
        self.assertEqual(
            classification["123456|2024|annual|CFS"]["status"],
            "amended_or_multiple_filings_review",
        )

    def test_amended_pair_never_authorizes_early_value(self):
        first = filing()
        second = filing(name_prefix="[기재정정] ",
                        rcept="20250601000123", date="20250601")
        result = classify_filing_records(
            [first, second], "123456", "00123456",
            {"123456|2024|annual|CFS"}
        )["123456|2024|annual|CFS"]
        self.assertEqual(result["status"], "amended_or_multiple_filings_review")
        self.assertEqual(result["filing_count"], 2)
        self.assertEqual(result["earliest_filing_date"], "2025-03-31")
        self.assertEqual(result["latest_filing_date"], "2025-06-01")
        self.assertNotIn("filing_date", result)

    def test_only_matching_company_and_known_private_period(self):
        original = filing()
        wrong = filing(stock="999999", rcept="20250401000001", date="20250401")
        out = classify_filing_records([original, wrong], "123456", "00123456",
                                      {"123456|2024|annual|CFS"})
        self.assertEqual(out["123456|2024|annual|CFS"]["status"],
                         "single_unamended_filing")

    def test_comparison_and_nonreport_rows_excluded(self):
        rejected = dict(filing())
        rejected["report_nm"] = "연결감사보고서 (2024.12)"
        self.assertIsNone(filing_identity(rejected))

    def test_empty_dart_status_returns_empty(self):
        res = Mock()
        res.json.return_value = {"status": "013"}
        res.raise_for_status.return_value = None
        session = Mock()
        session.get.return_value = res
        result = fetch_periodic_list(
            session, "fake", "00123456",
            earliest=dt.date(2024,1,1), latest=dt.date(2025,12,31)
        )
        self.assertEqual(result, [])
        params = session.get.call_args.kwargs["params"]
        self.assertEqual(params["pblntf_ty"], "A")
        self.assertEqual(params["last_reprt_at"], "N")

    def test_incomplete_pagination_rejected(self):
        res = Mock()
        res.json.return_value = {"status":"000","list":[filing()],"total_page":2}
        session = Mock()
        session.get.return_value = res
        with self.assertRaises(RuntimeError):
            fetch_periodic_list(
                session, "fake", "00123456",
                earliest=dt.date(2024,1,1), latest=dt.date(2025,12,31),
                max_pages=1
            )


if __name__ == "__main__":
    unittest.main()
