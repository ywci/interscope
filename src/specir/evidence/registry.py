# src/specir/evidence/registry.py
#
# SQLite-backed evidence registry for tracking verification artifacts
# (theorems, counterexamples, invariants, traces). Provides methods for
# adding, querying, updating, and deleting evidence entries.

import sqlite3
import json
import csv
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from specir.utils.config_loader import get_config, get_project_root
from specir.utils.logger import get_logger

logger = get_logger(__name__)

# Only the CREATE TABLE statement – indexes are created separately after migration.
SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    ref_type TEXT NOT NULL,
    ref_value TEXT NOT NULL,
    engine TEXT NOT NULL,
    status TEXT,
    property_name TEXT,
    design_name TEXT,
    iterations INTEGER,
    llm_used INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Index definitions – run after schema migration.
INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_evidence_type ON evidence(type);",
    "CREATE INDEX IF NOT EXISTS idx_evidence_property ON evidence(property_name);",
    "CREATE INDEX IF NOT EXISTS idx_evidence_engine ON evidence(engine);",
    "CREATE INDEX IF NOT EXISTS idx_evidence_status ON evidence(status);",
    "CREATE INDEX IF NOT EXISTS idx_evidence_design ON evidence(design_name);",
]


class EvidenceRegistry:
    """
    Manages the evidence SQLite database.

    Thread-safe: uses thread-local connections for concurrent access.
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize the registry.

        Args:
            db_path: Path to the SQLite database file. If None, read from config
                     (evidence.db_path) or default to 'build/evidence.db'.
        """
        if db_path is None:
            config = get_config()
            db_path_str = config.get("evidence", {}).get("db_path", "build/evidence.db")
            db_path = get_project_root() / db_path_str
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()
        self._migrate()
        self._create_indexes()

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        with self._get_connection() as conn:
            conn.executescript(SCHEMA)

    def _create_indexes(self) -> None:
        """Create indexes on the evidence table."""
        with self._get_connection() as conn:
            for stmt in INDEXES:
                conn.execute(stmt)

    def _migrate(self) -> None:
        """Add columns introduced in newer versions if they are missing."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Get existing columns
            cursor.execute("PRAGMA table_info(evidence)")
            existing_cols = {row[1] for row in cursor.fetchall()}
            new_cols = {
                "design_name": "TEXT",
                "iterations": "INTEGER",
                "llm_used": "INTEGER",
            }
            for col, col_type in new_cols.items():
                if col not in existing_cols:
                    try:
                        conn.execute(f"ALTER TABLE evidence ADD COLUMN {col} {col_type}")
                        logger.info("Added column '%s' to evidence table.", col)
                    except sqlite3.OperationalError as e:
                        logger.warning("Could not add column '%s': %s", col, e)

    def _get_connection(self) -> sqlite3.Connection:
        """
        Return a thread-local connection to the database.

        Each thread gets its own connection to avoid SQLite thread-safety issues.
        """
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def add_evidence(self,
                     evidence_type: str,
                     ref_type: str,
                     ref_value: str,
                     engine: str,
                     status: Optional[str] = None,
                     property_name: Optional[str] = None,
                     design_name: Optional[str] = None,
                     iterations: Optional[int] = None,
                     llm_used: Optional[bool] = None) -> int:
        """
        Add a new evidence entry.

        Args:
            evidence_type: One of 'counterexample_trace', 'inductive_invariant',
                           'coq_theorem', 'acl2_theorem', 'simulation_trace'.
            ref_type: 'uri' or 'local_id'.
            ref_value: The reference (e.g., file URI or identifier).
            engine: Verification engine (e.g., 'BMC', 'IC3', 'theorem_proving', 'perf_koika').
            status: Optional status (e.g., 'active', 'proved', 'counterexample').
            property_name: Optional property name associated with this evidence.
            design_name: Optional design name for batch tracking.
            iterations: Optional number of iterations (for PERF).
            llm_used: Whether an LLM was involved (bool).

        Returns:
            The auto-incremented ID of the new entry.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            llm_int = None if llm_used is None else (1 if llm_used else 0)
            cursor.execute(
                """
                INSERT INTO evidence (type, ref_type, ref_value, engine, status,
                                      property_name, design_name, iterations, llm_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (evidence_type, ref_type, ref_value, engine, status,
                 property_name, design_name, iterations, llm_int)
            )
            return cursor.lastrowid

    def get_evidence(self, evidence_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve an evidence entry by its ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM evidence WHERE id = ?", (evidence_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_evidence_by_ref(self, ref_value: str) -> List[Dict[str, Any]]:
        """Retrieve all evidence entries matching a given reference value (URI or local_id)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM evidence WHERE ref_value = ?", (ref_value,))
            return [dict(row) for row in cursor.fetchall()]

    def get_evidence_by_type(self, evidence_type: str) -> List[Dict[str, Any]]:
        """Retrieve all evidence entries of a given type."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM evidence WHERE type = ?", (evidence_type,))
            return [dict(row) for row in cursor.fetchall()]

    def list_evidence(self,
                      evidence_type: Optional[str] = None,
                      property_name: Optional[str] = None,
                      engine: Optional[str] = None,
                      status: Optional[str] = None,
                      design_name: Optional[str] = None,
                      limit: int = 100) -> List[Dict[str, Any]]:
        """
        List evidence entries with optional filters.

        Args:
            evidence_type: Filter by type.
            property_name: Filter by property name.
            engine: Filter by engine.
            status: Filter by status.
            design_name: Filter by design name.
            limit: Maximum number of entries to return.

        Returns:
            List of evidence dictionaries.
        """
        query = "SELECT * FROM evidence WHERE 1=1"
        params = []
        if evidence_type:
            query += " AND type = ?"
            params.append(evidence_type)
        if property_name:
            query += " AND property_name = ?"
            params.append(property_name)
        if engine:
            query += " AND engine = ?"
            params.append(engine)
        if status:
            query += " AND status = ?"
            params.append(status)
        if design_name:
            query += " AND design_name = ?"
            params.append(design_name)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_latest_evidence(self,
                            evidence_type: Optional[str] = None,
                            property_name: Optional[str] = None,
                            engine: Optional[str] = None,
                            design_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve the most recent evidence entry matching filters."""
        results = self.list_evidence(
            evidence_type=evidence_type,
            property_name=property_name,
            engine=engine,
            design_name=design_name,
            limit=1
        )
        return results[0] if results else None

    def update_status(self, evidence_id: int, status: str) -> bool:
        """
        Update the status of an evidence entry.

        Returns:
            True if an entry was updated, False otherwise.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE evidence SET status = ? WHERE id = ?",
                (status, evidence_id)
            )
            return cursor.rowcount > 0

    def delete_evidence(self, evidence_id: int) -> bool:
        """Delete an evidence entry by ID. Returns True if deleted."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM evidence WHERE id = ?", (evidence_id,))
            return cursor.rowcount > 0

    def get_statistics(self) -> Dict[str, Any]:
        """Return counts of evidence by type, plus overall totals."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT type, COUNT(*) as count FROM evidence GROUP BY type")
            rows = cursor.fetchall()
            by_type = {row["type"]: row["count"] for row in rows}
            cursor.execute("SELECT COUNT(*) FROM evidence")
            total = cursor.fetchone()[0]
            return {"total": total, "by_type": by_type}

    def get_summary_stats(self) -> Dict[str, Any]:
        """
        Return comprehensive summary statistics grouped by backend, design, and status.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM evidence")
            total = cursor.fetchone()[0]

            cursor.execute("SELECT engine, COUNT(*) FROM evidence GROUP BY engine")
            by_backend = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute("SELECT status, COUNT(*) FROM evidence GROUP BY status")
            by_status = {row[0] if row[0] else "unknown": row[1] for row in cursor.fetchall()}

            cursor.execute("SELECT design_name, COUNT(*) FROM evidence WHERE design_name IS NOT NULL GROUP BY design_name")
            by_design = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute(
                "SELECT engine, COUNT(*) FROM evidence WHERE type IN ('coq_theorem','acl2_theorem') AND status='proved' GROUP BY engine"
            )
            proved_by_backend = {row[0]: row[1] for row in cursor.fetchall()}

            return {
                "total_entries": total,
                "by_backend": by_backend,
                "by_status": by_status,
                "by_design": by_design,
                "proved_by_backend": proved_by_backend,
            }

    def query(
        self,
        design: Optional[str] = None,
        backend: Optional[str] = None,
        status: Optional[str] = None,
        property_name: Optional[str] = None,
        evidence_type: Optional[str] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Query evidence entries with optional filters.

        Args:
            design: Filter by design_name.
            backend: Filter by engine (e.g., 'perf_koika', 'BMC').
            status: Filter by status.
            property_name: Filter by property name.
            evidence_type: Filter by type.
            limit: Max rows to return.

        Returns:
            List of matching evidence dictionaries.
        """
        return self.list_evidence(
            evidence_type=evidence_type,
            property_name=property_name,
            engine=backend,
            status=status,
            design_name=design,
            limit=limit,
        )

    def export_to_json(
        self,
        filepath: Union[str, Path],
        design: Optional[str] = None,
        backend: Optional[str] = None,
        status: Optional[str] = None,
    ) -> None:
        """
        Export matching evidence entries to a JSON file.

        Args:
            filepath: Output JSON file path.
            design: Optional filter by design_name.
            backend: Optional filter by engine.
            status: Optional filter by status.
        """
        entries = self.query(design=design, backend=backend, status=status, limit=100000)
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, default=str)
        logger.info("Exported %d evidence entries to %s", len(entries), filepath)

    def export_to_csv(
        self,
        filepath: Union[str, Path],
        design: Optional[str] = None,
        backend: Optional[str] = None,
        status: Optional[str] = None,
    ) -> None:
        """
        Export matching evidence entries to a CSV file.

        Args:
            filepath: Output CSV file path.
            design: Optional filter by design_name.
            backend: Optional filter by engine.
            status: Optional filter by status.
        """
        entries = self.query(design=design, backend=backend, status=status, limit=100000)
        if not entries:
            return
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = entries[0].keys()
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(entries)
        logger.info("Exported %d evidence entries to %s", len(entries), filepath)

    def add_counterexample(
        self,
        property_name: str,
        engine: str = "BMC",
        trace_path: Optional[Path] = None,
        status: str = "counterexample",
        design_name: Optional[str] = None,
    ) -> int:
        """
        Add a counterexample evidence entry (typically from model checking).

        Args:
            property_name: Name of the violated property.
            engine: Model‑checking engine used (e.g., 'BMC', 'IC3').
            trace_path: Path to the counterexample VCD file.  If provided,
                        the ref_type will be 'uri' and the value the absolute
                        path.  Otherwise 'local_id' and the property name.
            status: Evidence status (default 'counterexample').
            design_name: Optional design name.

        Returns:
            ID of the newly created evidence entry.
        """
        if trace_path and trace_path.exists():
            ref_type = "uri"
            ref_value = str(trace_path.resolve())
        else:
            ref_type = "local_id"
            ref_value = f"local:{property_name}"

        return self.add_evidence(
            evidence_type="counterexample_trace",
            ref_type=ref_type,
            ref_value=ref_value,
            engine=engine,
            status=status,
            property_name=property_name,
            design_name=design_name,
        )

    def get_counterexample(self, property_name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve the most recent counterexample trace for a property.
        """
        return self.get_latest_evidence(
            evidence_type="counterexample_trace",
            property_name=property_name,
        )

    def get_proven_theorem(
        self,
        property_name: str,
        backend: str = "koika"
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a proven theorem for a property (from any engine).
        """
        evidence_type = "coq_theorem" if backend == "koika" else "acl2_theorem"
        return self.get_latest_evidence(
            evidence_type=evidence_type,
            property_name=property_name,
            status="proved",
        )

    def get_perf_evidence(
        self,
        property_name: Optional[str] = None,
        backend: Optional[str] = None,
        status: Optional[str] = None,
        design_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve PERF-generated evidence (proofs and counterexamples).
        """
        if backend:
            engine_filter = f"perf_{backend}" if backend in ("koika", "acl2") else f"perf_{backend}"
        else:
            engine_filter = None

        results = []
        if engine_filter:
            results = self.list_evidence(
                property_name=property_name,
                engine=engine_filter,
                status=status,
                design_name=design_name,
                limit=1000
            )
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                query = "SELECT * FROM evidence WHERE engine LIKE 'perf_%'"
                params = []
                if property_name:
                    query += " AND property_name = ?"
                    params.append(property_name)
                if status:
                    query += " AND status = ?"
                    params.append(status)
                if design_name:
                    query += " AND design_name = ?"
                    params.append(design_name)
                query += " ORDER BY created_at DESC LIMIT 1000"
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        return results

    def get_perf_statistics(self) -> Dict[str, Any]:
        """
        Return statistics about PERF-generated evidence.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM evidence WHERE engine LIKE 'perf_%'")
            total = cursor.fetchone()[0]

            cursor.execute(
                "SELECT type, COUNT(*) FROM evidence WHERE engine LIKE 'perf_%' GROUP BY type"
            )
            by_type = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute(
                "SELECT status, COUNT(*) FROM evidence WHERE engine LIKE 'perf_%' GROUP BY status"
            )
            by_status = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute(
                "SELECT property_name, type, status, COUNT(*) FROM evidence "
                "WHERE engine LIKE 'perf_%' AND property_name IS NOT NULL "
                "GROUP BY property_name, type, status"
            )
            rows = cursor.fetchall()
            per_property = {}
            for prop, typ, stat, count in rows:
                if prop not in per_property:
                    per_property[prop] = {}
                if typ not in per_property[prop]:
                    per_property[prop][typ] = {}
                per_property[prop][typ][stat] = count

            proved = by_status.get("proved", 0)
            total_non_null = total or 1
            success_rate = proved / total_non_null if total_non_null > 0 else 0.0

            return {
                "total_perf_entries": total,
                "by_type": by_type,
                "by_status": by_status,
                "per_property": per_property,
                "success_rate": success_rate,
                "proved_count": proved,
                "failed_count": total - proved,
            }
