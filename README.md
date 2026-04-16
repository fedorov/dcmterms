# dcmterms

The DICOM Standard governs how medical imaging devices communicate — it defines thousands of coded terms (anatomy, measurements, findings, procedures) that scanners and software use to mean the same thing. These terms are scattered across hundreds of tables buried in the standard's Part 16, with no single place to look them up or understand how they relate.

dcmterms extracts all coded terminology and template definitions from Part 16 into searchable tabular resources (CSV + Parquet) and a static web browser.

**Live browser:** https://fedorov.github.io/dcmterms/

## What it produces

Parsing 1,466 Context Group files and 333 SR Template source files from Part 16 yields:

| File | Description |
|------|-------------|
| `coded_entries` | Every coded entry with its CID number and CID name |
| `codes_unique` | Deduplicated codes with `num_cids` occurrence count |
| `context_groups` | CID metadata: name, type, keyword, UID, code count, include list |
| `templates` | TID metadata: name, row count, TID includes, CID references |
| `relationships` | Normalized edge list: CID→CID includes, TID→TID includes, TID→CID references |
| `extraction_metadata.json` | Provenance: DICOM edition, date, counts, per-scheme breakdown |

Latest extraction (2026b): **16,570 coded entries · 14,756 unique codes · 21 coding schemes · 4,039 template rows · 3,281 relationships**

## Installation

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

### Extract from local cache (fast, ~10 s)

```bash
python -m dcmterms extract --source ./cache/part16 --output ./output
```

### Download and extract (~15 min download, then ~10 s parse)

```bash
python -m dcmterms extract \
  --source https://dicom.nema.org/medical/dicom/current/output/chtml/part16/ \
  --output ./output
```

### Download only (populate local cache)

```bash
python -m dcmterms download --cache-dir ./cache/part16
```

### Validate extraction completeness

```bash
python -m dcmterms validate --source ./cache/part16 --output ./output
```

### Use the GCS cache

Source files are archived in GCS by DICOM edition:

```bash
gsutil -m cp -r gs://af-dev-storage/dcmterm/2026b/part16/ ./cache/part16/
python -m dcmterms extract --source ./cache/part16 --output ./output
```

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT
