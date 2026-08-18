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

if [[ -n "${PERF_BEAM_SIZE:-}" ]]; then
    export PERF_BEAM_SIZE
    log_info "PERF_BEAM_SIZE overridden to ${PERF_BEAM_SIZE}"
fi
if [[ -n "${PERF_BRANCHES:-}" ]]; then
    export PERF_BRANCHES
    log_info "PERF_BRANCHES overridden to ${PERF_BRANCHES}"
fi
if [[ -n "${PERF_DEPTH:-}" ]]; then
    export PERF_DEPTH
    log_info "PERF_DEPTH overridden to ${PERF_DEPTH}"
fi
if [[ -n "${PERF_ENABLED:-}" ]]; then
    export PERF_ENABLED
    log_info "PERF_ENABLED overridden to ${PERF_ENABLED}"
fi
if [[ -n "${PERF_DIMENSIONS:-}" ]]; then
    export PERF_DIMENSIONS
    log_info "PERF_DIMENSIONS overridden to ${PERF_DIMENSIONS}"
fi
if [[ -n "${PERF_PRIMARY_DIMENSION:-}" ]]; then
    export PERF_PRIMARY_DIMENSION
    log_info "PERF_PRIMARY_DIMENSION overridden to ${PERF_PRIMARY_DIMENSION}"
fi
if [[ -n "${PERF_TEMPERATURE:-}" ]]; then
    export PERF_TEMPERATURE
    log_info "PERF_TEMPERATURE overridden to ${PERF_TEMPERATURE}"
fi
if [[ -n "${PERF_MAX_WORKERS:-}" ]]; then
    export PERF_MAX_WORKERS
    log_info "PERF_MAX_WORKERS overridden to ${PERF_MAX_WORKERS}"
fi
if [[ -n "${PERF_TIMEOUT_NODE:-}" ]]; then
    export PERF_TIMEOUT_NODE
    log_info "PERF_TIMEOUT_NODE overridden to ${PERF_TIMEOUT_NODE}"
fi
if [[ -n "${PERF_TOURNAMENT_SIZE:-}" ]]; then
    export PERF_TOURNAMENT_SIZE
    log_info "PERF_TOURNAMENT_SIZE overridden to ${PERF_TOURNAMENT_SIZE}"
fi
if [[ -n "${PERF_ALWAYS_VERIFY:-}" ]]; then
    export PERF_ALWAYS_VERIFY
    log_info "PERF_ALWAYS_VERIFY overridden to ${PERF_ALWAYS_VERIFY}"
fi

check_uv() {
    if ! command -v uv &>/dev/null; then
        log_error "uv not found. Please run './install.sh' first."
    fi
}

MARKER_DEF="integration: integration test"

run_unit_tests() {
    log_info "Running unit tests..."
    PYTHONPATH=src uv run pytest tests/unit -v \
        -o "markers=${MARKER_DEF}" \
        -W ignore::pytest.PytestUnknownMarkWarning
}

run_integration_tests() {
    log_info "Running integration tests..."
    PYTHONPATH=src uv run pytest tests/integration -v \
        -o "markers=${MARKER_DEF}" \
        -W ignore::pytest.PytestUnknownMarkWarning
}

run_all_tests() {
    log_info "Running all tests..."
    PYTHONPATH=src uv run pytest tests/unit tests/integration -v \
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
    find . -type f -name 'test.v' -delete || true
    find . -type f -name 'test.ml' -delete || true
    find . -type f -name 'test.mli' -delete || true

    rm -rf build/ || true

    log_success "Cleaned generated files."
}

show_help() {
    cat <<EOF
${BOLD}InterScope run.sh wrapper${RESET} – Version 0.2 (with batch & structured output)

${BOLD}Global options:${RESET}
  --batch [DIR]                Process all .specir files in DIR (default: current directory)
  --output-format json|text    Output format for results (default: text)
  --report-file PATH           Save aggregated report to PATH (JSON/CSV)
  --config FILE                Load additional YAML configuration overrides
  --debug                      Enable debug logging

${BOLD}Commands:${RESET}
  --test unit|integration|all   Run tests
  --validate-config             Validate config.yaml (checks for conflicts)
  --compile <file> ...          Compile a .specir file
  --verify <file> ...           Verify proof obligations
  --sim <file> ...              Simulate a design (compile + Verilator)
  --lift <vcd> ...              Lift VCD trace to abstract trace
  --check <trace> ...           Check properties against trace
  --query ...                   Query evidence registry
  --vcd-to-trace <vcd> ...      Convert VCD file to trace dialect (debug)
  --extract-mapping <vfile> ... Extract SpecIR mapping from Verilog annotations
  --clean                       Remove generated files
  --help                        Show this help
  --version                     Show version

${BOLD}Examples:${RESET}
  # Single file with JSON output
  ./run.sh --output-format json --compile examples/fifo/fifo.specir

  # Batch compile all designs in a directory, save report
  ./run.sh --batch benchmarks/level1/ --compile --output-format json --report-file compile_results.json

  # Batch verify with PERF and external config
  ./run.sh --config custom_config.yaml --batch my_designs/ --verify --perf

${BOLD}Environment Variables (PERF overrides):${RESET}
  PERF_ENABLED=true|false       Override PERF master switch
  PERF_BEAM_SIZE=5              Override beam size
  PERF_BRANCHES=6               Override branches per node
  PERF_DEPTH=4                  Override depth limit
  PERF_DIMENSIONS="a,b,c"       Override dimensions (comma-separated)
  PERF_PRIMARY_DIMENSION="a"    Override primary dimension
  PERF_TEMPERATURE=0.5          Override generation temperature
  PERF_MAX_WORKERS=8            Override max workers
  PERF_TIMEOUT_NODE=600         Override timeout per node (seconds)
  PERF_TOURNAMENT_SIZE=3        Override tournament size
  PERF_ALWAYS_VERIFY=false      Override always verify children
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
    --validate-config)
        check_uv
        shift
        exec env PYTHONPATH=src uv run python -m specir.cli.validate_config "$@"
        ;;
    --version)
        echo "InterScope version 0.2 (alpha)"
        ;;
    --help)
        show_help
        ;;
    --clean)
        run_clean
        ;;
    --compile|--verify|--sim|--lift|--check|--query)
        check_uv
        subcmd="${1#--}"
        shift
        exec env PYTHONPATH=src uv run python -m specir.cli."$subcmd" "$@"
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
        exec env PYTHONPATH=src uv run python -m specir.cli.main "$@"
        ;;
esac
