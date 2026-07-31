# src/specir/verification/perf/perf_evidence.py
#
# PERF-specific evidence management.
# Handles registration of proofs, counterexamples, and statistics
# generated during PERF traversal. All entries are tagged with a
# PERF-specific engine name to distinguish them from manually written
# or other automatically generated proofs.

from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime
from specir.evidence.registry import EvidenceRegistry
from specir.evidence.annotator import create_evidence_ref, add_evidence_to_registry
from specir.verification.perf.perf_stats import PERFStats
from specir.utils.logger import get_logger

logger = get_logger(__name__)


class PERFEvidence:
    """
    Manages PERF-generated evidence in the evidence registry.

    All evidence entries are tagged with a PERF-specific engine name
    (e.g., 'perf_koika', 'perf_acl2', or 'perf_model_check') to allow
    easy filtering and statistics.

    The class also provides helper methods to retrieve PERF-specific
    evidence for analysis or reuse.
    """

    def __init__(self, registry: Optional[EvidenceRegistry] = None):
        """
        Initialize the PERF evidence manager.

        Args:
            registry: Optional EvidenceRegistry instance. If not provided,
                      a new one is created using the default database path.
        """
        self.registry = registry or EvidenceRegistry()

    def register_proof(
        self,
        property_name: str,
        proof_script: str,
        backend: str,
        stats: Optional[PERFStats] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Register a proof successfully found by PERF.

        Args:
            property_name: Name of the proven property.
            proof_script: The full proof script (Coq or ACL2).
            backend: 'koika' or 'acl2' (or their normalized forms).
            stats: Optional PERFStats object for additional context.
            metadata: Optional extra metadata to attach.

        Returns:
            The ID of the newly created evidence entry.
        """
        # Normalize backend
        backend_norm = backend.lower().replace("ō", "o")
        if backend_norm.startswith("koi"):
            engine = "perf_koika"
            evidence_type = "coq_theorem"
        elif backend_norm == "acl2":
            engine = "perf_acl2"
            evidence_type = "acl2_theorem"
        else:
            logger.warning("Unknown backend '%s'; defaulting to perf_unknown", backend)
            engine = "perf_unknown"
            evidence_type = "coq_theorem"

        # Generate a reference value that includes the property name and a timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ref_value = f"perf:{property_name}:{timestamp}"

        # Build the evidence object
        evidence = create_evidence_ref(
            evidence_type=evidence_type,
            ref_type="uri",  # We could also use local_id, but URI is more informative
            ref_value=ref_value,
            engine=engine,
            status="proved",
            property_name=property_name,
        )

        # Add to registry
        evidence_id = add_evidence_to_registry(
            evidence=evidence,
            property_name=property_name,
            db_path=None,  # uses default from config
        )

        # Optionally, store the proof script itself as an artifact.
        # We could also store it in a separate file and reference it, but
        # the registry only stores references. For now, we just log.
        logger.info(
            "Registered PERF proof for '%s' (backend=%s, id=%d)",
            property_name, backend, evidence_id
        )

        # If stats are provided, register them as well
        if stats:
            self.register_stats(stats, property_name=property_name)

        return evidence_id

    def register_counterexample(
        self,
        property_name: str,
        trace_path: Optional[Path] = None,
        engine: str = "BMC",
        status: str = "counterexample",
    ) -> int:
        """
        Register a counterexample trace found during PERF.

        This is typically called when model checking (part of PERF's
        trace_alignment dimension) finds a counterexample, which is then
        used as reflection input.

        Args:
            property_name: Name of the violated property.
            trace_path: Path to the counterexample VCD file.
            engine: Model-checking engine (e.g., 'BMC', 'IC3').
            status: Evidence status (default 'counterexample').

        Returns:
            The ID of the newly created evidence entry.
        """
        # Use the registry's helper method for adding counterexamples
        evidence_id = self.registry.add_counterexample(
            property_name=property_name,
            engine=engine,
            trace_path=trace_path,
            status=status,
        )
        # Override engine to mark it as PERF-generated
        # (add_counterexample uses the engine we pass, so it's already correct)
        logger.info(
            "Registered PERF counterexample for '%s' (engine=%s, id=%d)",
            property_name, engine, evidence_id
        )
        return evidence_id

    def register_stats(
        self,
        stats: PERFStats,
        property_name: Optional[str] = None,
        tag: str = "perf_traversal",
    ) -> int:
        """
        Register PERF statistics as a simulation_trace evidence entry.

        This allows keeping a record of each PERF run for later analysis.

        Args:
            stats: PERFStats object to register.
            property_name: Optional property name to associate with.
            tag: A tag to identify the run (e.g., "perf_traversal").

        Returns:
            The ID of the newly created evidence entry.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ref_value = f"{tag}:{timestamp}"
        if property_name:
            ref_value = f"{property_name}:{ref_value}"

        # Convert stats to a JSON string for storage in the ref value?
        # Actually, we can store the stats as a text blob in the ref value,
        # but the evidence registry only has text fields. We'll store a
        # serialized summary as the ref value (limited length).
        stats_summary = stats.to_dict()
        # For brevity, store only key numbers in the ref string
        summary_str = (
            f"nodes={stats.total_nodes}, "
            f"depth={stats.max_depth}, "
            f"verifier_calls={stats.total_verifier_calls}, "
            f"beam={stats.beam_size}, "
            f"pruned={stats.pruned_by_pareto}"
        )
        ref_value = f"{ref_value}:{summary_str}"

        evidence = create_evidence_ref(
            evidence_type="simulation_trace",
            ref_type="local_id",
            ref_value=ref_value,
            engine="perf_stats",
            status="completed",
            property_name=property_name,
        )

        evidence_id = add_evidence_to_registry(
            evidence=evidence,
            property_name=property_name,
            db_path=None,
        )

        logger.info(
            "Registered PERF statistics (id=%d): %s",
            evidence_id, summary_str
        )
        return evidence_id

    def get_perf_proofs(
        self,
        property_name: Optional[str] = None,
        backend: Optional[str] = None,
    ) -> list:
        """
        Retrieve PERF-generated proofs from the evidence registry.

        Args:
            property_name: Optional filter by property name.
            backend: Optional filter by backend ('koika' or 'acl2').

        Returns:
            List of evidence entries (as dicts) that match.
        """
        engine_filter = "perf_koika" if backend and backend.startswith("koi") else "perf_acl2"
        if backend is None:
            engine_filter = None  # list all PERF engines

        # If engine_filter is None, we need to list both
        if engine_filter is None:
            # Get evidence from both engine types
            results = []
            for eng in ("perf_koika", "perf_acl2"):
                results.extend(
                    self.registry.list_evidence(
                        evidence_type="coq_theorem" if eng == "perf_koika" else "acl2_theorem",
                        property_name=property_name,
                        engine=eng,
                    )
                )
            return results
        else:
            evidence_type = "coq_theorem" if engine_filter == "perf_koika" else "acl2_theorem"
            return self.registry.list_evidence(
                evidence_type=evidence_type,
                property_name=property_name,
                engine=engine_filter,
            )

    def get_perf_counterexamples(
        self,
        property_name: Optional[str] = None,
    ) -> list:
        """
        Retrieve PERF-generated counterexample traces.

        Args:
            property_name: Optional filter by property name.

        Returns:
            List of counterexample evidence entries.
        """
        return self.registry.list_evidence(
            evidence_type="counterexample_trace",
            property_name=property_name,
            engine="BMC",  # We use BMC as engine, but could be PERF-specific
            # We could also filter by engine starting with 'perf' but we don't
            # set engine to 'perf' for counterexamples; we keep the MC engine.
            # To distinguish, we could add a note in status or metadata.
            # For now, we filter by status='counterexample' and type.
        )

    def get_latest_proof(self, property_name: str, backend: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve the most recent PERF proof for a given property and backend.

        Args:
            property_name: Name of the property.
            backend: 'koika' or 'acl2'.

        Returns:
            The most recent evidence entry, or None if not found.
        """
        engine = "perf_koika" if backend.startswith("koi") else "perf_acl2"
        entries = self.registry.list_evidence(
            property_name=property_name,
            engine=engine,
            limit=1,
        )
        return entries[0] if entries else None

    def get_stats_for_run(self, run_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieve PERF statistics evidence entry by run ID or the most recent.

        Args:
            run_id: Optional specific run ID (the ref_value suffix).

        Returns:
            The evidence entry, or None.
        """
        if run_id:
            entries = self.registry.get_evidence_by_ref(run_id)
            return entries[0] if entries else None
        else:
            # Get the most recent stats entry
            entries = self.registry.list_evidence(
                evidence_type="simulation_trace",
                engine="perf_stats",
                limit=1,
            )
            return entries[0] if entries else None
