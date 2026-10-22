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


if __name__ == "__main__":
    main()
