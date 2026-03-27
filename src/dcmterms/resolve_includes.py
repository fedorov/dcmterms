"""Resolve Include directives across Context Groups (DAG traversal)."""

from __future__ import annotations

import logging

from .schema import CIDParseResult, Relationship

logger = logging.getLogger(__name__)


def build_include_graph(
    results: dict[int, CIDParseResult],
) -> dict[int, list[int]]:
    """Build adjacency list of CID include relationships."""
    graph: dict[int, list[int]] = {}
    for cid_num, result in results.items():
        if result.includes:
            graph[cid_num] = result.includes
    return graph


def resolve_includes(
    results: dict[int, CIDParseResult],
) -> dict[int, set[str]]:
    """Return mapping of CID -> set of all code values (fully resolved).

    Each CID's code set includes codes from directly listed entries
    plus codes from all transitively included CIDs.
    """
    graph = build_include_graph(results)

    # Cache for resolved sets
    resolved: dict[int, set[str]] = {}

    def _resolve(cid_num: int, visiting: set[int]) -> set[str]:
        if cid_num in resolved:
            return resolved[cid_num]

        if cid_num in visiting:
            logger.warning("Circular include detected at CID %d", cid_num)
            return set()

        visiting.add(cid_num)

        # Start with direct codes
        codes: set[str] = set()
        if cid_num in results:
            for entry in results[cid_num].entries:
                codes.add(entry.code_value)

        # Add codes from included CIDs
        for included_cid in graph.get(cid_num, []):
            codes |= _resolve(included_cid, visiting)

        visiting.discard(cid_num)
        resolved[cid_num] = codes
        return codes

    for cid_num in results:
        _resolve(cid_num, set())

    return resolved


def build_relationships(
    results: dict[int, CIDParseResult],
) -> list[Relationship]:
    """Build the normalized relationship edge list from include directives."""
    relationships: list[Relationship] = []
    for cid_num, result in sorted(results.items()):
        for included_cid in result.includes:
            relationships.append(
                Relationship(
                    source_type="CID",
                    source_id=cid_num,
                    target_type="CID",
                    target_id=included_cid,
                    relationship="includes",
                )
            )
    return relationships
