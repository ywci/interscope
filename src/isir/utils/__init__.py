# isir/utils — shared utilities.

import re


def sanitize_design_name(name: str) -> str:
    """Filesystem/identifier-safe form of a design (module) name.

    Design names may contain ``/``, ``.``, and other characters (e.g. ONNX
    node paths); this maps them to a safe ``[A-Za-z0-9_-]`` token used for
    build directories, file names, and Verilog/Coq module identifiers.  The
    original name is preserved in ``SpecModule.source_name`` (evidence and
    logs can still show it).
    """
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", name or "")
    safe = safe or "design"
    if safe[0].isdigit():
        safe = "_" + safe
    return safe
