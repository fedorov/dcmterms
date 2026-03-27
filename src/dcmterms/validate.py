"""Validate extraction completeness against source files."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd


def run_validation(source_dir: Path, output_dir: Path) -> bool:
    """Validate that all source CID files are accounted for in the output.

    Prints a detailed report and returns True if validation passes.
    """
    # Discover source CID files
    source_files = sorted(source_dir.glob("sect_CID_*.html"))
    source_cids: set[int] = set()
    for f in source_files:
        m = re.search(r"sect_CID_(\d+)", f.name)
        if m:
            source_cids.add(int(m.group(1)))

    # Load output tables
    cg = pd.read_csv(output_dir / "context_groups.csv")
    ce = pd.read_csv(output_dir / "coded_entries.csv")
    meta_path = output_dir / "extraction_metadata.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}

    output_cids = set(cg["cid_number"])
    cids_with_entries = set(ce["cid_number"])

    # Categorize
    missing_from_output = sorted(source_cids - output_cids)
    extra_in_output = sorted(output_cids - source_cids)

    has_entries = output_cids & cids_with_entries
    empty_cids = output_cids - cids_with_entries

    aggregators: list[int] = []
    genuinely_empty: list[int] = []
    for cid_num in sorted(empty_cids):
        row = cg[cg["cid_number"] == cid_num].iloc[0]
        includes = row["includes"]
        if pd.notna(includes) and includes != "":
            aggregators.append(cid_num)
        else:
            genuinely_empty.append(cid_num)

    # Print report
    print(f"Validation Report")
    print(f"{'=' * 60}")

    if meta:
        print(f"  DICOM edition: {meta.get('dicom_edition', 'unknown')}")
        print(f"  Extraction date: {meta.get('extraction_date', 'unknown')}")
        print()

    print(f"Source files:              {len(source_cids):>6}")
    print(f"CIDs in output:            {len(output_cids):>6}")
    print()
    print(f"  With coded entries:      {len(has_entries):>6}")
    print(f"  Aggregators (only includes): {len(aggregators):>4}")
    print(f"  Empty/retired:           {len(genuinely_empty):>6}")
    print(f"  ─────────────────────────────────")
    print(f"  Total accounted:         {len(has_entries) + len(aggregators) + len(genuinely_empty):>6}")

    ok = True

    if missing_from_output:
        ok = False
        print(f"\nERROR: {len(missing_from_output)} source CIDs missing from output:")
        for cid_num in missing_from_output:
            print(f"  CID {cid_num}")

    if extra_in_output:
        ok = False
        print(f"\nERROR: {len(extra_in_output)} output CIDs not found in source:")
        for cid_num in extra_in_output:
            print(f"  CID {cid_num}")

    if not missing_from_output and not extra_in_output:
        print(f"\nAll {len(source_cids)} source CIDs accounted for.")

    # Detail sections
    if aggregators:
        print(f"\nAggregator CIDs ({len(aggregators)}):")
        print(f"  These have no direct entries but include other CIDs.")
        for cid_num in aggregators:
            row = cg[cg["cid_number"] == cid_num].iloc[0]
            print(f"  CID {cid_num}: {row['cid_name']} → includes {row['includes']}")

    if genuinely_empty:
        print(f"\nEmpty/Retired CIDs ({len(genuinely_empty)}):")
        print(f"  These have no entries and no includes.")
        for cid_num in genuinely_empty:
            row = cg[cg["cid_number"] == cid_num].iloc[0]
            print(f"  CID {cid_num}: {row['cid_name']}")

    if ok:
        print(f"\nValidation PASSED")
    else:
        print(f"\nValidation FAILED")

    return ok
