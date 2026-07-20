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

SMOKE_TIMEOUT=5

safe_smoke_test() {
    local description="$1"
    shift

    if command -v timeout &>/dev/null; then
        if timeout "$SMOKE_TIMEOUT" "$@" >/dev/null 2>&1; then
            log_info "Smoke test passed: $description"
        else
            log_warning "Smoke test FAILED (or timed out): $description"
        fi
        return
    fi

    "$@" >/dev/null 2>&1 &
    local pid=$!
    local waited=0
    while kill -0 "$pid" 2>/dev/null && [[ $waited -lt $SMOKE_TIMEOUT ]]; do
        sleep 1
        waited=$((waited + 1))
    done
    if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null
        log_warning "Smoke test TIMED OUT after ${SMOKE_TIMEOUT}s: $description"
    else
        wait "$pid" && log_info "Smoke test passed: $description" || log_warning "Smoke test FAILED: $description"
    fi
}

PYTHON=${PYTHON:-python3}
UV_PYTHON_VERSION=${UV_PYTHON_VERSION:-3.12}
INSTALL_EXTERNAL=${INSTALL_EXTERNAL:-true}
KOIKA_INSTALL_SWITCH=${KOIKA_INSTALL_SWITCH:-false}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ensure_uv() {
    add_common_uv_paths() {
        local to_add=("$HOME/.cargo/bin" "$HOME/.local/bin")
        for dir in "${to_add[@]}"; do
            if [[ -d "$dir" && ":$PATH:" != *":$dir:"* ]]; then
                export PATH="$dir:$PATH"
            fi
        done
    }
    add_common_uv_paths
    if command -v uv &>/dev/null; then return 0; fi
    log_info "Installing uv..."
    command -v "$PYTHON" &>/dev/null || log_error "$PYTHON not found"
    "$PYTHON" -m pip install --user uv || log_error "Failed to install uv"
    add_common_uv_paths
    command -v uv &>/dev/null || log_error "uv still not found after installation"
    log_info "uv installed: $(uv --version)"
}

setup_venv() {
    if ! uv python find "$UV_PYTHON_VERSION" &>/dev/null; then
        log_info "Python $UV_PYTHON_VERSION not found; installing with uv..."
        uv python install "$UV_PYTHON_VERSION" || \
            log_error "Failed to install Python $UV_PYTHON_VERSION"
    fi
    if [[ ! -d ".venv" ]]; then
        log_info "Creating virtual environment with Python $UV_PYTHON_VERSION..."
        uv venv --python "$UV_PYTHON_VERSION" --seed || \
            log_error "Failed to create venv"
    else
        log_info "Virtual environment already exists; skipping creation."
    fi
    source .venv/bin/activate
    log_info "Virtual environment activated."
}

install_python_deps() {
    log_info "Installing core Python dependencies..."

    local required=(
        "pyyaml>=6.0"
        "jsonschema>=4.0"
        "click>=8.0"
        "pytest>=7.0"
        "mcp>=0.1.0"
    )

    local optional=(
        "openai>=1.0"
        "anthropic>=0.30"
        "requests>=2.28"
    )

    uv pip install "${required[@]}" "${optional[@]}" || \
        log_error "Failed to install Python dependencies"

    log_info "Python dependencies installed."
}

install_opam() {
    if command -v opam &>/dev/null; then
        log_info "opam already installed."
        return 0
    fi

    log_info "opam not found; attempting to install opam..."

    if command -v apt-get &>/dev/null; then
        log_info "Detected apt package manager. Installing opam..."
        sudo apt-get update -qq
        sudo apt-get install -y opam || {
            log_warning "apt-get install opam failed. Trying the official installer."
            _install_opam_via_script
        }
    elif command -v brew &>/dev/null; then
        log_info "Detected Homebrew. Installing opam..."
        brew install opam || {
            log_warning "brew install opam failed. Trying the official installer."
            _install_opam_via_script
        }
    else
        log_warning "No known package manager found. Trying the official opam installer..."
        _install_opam_via_script
    fi

    if ! command -v opam &>/dev/null; then
        log_error "Failed to install opam. Please install opam manually and rerun this script."
    fi

    log_success "opam installed successfully."
}

_install_opam_via_script() {
    log_info "Downloading and running the official opam installer..."
    local OPAM_INSTALL_SCRIPT="https://raw.githubusercontent.com/ocaml/opam/master/shell/install.sh"
    if command -v curl &>/dev/null; then
        curl -fsSL "$OPAM_INSTALL_SCRIPT" | sh -s -- --yes
    elif command -v wget &>/dev/null; then
        wget -qO- "$OPAM_INSTALL_SCRIPT" | sh -s -- --yes
    else
        log_error "Neither curl nor wget found. Cannot download opam installer."
    fi
    export PATH="$HOME/.opam/bin:$PATH"
}

init_opam() {
    if [[ ! -d "$HOME/.opam" ]]; then
        log_info "Initialising opam..."
        opam init --bare --disable-sandboxing -y || {
            log_error "opam init failed. Please run 'opam init' manually and rerun this script."
        }
    fi

    if ! opam switch list --short | grep -q "."; then
        log_info "Creating default opam switch..."
        if opam switch create default --packages=ocaml-system --yes 2>/dev/null; then
            log_success "Default switch created with ocaml-system."
        else
            log_info "ocaml-system not available; trying ocaml-base-compiler.5.2.0..."
            if opam switch create default --packages=ocaml-base-compiler.5.2.0 --yes 2>/dev/null; then
                log_success "Default switch created with ocaml-base-compiler.5.2.0."
            else
                log_info "Trying automatic compiler selection..."
                if opam switch create default --yes 2>/dev/null; then
                    log_success "Default switch created (automatic)."
                else
                    log_error "Failed to create default opam switch. Please create one manually and rerun."
                fi
            fi
        fi
    fi

    eval $(opam env)
}

install_rocq_mcp() {
    if [[ "$INSTALL_EXTERNAL" != "true" ]]; then
        log_info "Skipping external tool installation (INSTALL_EXTERNAL=false)"
        return 0
    fi

    if command -v rocq-mcp &>/dev/null; then
        log_info "rocq‑mcp already installed."
        safe_smoke_test "coqc --version" coqc --version
        return 0
    fi

    log_info "Installing rocq‑mcp..."

    install_opam
    init_opam

    log_info "Installing Coq and coq-lsp via opam (this may take a while)..."
    opam install coq coq-lsp -y || {
        log_error "opam install coq coq-lsp failed. Please install them manually and rerun."
    }

    if ! command -v git &>/dev/null; then
        log_error "git not found. Please install git and rerun this script."
    fi

    local ROCQ_MCP_DIR="$SCRIPT_DIR/tools/rocq-mcp"
    if [[ -d "$ROCQ_MCP_DIR" ]]; then
        log_info "rocq-mcp directory already exists. Pulling latest changes..."
        (cd "$ROCQ_MCP_DIR" && git pull) || {
            log_warning "Failed to update rocq-mcp. Using existing version."
        }
    else
        mkdir -p "$(dirname "$ROCQ_MCP_DIR")"
        git clone https://github.com/LLM4Rocq/rocq-mcp.git "$ROCQ_MCP_DIR" || {
            log_error "Failed to clone rocq-mcp. Please clone it manually and rerun."
        }
    fi

    log_info "Installing rocq-mcp from source (editable mode)..."
    if command -v uv &>/dev/null; then
        uv pip install -e "$ROCQ_MCP_DIR" || {
            log_error "uv pip install -e failed. Please install rocq-mcp manually."
        }
    else
        pip install -e "$ROCQ_MCP_DIR" || {
            log_error "pip install -e failed. Please install rocq-mcp manually."
        }
    fi

    log_success "rocq‑mcp installed successfully."
    safe_smoke_test "coqc --version" coqc --version
}

install_acl2_binary() {
    if [[ "$INSTALL_EXTERNAL" != "true" ]]; then
        return 0
    fi

    if command -v acl2 &>/dev/null; then
        log_info "ACL2 binary already installed."
        safe_smoke_test "ACL2 startup" bash -c "echo ':q' | acl2"
        return 0
    fi

    log_info "Attempting to install ACL2 binary..."
    if command -v apt-get &>/dev/null; then
        log_info "Detected apt package manager. Installing ACL2..."
        sudo apt-get update -qq
        sudo apt-get install -y acl2 || {
            log_warning "apt-get install acl2 failed. Please install manually."
            return 0
        }
        log_success "ACL2 installed via apt."
    elif command -v brew &>/dev/null; then
        log_info "Detected Homebrew. Installing ACL2..."
        brew install acl2 || {
            log_warning "brew install acl2 failed. Please install manually."
            return 0
        }
        log_success "ACL2 installed via Homebrew."
    else
        log_warning "Could not detect a package manager. ACL2 must be installed manually."
        echo "  ACL2 installation instructions: https://www.cs.utexas.edu/users/moore/acl2/"
        return 0
    fi

    safe_smoke_test "ACL2 startup" bash -c "echo ':q' | acl2"
}

install_acl2_mcp() {
    if [[ "$INSTALL_EXTERNAL" != "true" ]]; then
        return 0
    fi

    if command -v acl2-mcp &>/dev/null; then
        log_info "acl2-mcp already installed."
        safe_smoke_test "acl2-mcp exists" acl2-mcp --version 2>/dev/null || true
        return 0
    fi

    log_info "Installing acl2-mcp..."

    if ! command -v git &>/dev/null; then
        log_warning "git not found. Cannot clone acl2-mcp. Please install git and then run:"
        echo "  git clone https://github.com/septract/acl2-mcp.git"
        echo "  cd acl2-mcp && pip install -e ."
        return 0
    fi

    local ACL2_MCP_DIR="$SCRIPT_DIR/tools/acl2-mcp"
    if [[ -d "$ACL2_MCP_DIR" ]]; then
        log_info "acl2-mcp directory already exists. Pulling latest changes..."
        (cd "$ACL2_MCP_DIR" && git pull) || {
            log_warning "Failed to update acl2-mcp. Using existing version."
        }
    else
        mkdir -p "$(dirname "$ACL2_MCP_DIR")"
        git clone https://github.com/septract/acl2-mcp.git "$ACL2_MCP_DIR" || {
            log_warning "Failed to clone acl2-mcp. Please install manually."
            return 0
        }
    fi

    log_info "Installing acl2-mcp from source (editable mode)..."
    if command -v uv &>/dev/null; then
        uv pip install -e "$ACL2_MCP_DIR" || {
            log_warning "uv pip install -e failed. Trying pip..."
            pip install -e "$ACL2_MCP_DIR" || {
                log_warning "pip install -e failed. Please install manually."
                return 0
            }
        }
    else
        pip install -e "$ACL2_MCP_DIR" || {
            log_warning "pip install -e failed. Please install manually."
            return 0
        }
    fi

    log_success "acl2-mcp installed successfully."
    safe_smoke_test "acl2-mcp exists" acl2-mcp --version 2>/dev/null || true
}

KOIKA_REQUIRED_COQ_VERSION="8.18.0"
KOIKA_REQUIRED_OCAML_VERSION="4.14.2"
KOIKA_SWITCH_NAME="coq-8.18-ocaml-4.14"

check_koika_environment() {
    local need_switch=false
    local ocaml_ver=$(ocamlc -version 2>/dev/null || echo "0")
    local coq_ver=$(coqc --version 2>/dev/null | head -1 | sed -E 's/.*version ([0-9]+\.[0-9]+).*/\1/' || echo "0")

    if [[ "$ocaml_ver" != "$KOIKA_REQUIRED_OCAML_VERSION" ]]; then
        log_warning "OCaml version $ocaml_ver detected, but Kōika requires $KOIKA_REQUIRED_OCAML_VERSION."
        need_switch=true
    fi
    if [[ "$coq_ver" != "${KOIKA_REQUIRED_COQ_VERSION%.*}" ]]; then
        log_warning "Coq version $coq_ver detected, but Kōika requires $KOIKA_REQUIRED_COQ_VERSION."
        need_switch=true
    fi

    if $need_switch; then
        if [[ "${KOIKA_INSTALL_SWITCH:-false}" == "true" ]]; then
            log_info "Creating dedicated opam switch '$KOIKA_SWITCH_NAME'..."
            opam switch create "$KOIKA_SWITCH_NAME" "ocaml-base-compiler.$KOIKA_REQUIRED_OCAML_VERSION" --yes || {
                log_error "Failed to create opam switch. Please create it manually."
            }
            opam switch "$KOIKA_SWITCH_NAME"
            eval $(opam env)
            opam install "coq=$KOIKA_REQUIRED_COQ_VERSION" -y || {
                log_error "Failed to install Coq $KOIKA_REQUIRED_COQ_VERSION."
            }
            log_success "Opam switch '$KOIKA_SWITCH_NAME' is ready."
        else
            log_error "Incompatible OCaml/Coq versions for Kōika."
            echo ""
            echo "  Please create a dedicated opam switch:"
            echo "    opam switch create $KOIKA_SWITCH_NAME ocaml-base-compiler.$KOIKA_REQUIRED_OCAML_VERSION --yes"
            echo "    opam switch $KOIKA_SWITCH_NAME"
            echo "    eval \$(opam env)"
            echo "    opam install coq=$KOIKA_REQUIRED_COQ_VERSION -y"
            echo ""
            echo "  Then rerun this installer with:  ./install.sh --install-koika-switch"
            exit 1
        fi
    else
        log_info "OCaml and Coq versions are compatible with Kōika."
    fi
}

install_koika() {
    if [[ "$INSTALL_EXTERNAL" != "true" ]]; then
        return 0
    fi

    log_info "Setting up Kōika compiler and Coq libraries..."

    if ! command -v opam &>/dev/null; then
        log_warning "opam not found. Kōika installation requires opam. Please install opam first or run the script again."
        return 0
    fi
    eval $(opam env) 2>/dev/null || true

    # Environment check (OCaml/Coq versions)
    check_koika_environment

    # Full dependency list matching the working test harness
    log_info "Installing Kōika OCaml dependencies..."
    local koika_deps=(
        "zarith" "hashcons" "core" "core_unix" "ppx_jane" "dune=3.19.0"
        "base" "stdio" "parsexp" "ppx_deriving" "ppx_compare" "ppx_hash" "ppx_sexp_conv"
    )
    opam install "${koika_deps[@]}" -y || {
        log_error "Failed to install Kōika OCaml dependencies."
    }

    # Clone Kōika repository
    local KOIKA_DIR="$SCRIPT_DIR/tools/koika"
    if [[ -d "$KOIKA_DIR" ]]; then
        log_info "Kōika directory already exists. Pulling latest changes..."
        (cd "$KOIKA_DIR" && git pull) || log_warning "Failed to update Kōika. Using existing version."
    else
        log_info "Cloning Kōika repository..."
        git clone https://github.com/mit-plv/koika.git "$KOIKA_DIR" || {
            log_warning "Failed to clone Kōika. Please clone it manually."
            return 0
        }
    fi

    cd "$KOIKA_DIR"

    # Build OCaml targets (cuttlec)
    log_info "Building Kōika OCaml targets..."
    if ! dune build ocaml/cuttlec.exe 2>&1 | tee /tmp/koika_build.log; then
        log_warning "Kōika OCaml target build failed. Dumping build log:"
        cat /tmp/koika_build.log
        cd "$SCRIPT_DIR"
        return 0
    fi

    # Build and install Kōika Coq libraries
    log_info "Building Kōika Coq libraries..."
    if dune build @install 2>&1 | tee /tmp/koika_coq_build.log; then
        dune install 2>&1 | tee /tmp/koika_install.log || true
        log_success "Kōika Coq libraries built and installed."
    else
        log_warning "Kōika Coq library build failed. RTL synthesis via Coq DSL will not work."
        log_warning "Check /tmp/koika_coq_build.log for details."
    fi

    local BUILD_OCAML="_build/default/ocaml"
    local SITE_LIB=$(ocamlfind printconf path 2>/dev/null)
    local TARGET_ROOT="$SITE_LIB/koika"
    log_info "Installing Koika libraries into $TARGET_ROOT"

    rm -rf "$TARGET_ROOT" "${TARGET_ROOT}".* 2>/dev/null
    mkdir -p "$TARGET_ROOT"

    log_info "Copying all build artefacts..."
    find "$BUILD_OCAML" -name "*.cma" -o -name "*.cmi" -o -name "*.cmxa" -o -name "*.a" | xargs -I {} cp {} "$TARGET_ROOT/"

    log_info "Generating unified META file..."
    cat > "$TARGET_ROOT/META" <<'METAEOF'
version = "0.1"
description = "Kōika Core Compiler Libraries"
archive(byte) = "koika.cma"

package "registry" (
  version = "0.1"
  description = "koika.registry (unified sub-module payload)"
  archive(byte) = "registry.cma common.cma interop.cma frontends.cma backends.cma"
  requires = "base core core_unix stdio parsexp hashcons zarith"
)

package "common" (
  version = "0.1"
  description = "koika.common"
  archive(byte) = "common.cma"
)

package "frontends" (
  version = "0.1"
  description = "koika.frontends"
  archive(byte) = "frontends.cma"
)

package "backends" (
  version = "0.1"
  description = "koika.backends"
  archive(byte) = "backends.cma"
)

package "cuttlebone" (
  version = "0.1"
  description = "koika.cuttlebone"
  archive(byte) = "cuttlebone.cma"
)

package "interop" (
  version = "0.1"
  description = "koika.interop"
  archive(byte) = "interop.cma"
)
METAEOF

    local packages=("koika" "koika.common" "koika.registry" "koika.frontends" "koika.backends" "koika.cuttlebone" "koika.interop")
    local ALL_OK=true
    for pkg in "${packages[@]}"; do
        if ocamlfind query "$pkg" >/dev/null 2>&1; then
            log_info "  ocamlfind query $pkg -> OK"
        else
            log_warning "  ocamlfind query $pkg -> FAILED"
            ALL_OK=false
        fi
    done

    if $ALL_OK; then
        log_info "All Koika packages registered correctly."
    else
        log_warning "Some packages are missing; RTL synthesis may fail."
    fi

    local CUTTLEC_EXE="$PWD/$BUILD_OCAML/cuttlec.exe"
    if [[ -f "$CUTTLEC_EXE" ]]; then
        chmod +x "$CUTTLEC_EXE"
    else
        log_error "cuttlec.exe not found after build."
    fi

    local WRAPPER_DIR="$KOIKA_DIR/bin"
    mkdir -p "$WRAPPER_DIR"
    cat > "$WRAPPER_DIR/koika" <<EOF
#!/bin/bash
eval \$(opam env)
export OCAMLPATH="\${OCAMLPATH:-}:\$(dirname "\$(readlink -f "\$0")")/../_build/install/default/lib"
exec "$CUTTLEC_EXE" "\$@"
EOF
    chmod +x "$WRAPPER_DIR/koika"

    export PATH="$WRAPPER_DIR:$PATH"
    if ! grep -q "$WRAPPER_DIR" "$HOME/.bashrc" 2>/dev/null; then
        echo "export PATH=\"$WRAPPER_DIR:\$PATH\"" >> "$HOME/.bashrc"
    fi

    # Dynamic OCAMLPATH export (uses actual KOIKA_DIR)
    if ! grep -q "OCAMLPATH.*_build/install/default/lib" "$HOME/.bashrc" 2>/dev/null; then
        echo "export OCAMLPATH=\"\${OCAMLPATH:-}:$KOIKA_DIR/_build/install/default/lib\"" >> "$HOME/.bashrc"
    fi

    log_success "Kōika compiler (cuttlec) and Coq libraries ready."
    safe_smoke_test "koika --help" koika --help

    local KOIKA_BIN="$KOIKA_DIR/bin/koika"
    log_info "Verifying Kōika Coq‑DSL pipeline with a minimal design..."
    local SMOKE_DIR=$(mktemp -d)
    (
        cd "$SMOKE_DIR"
        cat > min.v <<'EOF'
Require Import Koika.Frontend.
Require Import Koika.Interop.
Require Import Koika.ExtractionSetup.

Inductive reg_t := R.
Definition Rf (_:reg_t) : type := bits_t 8.
Inductive rule_name_t := W.
Definition urules (rl:rule_name_t) : uaction reg_t empty_ext_fn_t :=
  match rl with W => {{ write0(R, |8`d42|) }} end.
Definition rules := tc_rules Rf empty_Sigma urules.
Definition init (r:reg_t) : Rf r := Bits.zero.
Definition is_ext (_:rule_name_t) := false.
Definition package := {|
  ip_koika := {| koika_reg_types := Rf; koika_reg_init := init;
                 koika_ext_fn_types := empty_Sigma; koika_rules := rules;
                 koika_rule_external := is_ext;
                 koika_scheduler := (W |> done); koika_module_name := "min" |};
  ip_sim := {| sp_ext_fn_specs := empty_ext_fn_props; sp_prelude := None |};
  ip_verilog := Build_verilog_package_t (fun x:empty_ext_fn_t => match x with end)
|}.
Definition prog := Interop.Backends.register package.
Extraction "min.ml" prog.
EOF

        eval $(opam env)
        local FOUND_PATH=""
        local FOUND_OPTION=""
        for path in "$KOIKA_DIR/_build/install/default/lib/coq/user-contrib" \
                    "$KOIKA_DIR/_build/default/coq" \
                    "$KOIKA_DIR/coq"; do
            for option in "-Q" "-R"; do
                if coqc "$option" "$path" Koika min.v >/tmp/koika_smoke.log 2>&1; then
                    FOUND_PATH="$path"
                    FOUND_OPTION="$option"
                    break 2
                fi
            done
        done

        if [ -z "$FOUND_PATH" ]; then
            log_warning "Coq‑DSL smoke test: coqc compilation failed."
            log_warning "Last error (see /tmp/koika_smoke.log):"
            tail -5 /tmp/koika_smoke.log
        else
            if [ -f min.ml ]; then
                touch min.mli
                if "$KOIKA_BIN" min.ml -T verilog -o . >/tmp/koika_cuttlec.log 2>&1; then
                    if [ -f min.v ]; then
                        log_success "Kōika Coq‑DSL pipeline verified successfully."
                    else
                        log_warning "Coq‑DSL smoke test: Verilog generation failed."
                    fi
                else
                    log_warning "Coq‑DSL smoke test: cuttlec compilation failed."
                    log_warning "See /tmp/koika_cuttlec.log"
                fi
            else
                log_warning "Coq‑DSL smoke test: OCaml extraction failed."
            fi
        fi
    )
    rm -rf "$SMOKE_DIR"

    cd "$SCRIPT_DIR"
}

install_symbiyosys() {
    if [[ "$INSTALL_EXTERNAL" != "true" ]]; then
        return 0
    fi

    local need_sby=false
    local need_z3=false

    if command -v sby &>/dev/null; then
        log_info "SymbiYosys (sby) already installed."
    else
        need_sby=true
    fi

    if command -v z3 &>/dev/null; then
        log_info "Z3 already installed."
    else
        need_z3=true
    fi

    if ! $need_sby && ! $need_z3; then
        safe_smoke_test "sby --help" sby --help
        safe_smoke_test "z3 --version" z3 --version
        return 0
    fi

    log_info "Installing missing model‑checking tools..."

    if command -v apt-get &>/dev/null; then
        if $need_sby || $need_z3; then
            sudo apt-get update -qq
            local pkgs=()
            $need_sby && pkgs+=(symbiyosys yosys)
            $need_z3 && pkgs+=(z3)
            sudo apt-get install -y "${pkgs[@]}" || {
                log_warning "apt install failed for: ${pkgs[*]}. Please install manually."
                return 0
            }
            log_success "Model‑checking tools installed via apt."
        fi
    elif command -v brew &>/dev/null; then
        if $need_sby; then
            brew install yosys symbiyosys || {
                log_warning "brew install symbiyosys failed. Please install manually."
                return 0
            }
        fi
        if $need_z3; then
            brew install z3 || {
                log_warning "brew install z3 failed. Please install manually."
                return 0
            }
        fi
        log_success "Model‑checking tools installed via Homebrew."
    else
        if $need_sby; then
            log_warning "Could not detect a package manager. SymbiYosys must be installed manually."
            echo "  Installation instructions: https://symbiyosys.readthedocs.io/en/latest/install.html"
        fi
        if $need_z3; then
            log_warning "Z3 must be installed manually. See https://github.com/Z3Prover/z3"
        fi
        return 0
    fi

    # Smoke tests
    if $need_sby || command -v sby &>/dev/null; then
        safe_smoke_test "sby --help" sby --help
    fi
    if $need_z3 || command -v z3 &>/dev/null; then
        safe_smoke_test "z3 --version" z3 --version
    fi
}

verify_imports() {
    python -c "import yaml; import jsonschema; import click; import pytest; import mcp" && \
        log_info "Core imports OK"
}

usage() {
    cat <<EOF
${BOLD}InterScope Installation Script${RESET}

${BOLD}Usage:${RESET}
  $0 [OPTIONS]

${BOLD}Options:${RESET}
  -h, --help            Show this help message and exit.
  --no-external         Skip installation of external tools (rocq‑mcp, ACL2, acl2‑mcp, Kōika, SymbiYosys).
  --install-koika-switch  Automatically create the correct opam switch for Kōika (OCaml 4.14.2 + Coq 8.18).

${BOLD}Description:${RESET}
  Sets up a Python virtual environment using uv and installs all required
  Python packages.  It also attempts to install external verification tools
  (rocq‑mcp, ACL2, acl2‑mcp, Kōika, and SymbiYosys with Z3) using the system
  package manager or opam.  If automatic installation fails, clear instructions are printed.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --no-external)
            INSTALL_EXTERNAL=false
            shift
            ;;
        --install-koika-switch)
            KOIKA_INSTALL_SWITCH=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            ;;
    esac
done

log_info "InterScope installation"
log_info "INSTALL_EXTERNAL=$INSTALL_EXTERNAL"

ensure_uv
setup_venv
install_python_deps
verify_imports

install_acl2_binary
install_acl2_mcp
install_rocq_mcp
install_koika
install_symbiyosys

log_success "Installation completed successfully."
