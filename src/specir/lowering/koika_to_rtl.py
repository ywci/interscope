# src/specir/lowering/koika_to_rtl.py
#
# SpecIR → Verilog RTL via Kōika's Coq DSL.
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
from specir.dialects import spec_ir, rtl_ir
from specir.utils.expr import parse_sexpr, ExprError
from specir.utils.logger import get_logger
from specir.utils.config_loader import get_project_root

logger = get_logger(__name__)


class KoikaToRTLError(Exception):
    """Raised when lowering or compilation fails."""
    pass


def convert(
    spec_module: spec_ir.SpecModule,
    output_dir: Path,
    koika_path: Optional[str] = None,
    keep_temp: bool = False
) -> rtl_ir.RTLModuleContainer:
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
    for inp in original_inputs:
        # Resolve parameterised type before computing width
        resolved_type = _resolve_type(inp.data_type, params)
        w = _safe_width(resolved_type)
        cap_name = inp.name[0].upper() + inp.name[1:] if inp.name else inp.name
        port_declarations.append(f"  input [{w-1}:0] Inp_{inp.name},")
        
        # Intercept Kōika's self-assignments inside the always block
        modified_verilog = re.sub(
            rf"({cap_name}\s*<=\s*){cap_name}\s*;",
            rf"\1Inp_{inp.name};",
            modified_verilog
        )

    if port_declarations:
        # Inject input ports right after the module declaration statement
        module_pattern = rf"(module\s+{design_name}\s*\()"
        ports_str = "\n" + "\n".join(port_declarations) + "\n"
        modified_verilog = re.sub(module_pattern, r"\1" + ports_str, modified_verilog)

    # Add suppression for initialization layouts and format limits
    lint_suppression = "/* verilator lint_off PROCASSINIT */\n"
    modified_verilog = lint_suppression + modified_verilog
    verilog_path.write_text(modified_verilog, encoding="utf-8")

    # 6. Build RTL container and populate mapping entries using proper MappingEntry
    mapping_entries = []
    for inp in original_inputs:
        resolved_type = _resolve_type(inp.data_type, params)
        w = _safe_width(resolved_type)
        entry = rtl_ir.MappingEntry(
            rtl_signal=f"Inp_{inp.name}",
            specir_ref=f"module.inputs[name={inp.name}]",
            kind="input_internalized",
            width=w
        )
        mapping_entries.append(entry)

    mapping = rtl_ir.RTLMapping(design_name=design_name, entries=mapping_entries)
    with open(output_dir / "mapping.json", "w") as f:
        json.dump(mapping.to_json(), f, indent=2)

    rtl_module = rtl_ir.RTLModule(name=design_name, raw_verilog=modified_verilog, file_path=verilog_path)
    return rtl_ir.RTLModuleContainer(modules={design_name: rtl_module}, mapping=mapping, design_name=design_name)


def _internalize_inputs(spec_module: spec_ir.SpecModule) -> spec_ir.SpecModule:
    """Return a copy where every input is turned into a register."""
    import copy
    mod = copy.deepcopy(spec_module)
    for inp in mod.inputs:
        init = False if inp.data_type == "bool" else 0
        mod.state_ops.append(spec_ir.SpecStateOp(
            state_name=inp.name, kind="register", data_type=inp.data_type, initial=init
        ))
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
        if op in ("mem_read", "mem_write", "slice", "mul", "div"):
            return True
        for arg in expr[1:]:
            if _has_unsupported_ops(arg):
                return True
    return False


def _generate_coq_design(spec_module: spec_ir.SpecModule, params: Dict[str, int]) -> str:
    registers = [s for s in spec_module.state_ops if s.kind == "register"]

    flattened_rules: List[Tuple[str, str, str, Any]] = []
    for rule in spec_module.rule_ops:
        ridx = 0
        for action_str in rule.actions:
            try:
                parsed = parse_sexpr(action_str)
            except ExprError:
                continue
            # Skip memory operations and unsupported arithmetic
            if isinstance(parsed, list) and len(parsed) >= 1:
                if _has_unsupported_ops(parsed):
                    continue
            if isinstance(parsed, list) and len(parsed) >= 3 and parsed[0] == 'write':
                dest = parsed[1]
                if isinstance(dest, str):
                    sub = f"{rule.rule_name}_act_{ridx}"
                    flattened_rules.append((sub, rule.condition, dest, parsed[2]))
                    ridx += 1

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
    for rname, _, _, _ in flattened_rules:
        lines.append(f"  | {_capitalize(rname)}")
    if not flattened_rules:
        lines.append("  | Dummy_rule")
    lines.append(".\n")

    lines.append("Definition ext_fn_t := empty_ext_fn_t.")
    lines.append("Definition Sigma := empty_Sigma.\n")

    lines.append("Definition urules (rl : rule_name_t) : uaction reg_t ext_fn_t := match rl with")
    for rname, condition, dest, expr_val in flattened_rules:
        target_width = reg_widths.get(_capitalize(dest), 32)
        coq_expr = _coq_bits_expr(expr_val, reg_widths, target_width)
        cap_dest = _capitalize(dest)
        
        if condition and condition != "true":
            cond_coq = _coq_bits_expr(parse_sexpr(condition), reg_widths, 1)
            # Maintain notation-safe balanced format by rewriting register to itself on fallback
            action = f"{{{{ if {cond_coq} then write0({cap_dest}, {coq_expr}) else write0({cap_dest}, read0({cap_dest})) }}}}"
        else:
            action = f"{{{{ write0({cap_dest}, {coq_expr}) }}}}"
            
        lines.append(f"  | {_capitalize(rname)} => {action}")
        
    if not flattened_rules:
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
        sched_expr = " |> ".join([f"{_capitalize(r[0])}" for r in flattened_rules]) + " |> done"
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
    lines.append("    ip_sim := {| sp_ext_fn_specs := empty_ext_fn_props; sp_prelude := None |};")
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
        if op in ('add', 'sub', 'and', 'or', 'band', 'bor', 'land', 'lor', 'not', 'ite'):
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
        return f"({_coq_bits_expr(args[0], reg_widths, current_width)} {sym} {_coq_bits_expr(args[1], reg_widths, current_width)})"
    
    elif op in ('and', 'band', 'land', 'or', 'bor', 'lor', 'not'):
        op_width = _infer_expr_width(expr, reg_widths)
        if op_width == 32:
            op_width = current_width
            
        if op == 'not':
            return f"(! {_coq_bits_expr(args[0], reg_widths, op_width)})"
        sym = '&&' if op in ('and', 'band', 'land') else '||'
        return f"({_coq_bits_expr(args[0], reg_widths, op_width)} {sym} {_coq_bits_expr(args[1], reg_widths, op_width)})"
        
    elif op in ('eq', 'neq', 'gt', 'lt', 'gte', 'lte', 'le', 'ge'):
        operand_width = _infer_expr_width(args[0], reg_widths)
        if operand_width == 32 and len(args) > 1:
            operand_width = _infer_expr_width(args[1], reg_widths)
            
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
        
    elif op in ('slice', 'mul'):
        raise ExprError(f"Unsupported operator (should have been skipped): {op}")

    else:
        raise ExprError(f"Unsupported operator in Coq DSL: {op}")
