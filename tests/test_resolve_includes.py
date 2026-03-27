"""Tests for include resolution."""

from dcmterms.resolve_includes import build_relationships, resolve_includes
from dcmterms.schema import CIDMetadata, CIDParseResult, CodedEntry


def _make_result(cid_num: int, codes: list[str], includes: list[int]) -> CIDParseResult:
    return CIDParseResult(
        metadata=CIDMetadata(
            cid_number=cid_num,
            cid_name=f"Test CID {cid_num}",
            cid_type="extensible",
            keyword=f"TestCID{cid_num}",
            version="20260101",
            uid=f"1.2.3.{cid_num}",
        ),
        entries=[
            CodedEntry(
                coding_scheme_designator="SCT",
                code_value=c,
                code_meaning=f"Concept {c}",
            )
            for c in codes
        ],
        includes=includes,
    )


def test_no_includes():
    results = {
        1: _make_result(1, ["A", "B"], []),
        2: _make_result(2, ["C", "D"], []),
    }
    resolved = resolve_includes(results)
    assert resolved[1] == {"A", "B"}
    assert resolved[2] == {"C", "D"}


def test_simple_include():
    results = {
        1: _make_result(1, ["A"], [2]),
        2: _make_result(2, ["B", "C"], []),
    }
    resolved = resolve_includes(results)
    assert resolved[1] == {"A", "B", "C"}
    assert resolved[2] == {"B", "C"}


def test_transitive_include():
    results = {
        1: _make_result(1, ["A"], [2]),
        2: _make_result(2, ["B"], [3]),
        3: _make_result(3, ["C"], []),
    }
    resolved = resolve_includes(results)
    assert resolved[1] == {"A", "B", "C"}
    assert resolved[2] == {"B", "C"}
    assert resolved[3] == {"C"}


def test_diamond_include():
    results = {
        1: _make_result(1, ["A"], [2, 3]),
        2: _make_result(2, ["B"], [4]),
        3: _make_result(3, ["C"], [4]),
        4: _make_result(4, ["D"], []),
    }
    resolved = resolve_includes(results)
    assert resolved[1] == {"A", "B", "C", "D"}


def test_include_missing_target():
    results = {
        1: _make_result(1, ["A"], [999]),
    }
    resolved = resolve_includes(results)
    # CID 999 not in results, so no codes added from it
    assert resolved[1] == {"A"}


def test_build_relationships():
    results = {
        1: _make_result(1, ["A"], [2, 3]),
        2: _make_result(2, ["B"], []),
        3: _make_result(3, ["C"], [4]),
        4: _make_result(4, ["D"], []),
    }
    rels = build_relationships(results)
    assert len(rels) == 3
    assert rels[0].source_id == 1 and rels[0].target_id == 2
    assert rels[1].source_id == 1 and rels[1].target_id == 3
    assert rels[2].source_id == 3 and rels[2].target_id == 4
