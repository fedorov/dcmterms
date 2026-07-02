"""Tests for BigQuery load preparation helpers (no network/bq CLI needed)."""

from pathlib import Path

import pandas as pd

from dcmterms.bigquery import _prepare_csv


def test_prepare_csv_recasts_nullable_int_column(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    csv_path = src_dir / "coded_entries.csv"
    pd.DataFrame(
        {
            "code_value": ["1", "2", "3"],
            "context_group_cid": [7191.0, None, 7193.0],
        }
    ).to_csv(csv_path, index=False)

    tmp_dir = tmp_path / "out"
    tmp_dir.mkdir()
    out_path = _prepare_csv(csv_path, "coded_entries", tmp_dir)

    assert out_path != csv_path
    df = pd.read_csv(out_path)
    assert df["context_group_cid"].tolist()[0] == 7191
    assert pd.isna(df["context_group_cid"].tolist()[1])
    # Plain integers, no floats, in the raw CSV text
    assert ".0" not in out_path.read_text()


def test_prepare_csv_passthrough_for_tables_without_nullable_ints(tmp_path):
    csv_path = tmp_path / "relationships.csv"
    csv_path.write_text("source_type,source_id\nCID,1\n")

    out_path = _prepare_csv(csv_path, "relationships", tmp_path)

    assert out_path == csv_path
