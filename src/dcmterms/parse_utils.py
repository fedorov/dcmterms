"""Shared XHTML parsing utilities for DICOM standard pages."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

NS = "http://www.w3.org/1999/xhtml"
NS_MAP = {"x": NS}


def ns(tag: str) -> str:
    """Return a namespace-qualified tag name."""
    return f"{{{NS}}}{tag}"


def get_text(element: ET.Element | None) -> str:
    """Recursively extract all text content from an XML element, stripped.

    Normalizes non-breaking spaces (\xa0) to regular spaces.
    """
    if element is None:
        return ""
    text = "".join(element.itertext())
    # Replace non-breaking space with regular space
    text = text.replace("\xa0", " ")
    return text.strip()


def parse_xhtml(filepath: Path) -> ET.Element:
    """Parse an XHTML file and return the root element.

    Handles the DOCTYPE declaration that ElementTree can't process
    by stripping it before parsing.
    """
    text = filepath.read_text(encoding="utf-8")
    # Remove DOCTYPE declaration (ET doesn't handle it)
    text = re.sub(r"<!DOCTYPE[^>]*>", "", text)
    return ET.fromstring(text)


def find_main_table(root: ET.Element) -> ET.Element | None:
    """Find the main data table inside a div.table element.

    Returns the <table frame="box"> element, or None if not found.
    Skips tables inside note divs (which contain retired codes).
    """
    # Look for div[@class='table'] > div[@class='table-contents'] > table
    for div in root.iter(ns("div")):
        if div.get("class") == "table":
            for table_contents in div.iter(ns("div")):
                if table_contents.get("class") == "table-contents":
                    for table in table_contents.iter(ns("table")):
                        if table.get("frame") == "box":
                            return table
    return None


def parse_table_headers(table: ET.Element) -> dict[str, int]:
    """Extract header names from a table's thead, returning {name: column_index}.

    Normalizes header names by stripping whitespace. Known variants:
    - "SNOMED-RT ID", "SNOMED-CT Concept ID", "SNOMED-RT Concept ID"
    - "UMLS Concept Unique ID"
    - "Coding Scheme Version"
    - "Units"
    """
    headers: dict[str, int] = {}
    thead = table.find(ns("thead"))
    if thead is None:
        return headers

    tr = thead.find(ns("tr"))
    if tr is None:
        return headers

    for idx, th in enumerate(tr.findall(ns("th"))):
        name = get_text(th).strip()
        headers[name] = idx

    return headers


def get_edition_string(root: ET.Element) -> str | None:
    """Extract the DICOM edition string from the page header.

    Looks for <span class="documentreleaseinformation"> which contains
    text like "DICOM PS3.16 2026b - Content Mapping Resource".
    Returns just the edition part, e.g., "2026b".
    """
    for span in root.iter(ns("span")):
        if span.get("class") == "documentreleaseinformation":
            text = get_text(span)
            # Extract edition: "DICOM PS3.16 2026b - ..."
            m = re.search(r"PS3\.\d+\s+(\d{4}[a-z]?)", text)
            if m:
                return m.group(1)
    # Also check elements without namespace (some elements reset xmlns="")
    for span in root.iter("span"):
        if span.get("class") == "documentreleaseinformation":
            text = get_text(span)
            m = re.search(r"PS3\.\d+\s+(\d{4}[a-z]?)", text)
            if m:
                return m.group(1)
    return None
