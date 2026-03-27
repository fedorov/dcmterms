# dcmterms

Extract coded terminology from the DICOM standard Part 16 Context Groups into accessible tabular resources (CSV + Parquet).

## Installation

```bash
pip install -e ".[dev]"
```

## Usage

### Extract from a local directory

```bash
dcmterms extract --source /path/to/chtml/part16 --output ./output
```

### Download and extract from the DICOM website

```bash
dcmterms extract --source https://dicom.nema.org/medical/dicom/current/output/chtml/part16/ --output ./output
```

### Download only

```bash
dcmterms download --cache-dir ./cache/part16
```

## Output

The extraction produces these tables in CSV and Parquet format:

| File | Description |
|------|-------------|
| `coded_entries` | All coded entries with CID association |
| `codes_unique` | Deduplicated master table of unique codes |
| `context_groups` | CID metadata with code counts and include lists |
| `relationships` | Normalized edge list of CID include relationships |
| `extraction_metadata.json` | Provenance (DICOM edition, date, counts) |

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```
