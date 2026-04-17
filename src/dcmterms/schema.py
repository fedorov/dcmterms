"""Data model for dcmterms extraction."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CIDMetadata:
    cid_number: int
    cid_name: str
    cid_type: str  # "extensible" or "non-extensible"
    keyword: str
    version: str  # e.g., "20260321"
    uid: str  # e.g., "1.2.840.10008.6.1.8"


@dataclass
class CodedEntry:
    coding_scheme_designator: str  # e.g., SCT, DCM, LN, NCIt, UCUM
    code_value: str
    code_meaning: str
    snomed_rt_id: str | None = None
    umls_concept_uid: str | None = None
    context_group_cid: int | None = None  # per-row CID ref (e.g., "Segmentation Property Type Context Group")


@dataclass
class CIDParseResult:
    metadata: CIDMetadata
    entries: list[CodedEntry] = field(default_factory=list)
    includes: list[int] = field(default_factory=list)  # CID numbers


@dataclass
class Relationship:
    source_type: str  # "CID" or "TID"
    source_id: int
    target_type: str  # "CID" or "TID"
    target_id: int
    relationship: str  # "includes", "references", "constrains"
