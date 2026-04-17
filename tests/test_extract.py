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
    assert len(results) == 6
    assert set(results.keys()) == {4, 10, 26, 29, 7150, 7194}


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
        "context_group_cid",
    ]
    # CID 10 has 45 entries
    assert len(df[df["cid_number"] == 10]) == 45
    # CID 7150 entries have context_group_cid populated
    cid7150 = df[df["cid_number"] == 7150]
    assert len(cid7150) == 9
    assert cid7150["context_group_cid"].notna().all()
    # CID 7194 has no direct entries
    assert len(df[df["cid_number"] == 7194]) == 0


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
    assert len(df) == 6
    cid4 = df[df["cid_number"] == 4].iloc[0]
    assert cid4["includes"] == "4030,4040,4042"
    assert cid4["cid_name"] == "Anatomic Region"
    # CID 7194 is an aggregator with includes
    cid7194 = df[df["cid_number"] == 7194].iloc[0]
    assert cid7194["includes"] == "7159,7199"


def test_relationships_df(results):
    df = build_relationships_df(results)
    assert set(df.columns) == {
        "source_type",
        "source_id",
        "target_type",
        "target_id",
        "relationship",
    }
    # CID→CID includes: CID4→3, CID26→1, CID29→1, CID7194→2 = 7 include edges
    includes = df[df["relationship"] == "includes"]
    assert len(includes) == 7
    assert (includes["source_type"] == "CID").all()
    assert (includes["target_type"] == "CID").all()
    # CID 7150 code-context-group edges (9 unique target CIDs)
    ctxgrp = df[df["relationship"] == "code-context-group"]
    assert len(ctxgrp) == 9
    assert set(ctxgrp["source_id"].astype(str)) == {"7150"}
