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

check_uv() {
    if ! command -v uv &>/dev/null; then
        log_error "uv not found. Please run './install.sh' first."
    fi
}

MARKER_DEF="integration: integration test"

run_unit_tests() {
    log_info "Running unit tests..."
    PYTHONPATH=src uv run pytest tests/unit -v -o "markers=${MARKER_DEF}"
}

run_integration_tests() {
    log_info "Running integration tests..."
    PYTHONPATH=src uv run pytest tests/integration -v -o "markers=${MARKER_DEF}"
}

run_all_tests() {
    log_info "Running all tests..."
    PYTHONPATH=src uv run pytest tests/unit tests/integration -v -o "markers=${MARKER_DEF}"
}

run_clean() {
    log_info "Cleaning generated files..."

    find . -type f -name '*.pyc' -delete
    find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name '.pytest_cache' -exec rm -rf {} + 2>/dev/null || true

    find . -type f -name '_CoqProject' -delete
    find . -type f -name '*.vo' -delete
    find . -type f -name '*.vos' -delete
    find . -type f -name '*.vok' -delete
    find . -type f -name '*.glob' -delete
    find . -type f -name '*.aux' -delete
    find . -type f -name 'test.v' -delete
    find . -type f -name 'test.ml' -delete
    find . -type f -name 'test.mli' -delete

    rm -rf build/

    log_success "Cleaned generated files."
}

show_help() {
    cat <<EOF
${BOLD}InterScope run.sh wrapper${RESET} – Version 0.1 (alpha)

${BOLD}Commands:${RESET}
  --test unit|integration|all   Run tests
  --compile <file> ...          Compile a .specir file
  --verify <file> ...           Verify proof obligations
  --sim <file> ...              Simulate a design (compile + Verilator)
  --lift <vcd> ...              Lift VCD trace to abstract trace
  --check <trace> ...           Check properties against trace
  --query ...                   Query evidence registry
  --vcd-to-trace <vcd> ...      Convert VCD file to trace dialect (debug)
  --extract-mapping <vfile> ... Extract SpecIR mapping from Verilog annotations
  --clean                       Remove generated files (*.pyc, __pycache__, .pytest_cache, _CoqProject, build/, etc.)
  --help                        Show this help
  --version                     Show version

${BOLD}Examples:${RESET}
  ./run.sh --compile examples/fifo/fifo.specir
  ./run.sh --verify examples/fifo/fifo.specir --backend koika
  ./run.sh --sim examples/fifo/fifo.specir --cycles 100
  ./run.sh --lift build/traces/fifo.vcd --mapping build/rtl/mapping.json
  ./run.sh --check build/traces/lifted.yaml --spec examples/fifo/fifo.specir
  ./run.sh --vcd-to-trace build/traces/fifo.vcd --mapping build/rtl/mapping.json
  ./run.sh --extract-mapping build/rtl/fifo.v --output mapping.json
  ./run.sh --clean
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
    --version)
        echo "InterScope version 0.1 (alpha)"
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
        log_error "Unknown option '$1'. Use --help for usage."
        ;;
esac
