"""Orchestrate extraction across all CID files and produce output tables."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from . import __version__
from .parse_cid import parse_cid_file
from .parse_utils import get_edition_string, parse_xhtml
from .parse_tid import TIDParseResult, parse_tid_file
from .resolve_includes import build_relationships
from .schema import CIDParseResult, Relationship

logger = logging.getLogger(__name__)


def discover_cid_files(source_dir: Path) -> list[Path]:
    """Find all sect_CID_*.html files in a directory."""
    files = sorted(source_dir.glob("sect_CID_*.html"))
    if not files:
        raise FileNotFoundError(
            f"No sect_CID_*.html files found in {source_dir}"
        )
    return files


def detect_edition(source_dir: Path) -> str:
    """Detect the DICOM edition from the first CID file."""
    files = discover_cid_files(source_dir)
    root = parse_xhtml(files[0])
    edition = get_edition_string(root)
    return edition or "unknown"


def parse_all_cids(
    source_dir: Path,
) -> dict[int, CIDParseResult]:
    """Parse all CID files in a directory."""
    files = discover_cid_files(source_dir)
    results: dict[int, CIDParseResult] = {}
    total = len(files)

    failures: list[str] = []
    for i, filepath in enumerate(files, 1):
        try:
            result = parse_cid_file(filepath)
            results[result.metadata.cid_number] = result
        except Exception:
            logger.exception("Failed to parse %s", filepath.name)
            failures.append(filepath.name)

        if i % 100 == 0 or i == total:
            print(f"\r  Parsing: [{i}/{total}] {100*i/total:.0f}%", end="", flush=True)

    print()
    if failures:
        raise RuntimeError(
            f"Failed to parse {len(failures)} CID file(s): {', '.join(failures)}"
        )
    logger.info("Parsed %d CID files", len(results))
    return results


def build_coded_entries_df(
    results: dict[int, CIDParseResult],
) -> pd.DataFrame:
    """Build the coded_entries DataFrame (all entries with CID association)."""
    rows = []
    for cid_num in sorted(results):
        result = results[cid_num]
        for entry in result.entries:
            rows.append(
                {
                    "cid_number": cid_num,
                    "cid_name": result.metadata.cid_name,
                    "coding_scheme_designator": entry.coding_scheme_designator,
                    "code_value": entry.code_value,
                    "code_meaning": entry.code_meaning,
                    "snomed_rt_id": entry.snomed_rt_id,
                    "umls_concept_uid": entry.umls_concept_uid,
                    "context_group_cid": entry.context_group_cid,
                }
            )
    return pd.DataFrame(rows)


def build_codes_unique_df(coded_entries_df: pd.DataFrame) -> pd.DataFrame:
    """Build the deduplicated codes_unique DataFrame."""
    if coded_entries_df.empty:
        return pd.DataFrame(
            columns=[
                "coding_scheme_designator",
                "code_value",
                "code_meaning",
                "snomed_rt_id",
                "umls_concept_uid",
                "num_cids",
            ]
        )

    # Deduplicate on (scheme, code_value, code_meaning) so that the same
    # code with different meanings in different CIDs is preserved as
    # separate rows.
    dedup_key = ["coding_scheme_designator", "code_value", "code_meaning"]

    # Count CIDs per unique (scheme, code_value, meaning) combination
    cid_counts = (
        coded_entries_df.groupby(dedup_key)["cid_number"]
        .nunique()
        .reset_index()
        .rename(columns={"cid_number": "num_cids"})
    )

    # Take first occurrence for the optional ID columns
    first_occ = (
        coded_entries_df.drop_duplicates(subset=dedup_key, keep="first")[
            dedup_key + ["snomed_rt_id", "umls_concept_uid"]
        ]
    )

    return first_occ.merge(cid_counts, on=dedup_key)


def build_context_groups_df(
    results: dict[int, CIDParseResult],
) -> pd.DataFrame:
    """Build the context_groups DataFrame (CID metadata)."""
    rows = []
    for cid_num in sorted(results):
        result = results[cid_num]
        m = result.metadata
        rows.append(
            {
                "cid_number": m.cid_number,
                "cid_name": m.cid_name,
                "cid_type": m.cid_type,
                "keyword": m.keyword,
                "version": m.version,
                "uid": m.uid,
                "num_codes": len(result.entries),
                "includes": ",".join(str(c) for c in result.includes) if result.includes else "",
            }
        )
    return pd.DataFrame(rows)


def build_relationships_df(
    results: dict[int, CIDParseResult],
) -> pd.DataFrame:
    """Build the relationships DataFrame (normalized edge list)."""
    rels = build_relationships(results)
    rows = [
        {
            "source_type": r.source_type,
            "source_id": str(r.source_id),
            "target_type": r.target_type,
            "target_id": str(r.target_id),
            "relationship": r.relationship,
        }
        for r in rels
    ]

    # Per-row CID references (e.g., "Segmentation Property Type Context Group" column)
    seen: set[tuple] = {(r["source_id"], r["target_id"], r["relationship"]) for r in rows}
    for cid_num, result in sorted(results.items()):
        for entry in result.entries:
            if entry.context_group_cid is not None:
                key = (str(cid_num), str(entry.context_group_cid), "code-context-group")
                if key not in seen:
                    seen.add(key)
                    rows.append({
                        "source_type": "CID",
                        "source_id": str(cid_num),
                        "target_type": "CID",
                        "target_id": str(entry.context_group_cid),
                        "relationship": "code-context-group",
                    })

    if not rows:
        return pd.DataFrame(
            columns=["source_type", "source_id", "target_type", "target_id", "relationship"]
        )
    return pd.DataFrame(rows)


def run_extraction(
    source_dir: Path,
    output_dir: Path,
    formats: list[str] | None = None,
) -> dict:
    """Run the full extraction pipeline.

    Returns the extraction metadata dict.
    """
    logger.info("Starting extraction from %s", source_dir)

    edition = detect_edition(source_dir)
    logger.info("DICOM edition: %s", edition)

    results = parse_all_cids(source_dir)

    coded_entries_df = build_coded_entries_df(results)
    codes_unique_df = build_codes_unique_df(coded_entries_df)
    context_groups_df = build_context_groups_df(results)
    relationships_df = build_relationships_df(results)

    # Scheme breakdown
    scheme_counts = {}
    if not coded_entries_df.empty:
        scheme_counts = (
            coded_entries_df["coding_scheme_designator"]
            .value_counts()
            .to_dict()
        )

    metadata = {
        "dicom_edition": edition,
        "extraction_date": date.today().isoformat(),
        "source": str(source_dir),
        "total_cid_files_parsed": len(results),
        "total_coded_entries": len(coded_entries_df),
        "unique_codes": len(codes_unique_df),
        "cids_with_includes": sum(1 for r in results.values() if r.includes),
        "total_relationships": len(relationships_df),
        "scheme_counts": scheme_counts,
        "dcmterms_version": __version__,
    }

    # TID extraction (if TID files exist in source_dir)
    tid_results = parse_all_tids(source_dir)
    templates_df = pd.DataFrame()
    tid_relationships_df = pd.DataFrame()

    if tid_results:
        templates_df = build_templates_df(tid_results)
        tid_relationships_df = build_tid_relationships_df(tid_results)

        # Merge TID relationships into the main relationships table
        if not tid_relationships_df.empty:
            # Ensure consistent string types for source_id/target_id
            # (CID relationships use int, TID uses str like "10003A")
            relationships_df["source_id"] = relationships_df["source_id"].astype(str)
            relationships_df["target_id"] = relationships_df["target_id"].astype(str)
            tid_relationships_df["source_id"] = tid_relationships_df["source_id"].astype(str)
            tid_relationships_df["target_id"] = tid_relationships_df["target_id"].astype(str)
            relationships_df = pd.concat(
                [relationships_df, tid_relationships_df], ignore_index=True
            )

        metadata["total_tid_files_parsed"] = len(tid_results)
        metadata["total_template_rows"] = int(templates_df["num_rows"].sum()) if not templates_df.empty else 0
        metadata["tid_relationships"] = len(tid_relationships_df)

    metadata["total_relationships"] = len(relationships_df)

    # Write outputs
    tables = {
        "coded_entries": coded_entries_df,
        "codes_unique": codes_unique_df,
        "context_groups": context_groups_df,
        "relationships": relationships_df,
    }
    if not templates_df.empty:
        tables["templates"] = templates_df

    if formats is None:
        formats = ["csv", "parquet"]
    output_dir.mkdir(parents=True, exist_ok=True)

    for name, df in tables.items():
        if "csv" in formats:
            df.to_csv(output_dir / f"{name}.csv", index=False)
        if "parquet" in formats:
            df.to_parquet(output_dir / f"{name}.parquet", index=False)

    with open(output_dir / "extraction_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info("Outputs written to %s", output_dir)

    return metadata


# --- TID extraction ---


def discover_tid_files(source_dir: Path) -> list[Path]:
    """Find all TID-related HTML files in a directory."""
    files: list[Path] = []
    # Individual TID files
    files.extend(sorted(source_dir.glob("sect_TID_*.html")))
    # Section template files
    files.extend(sorted(source_dir.glob("sect_*Templates.html")))
    # chapter_A.html
    chapter_a = source_dir / "chapter_A.html"
    if chapter_a.exists():
        files.append(chapter_a)
    return files


def parse_all_tids(
    source_dir: Path,
) -> dict[str, TIDParseResult]:
    """Parse all TID files in a directory. Returns {tid_id: TIDParseResult}."""
    files = discover_tid_files(source_dir)
    if not files:
        return {}

    results: dict[str, TIDParseResult] = {}
    total = len(files)

    failures: list[str] = []
    for i, filepath in enumerate(files, 1):
        try:
            file_results = parse_tid_file(filepath)
            for r in file_results:
                tid_id = r.metadata.tid_id
                # Keep the result with more rows if duplicate
                if tid_id not in results or len(r.rows) > len(results[tid_id].rows):
                    results[tid_id] = r
        except Exception:
            logger.exception("Failed to parse %s", filepath.name)
            failures.append(filepath.name)

        if i % 50 == 0 or i == total:
            print(f"\r  Parsing TIDs: [{i}/{total}] {100*i/total:.0f}%", end="", flush=True)

    if total > 0:
        print()
    if failures:
        raise RuntimeError(
            f"Failed to parse {len(failures)} TID file(s): {', '.join(failures)}"
        )
    logger.info("Parsed %d unique TIDs from %d files", len(results), total)
    return results


def build_templates_df(
    results: dict[str, TIDParseResult],
) -> pd.DataFrame:
    """Build the templates DataFrame (TID metadata)."""
    rows = []
    for tid_id in sorted(results, key=lambda x: (x.isdigit(), int(x) if x.isdigit() else 0, x)):
        r = results[tid_id]
        m = r.metadata
        tid_includes = [
            rel.target_id
            for rel in r.relationships
            if rel.target_type == "TID" and rel.relationship == "includes"
        ]
        cid_refs = [
            str(rel.target_id)
            for rel in r.relationships
            if rel.target_type == "CID"
        ]
        rows.append(
            {
                "tid_id": m.tid_id,
                "tid_name": m.tid_name,
                "tid_type": m.tid_type,
                "order": m.order,
                "root": m.root,
                "num_rows": len(r.rows),
                "tid_includes": ",".join(str(t) for t in tid_includes),
                "cid_references": ",".join(cid_refs),
            }
        )
    return pd.DataFrame(rows)


def build_tid_relationships_df(
    results: dict[str, TIDParseResult],
) -> pd.DataFrame:
    """Build the relationships DataFrame from TID references."""
    rels: list[dict] = []
    for tid_id in sorted(results):
        for rel in results[tid_id].relationships:
            rels.append(
                {
                    "source_type": rel.source_type,
                    "source_id": rel.source_id,
                    "target_type": rel.target_type,
                    "target_id": rel.target_id,
                    "relationship": rel.relationship,
                }
            )
    if not rels:
        return pd.DataFrame(
            columns=["source_type", "source_id", "target_type", "target_id", "relationship"]
        )
    return pd.DataFrame(rels)
