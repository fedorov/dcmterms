# dcmterms: Coded Terminology Resource from the DICOM Standard

## Context

The DICOM standard uses coded terminology (SNOMED-CT, LOINC, NCIt, UCUM, DICOM-defined codes, etc.) extensively across 1,300+ Context Groups and hundreds of SR Templates in Part 16. These coded entries are scattered and there is no single, easily accessible resource listing them or their relationships. This project creates reproducible tooling to extract all coded entries, capture template-to-CID relationships, and make the results navigable.

## Roadmap Overview

| Milestone | Scope | Status |
|-----------|-------|--------|
| **M1: Context Group Extraction** | Parse all CIDs, produce tabular outputs (CSV + Parquet) | Done |
| **M2: SR Template Parsing** | Parse TID definitions, capture template→CID relationships | Done |
| **M3: Graph Visualization** | Interactive graph of CID↔CID includes + TID→CID references | Planned |
| **M4: GitHub Actions Auto-update** | CI workflow to re-extract on each DICOM standard release | Planned |
| **M5: Web Interface** | GitHub Pages site for browsing/searching extracted content | In progress |

Architecture decisions in M1 are made with M2–M5 in mind. Specifically:
- **Modular parsers**: `parse_cid.py` and (future) `parse_tid.py` share common XHTML parsing utilities
- **Normalized relationship storage**: Include edges stored as `(source_type, source_id, target_type, target_id)` tuples — works for CID→CID includes now and TID→CID references later, and feeds directly into graph visualization
- **Deterministic CLI pipeline**: `python -m dcmterms extract` produces all outputs from a source directory — easy to wrap in a GitHub Action
- **Structured output directory**: outputs are self-contained (data + metadata JSON) so a static web UI can consume them directly

---

## M1: Context Group Extraction (implement now)

### Data Source: CHTML Pages

Parse individual `sect_CID_*.html` files from the DICOM standard website:
- Well-formed XHTML, parseable with stdlib `xml.etree.ElementTree`
- One file per CID — simple iteration, easy to test
- Source: `https://dicom.nema.org/medical/dicom/current/output/chtml/part16/` or local directory

### Output Tables (CSV + Parquet)

**`coded_entries`** — All coded entries with CID association

| Column | Type | Description |
|--------|------|-------------|
| `cid_number` | int | Context Group number |
| `coding_scheme_designator` | str | e.g., SCT, DCM, LN, NCIt, UCUM |
| `code_value` | str | Code identifier |
| `code_meaning` | str | Human-readable meaning |
| `snomed_rt_id` | str/null | SNOMED-RT ID (when present) |
| `umls_concept_uid` | str/null | UMLS Concept UID (when present) |

**`codes_unique`** — Deduplicated master table of unique codes

| Column | Type | Description |
|--------|------|-------------|
| `coding_scheme_designator` | str | Coding scheme |
| `code_value` | str | Code identifier |
| `code_meaning` | str | Human-readable meaning |
| `snomed_rt_id` | str/null | SNOMED-RT ID |
| `umls_concept_uid` | str/null | UMLS Concept UID |
| `num_cids` | int | Number of CIDs using this code |

**`context_groups`** — Metadata for all context groups

| Column | Type | Description |
|--------|------|-------------|
| `cid_number` | int | CID number |
| `cid_name` | str | CID name |
| `cid_type` | str | "extensible" or "non-extensible" |
| `keyword` | str | CID keyword |
| `version` | str | Version date |
| `uid` | str | DICOM UID |
| `num_codes` | int | Total coded entries (direct) |
| `includes` | str | Comma-separated included CID numbers |

**`relationships`** — Normalized edge list (extensible for M2)

| Column | Type | Description |
|--------|------|-------------|
| `source_type` | str | "CID" (later: "TID") |
| `source_id` | int | Source CID/TID number |
| `target_type` | str | "CID" (later: "CID" or "TID") |
| `target_id` | int | Target CID/TID number |
| `relationship` | str | "includes" (later: "references", "constrains") |

**`extraction_metadata.json`** — Provenance

```json
{
  "dicom_edition": "2026b",
  "extraction_date": "2026-03-27",
  "source": "...",
  "total_cid_files_parsed": 1365,
  "unique_codes": 12000,
  "dcmterms_version": "0.1.0"
}
```

### Project Structure

```
dcmterms/
  CLAUDE.md
  PLAN.md
  pyproject.toml
  README.md
  .gitignore
  src/
    dcmterms/
      __init__.py
      schema.py               # Dataclass definitions (shared across parsers)
      parse_utils.py          # Shared XHTML parsing helpers (reused by M2)
      parse_cid.py            # Parse individual CID XHTML files
      resolve_includes.py     # Resolve CID include DAG
      extract.py              # Orchestrate extraction, deduplication, output
      download.py             # Fetch CHTML files from DICOM website
      cli.py                  # CLI entry point (argparse)
  output/                     # Generated artifacts (gitignored)
  tests/
    test_parse_cid.py
    test_resolve_includes.py
    test_extract.py
    fixtures/                 # Sample CID XHTML files
```

### Implementation Steps

#### Step 1: Project scaffolding
- `pyproject.toml` — metadata, dependencies: `pandas`, `pyarrow`, `requests`
- `.gitignore` — output/, cache/, __pycache__, etc.
- `src/dcmterms/__init__.py`

#### Step 2: Data model (`schema.py`)
Dataclasses shared across all parsers:
- `CIDMetadata` — cid_number, cid_name, cid_type, keyword, version, uid
- `CodedEntry` — coding_scheme_designator, code_value, code_meaning, snomed_rt_id, umls_concept_uid
- `CIDParseResult` — metadata, entries (list[CodedEntry]), includes (list[int])
- `Relationship` — source_type, source_id, target_type, target_id, relationship

#### Step 3: Shared parsing utilities (`parse_utils.py`)
- `get_text(element)` — recursively extract text content from an XML element
- `parse_xhtml(filepath)` — parse XHTML file, return ElementTree root (handle namespace)
- `find_table(root, ...)` — locate the data table in a CID/TID page
- `parse_table_headers(table)` — extract header names, return column index mapping

These utilities will be reused by `parse_tid.py` in M2.

#### Step 4: CID parser (`parse_cid.py`)
- Extract CID number/name from `<h2>` heading
- Extract metadata (type, keyword, version, UID) from `<dl class="variablelist compact">`
- Parse table with header-driven column mapping (find columns by name, not position)
- Detect Include rows (colspan > 1 or text starts with "Include")
- Handle 40+ header variants; normalize "Non-Extensible"/"Non-extensible"
- Return ALL coded entries plus include directives

#### Step 5: Include resolution (`resolve_includes.py`)
- Build include DAG from all CIDParseResult.includes lists
- Resolve transitively with cycle detection (max observed depth: 4)
- Produce both direct and resolved views

#### Step 6: Extraction orchestrator (`extract.py`)
- Iterate all CID files, collect CIDParseResults
- Build output DataFrames: coded_entries, codes_unique, context_groups, relationships
- Write CSV + Parquet + extraction_metadata.json

#### Step 7: Bulk download support (`download.py`)
- Discover all `sect_CID_*.html` filenames from Part 16 directory listing
- Parallel bulk download all ~1,365 files using `concurrent.futures.ThreadPoolExecutor`
- Cache in `cache/<edition>/part16/` so subsequent runs skip download
- Extract DICOM edition string from page metadata
- Progress bar and retry logic
- Support local directory as source (skip download)

#### Step 8: CLI (`cli.py`)
```
python -m dcmterms extract --source <path-or-url> --output ./output --format csv parquet
python -m dcmterms extract --source /path/to/chtml/part16 --output ./output
```

#### Step 9: Tests
Fixtures covering edge cases:
- 3-col table, all DCM codes (CID 29) — no SNOMED columns
- 5-col table with SNOMED (CID 10)
- Includes (CID 4 → CID 4030, 4040, 4042)
- Coding Scheme Version extra column (CID 6027)
- SRT entries (CID 26)
- Variant headers: "SNOMED-CT Concept ID" (CID 8134)

#### Step 10: README.md

### Key Parsing Details

- CHTML files are well-formed XHTML; use `xml.etree.ElementTree`
- First 3 columns always: Coding Scheme Designator, Code Value, Code Meaning
- Additional columns vary: SNOMED-RT ID, UMLS Concept Unique ID, Coding Scheme Version, Units, etc.
- Include directives: table rows with colspan > 1, text like "Include CID 4030"
- ~217 CIDs include other CIDs; max depth 4
- 10 CIDs have extra "Coding Scheme Version" column
- Normalize CID type: "Non-Extensible" → "non-extensible"

---

## M2: SR Template Parsing (future)

Parse `sect_TID_*.html` files from Part 16 Annex A. Templates define hierarchical structures that reference Context Groups (e.g., TID 300 references CID 244 for Laterality).

- Add `parse_tid.py` reusing `parse_utils.py`
- Define `TIDMetadata`, `TIDRow`, `TIDParseResult` in `schema.py`
- Extract TID→CID and TID→TID relationships into the `relationships` table
- Template rows contain: Row#, NL (nesting level), Content Item, VT (value type), Concept Name, VM, Requirement, Condition, Value Set Constraint

## M3: Graph Visualization (future)

Build interactive graph from the `relationships` table:
- CID→CID include edges (from M1)
- TID→CID reference edges (from M2)
- TID→TID include edges (from M2)
- Technology: D3.js or Cytoscape.js, deployed as static HTML
- Nodes: CIDs and TIDs with metadata on hover
- Filtering by coding scheme, CID type, template category

## M4: GitHub Actions Auto-update (future)

Workflow triggered on schedule (e.g., monthly) or manually:
1. Download latest CHTML from DICOM website
2. Run `python -m dcmterms extract`
3. Compare outputs with existing; if changed, commit and create a release tagged with DICOM edition
4. Optionally rebuild web interface (M5)

## M5: Web Interface (future)

Static GitHub Pages site consuming the output tables:
- Search/filter codes by scheme, meaning, CID
- Browse context groups with their codes
- Interactive graph view (from M3)
- Technology: vanilla JS or lightweight framework, no server needed

---

## Verification (M1)

1. Parse a single known CID file (e.g., CID 10) and verify entries match the DICOM website
2. Run full extraction on a local CHTML copy and check:
   - Total CID files parsed (~1,365)
   - Reasonable code counts (~9,000+ SCT entries, plus DCM/LN/NCIt/UCUM)
   - Include resolution produces expected expansions (CID 4 includes CID 4030 codes)
   - Relationships table has entries for all include directives
3. Spot-check output CSV against the DICOM standard website for a few CIDs
4. `pytest` passes on all fixtures
