"""Run private quarterly tests but expose ONLY numeric failed test positions.

Do not reveal individual private test names, amounts, tracebacks or source.
This helper is only executed after a failed public-runner regression step.
"""
import io
import unittest


def flatten(suite):
    for node in suite:
        if isinstance(node, unittest.TestSuite):
            yield from flatten(node)
        else:
            yield node


def main():
    loader = unittest.TestLoader()
    suite = loader.discover("test", pattern="test_quarterly_parent_profit.py")
    cases = list(flatten(suite))
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(
        unittest.TestSuite(cases)
    )
    problem_ids = {id(test) for test, _ in result.failures + result.errors}
    failed_indices = [str(i + 1) for i, test in enumerate(cases) if id(test) in problem_ids]
    print("TEST_DIAGNOSTIC_FAIL_POSITIONS=" + ",".join(failed_indices))
    print("TEST_DIAGNOSTIC_TOTAL=" + str(len(cases)))
    print("TEST_DIAGNOSTIC_FAILED=" + str(len(problem_ids)))
    for _, trace in result.errors:
        last_line = trace.strip().splitlines()[-1]
        category = last_line.split(":", 1)[0]
        if category in {"SyntaxError", "ImportError", "ModuleNotFoundError", "NameError", "TypeError", "ValueError", "AttributeError", "IndentationError"}:
            print("TEST_DIAGNOSTIC_ERROR_CATEGORY=" + category.upper())
            if category == "ModuleNotFoundError":
                import re
                found = re.search(r"No module named [\x27\x22]([a-zA-Z0-9_.]+)[\x27\x22]", last_line)
                if found:
                    item = found.group(1)
                    safe_known = {"operations.calculate_quarterly_parent_profit", "operations", "test_quarterly_parent_profit", "requests", "pandas"}
                    print("TEST_DIAGNOSTIC_MODULE=" + (item if item in safe_known else "OTHER"))
    for source in ("operations/calculate_quarterly_parent_profit.py", "test/test_quarterly_parent_profit.py"):
        try:
            from pathlib import Path
            code = Path(source).read_text(encoding="utf-8")
            compile(code, source, "exec")
        except SyntaxError as exc:
            print("TEST_DIAGNOSTIC_SYNTAX_LINE=" + str(exc.lineno))



if __name__ == "__main__":
    main()
