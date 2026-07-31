# src/specir/cli/query.py
#
# CLI subcommand `query` – queries the evidence registry (SQLite database)
# to retrieve proven theorems, counterexamples, invariants, and other
# verification artifacts.

import argparse
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any
from specir.evidence.registry import EvidenceRegistry
from specir.utils.logger import setup_logging, get_logger

logger = get_logger(__name__)


def _setup_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="specir query",
        description="Query the evidence registry for verification artifacts."
    )
    parser.add_argument("--list", action="store_true", help="List all evidence entries")
    parser.add_argument("--type", "-t", type=str, choices=[
        "counterexample_trace", "inductive_invariant", "coq_theorem",
        "acl2_theorem", "simulation_trace"
    ], help="Filter by evidence type")
    parser.add_argument("--property", "-p", type=str, help="Filter by property name")
    parser.add_argument("--engine", "-e", type=str,
                        help="Filter by verification engine (e.g., BMC, IC3, theorem_proving)")
    parser.add_argument("--id", type=str,
                        help="Show details for a specific evidence ID (local_id or URI)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser


def _format_evidence(ev: Dict[str, Any]) -> str:
    """Pretty-print a single evidence entry (as returned by the registry)."""
    lines = [
        f"ID: {ev.get('id')}",
        f"Type: {ev.get('type')}",
        f"Reference: {ev.get('ref_type')} {ev.get('ref_value')}",
        f"Engine: {ev.get('engine')}",
        f"Status: {ev.get('status', 'N/A')}",
        f"Property: {ev.get('property_name', 'N/A')}",
        f"Created: {ev.get('created_at')}"
    ]
    return "\n".join(lines)


def _get_evidence_by_id(registry: EvidenceRegistry, ev_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a single evidence entry by a user‑supplied identifier string.
    If the string is a pure integer, treat it as the auto‑increment ID.
    Otherwise treat it as a reference value (URI or local_id) and return the
    first matching entry.
    """
    if ev_id.isdigit():
        return registry.get_evidence(int(ev_id))

    entries = registry.get_evidence_by_ref(ev_id)
    return entries[0] if entries else None


def query_evidence(args: argparse.Namespace) -> int:
    """Execute the query command."""
    log_level = "DEBUG" if args.debug else "INFO"
    setup_logging(level=log_level)

    try:
        registry = EvidenceRegistry()
    except Exception as e:
        logger.error(f"Failed to open evidence registry: {e}")
        return 1

    if args.id:
        ev = _get_evidence_by_id(registry, args.id)
        if ev:
            print(_format_evidence(ev))
        else:
            logger.error(f"No evidence found with ID '{args.id}'")
            return 1
        return 0

    if not args.list and not (args.type or args.property or args.engine):
        args.list = True

    if args.list:
        entries = registry.list_evidence(
            evidence_type=args.type,
            property_name=args.property,
            engine=args.engine,
            limit=100
        )
        if not entries:
            print("No evidence found matching the criteria.")
            return 0

        print(f"{'ID':<6} {'Type':<22} {'Engine':<18} {'Property':<20} {'Created':<20}")
        print("-" * 90)
        for e in entries:
            prop = e.get('property_name', '')[:20]
            created = e.get('created_at', '')[:19]
            print(f"{e['id']:<6} {e['type']:<22} {e['engine']:<18} {prop:<20} {created:<20}")
        print(f"\nTotal: {len(entries)} entries")
    else:
        print("Use --list or --id to query evidence. See --help for details.")
        return 1

    return 0


def main() -> int:
    parser = _setup_arg_parser()
    args = parser.parse_args()
    return query_evidence(args)


if __name__ == "__main__":
    sys.exit(main())
