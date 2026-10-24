# src/isir/verification/proof/koika/__init__.py
#
# Wire the deterministic proof strategies (domain extensions) into the generic
# strategy registry.  The core prover is strategy-agnostic; this module registers
# the built-in domain extensions so they participate in the escalation without
# the core importing them directly.
from . import prover
from . import coherence

prover.register_proof_strategy("coherence")(coherence.try_coherence_synthesis)
