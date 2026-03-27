# dcmterms

Extract all coded terminology from DICOM Standard Part 16 Context Groups into accessible tabular resources (CSV + Parquet).

## Project Goal

The DICOM standard uses coded terms (SNOMED-CT, LOINC, NCIt, UCUM, DCM, etc.) across 1,466 Context Groups in Part 16, but there is no single accessible resource listing them. This project provides reproducible tooling to parse the standard and produce consolidated tabular outputs.

See PLAN.md for the full roadmap (M1–M5).

## Data Source

CHTML (chunked XHTML) pages from the DICOM standard website — individual `sect_CID_*.html` files per Context Group. Parsed with stdlib `xml.etree.ElementTree` (files are well-formed XHTML).

- Source URL: `https://dicom.nema.org/medical/dicom/current/output/chtml/part16/`
- CID file discovery uses the directory listing at the base URL (not chapter_B.html, which only links to the first CID)
- Downloaded files are cached in `cache/part16/` to avoid re-fetching
- Downloads are throttled (2 workers, 0.25s delay) to be polite to the NEMA server

## Key Parsing Details

- First 3 table columns always: Coding Scheme Designator, Code Value, Code Meaning
- Additional columns vary across 40+ header variants (SNOMED-RT ID, UMLS Concept UID, Coding Scheme Version, Units, etc.)
- Column lookup is by name, not position — handles all header variants
- Include directives appear as table rows with colspan > 1, text like "Include CID 4030"
- 227 CIDs include other CIDs via 624 include relationships; max include depth is 4
- 10 CIDs have an extra "Coding Scheme Version" column
- Normalize CID type capitalization: "Non-Extensible" → "non-extensible"
- 30 CIDs have no main data table (retired/empty context groups) — these are logged as warnings and skipped
- Retired codes (e.g., SRT entries in CID 26) appear in `div.note` sections after the main table, not in the table itself — the parser correctly ignores these
- The DICOM website serves XHTML with non-breaking spaces (`\xc2\xa0`) between CID number and name (e.g., `CID 10\xa0Interventional Drug`). `get_text()` normalizes these to regular spaces. When downloading, files must be written as raw bytes (`resp.content`) not re-encoded text (`resp.text`) to avoid double-encoding corruption.

## Deduplication

`codes_unique` deduplicates by `(coding_scheme_designator, code_value, code_meaning)` — if the same code value appears with different meaning strings across CIDs, both rows are preserved. The `coded_entries` table always has every occurrence.

## Output Tables

- `coded_entries.csv/.parquet` — All coded entries with CID number, CID name, and code details
- `codes_unique.csv/.parquet` — Deduplicated by (scheme, code_value, code_meaning) with `num_cids` count
- `context_groups.csv/.parquet` — CID metadata with code counts and include lists
- `relationships.csv/.parquet` — Normalized edge list of CID include relationships (extensible for TID relationships in M2)
- `extraction_metadata.json` — Provenance (DICOM edition, date, counts, per-scheme breakdown)

## Latest Extraction (2026b)

- 1,466 CID files parsed, 16,570 coded entries, 14,756 unique codes
- 21 coding schemes: SCT (9,680), DCM (3,973), MDC (1,348), LN (956), IBSI (154), UCUM (127), RADLEX (75), UMLS (65), NCIt (57), FMA (45), NCDR (39), plus 10 more
- BigQuery: loaded into `idc-sandbox-000.dcmterm` dataset (coded_entries, codes_unique, context_groups, relationships)

## Tech Stack

- Python 3.10+, pandas, pyarrow, requests
- stdlib xml.etree.ElementTree for XHTML parsing
- argparse CLI (`python -m dcmterms extract ...`)
- Use `python3 -m venv .venv` for environment management

## Project Layout

```
src/dcmterms/
  schema.py             — Dataclass definitions (CIDMetadata, CodedEntry, Relationship)
  parse_utils.py        — Shared XHTML parsing helpers (namespace handling, text extraction, table finding)
  parse_cid.py          — CID file parser (metadata + coded entries + includes)
  resolve_includes.py   — Resolve Include CID directives (DAG traversal)
  extract.py            — Orchestrate extraction, deduplication, output generation
  download.py           — Bulk download CHTML files from DICOM website (throttled)
  cli.py                — CLI entry point (extract, download subcommands)
tests/
  fixtures/             — 4 real CID XHTML files (CID 4, 10, 26, 29) covering edge cases
output/                 — Generated artifacts (gitignored)
cache/                  — Downloaded CHTML files (gitignored)
```

## Running

```bash
# From local cache (fast, ~5s)
python -m dcmterms extract --source ./cache/part16 --output ./output

# Download and extract (~12 min download, then ~5s parse)
python -m dcmterms extract --source https://dicom.nema.org/medical/dicom/current/output/chtml/part16/ --output ./output

# Tests
pytest tests/ -v
```
