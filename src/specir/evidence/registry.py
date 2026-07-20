# src/specir/evidence/registry.py
#
# SQLite-backed evidence registry for tracking verification artifacts
# (theorems, counterexamples, invariants, traces). Provides methods for
# adding, querying, updating, and deleting evidence entries.

import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from specir.utils.config_loader import get_config, get_project_root

SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    ref_type TEXT NOT NULL,
    ref_value TEXT NOT NULL,
    engine TEXT NOT NULL,
    status TEXT,
    property_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_evidence_type ON evidence(type);
CREATE INDEX IF NOT EXISTS idx_evidence_property ON evidence(property_name);
CREATE INDEX IF NOT EXISTS idx_evidence_engine ON evidence(engine);
"""


class EvidenceRegistry:
    """Manages the evidence SQLite database."""

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
        self._init_db()

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        with self._get_connection() as conn:
            conn.executescript(SCHEMA)

    def _get_connection(self) -> sqlite3.Connection:
        """Return a connection to the database with row_factory set to dict."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def add_evidence(self,
                     evidence_type: str,
                     ref_type: str,
                     ref_value: str,
                     engine: str,
                     status: Optional[str] = None,
                     property_name: Optional[str] = None) -> int:
        """
        Add a new evidence entry.

        Args:
            evidence_type: One of 'counterexample_trace', 'inductive_invariant',
                           'coq_theorem', 'acl2_theorem', 'simulation_trace'.
            ref_type: 'uri' or 'local_id'.
            ref_value: The reference (e.g., file URI or identifier).
            engine: Verification engine (e.g., 'BMC', 'IC3', 'theorem_proving').
            status: Optional status (e.g., 'active', 'proved', 'counterexample').
            property_name: Optional property name associated with this evidence.

        Returns:
            The auto-incremented ID of the new entry.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO evidence (type, ref_type, ref_value, engine, status, property_name)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (evidence_type, ref_type, ref_value, engine, status, property_name)
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

    def list_evidence(self,
                      evidence_type: Optional[str] = None,
                      property_name: Optional[str] = None,
                      engine: Optional[str] = None,
                      limit: int = 100) -> List[Dict[str, Any]]:
        """
        List evidence entries with optional filters.

        Args:
            evidence_type: Filter by type.
            property_name: Filter by property name.
            engine: Filter by engine.
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
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

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

    def get_statistics(self) -> Dict[str, int]:
        """Return counts of evidence by type."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT type, COUNT(*) as count FROM evidence GROUP BY type")
            rows = cursor.fetchall()
            return {row["type"]: row["count"] for row in rows}

    def add_counterexample(
        self,
        property_name: str,
        engine: str = "BMC",
        trace_path: Optional[Path] = None,
        status: str = "counterexample",
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
            property_name=property_name
        )
