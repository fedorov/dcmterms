"""Parse individual CID XHTML files from the DICOM standard."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .parse_utils import (
    find_main_table,
    get_text,
    ns,
    parse_table_headers,
    parse_xhtml,
)
from .schema import CIDMetadata, CIDParseResult, CodedEntry

logger = logging.getLogger(__name__)

# Column names that map to the SNOMED-RT ID field
SNOMED_RT_COLUMNS = {"SNOMED-RT ID", "SNOMED-CT Concept ID", "SNOMED-RT Concept ID"}

# Column name for UMLS
UMLS_COLUMN = "UMLS Concept Unique ID"

# Columns that contain a per-row CID reference (e.g., a linked context group)
CONTEXT_GROUP_COLUMNS = {"Segmentation Property Type Context Group"}


def _parse_metadata(root: "ET.Element") -> CIDMetadata:
    """Extract CID metadata from the page heading and variablelist."""
    # Find the h2 heading: "CID NNN Name"
    cid_number = 0
    cid_name = ""
    for h2 in root.iter(ns("h2")):
        text = get_text(h2)
        m = re.match(r"CID\s+(\d+)\s+(.*)", text)
        if m:
            cid_number = int(m.group(1))
            cid_name = m.group(2).strip()
            break

    # Parse the dl.variablelist for keyword, type, version, uid
    keyword = ""
    cid_type = ""
    version = ""
    uid = ""

    for dl in root.iter(ns("dl")):
        if "variablelist" not in (dl.get("class") or ""):
            continue

        # Iterate dt/dd pairs
        dts = dl.findall(ns("dt"))
        dds = dl.findall(ns("dd"))

        for dt, dd in zip(dts, dds):
            label = get_text(dt).rstrip(":")
            value = get_text(dd)

            if label == "Keyword":
                keyword = value
            elif label == "Type":
                cid_type = value.lower().strip()
            elif label == "Version":
                version = value
            elif label == "UID":
                uid = value

        break  # Only process the first variablelist

    return CIDMetadata(
        cid_number=cid_number,
        cid_name=cid_name,
        cid_type=cid_type,
        keyword=keyword,
        version=version,
        uid=uid,
    )


def _is_include_row(tr: "ET.Element", num_columns: int) -> bool:
    """Check if a table row is an Include directive."""
    tds = tr.findall(ns("td"))
    if len(tds) == 1:
        td = tds[0]
        colspan = td.get("colspan", "1")
        if colspan != "1":
            return True
        text = get_text(td)
        if text.strip().startswith("Include"):
            return True
    return False


def _parse_include_cid(tr: "ET.Element") -> int | None:
    """Extract the included CID number from an Include row."""
    text = get_text(tr)
    m = re.search(r"CID\s+(\d+)", text)
    if m:
        return int(m.group(1))
    return None


def _parse_data_row(
    tr: "ET.Element",
    headers: dict[str, int],
) -> CodedEntry | None:
    """Parse a single data row into a CodedEntry."""
    tds = tr.findall(ns("td"))
    if not tds:
        return None

    def cell(col_name: str) -> str:
        idx = headers.get(col_name)
        if idx is None or idx >= len(tds):
            return ""
        return get_text(tds[idx])

    designator = cell("Coding Scheme Designator")
    code_value = cell("Code Value")
    code_meaning = cell("Code Meaning")

    if not designator or not code_value:
        return None

    # Find SNOMED-RT ID column (multiple possible names)
    snomed_rt_id: str | None = None
    for col_name in SNOMED_RT_COLUMNS:
        if col_name in headers:
            val = cell(col_name)
            if val:
                snomed_rt_id = val
            break

    umls_uid: str | None = None
    if UMLS_COLUMN in headers:
        val = cell(UMLS_COLUMN)
        if val:
            umls_uid = val

    context_group_cid: int | None = None
    for col_name in CONTEXT_GROUP_COLUMNS:
        if col_name in headers:
            val = cell(col_name)
            m = re.search(r"CID\s+(\d+)", val)
            if m:
                context_group_cid = int(m.group(1))
            break

    return CodedEntry(
        coding_scheme_designator=designator,
        code_value=code_value,
        code_meaning=code_meaning,
        snomed_rt_id=snomed_rt_id,
        umls_concept_uid=umls_uid,
        context_group_cid=context_group_cid,
    )


def parse_cid_file(filepath: Path) -> CIDParseResult:
    """Parse a single CID XHTML file and return the parsed result."""
    root = parse_xhtml(filepath)
    metadata = _parse_metadata(root)

    m = re.search(r"CID_(\d+)", filepath.name)
    if m:
        expected = int(m.group(1))
        if metadata.cid_number != expected:
            raise ValueError(
                f"CID number mismatch in {filepath.name}: "
                f"filename says {expected}, parsed {metadata.cid_number}"
            )
    if metadata.cid_number == 0:
        raise ValueError(f"Failed to parse CID number from {filepath.name}")

    table = find_main_table(root)
    if table is None:
        logger.warning("No main table found in %s", filepath.name)
        return CIDParseResult(metadata=metadata)

    headers = parse_table_headers(table)
    if not headers:
        logger.warning("No table headers found in %s", filepath.name)
        return CIDParseResult(metadata=metadata)

    num_columns = len(headers)
    entries: list[CodedEntry] = []
    includes: list[int] = []

    tbody = table.find(ns("tbody"))
    if tbody is None:
        return CIDParseResult(metadata=metadata)

    for tr in tbody.findall(ns("tr")):
        if _is_include_row(tr, num_columns):
            cid_num = _parse_include_cid(tr)
            if cid_num is not None:
                includes.append(cid_num)
        else:
            entry = _parse_data_row(tr, headers)
            if entry is not None:
                entries.append(entry)

    return CIDParseResult(metadata=metadata, entries=entries, includes=includes)
