"""Tests for extraction orchestrator using fixture files."""

from pathlib import Path

import pytest

from dcmterms.extract import (
    build_coded_entries_df,
    build_codes_unique_df,
    build_context_groups_df,
    build_relationships_df,
    parse_all_cids,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def results():
    return parse_all_cids(FIXTURES)


def test_parse_all_cids(results):
    assert len(results) == 4
    assert set(results.keys()) == {4, 10, 26, 29}


def test_coded_entries_df(results):
    df = build_coded_entries_df(results)
    assert len(df) > 0
    assert list(df.columns) == [
        "cid_number",
        "cid_name",
        "coding_scheme_designator",
        "code_value",
        "code_meaning",
        "snomed_rt_id",
        "umls_concept_uid",
    ]
    # CID 10 has 45 entries
    assert len(df[df["cid_number"] == 10]) == 45


def test_codes_unique_df(results):
    coded = build_coded_entries_df(results)
    unique = build_codes_unique_df(coded)
    assert len(unique) > 0
    assert "num_cids" in unique.columns
    # Every unique code should have num_cids >= 1
    assert (unique["num_cids"] >= 1).all()
    # Unique codes should be fewer than or equal to total entries
    assert len(unique) <= len(coded)


def test_context_groups_df(results):
    df = build_context_groups_df(results)
    assert len(df) == 4
    cid4 = df[df["cid_number"] == 4].iloc[0]
    assert cid4["includes"] == "4030,4040,4042"
    assert cid4["cid_name"] == "Anatomic Region"


def test_relationships_df(results):
    df = build_relationships_df(results)
    # CID 4 includes 3, CID 26 includes 1, CID 29 includes 1 = 5 relationships
    assert len(df) == 5
    assert set(df.columns) == {
        "source_type",
        "source_id",
        "target_type",
        "target_id",
        "relationship",
    }
    # All should be CID->CID includes
    assert (df["source_type"] == "CID").all()
    assert (df["target_type"] == "CID").all()
    assert (df["relationship"] == "includes").all()
