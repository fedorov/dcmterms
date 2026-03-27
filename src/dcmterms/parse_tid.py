"""Parse TID (Template) XHTML files from the DICOM standard."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .parse_utils import (
    find_main_table,
    find_table_by_anchor,
    get_text,
    ns,
    parse_table_headers,
    parse_xhtml,
)
from .schema import Relationship

logger = logging.getLogger(__name__)


class TIDMetadata:
    __slots__ = ("tid_id", "tid_name", "tid_type", "order", "root")

    def __init__(
        self,
        tid_id: str,
        tid_name: str,
        tid_type: str = "",
        order: str = "",
        root: str = "",
    ):
        self.tid_id = tid_id  # e.g., "2001" or "10003A"
        self.tid_name = tid_name
        self.tid_type = tid_type  # "extensible" or "non-extensible"
        self.order = order  # "significant" or "non-significant"
        self.root = root  # "yes" or "no"

    def __repr__(self) -> str:
        return f"TIDMetadata(tid_id={self.tid_id!r}, tid_name={self.tid_name!r})"


class TIDRow:
    __slots__ = (
        "row_number",
        "nesting_level",
        "rel_with_parent",
        "value_type",
        "concept_name",
        "vm",
        "req_type",
        "condition",
        "value_set_constraint",
    )

    def __init__(
        self,
        row_number: str = "",
        nesting_level: str = "",
        rel_with_parent: str = "",
        value_type: str = "",
        concept_name: str = "",
        vm: str = "",
        req_type: str = "",
        condition: str = "",
        value_set_constraint: str = "",
    ):
        self.row_number = row_number
        self.nesting_level = nesting_level
        self.rel_with_parent = rel_with_parent
        self.value_type = value_type
        self.concept_name = concept_name
        self.vm = vm
        self.req_type = req_type
        self.condition = condition
        self.value_set_constraint = value_set_constraint


class TIDParseResult:
    __slots__ = ("metadata", "rows", "relationships")

    def __init__(
        self,
        metadata: TIDMetadata,
        rows: list[TIDRow] | None = None,
        relationships: list[Relationship] | None = None,
    ):
        self.metadata = metadata
        self.rows = rows or []
        self.relationships = relationships or []


# Regex for TID and CID references
_TID_REF = re.compile(r"TID\s+(\w+)")
_CID_REF = re.compile(r"CID\s+(\d+)")


def _extract_references(
    tid_id: str,
    row: TIDRow,
) -> list[Relationship]:
    """Extract TID→TID and TID→CID relationships from a template row."""
    rels: list[Relationship] = []

    # INCLUDE rows reference other TIDs
    if row.value_type.strip().upper() == "INCLUDE":
        m = _TID_REF.search(row.concept_name)
        if m:
            rels.append(
                Relationship(
                    source_type="TID",
                    source_id=tid_id,
                    target_type="TID",
                    target_id=m.group(1),
                    relationship="includes",
                )
            )

    # CID references in Concept Name or Value Set Constraint
    for text in (row.concept_name, row.value_set_constraint):
        for m in _CID_REF.finditer(text):
            rels.append(
                Relationship(
                    source_type="TID",
                    source_id=tid_id,
                    target_type="CID",
                    target_id=int(m.group(1)),
                    relationship="references",
                )
            )

    return rels


def _parse_tid_section(
    section_root: "ET.Element",
    heading_tag: str = "h3",
) -> TIDParseResult | None:
    """Parse a single TID section (within a page that may contain multiple TIDs)."""
    # Find heading
    tid_id = ""
    tid_name = ""
    for h in section_root.iter(ns(heading_tag)):
        text = get_text(h)
        m = re.match(r"TID\s+(\w+)\s+(.*)", text)
        if m:
            tid_id = m.group(1)
            tid_name = m.group(2).strip()
            break

    if not tid_id:
        # Try h2 as well (individual TID pages may use h2)
        if heading_tag != "h2":
            for h in section_root.iter(ns("h2")):
                text = get_text(h)
                m = re.match(r"TID\s+(\w+)\s+(.*)", text)
                if m:
                    tid_id = m.group(1)
                    tid_name = m.group(2).strip()
                    break

    if not tid_id:
        return None

    # Parse metadata from variablelist
    tid_type = ""
    order = ""
    root = ""

    for dl in section_root.iter(ns("dl")):
        if "variablelist" not in (dl.get("class") or ""):
            continue
        dts = dl.findall(ns("dt"))
        dds = dl.findall(ns("dd"))
        for dt, dd in zip(dts, dds):
            label = get_text(dt).rstrip(":")
            value = get_text(dd)
            if label == "Type":
                tid_type = value.lower().strip()
            elif label == "Order":
                order = value.lower().strip()
            elif label == "Root":
                root = value.lower().strip()
        break

    metadata = TIDMetadata(
        tid_id=tid_id,
        tid_name=tid_name,
        tid_type=tid_type,
        order=order,
        root=root,
    )

    # Find the TID table (not the Parameters table)
    # Use anchor pattern table_TID_XXX (exact match, no suffix like _Parameters)
    table = find_table_by_anchor(section_root, f"table_TID_{re.escape(tid_id)}")
    if table is None:
        # Fall back to generic search
        table = find_main_table(section_root)
    if table is None:
        return TIDParseResult(metadata=metadata)

    headers = parse_table_headers(table)
    if not headers:
        return TIDParseResult(metadata=metadata)

    # Map header names to our fields (handle variants)
    col_map = {}
    for name, idx in headers.items():
        lower = name.lower().strip()
        if lower == "" or lower == "row":
            col_map["row_number"] = idx
        elif lower == "nl" or "nesting" in lower:
            col_map["nesting_level"] = idx
        elif "rel" in lower and "parent" in lower:
            col_map["rel_with_parent"] = idx
        elif lower == "vt" or "value type" in lower:
            col_map["value_type"] = idx
        elif "concept" in lower:
            col_map["concept_name"] = idx
        elif lower == "vm":
            col_map["vm"] = idx
        elif "req" in lower:
            col_map["req_type"] = idx
        elif "condition" in lower:
            col_map["condition"] = idx
        elif "value set" in lower:
            col_map["value_set_constraint"] = idx

    # If first header is empty, it's the row number column
    if 0 in headers.values() and "row_number" not in col_map:
        # Check if index 0 is an unnamed column
        for name, idx in headers.items():
            if idx == 0 and name.strip() == "":
                col_map["row_number"] = 0
                break

    tbody = table.find(ns("tbody"))
    if tbody is None:
        return TIDParseResult(metadata=metadata)

    rows: list[TIDRow] = []
    relationships: list[Relationship] = []

    for tr in tbody.findall(ns("tr")):
        tds = tr.findall(ns("td"))
        if not tds:
            continue

        def cell(field: str) -> str:
            idx = col_map.get(field)
            if idx is None or idx >= len(tds):
                return ""
            return get_text(tds[idx])

        row = TIDRow(
            row_number=cell("row_number"),
            nesting_level=cell("nesting_level"),
            rel_with_parent=cell("rel_with_parent"),
            value_type=cell("value_type"),
            concept_name=cell("concept_name"),
            vm=cell("vm"),
            req_type=cell("req_type"),
            condition=cell("condition"),
            value_set_constraint=cell("value_set_constraint"),
        )
        rows.append(row)
        relationships.extend(_extract_references(tid_id, row))

    return TIDParseResult(metadata=metadata, rows=rows, relationships=relationships)


def parse_tid_file(filepath: Path) -> list[TIDParseResult]:
    """Parse a TID XHTML file and return parsed results.

    A file may contain multiple TID sections (e.g., chapter_A.html
    or section template files), so this returns a list.
    """
    root = parse_xhtml(filepath)
    results: list[TIDParseResult] = []

    # Find all div.section elements that contain TID definitions
    # These are identified by having an anchor with id="sect_TID_*"
    tid_sections = _find_tid_sections(root)

    if tid_sections:
        for section in tid_sections:
            result = _parse_tid_section(section)
            if result is not None:
                results.append(result)
    else:
        # Try parsing the whole page as a single TID
        result = _parse_tid_section(root)
        if result is not None:
            results.append(result)

    # Deduplicate: if the same TID appears twice (parent/child section),
    # keep the one with more rows
    seen: dict[str, TIDParseResult] = {}
    for r in results:
        tid_id = r.metadata.tid_id
        if tid_id not in seen or len(r.rows) > len(seen[tid_id].rows):
            seen[tid_id] = r
    return list(seen.values())


def _find_tid_sections(root: "ET.Element") -> list["ET.Element"]:
    """Find all div.section elements that define TIDs.

    Looks for sections containing an anchor with id matching sect_TID_*.
    Returns the innermost section div for each TID.
    """
    sections = []

    for div in root.iter(ns("div")):
        if div.get("class") != "section":
            continue

        # Check if this section contains a TID anchor
        for a in div.iter(ns("a")):
            aid = a.get("id", "")
            if re.match(r"sect_TID_\w+$", aid):
                sections.append(div)
                break

    # Deduplicate: if a parent section contains child sections,
    # we only want the innermost ones that have their own tables
    if len(sections) <= 1:
        return sections

    # Filter to only sections that directly contain a table_TID anchor
    innermost = []
    for div in sections:
        has_table = False
        for a in div.iter(ns("a")):
            aid = a.get("id", "")
            if re.match(r"table_TID_\w+$", aid):
                has_table = True
                break
        if has_table:
            innermost.append(div)

    return innermost if innermost else sections
