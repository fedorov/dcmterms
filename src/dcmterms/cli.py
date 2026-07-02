"""Command-line interface for dcmterms."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="dcmterms",
        description="Extract coded terminology from the DICOM standard.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command")

    # extract command
    extract_parser = subparsers.add_parser(
        "extract",
        help="Extract coded entries from CID CHTML files.",
    )
    extract_parser.add_argument(
        "--source",
        type=str,
        required=True,
        help="Path to local directory with sect_CID_*.html files, "
        "or URL to download from (e.g., https://dicom.nema.org/medical/dicom/current/output/chtml/part16/).",
    )
    extract_parser.add_argument(
        "--output",
        type=Path,
        default=Path("output"),
        help="Output directory (default: ./output).",
    )
    extract_parser.add_argument(
        "--format",
        nargs="+",
        choices=["csv", "parquet"],
        default=["csv", "parquet"],
        help="Output formats (default: csv parquet).",
    )
    extract_parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Cache directory for downloaded files (default: ./cache/part16).",
    )
    extract_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )

    # download command
    download_parser = subparsers.add_parser(
        "download",
        help="Download CID CHTML files from the DICOM website.",
    )
    download_parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Base URL for DICOM Part 16 CHTML files.",
    )
    download_parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Directory to save downloaded files (default: ./cache/part16).",
    )
    download_parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="Number of parallel download workers (default: 2).",
    )
    download_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )

    # validate command
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate extraction completeness against source files.",
    )
    validate_parser.add_argument(
        "--source",
        type=str,
        required=True,
        help="Path to local directory with sect_CID_*.html files.",
    )
    validate_parser.add_argument(
        "--output",
        type=Path,
        default=Path("output"),
        help="Output directory to validate (default: ./output).",
    )
    validate_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )

    # load-bigquery command
    from .bigquery import DEFAULT_DATASET, TABLE_SCHEMAS

    bq_parser = subparsers.add_parser(
        "load-bigquery",
        help="Overwrite BigQuery tables from extracted CSVs.",
    )
    bq_parser.add_argument(
        "--output",
        type=Path,
        default=Path("output"),
        help="Directory with extracted CSV files (default: ./output).",
    )
    bq_parser.add_argument(
        "--dataset",
        type=str,
        default=DEFAULT_DATASET,
        help=f"BigQuery project:dataset (default: {DEFAULT_DATASET}).",
    )
    bq_parser.add_argument(
        "--tables",
        nargs="+",
        choices=list(TABLE_SCHEMAS),
        default=None,
        help="Tables to load (default: all).",
    )
    bq_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if args.command == "extract":
        _run_extract(args)
    elif args.command == "download":
        _run_download(args)
    elif args.command == "validate":
        _run_validate(args)
    elif args.command == "load-bigquery":
        _run_load_bigquery(args)


def _run_extract(args: argparse.Namespace) -> None:
    from .download import download_chtml
    from .extract import run_extraction

    source = args.source

    # If source looks like a URL, download first
    if source.startswith("http://") or source.startswith("https://"):
        from .download import download_tid_chtml
        source_dir = download_chtml(
            base_url=source,
            cache_dir=args.cache_dir,
        )
        download_tid_chtml(
            base_url=source,
            cache_dir=source_dir,
        )
    else:
        source_dir = Path(source)
        if not source_dir.is_dir():
            print(f"Error: {source_dir} is not a directory", file=sys.stderr)
            sys.exit(1)

    metadata = run_extraction(
        source_dir=source_dir,
        output_dir=args.output,
        formats=args.format,
    )

    print(f"\nExtraction complete:")
    print(f"  DICOM edition:       {metadata['dicom_edition']}")
    print(f"  CID files parsed:    {metadata['total_cid_files_parsed']}")
    print(f"  Total coded entries: {metadata['total_coded_entries']}")
    print(f"  Unique codes:        {metadata['unique_codes']}")
    if "total_tid_files_parsed" in metadata:
        print(f"  TIDs parsed:         {metadata['total_tid_files_parsed']}")
        print(f"  Template rows:       {metadata['total_template_rows']}")
    print(f"  Relationships:       {metadata['total_relationships']}")
    print(f"\n  Entries by scheme:")
    for scheme, count in sorted(
        metadata.get("scheme_counts", {}).items(),
        key=lambda x: -x[1],
    ):
        print(f"    {scheme:8s} {count:>6d}")
    print(f"\n  Output: {args.output}")


def _run_validate(args: argparse.Namespace) -> None:
    from .validate import run_validation

    source_dir = Path(args.source)
    if not source_dir.is_dir():
        print(f"Error: {source_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    ok = run_validation(source_dir=source_dir, output_dir=args.output)
    sys.exit(0 if ok else 1)


def _run_download(args: argparse.Namespace) -> None:
    from .download import DEFAULT_BASE_URL, download_chtml

    url = args.url or DEFAULT_BASE_URL
    cache_dir = download_chtml(
        base_url=url,
        cache_dir=args.cache_dir,
        max_workers=args.workers,
    )
    print(f"Files downloaded to: {cache_dir}")


def _run_load_bigquery(args: argparse.Namespace) -> None:
    from .bigquery import load_all

    print(f"Loading {args.output} into {args.dataset} ...")
    load_all(output_dir=args.output, dataset=args.dataset, tables=args.tables)
    print("Done.")
