# dcmterms

Extract all coded terminology and template definitions from DICOM Standard Part 16 into accessible tabular resources (CSV + Parquet).

## Project Goal

The DICOM standard uses coded terms (SNOMED-CT, LOINC, NCIt, UCUM, DCM, etc.) across 1,467 Context Groups and 386 SR Templates in Part 16, but there is no single accessible resource listing them or their relationships. This project provides reproducible tooling to parse the standard and produce consolidated tabular outputs.

See PLAN.md for the full roadmap (M1–M5).

## Data Source

CHTML (chunked XHTML) pages from the DICOM standard website. Parsed with stdlib `xml.etree.ElementTree` (files are well-formed XHTML).

- Source URL: `https://dicom.nema.org/medical/dicom/current/output/chtml/part16/`
- CID/TID file discovery uses the directory listing at the base URL
- CID files: `sect_CID_*.html` (1,467 individual files)
- TID files: `sect_TID_*.html` (301 individual files) + `sect_*Templates.html` (32 section files) + `chapter_A.html` (58 base templates like TID 300–1701). Total: 386 unique TIDs across 334 source files.
- Downloaded files are cached in `cache/part16/` to avoid re-fetching
- Downloads are throttled (2 workers, 0.25s delay) to be polite to the NEMA server

## Key Parsing Details

### CIDs
- First 3 table columns always: Coding Scheme Designator, Code Value, Code Meaning
- Additional columns vary across 40+ header variants (SNOMED-RT ID, UMLS Concept UID, Coding Scheme Version, Units, etc.)
- Column lookup is by name, not position — handles all header variants
- Include directives appear as table rows with colspan > 1, text like "Include CID 4030"
- 227 CIDs include other CIDs via 624 include relationships; max include depth is 4
- 31 CIDs have no main data table (retired/empty context groups) — logged as warnings and skipped
- 99 CIDs are pure aggregators (only includes, no direct entries)
- Retired codes (e.g., SRT entries in CID 26) appear in `div.note` sections — parser correctly ignores these
- Some CIDs have a per-row "context group" column (e.g., CID 7150 "Segmentation Property Category" has "Segmentation Property Type Context Group") — these columns are in `CONTEXT_GROUP_COLUMNS` set and extracted as `context_group_cid` on `CodedEntry`; also stored as `code-context-group` edges in `relationships`
- Parser raises `ValueError` if parsed CID number doesn't match filename (catches metadata parse failures early)
- Some CID files exist on the DICOM server but are absent from the Apache directory listing (e.g., CID 7150). `download.py` fixes this with `_fill_navigation_gaps()`: after bulk download it scans cached files for `next`/`prev` nav links pointing to undownloaded files, then fetches them

### TIDs
- TID table columns: (row#), NL, Rel with Parent, VT, Concept Name, VM, Req Type, Condition, Value Set Constraint
- TID headings use `<h3>` (not `<h2>` like CIDs)
- Some TID pages have a Parameters table (anchored `table_TID_*_Parameters`) before the main TID table — use `find_table_by_anchor` with exact match to skip it
- Multi-TID files (chapter_A.html, section template files) contain multiple TID sections — parser finds all `div.section` elements with `sect_TID_*` anchors
- TID 300 appears as both parent and child section in chapter_A.html — deduplication keeps the one with more rows
- Relationships extracted from TID rows: `INCLUDE` in VT column → TID→TID include; `CID nnnn` in Concept Name or Value Set Constraint → TID→CID reference

### Shared Gotchas
- The DICOM website serves XHTML with non-breaking spaces (`\xc2\xa0`) between number and name. `get_text()` normalizes these to regular spaces. When downloading, files must be written as raw bytes (`resp.content`) not re-encoded text (`resp.text`) to avoid double-encoding corruption.
- Normalize CID/TID type capitalization: "Non-Extensible" → "non-extensible"

## Deduplication

`codes_unique` deduplicates by `(coding_scheme_designator, code_value, code_meaning)` — if the same code value appears with different meaning strings across CIDs, both rows are preserved. The `coded_entries` table always has every occurrence.

## Output Tables

- `coded_entries.csv/.parquet` — All coded entries with CID number, CID name, and code details. Includes `context_group_cid` (nullable int) for CIDs that have a per-row "Segmentation Property Type Context Group" column (e.g., CID 7150).
- `codes_unique.csv/.parquet` — Deduplicated by (scheme, code_value, code_meaning) with `num_cids` count
- `context_groups.csv/.parquet` — CID metadata with code counts and include lists
- `templates.csv/.parquet` — TID metadata with row counts, TID includes, and CID references
- `relationships.csv/.parquet` — Normalized edge list: CID→CID includes, TID→TID includes, TID→CID references, CID→CID code-context-group. All IDs are strings (TIDs can have letter suffixes like "10003A").
- `extraction_metadata.json` — Provenance (DICOM edition, date, counts, per-scheme breakdown)

## GCS Cache

Downloaded CHTML source files are archived in GCS organized by DICOM edition:

```
gs://af-dev-storage/dcmterm/<edition>/part16/
```

Current: `gs://af-dev-storage/dcmterm/2026c/part16/` (1,801 files, 54 MB)

To use the GCS cache instead of downloading from the DICOM website:

```bash
# Sync GCS cache to local
gsutil -m cp -r gs://af-dev-storage/dcmterm/2026c/part16/ ./cache/part16/

# Then extract from local cache
python -m dcmterms extract --source ./cache/part16 --output ./output
```

## BigQuery

Tables loaded into `idc-sandbox-000.dcmterm`. When loading with `bq load`, use explicit schemas for tables with comma-separated string fields (`includes`, `tid_includes`, `cid_references`) — `--autodetect` misinterprets them as floats. Use `--skip_leading_rows=1` with explicit schemas.

## Latest Extraction (2026c)

- 1,467 CID files parsed, 16,582 coded entries, 14,765 unique codes
- 386 TIDs parsed, 4,069 template rows
- 3,301 relationships: 624 CID→CID includes + 1,129 TID→TID includes + 1,539 TID→CID references + 9 CID→CID code-context-group
- 21 coding schemes: SCT (9,681), DCM (3,984), MDC (1,348), LN (956), IBSI (154), UCUM (127), RADLEX (75), UMLS (65), NCIt (57), FMA (45), NCDR (39), plus 10 more

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
  parse_tid.py          — TID file parser (metadata + rows + TID/CID relationships)
  resolve_includes.py   — Resolve Include CID directives (DAG traversal)
  extract.py            — Orchestrate extraction, deduplication, output generation
  download.py           — Bulk download CHTML files from DICOM website (throttled)
  validate.py           — Validate extraction completeness against source files
  cli.py                — CLI entry point (extract, download, validate subcommands)
tests/
  fixtures/             — Real XHTML files for testing (CID 4, 10, 26, 29, 7150, 7194 + TID 2001, 10002 + chapter_A)
output/                 — Generated artifacts (gitignored)
cache/                  — Downloaded CHTML files (gitignored)
```

## Running

```bash
# From local cache (fast, ~10s)
python -m dcmterms extract --source ./cache/part16 --output ./output

# Download and extract (~15 min download, then ~10s parse)
python -m dcmterms extract --source https://dicom.nema.org/medical/dicom/current/output/chtml/part16/ --output ./output

# Validate extraction completeness
python -m dcmterms validate --source ./cache/part16 --output ./output

# Tests
pytest tests/ -v
```
