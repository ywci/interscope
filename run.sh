#!/bin/bash
set -euo pipefail

if [[ -t 1 ]]; then
    readonly BOLD=$(tput bold 2>/dev/null || echo)
    readonly RED=$(tput setaf 1 2>/dev/null || echo)
    readonly GREEN=$(tput setaf 2 2>/dev/null || echo)
    readonly YELLOW=$(tput setaf 3 2>/dev/null || echo)
    readonly BLUE=$(tput setaf 4 2>/dev/null || echo)
    readonly RESET=$(tput sgr0 2>/dev/null || echo)
else
    readonly BOLD="" RED="" GREEN="" YELLOW="" BLUE="" RESET=""
fi

log_info()    { echo "${BLUE}${BOLD}[INFO]${RESET} $*"; }
log_success() { echo "${GREEN}${BOLD}[SUCCESS]${RESET} $*"; }
log_warning() { echo "${YELLOW}${BOLD}[WARNING]${RESET} $*" >&2; }
log_error()   { echo "${RED}${BOLD}[ERROR]${RESET} $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -d "$SCRIPT_DIR/.venv/bin" ]]; then
    export PATH="$SCRIPT_DIR/.venv/bin:$PATH"
fi
for var in \
    PERF_BEAM_SIZE PERF_BRANCHES PERF_DEPTH PERF_ENABLED \
    PERF_DIMENSIONS PERF_PRIMARY_DIMENSION PERF_TEMPERATURE \
    PERF_MAX_WORKERS PERF_TIMEOUT_NODE PERF_TOURNAMENT_SIZE \
    PERF_ALWAYS_VERIFY PERF_ON_DEMAND_BACKTRACK \
    PERF_REFLECTION_QUALITY_WINDOW PERF_MIN_REFLECTION_QUALITY \
    PERF_MAX_REFLECTION_RETRIES
do
    if [[ -n "${!var:-}" ]]; then
        export "$var"
        log_info "$var overridden to ${!var}"
    fi
done

check_uv() {
    if ! command -v uv &>/dev/null; then
        log_error "uv not found. Please run './install.sh' first."
    fi
}

MARKER_DEF="integration: integration test"

run_unit_tests() {
    log_info "Running unit tests..."
    PYTHONPATH=src .venv/bin/python -m pytest tests/unit -v \
        -o "markers=${MARKER_DEF}" \
        -W ignore::pytest.PytestUnknownMarkWarning
}

run_integration_tests() {
    log_info "Running integration tests..."
    PYTHONPATH=src .venv/bin/python -m pytest tests/integration -v \
        -o "markers=${MARKER_DEF}" \
        -W ignore::pytest.PytestUnknownMarkWarning
}

run_all_tests() {
    log_info "Running all tests..."
    PYTHONPATH=src .venv/bin/python -m pytest tests/unit tests/integration -v \
        -o "markers=${MARKER_DEF}" \
        -W ignore::pytest.PytestUnknownMarkWarning
}

run_clean() {
    log_info "Cleaning generated files..."

    find . -type f -name '*.pyc' -delete || true
    find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name '.pytest_cache' -exec rm -rf {} + 2>/dev/null || true

    find . -type f -name '_CoqProject' -delete || true
    find . -type f -name '*.vo' -delete || true
    find . -type f -name '*.vos' -delete || true
    find . -type f -name '*.vok' -delete || true
    find . -type f -name '*.glob' -delete || true
    find . -type f -name '*.aux' -delete || true
    find . -type f -name '.lia.cache' -delete || true
    find . -type f -name '.nia.cache' -delete || true
    find . -type f -name 'test.v' -delete || true
    find . -type f -name 'test.ml' -delete || true
    find . -type f -name 'test.mli' -delete || true

    rm -rf build/ || true

    log_success "Cleaned generated files."
}

run_clean_all() {
    local assume_yes=0
    local include_tools=1
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --yes|-y)   assume_yes=1; shift ;;
            --no-tools) include_tools=0; shift ;;
            *) log_error "Unknown option for --clean-all: $1" ;;
        esac
    done

    local targets=(".venv" ".uv-cache" "build")
    if [[ $include_tools -eq 1 ]]; then
        targets+=(
            "tools/rocq-mcp"
            "tools/acl2-mcp"
            "tools/koika"
        )
    fi

    local existing=()
    local t
    for t in "${targets[@]}"; do
        [[ -e "$SCRIPT_DIR/$t" ]] && existing+=("$t")
    done

    echo ""
    log_warning "--clean-all will remove the following paths under the repo:"
    if [[ ${#existing[@]} -eq 0 ]]; then
        echo "    (nothing to remove — repo is already clean)"
    else
        for t in "${existing[@]}"; do
            echo "    $SCRIPT_DIR/$t"
        done
    fi
    log_warning "System-installed tools are NOT removed:"
    echo "    opam switches (e.g. coq-8.18-ocaml-4.14, default),"
    echo "    ACL2, SymbiYosys, Coq, uv, and any globally installed Python packages."
    echo "    The global uv cache (\$XDG_CACHE_HOME/uv or ~/.cache/uv) is also left"
    echo "    untouched — run 'uv cache clean' if you want to reclaim that space."
    echo ""

    if [[ ${#existing[@]} -eq 0 ]]; then
        log_info "Nothing to do."
        return 0
    fi

    if [[ $assume_yes -eq 0 && -t 0 ]]; then
        read -r -p "Proceed? [y/N] " reply
        case "$reply" in
            [yY]|[yY][eE][sS]) ;;
            *) log_info "Aborted."; return 0 ;;
        esac
    fi

    run_clean

    for t in "${targets[@]}"; do
        if [[ -e "$SCRIPT_DIR/$t" ]]; then
            rm -rf "$SCRIPT_DIR/$t"
            log_info "Removed $t"
        fi
    done

    log_success "Deep clean complete. Run './install.sh' to reinstall."
}

run_verify_examples() {
    local backend="koika"
    local pass_args=()
    local quiet=1
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --backend|-b)
                backend="${2:-koika}"
                shift 2
                ;;
            --debug)
                quiet=0
                pass_args+=("$1")
                shift
                ;;
            *)
                pass_args+=("$1")
                shift
                ;;
        esac
    done

    local examples=()
    local f
    for f in examples/*/*.isir; do
        [[ -f "$f" ]] && examples+=("$f")
    done
    if [[ ${#examples[@]} -eq 0 ]]; then
        log_error "No .isir files found under examples/"
    fi

    local total=${#examples[@]}
    local passed=0
    local failed=0
    local failed_names=()
    local name
    local ok=0

    echo ""
    log_info "Verifying ${total} example(s) with backend '${backend}'..."
    echo ""

    for f in "${examples[@]}"; do
        name="$(basename "$f" .isir)"
        if [[ $quiet -eq 1 ]]; then
            if env PYTHONPATH=src uv run python -m isir.cli.verify \
                    "$f" --backend "$backend" "${pass_args[@]}" >/dev/null 2>&1; then
                ok=1
            else
                ok=0
            fi
        else
            echo ""
            log_info "--- ${name} ---"
            if env PYTHONPATH=src uv run python -m isir.cli.verify \
                    "$f" --backend "$backend" "${pass_args[@]}"; then
                ok=1
            else
                ok=0
            fi
        fi

        if [[ $ok -eq 1 ]]; then
            passed=$((passed + 1))
            echo "  ${GREEN}${BOLD}[PASS]${RESET} ${name}"
        else
            failed=$((failed + 1))
            failed_names+=("${name}")
            echo "  ${RED}${BOLD}[FAIL]${RESET} ${name}"
        fi
    done

    echo ""
    echo "${BOLD}===== Examples: ${passed} passed, ${failed} failed =====${RESET}"
    if [[ $failed -gt 0 ]]; then
        echo "  Failed: ${failed_names[*]}"
        return 1
    fi
    log_success "All ${total} examples passed."
}

show_help() {
    cat <<EOF
${BOLD}InterScope run.sh wrapper${RESET} – Version 0.0.3 (ISIR, batch, structured output)

${BOLD}Global options:${RESET}
  --batch [DIR]                Process all .isir files in DIR (default: current directory)
  --output-format json|text    Output format for results (default: text)
  --report-file PATH           Save aggregated report to PATH (JSON/CSV)
  --config FILE                Load additional YAML configuration overrides
  --debug                      Enable debug logging

${BOLD}Commands:${RESET}
  --test unit|integration|all   Run tests
  --verify-examples [flags]     Verify all examples/ (backend: koika by default)
  --validate-config             Validate config.yaml (checks for conflicts)
  --compile <file> ...          Compile an .isir file
  --verify <file> ...           Verify proof obligations
  --sim <file> ...              Simulate a design (compile + Verilator)
  --lift <vcd> ...              Lift VCD trace to abstract trace
  --check <trace> ...           Check properties against trace
                                (use --no-validate to skip trace schema validation)
  --query ...                   Query evidence registry
  --vcd-to-trace <vcd> ...      Convert VCD file to trace dialect (debug)
  --extract-mapping <vfile> ... Extract ISIR mapping from Verilog annotations
  --clean                       Remove generated files (build artifacts only)
  --clean-all [--yes] [--no-tools]
                                Also remove .venv, .uv-cache, and tools/* clones.
                                  --yes       Skip the confirmation prompt.
                                  --no-tools  Keep tools/* clones; remove only
                                              build artifacts, .venv, and .uv-cache.
                                System-installed tools and the global uv cache
                                (~/.cache/uv) are NEVER removed.
  --help                        Show this help
  --version                     Show version

${BOLD}Examples:${RESET}
  # Single file with JSON output
  ./run.sh --output-format json --compile examples/fifo/fifo.isir

  # Batch compile all designs in a directory, save report
  ./run.sh --batch my_designs/ --compile --output-format json --report-file compile_results.json

  # Batch verify with PERF and external config
  ./run.sh --config custom_config.yaml --batch my_designs/ --verify --perf

  # Check properties against a lifted trace (schema validation on by default)
  ./run.sh --check build/traces/lifted.yaml --spec examples/fifo/fifo.isir

  # Fast reset: drop build artifacts only
  ./run.sh --clean

  # Full reset: drop build artifacts, .venv, .uv-cache, and cloned tool repos (interactive)
  ./run.sh --clean-all

  # Non-interactive full reset (CI), keeping cloned tool repos
  ./run.sh --clean-all --yes --no-tools

${BOLD}Environment Variables (PERF overrides):${RESET}
  PERF_ENABLED=true|false              Override PERF master switch
  PERF_BEAM_SIZE=5                     Override beam size
  PERF_BRANCHES=6                      Override branches per node
  PERF_DEPTH=4                         Override depth limit
  PERF_DIMENSIONS="a,b,c"              Override dimensions (comma-separated)
  PERF_PRIMARY_DIMENSION="a"           Override primary dimension
  PERF_TEMPERATURE=0.5                 Override generation temperature
  PERF_MAX_WORKERS=8                   Override max workers
  PERF_TIMEOUT_NODE=600                Override timeout per node (seconds)
  PERF_TOURNAMENT_SIZE=3               Override tournament size
  PERF_ALWAYS_VERIFY=false             Override always verify children
  PERF_ON_DEMAND_BACKTRACK=true|false  Enable on-demand backtracking
  PERF_REFLECTION_QUALITY_WINDOW=3     Depths to wait before evaluating reflection
  PERF_MIN_REFLECTION_QUALITY=0.15     Minimum reflection quality to accept
  PERF_MAX_REFLECTION_RETRIES=2        Retry limit for alternative backtrack depths
EOF
}

case "${1:-}" in
    --test)
        check_uv
        if [[ $# -lt 2 ]]; then
            log_error "--test requires an argument (unit, integration, or all)"
        fi
        case "$2" in
            unit)        run_unit_tests ;;
            integration) run_integration_tests ;;
            all)         run_all_tests ;;
            *)
                log_error "Unknown test type '$2'. Use 'unit', 'integration', or 'all'."
                ;;
        esac
        ;;
    --verify-examples)
        check_uv
        shift
        run_verify_examples "$@"
        ;;
    --validate-config)
        check_uv
        shift
        exec env PYTHONPATH=src uv run python -m isir.cli.validate_config "$@"
        ;;
    --version)
        echo "InterScope version 0.0.3"
        ;;
    --help)
        show_help
        ;;
    --clean)
        run_clean
        ;;
    --clean-all)
        shift
        run_clean_all "$@"
        ;;
    --compile|--verify|--sim|--lift|--check|--query)
        check_uv
        subcmd="${1#--}"
        shift
        exec env PYTHONPATH=src uv run python -m isir.cli."$subcmd" "$@"
        ;;
    --vcd-to-trace)
        check_uv
        shift
        exec env PYTHONPATH=src uv run python scripts/vcd_to_trace.py "$@"
        ;;
    --extract-mapping)
        check_uv
        shift
        exec env PYTHONPATH=src uv run python scripts/extract_mapping.py "$@"
        ;;
    *)
        check_uv
        exec env PYTHONPATH=src uv run python -m isir.cli.main "$@"
        ;;
esac
