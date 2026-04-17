"""Integration regression test: all CIDs/TIDs in cache must be parsed successfully."""

from pathlib import Path

import pandas as pd
import pytest

CACHE_DIR = Path(__file__).parent.parent / "cache" / "part16"
cache_available = pytest.mark.skipif(
    not CACHE_DIR.exists(),
    reason="local cache not available — run gsutil sync first",
)


@cache_available
class TestFullCacheExtraction:
    """Run full extraction + validation against local cache to catch regressions."""

    @pytest.fixture(scope="class")
    def output(self, tmp_path_factory):
        from dcmterms.extract import run_extraction
        from dcmterms.validate import run_validation

        out = tmp_path_factory.mktemp("output")
        run_extraction(CACHE_DIR, out)
        ok = run_validation(CACHE_DIR, out)
        assert ok, "Validation failed — some source CIDs/TIDs are missing from output"
        return out

    def test_cid_7150_in_context_groups(self, output):
        cg = pd.read_csv(output / "context_groups.csv")
        assert 7150 in cg["cid_number"].values, "CID 7150 missing from context_groups"

    def test_cid_7150_has_entries(self, output):
        ce = pd.read_csv(output / "coded_entries.csv")
        rows = ce[ce["cid_number"] == 7150]
        assert len(rows) == 9, f"Expected 9 entries for CID 7150, got {len(rows)}"

    def test_cid_7150_context_group_cid_column(self, output):
        ce = pd.read_csv(output / "coded_entries.csv")
        rows = ce[ce["cid_number"] == 7150]
        assert "context_group_cid" in rows.columns
        assert rows["context_group_cid"].notna().all(), "CID 7150 entries missing context_group_cid"

    def test_cid_7150_code_context_group_relationships(self, output):
        rels = pd.read_csv(output / "relationships.csv")
        cid7150_rels = rels[
            (rels["source_id"].astype(str) == "7150")
            & (rels["relationship"] == "code-context-group")
        ]
        assert len(cid7150_rels) > 0, "No code-context-group relationships for CID 7150"

    def test_cid_7194_in_context_groups(self, output):
        cg = pd.read_csv(output / "context_groups.csv")
        assert 7194 in cg["cid_number"].values, "CID 7194 missing from context_groups"

    def test_cid_7194_is_aggregator(self, output):
        cg = pd.read_csv(output / "context_groups.csv")
        ce = pd.read_csv(output / "coded_entries.csv")
        row = cg[cg["cid_number"] == 7194].iloc[0]
        # CID 7194 has no direct entries
        assert 7194 not in ce["cid_number"].values
        # CID 7194 has includes
        assert pd.notna(row["includes"]) and row["includes"] != ""

    def test_no_null_cid_numbers_in_context_groups(self, output):
        cg = pd.read_csv(output / "context_groups.csv")
        assert cg["cid_number"].notna().all()
        assert (cg["cid_number"] > 0).all(), "context_groups has cid_number=0 (metadata parse failure)"
