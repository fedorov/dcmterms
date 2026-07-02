"""Reload extraction output tables into BigQuery via the `bq` CLI."""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_DATASET = "idc-sandbox-000:dcmterm"

# bq load's inline "col:TYPE,col:TYPE,..." schema syntax. --autodetect
# misparses the comma-joined string columns (includes, tid_includes,
# cid_references) as floats, so schemas are always passed explicitly.
TABLE_SCHEMAS = {
    "coded_entries": (
        "cid_number:INTEGER,cid_name:STRING,coding_scheme_designator:STRING,"
        "code_value:STRING,code_meaning:STRING,snomed_rt_id:STRING,"
        "umls_concept_uid:STRING,context_group_cid:INTEGER"
    ),
    "codes_unique": (
        "coding_scheme_designator:STRING,code_value:STRING,code_meaning:STRING,"
        "snomed_rt_id:STRING,umls_concept_uid:STRING,num_cids:INTEGER"
    ),
    "context_groups": (
        "cid_number:INTEGER,cid_name:STRING,cid_type:STRING,keyword:STRING,"
        "version:STRING,uid:STRING,num_codes:INTEGER,includes:STRING"
    ),
    "templates": (
        "tid_id:STRING,tid_name:STRING,tid_type:STRING,order:STRING,root:STRING,"
        "num_rows:INTEGER,tid_includes:STRING,cid_references:STRING"
    ),
    "relationships": (
        "source_type:STRING,source_id:STRING,target_type:STRING,target_id:STRING,"
        "relationship:STRING"
    ),
}

# Nullable integer columns that pandas writes as floats in CSV (e.g. "7191.0"
# for context_group_cid) — BigQuery's strict INT64 CSV parser rejects those,
# so re-cast to pandas' nullable Int64 dtype (blank for null) before loading.
NULLABLE_INT_COLUMNS = {
    "coded_entries": ["context_group_cid"],
}


def _prepare_csv(csv_path: Path, table: str, tmp_dir: Path) -> Path:
    """Re-cast nullable-int columns so BigQuery's CSV parser accepts them."""
    nullable_cols = NULLABLE_INT_COLUMNS.get(table)
    if not nullable_cols:
        return csv_path
    df = pd.read_csv(csv_path)
    for col in nullable_cols:
        df[col] = df[col].astype("Int64")
    out_path = tmp_dir / csv_path.name
    df.to_csv(out_path, index=False)
    return out_path


def _row_count(dataset: str, table: str) -> int:
    ref = f"{dataset.replace(':', '.')}.{table}"
    result = subprocess.run(
        ["bq", "query", "--use_legacy_sql=false", "--format=csv", "-q",
         f"SELECT COUNT(*) FROM `{ref}`"],
        check=True, capture_output=True, text=True,
    )
    return int(result.stdout.strip().splitlines()[-1])


def load_table(table: str, output_dir: Path, dataset: str, tmp_dir: Path) -> None:
    """Overwrite one BigQuery table from its extracted CSV."""
    csv_path = output_dir / f"{table}.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"{csv_path} not found — run `dcmterms extract` first")

    expected_rows = len(pd.read_csv(csv_path))
    load_path = _prepare_csv(csv_path, table, tmp_dir)

    cmd = [
        "bq", "load", "--replace", "--skip_leading_rows=1", "--source_format=CSV",
        f"{dataset}.{table}", str(load_path), TABLE_SCHEMAS[table],
    ]
    logger.info("Loading %s into %s.%s", load_path, dataset, table)
    subprocess.run(cmd, check=True)

    actual_rows = _row_count(dataset, table)
    if actual_rows != expected_rows:
        raise RuntimeError(
            f"{table}: loaded {actual_rows} rows, expected {expected_rows}"
        )
    print(f"  {table}: {actual_rows} rows")


def load_all(
    output_dir: Path,
    dataset: str = DEFAULT_DATASET,
    tables: list[str] | None = None,
) -> None:
    """Overwrite all (or a subset of) BigQuery tables from extracted CSVs."""
    tables = tables or list(TABLE_SCHEMAS)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for table in tables:
            load_table(table, output_dir, dataset, tmp_dir)
