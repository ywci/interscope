# src/isir/lowering/koika_to_rtl.py
#
# ISIR → Verilog RTL via Kōika's Coq DSL.
# - Resolves parameterized types (e.g., DATA_WIDTH) to integer widths.
# - Skips memory and unsupported arithmetic actions to keep the design compilable.
# - Post-processes the Verilog to expose input ports and normalize clock/reset names.

import json
import os
import shutil
import subprocess
import tempfile
import re
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from isir.dialects import isir, rtl
from isir.utils.expr import parse_sexpr, ExprError, expr_to_string, unfold_user_functions
from isir.utils.logger import get_logger
from isir.utils.config_loader import get_project_root

logger = get_logger(__name__)

# Blackbox (uninterpreted) function names for the current design; used by
# `_coq_bits_expr` to emit `extcall` for external calls.  Kōika's `extcall`
# signature is `Sig 1` (single argument), so only single-argument blackboxes are
# extcall-able; multi-argument ones are skipped in the RTL lowering.
_BLACKBOX_NAMES = set()
_MULTIARG_BLACKBOXES = set()
_BLACKBOX_SIGNATURES: Dict[str, Dict[str, Any]] = {}


class KoikaToRTLError(Exception):
    """Raised when lowering or compilation fails."""
    pass


def convert(
    spec_module: isir.SpecModule,
    output_dir: Path,
    koika_path: Optional[str] = None,
    keep_temp: bool = False
) -> rtl.RTLModuleContainer:
    """Lower a SpecModule to Verilog RTL. External inputs are internalized and exposed."""
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    design_name = spec_module.name
    original_inputs = list(spec_module.inputs)

    params: Dict[str, int] = {}
    for name, param_info in spec_module.parameters.items():
        if not isinstance(param_info, dict):
            continue
        default = param_info.get("default")
        if isinstance(default, int):
            params[name] = default
        elif isinstance(default, str):
            try:
                params[name] = int(default)
            except ValueError:
                logger.warning("Could not parse parameter '%s' default '%s' as int; skipping.", name, default)

    # Internalize inputs – they become plain registers for synthesis
    internal_spec = _internalize_inputs(spec_module)

    # 1. Generate Coq file (no external inputs, problematic actions skipped)
    coq_file = output_dir / f"{design_name}.v"
    logger.info("Generating Kōika Coq file for '%s'", design_name)
    coq_code = _generate_coq_design(internal_spec, params)
    coq_file.write_text(coq_code, encoding="utf-8")

    # 2. Locate (or build) the Kōika Coq library
    project_root = get_project_root()
    default_koika_dir = str(project_root / "tools" / "koika")
    koika_dir = os.environ.get("KOIKA_DIR", default_koika_dir)

    coq_path, coq_flag = _find_or_build_koika_coq_path(koika_dir)

    # 3. Compile with coqc → OCaml extraction
    coqc_cmd = _opam_coqc_command(coq_flag, coq_path, coq_file)
    logger.info("Compiling Coq: %s", " ".join(coqc_cmd))
    try:
        subprocess.run(coqc_cmd, capture_output=True, text=True, timeout=300, cwd=str(output_dir), check=True)
    except subprocess.CalledProcessError as e:
        logger.error("coqc failed:\n%s", e.stderr)
        raise KoikaToRTLError(f"Coq compilation failed: {e.stderr[:500]}")

    ml_file = output_dir / f"{design_name}.ml"
    if not ml_file.exists():
        raise KoikaToRTLError("Coq extraction did not produce %s.ml" % design_name)
    (output_dir / f"{design_name}.mli").touch()

    # 4. Invoke cuttlec on the extracted OCaml
    compiler = _find_compiler(koika_path)
    cmd = [str(compiler), str(ml_file), "-T", "verilog", "-o", str(output_dir)]
    logger.info("Invoking Kōika compiler: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=str(output_dir), check=True)
    except subprocess.CalledProcessError as e:
        logger.error("Kōika compiler stderr:\n%s", e.stderr)
        raise KoikaToRTLError(f"Kōika compilation failed: {e.stderr[:500]}")

    # 5. Locate generated Verilog
    verilog_path = output_dir / f"{design_name}.v"
    if not verilog_path.exists():
        nested = output_dir / f"{design_name}.v" / f"{design_name}.v"
        if nested.exists():
            verilog_path = nested
        else:
            for candidate in sorted(output_dir.rglob("*.v")):
                verilog_path = candidate
                break
    if not verilog_path.exists():
        raise KoikaToRTLError("Kōika compiler did not produce a Verilog file")

    # Read generated Verilog and apply fixes for Verilator compatibility
    raw_verilog_content = verilog_path.read_text()
    
    # Normalize Clock and Reset naming conventions
    modified_verilog = raw_verilog_content.replace("CLK", "clk").replace("RST_N", "rst_n")
    
    modified_verilog = re.sub(
        r"(reg\s*(?:\[[^\]]+\])?\s*\w+\s*(/\*.*?\*/)?)\s*=\s*[^;]+;",
        r"\1;",
        modified_verilog
    )
    
    # Post-process to inject the expected Inp_ top-level ports into the Verilog module
    port_declarations = []
    input_assigns = []
    for inp in original_inputs:
        # Resolve parameterised type before computing width
        resolved_type = _resolve_type(inp.data_type, params)
        w = _safe_width(resolved_type)
        cap_name = inp.name[0].upper() + inp.name[1:] if inp.name else inp.name
        port_declarations.append(f"  input [{w-1}:0] Inp_{inp.name},")

        # Make the internalized input a combinational wire driven by the port,
        # instead of a register latched on the clock.  The Kōika backend registers
        # every input (X <= Inp_x), which shifts all input-dependent state one
        # cycle later; exposing the port directly removes that latency.
        modified_verilog = re.sub(
            rf"reg(\[[^\]]+\])?\s*{cap_name}\b(\s*/\*[^*]*\*/)?",
            rf"wire\1 {cap_name}\2",
            modified_verilog, count=1
        )
        # Drop the reset, the self-hold, and the latch to the (now wire) input.
        modified_verilog = re.sub(
            rf"{cap_name}\b\s*<=\s*\d+'[bdh][0-9a-fA-F_xXzZ?]+\s*;", "", modified_verilog
        )
        modified_verilog = re.sub(
            rf"{cap_name}\b\s*<=\s*{cap_name}\b\s*;", "", modified_verilog
        )
        modified_verilog = re.sub(
            rf"{cap_name}\b\s*<=\s*Inp_{inp.name}\s*;", "", modified_verilog
        )
        input_assigns.append(f"  assign {cap_name} = Inp_{inp.name};")

    if port_declarations:
        # Inject input ports right after the module declaration statement
        module_pattern = rf"(module\s+{design_name}\s*\()"
        ports_str = "\n" + "\n".join(port_declarations) + "\n"
        modified_verilog = re.sub(module_pattern, r"\1" + ports_str, modified_verilog)

    if input_assigns:
        # Add the continuous assignments after the module declaration (before
        # the first always block).
        modified_verilog = re.sub(
            r"(module\s+\w+\s*\([^)]*\)\s*;)\n",
            r"\1\n" + "\n".join(input_assigns) + "\n",
            modified_verilog, count=1
        )

    # Add suppression for initialization layouts and format limits
    lint_suppression = "/* verilator lint_off PROCASSINIT */\n"
    modified_verilog = lint_suppression + modified_verilog

    # Append a zero-returning stub for each blackbox so the extcall'd module
    # resolves. The direct path and the reference both treat an uninterpreted
    # function as returning 0, so the stub matches that semantics.
    for name, sig in _BLACKBOX_SIGNATURES.items():
        ret_type = sig.get("return", "bits<1>")
        rw = _safe_width(_resolve_type(ret_type, params))
        param_types = sig.get("params", [])
        pw = _safe_width(_resolve_type(param_types[0], params)) if param_types else 1
        modified_verilog += (
            f"\nmodule {name}(input clk, input rst_n, input [{pw - 1}:0] arg, "
            f"output reg [{rw - 1}:0] out);\n"
            f"  always @(posedge clk) out <= {rw}'d0;\n"
            f"endmodule\n"
        )

    verilog_path.write_text(modified_verilog, encoding="utf-8")

    # 6. Build RTL container and populate mapping entries using proper MappingEntry
    mapping_entries = []
    for inp in original_inputs:
        resolved_type = _resolve_type(inp.data_type, params)
        w = _safe_width(resolved_type)
        entry = rtl.MappingEntry(
            rtl_signal=f"Inp_{inp.name}",
            isir_ref=f"module.inputs[name={inp.name}]",
            kind="input_internalized",
            width=w
        )
        mapping_entries.append(entry)

    mapping = rtl.RTLMapping(design_name=design_name, entries=mapping_entries)
    with open(output_dir / "mapping.json", "w") as f:
        json.dump(mapping.to_json(), f, indent=2)

    rtl_module = rtl.RTLModule(name=design_name, raw_verilog=modified_verilog, file_path=verilog_path)
    return rtl.RTLModuleContainer(modules={design_name: rtl_module}, mapping=mapping, design_name=design_name)


def _internalize_inputs(spec_module: isir.SpecModule) -> isir.SpecModule:
    """Return a copy where every input is turned into a register."""
    import copy
    mod = copy.deepcopy(spec_module)
    for inp in mod.inputs:
        init = False if inp.data_type == "bool" else 0
        mod.state_ops.append(isir.SpecStateOp(
            state_name=inp.name, kind="register", data_type=inp.data_type, initial=init
        ))
    # Also internalize outputs that a rule writes (they become registers, since
    # the Kōika reg_t is register-only and cannot express combinational outputs).
    output_types = {o.name: o.data_type for o in mod.outputs}
    state_names = {s.state_name for s in mod.state_ops}
    for r in mod.rule_ops:
        for act in r.actions:
            try:
                e = parse_sexpr(act)
            except ExprError:
                continue
            if isinstance(e, list) and e and e[0] == "write" and len(e) == 3 and isinstance(e[1], str):
                name = e[1]
                if name in output_types and name not in state_names:
                    mod.state_ops.append(isir.SpecStateOp(
                        state_name=name, kind="register", data_type=output_types[name], initial=0
                    ))
                    state_names.add(name)
    mod.inputs = []
    return mod


def _find_or_build_koika_coq_path(koika_dir: str) -> Tuple[str, str]:
    """Return (path, flag). Build and install the Coq libraries if necessary."""
    path, flag = _try_find_koika_coq_path(koika_dir)
    if path is not None:
        return path, flag

    logger.info("Kōika Coq libraries not found; building and installing them now...")
    _run_in_opam_env(
        f"cd {koika_dir} && dune build @install && dune install",
        timeout=600
    )

    path, flag = _try_find_koika_coq_path(koika_dir)
    if path is not None:
        return path, flag

    raise KoikaToRTLError(
        "Cannot locate Kōika Coq libraries even after building and installing. "
        "Check the Koika installation."
    )


def _try_find_koika_coq_path(koika_dir: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (path, flag) or (None, None)."""
    koika_root = Path(koika_dir)
    candidates = [
        (koika_root / "_build/install/default/lib/coq/user-contrib", "Koika"),
        (koika_root / "_build/default/coq", "Koika"),
        (koika_root / "coq", "Koika")
    ]
    for path, logical in candidates:
        for flag in ("-Q", "-R"):
            if _test_coq_import(path, logical, flag):
                logger.info("Using Coq library path: %s with %s", path, flag)
                return str(path), flag
    return None, None


def _test_coq_import(path: Path, logical: str, flag: str) -> bool:
    """Check coqc can import Koika.Frontend using a temporary file."""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test_import.v"
            test_file.write_text("Require Import Koika.Frontend.\n")
            cmd = (
                f"eval $(opam env) && "
                f"coqc {flag} {path} {logical} {test_file}"
            )
            subprocess.run(["bash", "-c", cmd], capture_output=True, timeout=15, check=True)
            return True
    except subprocess.CalledProcessError:
        return False


def _run_in_opam_env(cmd: str, timeout: int = 60) -> None:
    """Execute a shell command inside the opam environment."""
    full_cmd = f"eval $(opam env) && {cmd}"
    try:
        subprocess.run(["bash", "-c", full_cmd], capture_output=True, timeout=timeout, check=True)
    except subprocess.CalledProcessError as e:
        raise KoikaToRTLError(f"Command failed: {cmd}\n{e.stderr}")


def _opam_coqc_command(flag: str, path: str, coq_file: Path) -> List[str]:
    """coqc invocation inside opam env."""
    return [
        "bash", "-c",
        f'eval $(opam env) && coqc {flag} {path} Koika {coq_file}'
    ]


def _find_compiler(koika_path: Optional[str]) -> Path:
    if koika_path:
        candidate = Path(koika_path)
        if candidate.exists():
            return candidate
        raise KoikaToRTLError(f"Kōika compiler not found at '{koika_path}'")
    path = shutil.which("koika")
    if path:
        return Path(path)
    for loc in [Path.home() / ".opam" / "default" / "bin" / "koika", Path("/usr/local/bin/koika")]:
        if loc.exists():
            return loc
    raise KoikaToRTLError("Kōika compiler binary not found")


def _capitalize(name: str) -> str:
    return name[0].upper() + name[1:] if name else name


def _safe_width(data_type: str) -> int:
    """Return bit width, defaulting to 32 if the type string cannot be parsed."""
    try:
        return _koika_width(data_type)
    except (ValueError, KeyError):
        logger.warning("Could not parse width from type '%s'; defaulting to 32.", data_type)
        return 32


def _koika_width(data_type: str) -> int:
    """Return bit width. Assumes the type is already concrete (no parameters)."""
    if data_type == "bool": return 1
    if data_type.startswith("bits<"):
        return int(data_type[5:-1])
    raise ValueError(f"Unrecognized type: {data_type}")


def _resolve_type(type_spec: str, params: Dict[str, int]) -> str:
    """Replace parameter names in a type string with their integer values."""
    result = type_spec
    for name, value in params.items():
        result = result.replace(name, str(value))
    return result


def _has_unsupported_ops(expr: Any) -> bool:
    """Return True if the expression contains operators that cannot be lowered."""
    if isinstance(expr, list) and len(expr) > 0:
        op = expr[0]
        if op in ("mem_read", "mem_write", "slice", "mul", "div", "mod"):
            return True
        if op in _MULTIARG_BLACKBOXES:
            return True
        for arg in expr[1:]:
            if _has_unsupported_ops(arg):
                return True
    return False


def _collect_reads(expr: Any, acc: Optional[set] = None) -> set:
    """Return the set of register names read by an S-expression (`read` nodes)."""
    if acc is None:
        acc = set()
    if isinstance(expr, list):
        if expr and expr[0] == "read" and len(expr) > 1 and isinstance(expr[1], str):
            acc.add(expr[1])
        for a in expr:
            _collect_reads(a, acc)
    return acc


def _generate_coq_design(spec_module: isir.SpecModule, params: Dict[str, int]) -> str:
    registers = [s for s in spec_module.state_ops if s.kind == "register"]

    functions = getattr(spec_module, "functions", None) or []
    blackboxes = []
    for f in functions:
        name = f.get("name") if isinstance(f, dict) else getattr(f, "name", None)
        body = f.get("body") if isinstance(f, dict) else getattr(f, "body", None)
        if not name or body is not None:
            continue
        fparams = f.get("params", []) if isinstance(f, dict) else getattr(f, "params", [])
        ret = f.get("return", "bits<1>") if isinstance(f, dict) else getattr(f, "return", "bits<1>")
        param_types = [p.get("type", "bits<1>") if isinstance(p, dict) else getattr(p, "type", "bits<1>") for p in fparams]
        if len(param_types) == 1:
            blackboxes.append({"name": name, "params": param_types, "return": ret})
        else:
            logger.warning("Blackbox '%s' has %d arguments; Kōika extcall supports 1. Skipping its rules in RTL.", name, len(param_types))
    global _BLACKBOX_NAMES, _MULTIARG_BLACKBOXES, _BLACKBOX_SIGNATURES
    _BLACKBOX_NAMES = {bb["name"] for bb in blackboxes}
    _BLACKBOX_SIGNATURES = {bb["name"]: bb for bb in blackboxes}
    _MULTIARG_BLACKBOXES = {
        (f.get("name") if isinstance(f, dict) else getattr(f, "name", None))
        for f in functions
        if (f.get("body") if isinstance(f, dict) else getattr(f, "body", None)) is None
        and len((f.get("params", []) if isinstance(f, dict) else getattr(f, "params", []))) != 1
    }
    flattened_rules: List[Tuple[str, str, str, Any]] = []
    for rule in spec_module.rule_ops:
        ridx = 0
        # Unfold user functions in the rule's condition so the Coq DSL sees only
        # primitive operators.
        condition = unfold_user_functions(rule.condition or "true", functions)
        try:
            cond_parsed = parse_sexpr(condition)
        except ExprError:
            cond_parsed = None
        if cond_parsed is not None and _has_unsupported_ops(cond_parsed):
            continue  # condition uses an unsupported op (e.g. slice in a function)
        for action_str in rule.actions:
            try:
                parsed = parse_sexpr(action_str)
            except ExprError:
                continue
            if isinstance(parsed, list) and len(parsed) >= 3 and parsed[0] == 'write':
                dest = parsed[1]
                if isinstance(dest, str):
                    sub = f"{rule.rule_name}_act_{ridx}"
                    expr_val = parse_sexpr(unfold_user_functions(parsed[2], functions))
                    # Skip memory ops and unsupported arithmetic AFTER inlining, so
                    # an unsupported op inside a user-function body is also caught.
                    if _has_unsupported_ops(expr_val):
                        continue
                    flattened_rules.append((sub, condition, dest, expr_val))
                    ridx += 1

    # Merge multiple writes to the same register into ONE sub-rule with a nested
    # `ite` (last writer wins).  The Kōika `|>` scheduler drops the second write
    # to a register, so a register written by two rules would lose all but the
    # first write.  Merging keeps the observable semantics: later rules override
    # earlier ones when both fire.
    _by_dest: Dict[str, List[Tuple[str, Any]]] = {}
    for _sub, _cond, dest, expr_val in flattened_rules:
        _by_dest.setdefault(dest, []).append((_cond, expr_val))
    flattened_rules = []
    for dest, writes in _by_dest.items():
        merged_expr: Any = ["read", dest]
        # Forward order: the LAST writer becomes the OUTER ite (highest priority),
        # matching the ISIR "last write wins" semantics.
        for cond, expr_val in writes:
            merged_expr = ["ite", parse_sexpr(cond), expr_val, merged_expr]
        flattened_rules.append((f"{dest}_merged", "true", dest, merged_expr))

    # Topologically sort the merged writes so a register is written AFTER every
    # register that READS it.  The single {{ ...; ... }} action composes writes
    # sequentially, so a writer must come after its readers: then each reader
    # still sees the cycle-old value, matching the ISIR `parallel` schedule.
    _dest_set = {dest for _, _, dest, _ in flattened_rules}
    _reads = {dest: (_collect_reads(expr) & _dest_set) for _, _, dest, expr in flattened_rules}
    # _deps[X] = the destinations that READ X (X's write must come after them).
    _deps = {d: set() for d in _dest_set}
    for d in _dest_set:
        for r in _reads[d]:
            if r in _deps:
                _deps[r].add(d)
    _order: List[str] = []
    _avail = [d for d in _dest_set if not _deps[d]]
    while _avail:
        d = _avail.pop()
        _order.append(d)
        for other in _dest_set:
            if d in _deps[other]:
                _deps[other].discard(d)
                if not _deps[other]:
                    _avail.append(other)
    # Fallback for any cycle (shouldn't happen): keep original order.
    for d in _dest_set:
        if d not in _order:
            _order.append(d)
    _by_name = {dest: (name, "true", dest, expr) for name, _, dest, expr in flattened_rules}
    flattened_rules = [_by_name[d] for d in _order]

    lines = [
        "Require Import Koika.Frontend.",
        "Require Import Koika.Interop.",
        "Require Import Koika.ExtractionSetup.",
        "",
        "Set Primitive Projections.",
        "Set Printing Width 160.",
        ""
    ]

    lines.append("Inductive reg_t :=")
    for r in registers:
        lines.append(f"  | {_capitalize(r.state_name)}")
    if not registers:
        lines.append("  | Dummy")
    lines.append(".\n")

    lines.append("Definition R (r : reg_t) : type := match r with")
    reg_widths = {}
    for r in registers:
        # Resolve parameters before computing width
        resolved_type = _resolve_type(r.data_type, params)
        w = _safe_width(resolved_type)
        reg_widths[_capitalize(r.state_name)] = w
        lines.append(f"  | {_capitalize(r.state_name)} => bits_t {w}")
    if not registers:
        lines.append("  | Dummy => bits_t 32")
    lines.append("  end.\n")

    lines.append("Inductive rule_name_t :=")
    if flattened_rules:
        lines.append("  | Step_merged")
    else:
        lines.append("  | Dummy_rule")
    lines.append(".\n")

    if blackboxes:
        lines.append("Inductive ext_fn_t :=")
        for bb in blackboxes:
            lines.append(f"  | {_capitalize(bb['name'])}")
        lines.append(".\n")
        lines.append("Definition Sigma (fn : ext_fn_t) : ExternalSignature := match fn with")
        for bb in blackboxes:
            arg_types = [f"bits_t {_safe_width(t)}" for t in bb["params"]]
            ret_type = f"bits_t {_safe_width(bb['return'])}"
            sig = " ~> ".join(arg_types + [ret_type]) if arg_types else ret_type
            lines.append(f"  | {_capitalize(bb['name'])} => {{$ {sig} $}}")
        lines.append("  end.\n")
        lines.append("Definition sim_ext_fn_specs (fn : ext_fn_t) := match fn with")
        for bb in blackboxes:
            lines.append(f"  | {_capitalize(bb['name'])} => {{| efs_name := \"{bb['name']}\"; efs_method := false |}}")
        lines.append("  end.\n")
    else:
        lines.append("Definition ext_fn_t := empty_ext_fn_t.")
        lines.append("Definition Sigma := empty_Sigma.\n")

    lines.append("Definition urules (rl : rule_name_t) : uaction reg_t ext_fn_t := match rl with")
    if flattened_rules:
        # One combined rule performs every register write in topologically sorted
        # order (readers before writers).  A single {{ ...; ...; ... }} action
        # avoids the Kōika `|>` scheduler's read-after-write hazard, which dropped
        # a write whenever the register was read by an earlier rule.
        actions = []
        for rname, condition, dest, expr_val in flattened_rules:
            target_width = reg_widths.get(_capitalize(dest), 32)
            coq_expr = _coq_bits_expr(expr_val, reg_widths, target_width)
            cap_dest = _capitalize(dest)
            actions.append(f"write0({cap_dest}, {coq_expr})")
        lines.append(f"  | Step_merged => {{{{ {'; '.join(actions)} }}}}")
    else:
        if registers:
            first_reg = _capitalize(registers[0].state_name)
            lines.append(f"  | Dummy_rule => {{{{ write0({first_reg}, read0({first_reg})) }}}}")
        else:
            lines.append("  | Dummy_rule => {{ write0(Dummy, read0(Dummy)) }}")
    lines.append("  end.\n")

    lines.append("Definition rules := tc_rules R Sigma urules.\n")

    lines.append("Definition initial_r (r : reg_t) : R r := match r return R r with")
    for r in registers:
        init_val = r.initial if r.initial is not None else (0 if r.data_type != "bool" else False)
        w = reg_widths[_capitalize(r.state_name)]
        if isinstance(init_val, bool):
            val_int = 1 if init_val else 0
            coq_val = f"(Bits.of_nat {w} {val_int})"
        else:
            coq_val = f"(Bits.of_nat {w} {init_val})"
        lines.append(f"  | {_capitalize(r.state_name)} => {coq_val}")
    if not registers:
        lines.append("  | Dummy => (Bits.of_nat 32 0)")
    lines.append("  end.\n")

    lines.append("Definition is_external (_ : rule_name_t) := false.\n")

    if flattened_rules:
        sched_expr = "Step_merged |> done"
    else:
        sched_expr = "done"

    lines.append("Definition package :=")
    lines.append("  {|")
    lines.append("    ip_koika := {|")
    lines.append("      koika_reg_types := R;")
    lines.append("      koika_reg_init reg := initial_r reg;")
    lines.append("      koika_ext_fn_types := Sigma;")
    lines.append("      koika_rules := rules;")
    lines.append("      koika_rule_external := is_external;")
    lines.append(f"      koika_scheduler := ({sched_expr});")
    lines.append(f"      koika_module_name := \"{spec_module.name}\"")
    lines.append("    |};")
    sim_spec = "sim_ext_fn_specs" if blackboxes else "empty_ext_fn_props"
    lines.append(f"    ip_sim := {{| sp_ext_fn_specs := {sim_spec}; sp_prelude := None |}};")
    if blackboxes:
        lines.append("    ip_verilog := Build_verilog_package_t (fun (x : ext_fn_t) => match x with")
        for bb in blackboxes:
            lines.append(f"      | {_capitalize(bb['name'])} => {{| efr_name := \"{bb['name']}\"; efr_internal := true |}}")
        lines.append("      end)")
    else:
        lines.append("    ip_verilog := Build_verilog_package_t (fun (x : ext_fn_t) => match x with end)")
    lines.append("  |}.\n")

    lines.append(f"Definition prog := Interop.Backends.register package.")
    lines.append(f"Extraction \"{spec_module.name}.ml\" prog.")

    return "\n".join(lines) + "\n"


def _infer_expr_width(expr: Any, reg_widths: dict) -> int:
    if isinstance(expr, str):
        return reg_widths.get(_capitalize(expr), 32)
    if isinstance(expr, list) and len(expr) > 0:
        op = expr[0]
        if op == 'read' and len(expr) > 1:
            return reg_widths.get(_capitalize(expr[1]), 32)
        if op in ('add', 'sub', 'and', 'or', 'band', 'bor', 'land', 'lor', 'not', 'ite', 'min', 'max'):
            for arg in expr[1:]:
                w = _infer_expr_width(arg, reg_widths)
                if w != 32:
                    return w
        if op == 'slice' and len(expr) > 2:
            try:
                return int(expr[1]) - int(expr[2]) + 1
            except (ValueError, TypeError):
                pass
    return 32


def _coq_bits_expr(expr, reg_widths: dict, current_width: int) -> str:
    if isinstance(expr, bool):
        val = 1 if expr else 0
        return f"|{current_width}`d{val}|"
    if isinstance(expr, int):
        return f"|{current_width}`d{expr}|"
    if isinstance(expr, str):
        return f"read0({_capitalize(expr)})"

    if not isinstance(expr, list) or len(expr) == 0:
        return str(expr)

    op = expr[0]
    args = expr[1:]

    if op == 'read':
        return f"read0({_capitalize(args[0])})"

    if op in ('add', 'sub'):
        sym = {'add': '+', 'sub': '-'}[op]
        body = f"({_coq_bits_expr(args[0], reg_widths, current_width)} {sym} {_coq_bits_expr(args[1], reg_widths, current_width)})"
        # `+`/`-` wrap to the operand width; widen to `current_width` when the
        # enclosing comparison needs a wider common width (e.g. `ge (add x y) 256`).
        op_w = _infer_expr_width(expr, reg_widths)
        if op_w != 32 and op_w < current_width:
            # `zeroExtend(a, b)` extends `a` to *target* width `b`.
            return f"zeroExtend({body}, {current_width})"
        return body

    if op in ('min', 'max'):
        a = _coq_bits_expr(args[0], reg_widths, current_width)
        b = _coq_bits_expr(args[1], reg_widths, current_width)
        # Kōika's frontend has no C ternary; use its `if ... then ... else`.
        if op == 'min':
            return f"(if ({a} < {b}) then {a} else {b})"
        return f"(if ({b} < {a}) then {a} else {b})"
    
    elif op in ('and', 'band', 'land', 'or', 'bor', 'lor', 'not', 'xor'):
        op_width = _infer_expr_width(expr, reg_widths)
        if op_width == 32:
            op_width = current_width
            
        if op == 'not':
            return f"(! {_coq_bits_expr(args[0], reg_widths, op_width)})"
        sym = '^' if op == 'xor' else ('&&' if op in ('and', 'band', 'land') else '||')
        return f"({_coq_bits_expr(args[0], reg_widths, op_width)} {sym} {_coq_bits_expr(args[1], reg_widths, op_width)})"
        
    elif op in ('eq', 'neq', 'gt', 'lt', 'gte', 'lte', 'le', 'ge'):
        w0 = _infer_expr_width(args[0], reg_widths)
        w1 = _infer_expr_width(args[1], reg_widths)
        # An integer literal wider than the operand must widen the comparison so
        # it isn't truncated (e.g. `ge (add x y) 256` needs 9 bits, not 8).
        if isinstance(args[0], int):
            w0 = max(1, args[0].bit_length())
        if isinstance(args[1], int):
            w1 = max(1, args[1].bit_length())
        operand_width = max(w0, w1)
            
        a = _coq_bits_expr(args[0], reg_widths, operand_width)
        b = _coq_bits_expr(args[1], reg_widths, operand_width)
        
        if op == 'eq':
            return f"({a} == {b})"
        elif op == 'neq':
            return f"({a} != {b})"
        elif op == 'gt':
            return f"({b} < {a})"
        elif op == 'lt':
            return f"({a} < {b})"
        elif op in ('gte', 'ge'):
            return f"(! ({a} < {b}))"
        elif op in ('lte', 'le'):
            return f"(! ({b} < {a}))"
            
    elif op == 'ite':
        cond = _coq_bits_expr(args[0], reg_widths, 1)
        t_val = _coq_bits_expr(args[1], reg_widths, current_width)
        f_val = _coq_bits_expr(args[2], reg_widths, current_width)
        return f"(if {cond} then {t_val} else {f_val})"
        
    elif op in _BLACKBOX_NAMES:
        arg_coq = " ".join(_coq_bits_expr(a, reg_widths, current_width) for a in args)
        return f"extcall {_capitalize(op)}({arg_coq})"

    elif op in ('slice', 'mul'):
        raise ExprError(f"Unsupported operator (should have been skipped): {op}")

    else:
        raise ExprError(f"Unsupported operator in Coq DSL: {op}")
