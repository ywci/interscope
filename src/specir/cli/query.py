# src/specir/cli/query.py
#
# CLI subcommand `query` – queries the evidence registry (SQLite database)
# to retrieve proven theorems, counterexamples, invariants, and other
# verification artifacts.

import argparse
import json
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
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

    list_parser = subparsers.add_parser("list", help="List evidence entries (default)")
    list_parser.add_argument("--type", "-t", type=str, choices=[
        "counterexample_trace", "inductive_invariant", "coq_theorem",
        "acl2_theorem", "simulation_trace"
    ], help="Filter by evidence type")
    list_parser.add_argument("--property", "-p", type=str, help="Filter by property name")
    list_parser.add_argument("--engine", "-e", type=str,
                             help="Filter by verification engine (e.g., BMC, IC3, theorem_proving)")
    list_parser.add_argument("--design", "-d", type=str, help="Filter by design name")
    list_parser.add_argument("--output-format", choices=["json", "text"], default="text",
                             help="Output format (default: text)")

    id_parser = subparsers.add_parser("id", help="Show details for a specific evidence ID")
    id_parser.add_argument("id", type=str, help="Evidence ID (numeric or ref string)")
    id_parser.add_argument("--output-format", choices=["json", "text"], default="text")

    stats_parser = subparsers.add_parser("stats", help="Show summary statistics")
    stats_parser.add_argument("--output-format", choices=["json", "text"], default="text")

    export_parser = subparsers.add_parser("export", help="Export evidence entries to file")
    export_parser.add_argument("output_file", type=str, help="Output file path (.json or .csv)")
    export_parser.add_argument("--design", "-d", type=str, help="Filter by design name")
    export_parser.add_argument("--backend", "-b", type=str, help="Filter by engine/backend")
    export_parser.add_argument("--status", "-s", type=str, help="Filter by status")

    filter_parser = subparsers.add_parser("filter", help="Flexible filtering of evidence")
    filter_parser.add_argument("--design", "-d", type=str, help="Filter by design name")
    filter_parser.add_argument("--backend", "-b", type=str, help="Filter by engine")
    filter_parser.add_argument("--status", "-s", type=str, help="Filter by status")
    filter_parser.add_argument("--property", "-p", type=str, help="Filter by property name")
    filter_parser.add_argument("--type", "-t", type=str, help="Filter by evidence type")
    filter_parser.add_argument("--output-format", choices=["json", "text"], default="text")
    filter_parser.add_argument("--limit", type=int, default=1000, help="Max entries to return")

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
        f"Design: {ev.get('design_name', 'N/A')}",
        f"Iterations: {ev.get('iterations', 'N/A')}",
        f"LLM Used: {bool(ev.get('llm_used')) if ev.get('llm_used') is not None else 'N/A'}",
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

    if not hasattr(args, 'command') or args.command is None:
        if hasattr(args, 'id') and args.id:
            args.command = "id"
        else:
            args.command = "list"

    if args.command == "id":
        ev_id = args.id
        ev = _get_evidence_by_id(registry, ev_id)
        if ev:
            if args.output_format == "json":
                print(json.dumps(ev, indent=2, default=str))
            else:
                print(_format_evidence(ev))
        else:
            logger.error(f"No evidence found with ID '{ev_id}'")
            return 1
        return 0

    elif args.command == "stats":
        stats = registry.get_summary_stats()
        if args.output_format == "json":
            print(json.dumps(stats, indent=2, default=str))
        else:
            print("Evidence Registry Statistics")
            print("=" * 40)
            print(f"Total entries: {stats['total_entries']}")
            print("\nBy backend:")
            for backend, count in stats['by_backend'].items():
                print(f"  {backend}: {count}")
            print("\nBy status:")
            for status, count in stats['by_status'].items():
                print(f"  {status}: {count}")
            if stats['by_design']:
                print("\nBy design:")
                for design, count in stats['by_design'].items():
                    print(f"  {design}: {count}")
            if stats['proved_by_backend']:
                print("\nProved theorems by backend:")
                for backend, count in stats['proved_by_backend'].items():
                    print(f"  {backend}: {count}")
        return 0

    elif args.command == "export":
        filepath = Path(args.output_file)
        if filepath.suffix.lower() == '.csv':
            registry.export_to_csv(
                filepath,
                design=args.design,
                backend=args.backend,
                status=args.status,
            )
        else:
            registry.export_to_json(
                filepath,
                design=args.design,
                backend=args.backend,
                status=args.status,
            )
        logger.info(f"Evidence exported to {filepath}")
        return 0

    elif args.command == "filter":
        entries = registry.query(
            design=args.design,
            backend=args.backend,
            status=args.status,
            property_name=args.property,
            evidence_type=args.type,
            limit=args.limit,
        )
        if args.output_format == "json":
            print(json.dumps(entries, indent=2, default=str))
        else:
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
        return 0

    elif args.command == "list":
        entries = registry.list_evidence(
            evidence_type=args.type,
            property_name=args.property,
            engine=args.engine,
            design_name=args.design,
            limit=100
        )
        if args.output_format == "json":
            print(json.dumps(entries, indent=2, default=str))
        else:
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
        return 0

    else:
        logger.error(f"Unknown command: {args.command}")
        return 1


def main() -> int:
    parser = _setup_arg_parser()
    args = parser.parse_args()
    return query_evidence(args)


if __name__ == "__main__":
    sys.exit(main())
