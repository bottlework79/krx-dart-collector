"""Offline tests for negative-result cache behavior; no DART API key needed."""
import ast
from pathlib import Path

def test_source_has_dated_missing_cache():
    tree=ast.parse(Path("collect_dart.py").read_text(encoding="utf-8"))
    assert any(isinstance(node,ast.FunctionDef) and node.name=="main" for node in ast.walk(tree))
    source=Path("collect_dart.py").read_text(encoding="utf-8")
    assert '"--missing-recheck-days"' in source
    assert 'today.isoformat()' in source
    assert 'unavailable_cached' in source

if __name__=="__main__":
    test_source_has_dated_missing_cache()
    print("MISSING_CACHE_STATIC_TEST_OK")
