# src/specir/verification/proof/prelude_templates.py
#
# Standard prelude templates for each proof backend.
#
# These templates contain the minimal set of imports and definitions
# that should be present in every generated proof file before any
# theorem or proof script is attempted.  They are used by the
# KoikaProver (and potentially other provers) to ensure that the Coq
# environment is fully set up, even if the original lowering pass
# omitted some imports.
#
# The prelude is designed to be idempotent: if the same text is already
# present in the file, the prover will not inject it again.

from typing import Dict, Optional
from specir.utils.logger import get_logger

logger = get_logger(__name__)

KOIKA_PRELUDE = """Require Import Init.Datatypes.
Require Import Arith.PeanoNat.
Require Import Lists.List.
Require Import Bool.Bool.
Require Import Lia.
Require Import Psatz.
Import ListNotations.
"""

ACL2_PRELUDE = """(in-package "ACL2")
(include-book "arithmetic-5/top" :dir :system)
(include-book "std/lists/nth" :dir :system)
(include-book "std/lists/update-nth" :dir :system)
"""

_PRELUDES: Dict[str, str] = {
    "koika": KOIKA_PRELUDE,
    "acl2": ACL2_PRELUDE,
}

def get_prelude(backend: str) -> str:
    """
    Return the standard prelude template for the given backend.

    Args:
        backend: Backend name, e.g., "koika", "acl2".

    Returns:
        The prelude string. If no template exists for the backend,
        an empty string is returned.
    """
    key = backend.lower()
    prelude = _PRELUDES.get(key, "")
    if not prelude:
        logger.debug("No prelude template defined for backend '%s'.", backend)
    return prelude
