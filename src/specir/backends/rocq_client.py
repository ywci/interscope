# src/specir/backends/rocq_client.py
#
# Low‑level client for the rocq‑mcp MCP server.

import json
import subprocess
import sys
import threading
import queue
import itertools
import shutil
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from specir.utils.logger import get_logger

logger = get_logger(__name__)


class RocqClientError(Exception):
    """Raised when rocq‑mcp communication fails."""

    def __init__(self, message: str, code: Optional[int] = None):
        super().__init__(message)
        self.code = code


class RocqEnvironmentError(RocqClientError):
    """Raised when rocq‑mcp cannot load the Coq environment for a file.

    This usually means compiled ``.vo`` artefacts are missing or the
    server is not using the same load paths as ``coqc``.
    """


class RocqClient:
    """Client for rocq‑mcp MCP server."""

    def __init__(
        self,
        rocq_mcp_path: str = "rocq-mcp",
        timeout: int = 300,
        cwd: Optional[Path] = None,
        server_args: Optional[List[str]] = None,
        load_paths: Optional[List[Tuple[str, str, str]]] = None,
        coqc_path: Optional[str] = None,
        on_notification: Optional[Callable[[str, Dict[str, Any]], None]] = None
    ):
        """
        Args:
            rocq_mcp_path: Path or command to the rocq‑mcp executable.
            timeout: Timeout in seconds for requests.
            cwd: Working directory for the server process.
            server_args: Additional command‑line arguments for the server.
            load_paths: Optional list of ``(path, coq_lib, mode)`` where
                        *mode* is either ``"R"`` (recursive) or ``"Q"``.
                        These are translated into ``-R path coq_lib`` or
                        ``-Q path coq_lib`` and appended to *server_args*.
            coqc_path: Optional path to the `coqc` executable for fallback.
            on_notification: Optional callback for server notifications.
        """
        self.rocq_mcp_path = rocq_mcp_path
        self.timeout = timeout
        self.cwd = cwd.resolve() if cwd is not None else None
        self.coqc_path = coqc_path or shutil.which("coqc") or "coqc"

        self.server_args = list(server_args or [])
        if load_paths:
            for path, coq_lib, mode in load_paths:
                flag = "-R" if mode.upper() == "R" else "-Q"
                self.server_args.extend([flag, str(Path(path).resolve()), coq_lib])

        # If a working directory is supplied and no load paths were
        # explicitly given, automatically register the workspace as
        # logical path `Test`.  This mirrors the `-R` flag used by coqc.
        if self.cwd is not None and not load_paths:
            self.server_args.extend(["-R", str(self.cwd), "Test"])

        self.on_notification = on_notification
        self.process: Optional[subprocess.Popen] = None
        self._id_counter = itertools.count(1)
        self._responses: Dict[int, queue.Queue] = {}
        self._reader_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def _build_command(self) -> List[str]:
        if self.rocq_mcp_path.endswith(".py"):
            cmd = [sys.executable, self.rocq_mcp_path]
        else:
            cmd = [self.rocq_mcp_path]

        resolved_args = list(self.server_args)
        # Resolve workspace in server_args to absolute path.
        new_args = []
        skip_next = False
        for i, arg in enumerate(resolved_args):
            if skip_next:
                skip_next = False
                continue
            if arg == "--workspace" and i + 1 < len(resolved_args):
                workspace_val = resolved_args[i + 1]
                resolved_ws = str(Path(workspace_val).resolve())
                new_args.append(arg)
                new_args.append(resolved_ws)
                skip_next = True
            else:
                new_args.append(arg)

        # Ensure --workspace is present when cwd is set.
        if self.cwd is not None and "--workspace" not in new_args:
            new_args.extend(["--workspace", str(self.cwd)])

        # Ensure -R or -Q is present when cwd is set (and not already).
        if self.cwd is not None and "-R" not in new_args and "-Q" not in new_args:
            new_args.extend(["-R", str(self.cwd), "Test"])

        cmd.extend(new_args)
        return cmd

    def start(self) -> None:
        if self.process is not None:
            return
        try:
            cmd = self._build_command()
            logger.info("Starting rocq‑mcp: %s", " ".join(cmd))
            if self.cwd is not None:
                logger.info(f"Server CWD set to: {self.cwd}")
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=str(self.cwd) if self.cwd else None
            )
            self._reader_thread = threading.Thread(
                target=self._read_responses, daemon=True
            )
            self._reader_thread.start()
            self._stderr_thread = threading.Thread(
                target=self._drain_stderr, daemon=True
            )
            self._stderr_thread.start()
            self._send_request("initialize", {
                "protocolVersion": "0.0.1",
                "capabilities": {},
                "clientInfo": {
                    "name": "specir",
                    "version": "0.0.1"
                }
            })
        except RocqClientError:
            raise
        except Exception as e:
            raise RocqClientError(f"Failed to start rocq‑mcp: {e}")

    def stop(self) -> None:
        if not self.process:
            return
        try:
            self._send_notification("shutdown", {})
        except Exception:
            pass
        try:
            self.process.terminate()
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        for thread in (self._reader_thread, self._stderr_thread):
            if thread and thread.is_alive():
                thread.join(timeout=2)
        self.process = None
        self._reader_thread = None
        self._stderr_thread = None

        with self._lock:
            for req_id, q in self._responses.items():
                q.put({"error": {"code": -32000, "message": "Client stopped"}})
            self._responses.clear()

    def _coqc_fallback(self, file_path: Path, workspace: Optional[Path]) -> bool:
        """Run coqc directly to produce .vo files in the given workspace."""
        workspace = Path(workspace or file_path.parent).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        cmd = [self.coqc_path, "-R", str(workspace), "Test", str(file_path)]
        logger.info("Running coqc fallback: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(workspace),
            )
            if result.returncode == 0:
                logger.info("coqc fallback succeeded.")
                return True
            else:
                logger.error("coqc fallback failed: %s", result.stderr[:500])
                return False
        except Exception as e:
            logger.error("coqc fallback exception: %s", e)
            return False

    def _looks_like_environment_error(self, error_msg: str) -> bool:
        lower = error_msg.lower()
        indicators = [
            "not found in the current environment",
            "the reference",
            "unable to locate",
            "cannot find",
            "no such file",
        ]
        return any(ind in lower for ind in indicators)

    def ensure_compiled(self, file_path: Path, workspace: Optional[Path] = None) -> bool:
        """Ensure the compiled `.vo` file exists in the workspace."""
        file_path = Path(file_path).resolve()
        workspace = Path(workspace or file_path.parent).resolve()
        vo_path = workspace / f"{file_path.stem}.vo"
        glob_path = workspace / f"{file_path.stem}.glob"

        if vo_path.exists() and glob_path.exists():
            logger.debug("Compiled artefacts found: %s, %s", vo_path, glob_path)
            return True

        logger.info(
            "Compiled artefacts for '%s' are missing; running coqc.",
            file_path.name,
        )
        return self._coqc_fallback(file_path, workspace)

    def load_file(self, file_path: Path, workspace: Optional[Path] = None) -> bool:
        """
        Explicitly load a Coq file into the rocq‑mcp environment.

        This method calls `rocq_compile_file` and returns True only if the
        tool reports success.  If the call fails, a coqc fallback is attempted
        and the method returns True if that succeeds (useful for later
        `rocq_start` attempts).
        """
        file_path = file_path.resolve()
        if workspace is not None:
            workspace = workspace.resolve()
        args = {"file": str(file_path), "keep_vo": True}
        if workspace is not None:
            args["workspace"] = str(workspace)
        logger.info(f"Loading file via rocq_compile_file: {args}")
        result = self._call_tool("rocq_compile_file", args)
        error = self._extract_error_from_response(result)
        if not error:
            logger.info("rocq_compile_file succeeded for '%s'.", file_path.name)
            return True

        logger.error(f"rocq_compile_file error: {error}")
        if self._looks_like_environment_error(error):
            logger.info("Attempting coqc fallback before considering load failed.")
            return self._coqc_fallback(file_path, workspace)
        return False

    def probe_environment(
        self,
        file_path: Path,
        theorem_name: str,
        workspace: Optional[Path] = None,
    ) -> bool:
        """
        Return True if rocq‑mcp can successfully start a proof session for
        *file_path* in *workspace*.  This is intended to be called before
        committing to the interactive proof path.

        The method forces a `coqc` compilation first, then attempts a
        session start.  If the attempt fails with an environment error,
        False is returned and the caller should consider disabling
        rocq‑mcp for the current run.
        """
        file_path = Path(file_path).resolve()
        workspace = Path(workspace or file_path.parent).resolve()
        workspace.mkdir(parents=True, exist_ok=True)

        if not self.ensure_compiled(file_path, workspace):
            logger.error("Could not create compiled artefacts; environment probe failed.")
            return False

        try:
            _, _ = self.start_session(file_path, theorem_name, workspace=workspace)
            logger.info("rocq‑mcp environment probe succeeded.")
            return True
        except RocqEnvironmentError as e:
            logger.warning("rocq‑mcp environment probe failed: %s", e)
            return False
        except RocqClientError as e:
            logger.warning("rocq‑mcp environment probe failed (client error): %s", e)
            return False
        except Exception as e:
            logger.warning("rocq‑mcp environment probe failed (unexpected): %s", e)
            return False

    def compile_file(
        self,
        file_path: Path,
        workspace: Optional[Path] = None,
        keep_vo: bool = True,
        retry_with_coqc: bool = True,
    ) -> Dict[str, Any]:
        file_path = file_path.resolve()
        if workspace is not None:
            workspace = workspace.resolve()
        args = {"file": str(file_path), "keep_vo": keep_vo}
        if workspace is not None:
            args["workspace"] = str(workspace)
        logger.info(f"rocq_compile_file args: {args}")
        result = self._call_tool("rocq_compile_file", args)
        error = self._extract_error_from_response(result)
        if error:
            logger.error(f"rocq_compile_file error: {error}")
            if retry_with_coqc and self._looks_like_environment_error(error):
                logger.info("Attempting coqc fallback before retrying rocq_compile_file.")
                if self._coqc_fallback(file_path, workspace):
                    logger.info("coqc fallback succeeded; retrying rocq_compile_file.")
                    result = self._call_tool("rocq_compile_file", args)
                    error = self._extract_error_from_response(result)
                    if error:
                        logger.error(f"Retry rocq_compile_file still failed: {error}")
        return result

    def verify(
        self,
        file_path: Path,
        theorem_name: str,
        workspace: Optional[Path] = None,
        retry_with_coqc: bool = True,
    ) -> Dict[str, Any]:
        file_path = file_path.resolve()
        if workspace is not None:
            workspace = workspace.resolve()
        args = {"file": str(file_path), "theorem": theorem_name}
        if workspace is not None:
            args["workspace"] = str(workspace)
        logger.info(f"rocq_verify args: {args}")
        result = self._call_tool("rocq_verify", args)
        error = self._extract_error_from_response(result)
        if error:
            logger.error(f"rocq_verify error: {error}")
            if retry_with_coqc and self._looks_like_environment_error(error):
                logger.info("Attempting coqc fallback before retrying rocq_verify.")
                if self._coqc_fallback(file_path, workspace):
                    logger.info("coqc fallback succeeded; retrying rocq_verify.")
                    result = self._call_tool("rocq_verify", args)
                    error = self._extract_error_from_response(result)
                    if error:
                        logger.error(f"Retry rocq_verify still failed: {error}")
        return result

    def start_session(
        self,
        file_path: Path,
        theorem_name: str,
        workspace: Optional[Path] = None
    ) -> Tuple[str, List[str]]:
        """
        Start a proof session for *file_path* and *theorem_name*.

        This method first ensures the compiled artefacts exist (running
        ``coqc`` if necessary).  It then calls ``rocq_start`` with only the
        file and theorem – the workspace is already known to the server via
        the command‑line arguments used at startup.  No redundant
        ``rocq_compile_file`` call is performed.
        """
        file_path = Path(file_path).resolve()
        if workspace is not None:
            workspace = Path(workspace).resolve()
            workspace.mkdir(parents=True, exist_ok=True)

        # Ensure the .vo/.glob files are present.  This may invoke coqc.
        if workspace is not None:
            if not self.ensure_compiled(file_path, workspace):
                raise RocqEnvironmentError(
                    "Could not create compiled artefacts for the Coq file."
                )

        params = {"file": str(file_path), "theorem": theorem_name}
        # Include workspace if provided (the server may use it for context,
        # but it is not strictly required for loading).
        if workspace is not None:
            params["workspace"] = str(workspace)

        logger.info(f"rocq_start request params: {params}")
        resp = self._call_tool("rocq_start", params)
        logger.debug(f"rocq_start raw response: {resp}")

        # Extract error, if any.
        error = self._extract_error_from_response(resp)
        if error:
            logger.error(f"rocq_start returned error: {error}")
            if self._looks_like_environment_error(error):
                raise RocqEnvironmentError(
                    f"rocq_start environment error: {error}"
                )
            raise RocqClientError(f"rocq_start error: {error}")

        content = resp.get("content", [])
        structured = resp.get("structuredContent", {})
        if structured:
            data = structured
        elif content and isinstance(content, list) and len(content) > 0:
            text = content[0].get("text", "")
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                raise RocqClientError(f"rocq_start failed: cannot parse response: {text}")
        else:
            data = resp

        if data.get("isError"):
            error_msg = data.get("error", data.get("message", "Unknown error"))
            raise RocqClientError(f"rocq_start error: {error_msg}")

        state_id = data.get("state_id")
        goals = data.get("goals", [])
        if state_id is None:
            raise RocqClientError(f"rocq_start did not return state_id. Response: {data}")

        # Normalise goals to a list of strings.
        def _normalize_goals(goals):
            if goals is None:
                return []
            if isinstance(goals, list):
                return goals
            if isinstance(goals, str):
                import ast
                try:
                    parsed = ast.literal_eval(goals)
                    if isinstance(parsed, list):
                        return parsed
                except Exception:
                    pass
                return [goals]
            return [goals]

        return state_id, _normalize_goals(goals)

    def check(self, state_id: str, command: str) -> Dict[str, Any]:
        return self._call_tool("rocq_check", {
            "from_state": state_id,
            "body": command
        })

    def step_multi(self, state_id: str, tactics: List[str]) -> Dict[str, Any]:
        return self._call_tool("rocq_step_multi", {
            "from_state": state_id,
            "tactics": tactics
        })

    def query(self, state_id: str, query: str, limit: int = 20) -> Dict[str, Any]:
        return self._call_tool("rocq_query", {
            "from_state": state_id,
            "query": query,
            "max_results": limit
        })

    def assumptions(self, state_id: str) -> Dict[str, Any]:
        return self._call_tool("rocq_assumptions", {"from_state": state_id})

    def _extract_error_from_response(self, response: Dict[str, Any]) -> Optional[str]:
        """
        Return a human‑readable error string from a rocq‑mcp response.

        This method searches for common error fields and nested structures.
        For structured error information (line, char, type), use
        `_extract_structured_errors`.
        """
        def _find_error(obj):
            if isinstance(obj, dict):
                for key in ["error", "message", "detail", "err", "reason", "failure", "description"]:
                    if key in obj and obj[key]:
                        if isinstance(obj[key], str):
                            return obj[key]
                        elif isinstance(obj[key], (dict, list)):
                            result = _find_error(obj[key])
                            if result:
                                return result
                if obj.get("isError") is True:
                    return obj.get("error", obj.get("message", "Unknown error (isError=True)"))
                if obj.get("success") is False:
                    return obj.get("error", obj.get("message", "Command failed (success=False)"))
                for value in obj.values():
                    if isinstance(value, (dict, list)):
                        result = _find_error(value)
                        if result:
                            return result
            elif isinstance(obj, list):
                for item in obj:
                    result = _find_error(item)
                    if result:
                        return result
            return None

        if response.get("isError"):
            return response.get("error", response.get("message", "Unknown error"))
        if "error" in response:
            return response["error"]

        if "structuredContent" in response:
            data = response["structuredContent"]
            found = _find_error(data)
            if found:
                return found

        if "content" in response:
            for item in response["content"]:
                if item.get("type") == "text":
                    text = item.get("text", "")
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, dict):
                            found = _find_error(parsed)
                            if found:
                                return found
                    except json.JSONDecodeError:
                        if "error" in text.lower() or "failed" in text.lower():
                            return text[:200]
        return None

    def _extract_structured_errors(self, response: Any) -> List[Dict[str, str]]:
        """
        Parse a rocq‑mcp response into structured error objects.

        Each returned dict contains:
          - "line": str, the line number (or "?")
          - "char": str, the starting character (or "?")
          - "type": str, error category (see `_classify_coq_error`)
          - "message": str, clean error message

        This method is intended for repair modules that need precise
        locations to guide LLM edits.
        """
        error_str = self._extract_error_from_response(response)
        if not error_str:
            return []
        return self.parse_coq_error(error_str)

    @staticmethod
    def parse_coq_error(error_str: str) -> List[Dict[str, str]]:
        """
        Parse a Coq/coqc error string into structured error dicts.

        Handles the standard format:
            File "path", line N, characters A-B:
            Error message

        Multiple errors are returned as a list.
        """
        errors = []
        pattern = re.compile(
            r'File\s+"(.*?)",\s*line\s+(\d+),\s*characters\s+(\d+)-(\d+):\s*\n?(.*?)(?=\nFile\s+"|$)',
            re.DOTALL,
        )
        matches = list(pattern.finditer(error_str))
        if matches:
            for match in matches:
                line = match.group(2)
                char_start = match.group(3)
                message = match.group(5).strip()
                error_type = _classify_coq_error(message)
                errors.append({
                    "line": line,
                    "char": char_start,
                    "type": error_type,
                    "message": message,
                })
            return errors

        # Fallback: no structured format; return one opaque error
        return [{
            "line": "?",
            "char": "?",
            "type": _classify_coq_error(error_str),
            "message": error_str.strip(),
        }]

    def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })

    def _next_id(self) -> int:
        return next(self._id_counter)

    def _send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        req_id = self._next_id()
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._responses[req_id] = q

        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params
        }
        self._write(json.dumps(request))

        try:
            response = q.get(timeout=self.timeout)
        except queue.Empty:
            with self._lock:
                self._responses.pop(req_id, None)
            logger.error("Timeout waiting for response to '%s'", method)
            raise RocqClientError(f"Timeout waiting for response to '{method}'")
        else:
            with self._lock:
                self._responses.pop(req_id, None)

        if "error" in response:
            err = response["error"]
            code = err.get("code", -1)
            message = err.get("message", str(err))
            data = err.get("data", "")
            full = f"RPC error [{code}]: {message}"
            if data:
                full += f"\ndata: {data}"
            logger.error("rocq‑mcp error for %s: %s", method, full)
            raise RocqClientError(full, code=code)
        return response.get("result", {})

    def _send_notification(self, method: str, params: Dict[str, Any]) -> None:
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        self._write(json.dumps(notification))

    def _write(self, message: str) -> None:
        if not self.process or not self.process.stdin:
            raise RocqClientError("Server not running")
        try:
            self.process.stdin.write(message + "\n")
            self.process.stdin.flush()
        except BrokenPipeError:
            raise RocqClientError("Server process terminated unexpectedly")

    def _read_responses(self) -> None:
        while self.process and self.process.stdout:
            try:
                line = self.process.stdout.readline()
            except Exception:
                break
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                resp = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("Non‑JSON line from rocq‑mcp: %s", line[:200])
                continue

            if "id" in resp:
                req_id = resp["id"]
                with self._lock:
                    q = self._responses.get(req_id)
                if q:
                    q.put(resp)
            else:
                if self.on_notification:
                    try:
                        self.on_notification(resp.get("method", ""), resp.get("params", {}))
                    except Exception:
                        logger.exception("Error in notification handler")

        with self._lock:
            for req_id, q in list(self._responses.items()):
                q.put({"error": {"code": -32000, "message": "Server process terminated"}})
            self._responses.clear()

    def _drain_stderr(self) -> None:
        while self.process and self.process.stderr:
            try:
                line = self.process.stderr.readline()
            except Exception:
                break
            if not line:
                break
            logger.debug("rocq‑mcp stderr: %s", line.strip())


def _classify_coq_error(message: str) -> str:
    """Classify a Coq error message into a category."""
    lower = message.lower()
    if "syntax error" in lower:
        return "syntax_error"
    if "not found in the current environment" in lower:
        return "unknown_reference"
    if "wrong bullet" in lower or "focus" in lower:
        return "focus"
    if "not a discriminable equality" in lower:
        return "discriminate"
    if "deprecated" in lower:
        return "deprecated"
    if "unable to unify" in lower:
        return "unification"
    if "found no subterm matching" in lower:
        return "rewrite_failure"
    if "no such hypothesis" in lower:
        return "missing_hypothesis"
    if "error" in lower:
        return "compile_error"
    return "unknown"
