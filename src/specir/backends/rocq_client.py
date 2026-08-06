# src/specir/backends/rocq_client.py
#
# Low-level client for the rocq-mcp MCP server.
# Supports passing server-side arguments for flexible configuration.
# All workspace and file paths are resolved to absolute paths to avoid
# "invalid path" errors from rocq‑mcp.

import json
import subprocess
import sys
import threading
import queue
import itertools
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from specir.utils.logger import get_logger

logger = get_logger(__name__)


class RocqClientError(Exception):
    """Raised when rocq‑mcp communication fails."""
    def __init__(self, message: str, code: Optional[int] = None):
        super().__init__(message)
        self.code = code


class RocqClient:
    """Client for rocq‑mcp MCP server."""
    def __init__(
        self,
        rocq_mcp_path: str = "rocq-mcp",
        timeout: int = 300,
        cwd: Optional[Path] = None,
        server_args: Optional[List[str]] = None,
        on_notification: Optional[Callable[[str, Dict[str, Any]], None]] = None
    ):
        self.rocq_mcp_path = rocq_mcp_path
        self.timeout = timeout
        # Resolve CWD to absolute path if provided
        self.cwd = cwd.resolve() if cwd is not None else None
        self.server_args = server_args or []
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
        # Resolve workspace in server_args to absolute path
        resolved_args = []
        skip_next = False
        for i, arg in enumerate(self.server_args):
            if skip_next:
                skip_next = False
                continue
            if arg == "--workspace" and i + 1 < len(self.server_args):
                workspace_val = self.server_args[i + 1]
                # Resolve to absolute if it's a path
                resolved_ws = str(Path(workspace_val).resolve())
                resolved_args.append(arg)
                resolved_args.append(resolved_ws)
                skip_next = True
            else:
                resolved_args.append(arg)
        cmd.extend(resolved_args)
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
        self.process.terminate()
        try:
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

    def _extract_error_from_response(self, response: Dict[str, Any]) -> Optional[str]:
        """
        Recursively extract error message from MCP response.
        Searches in structuredContent, content, and common error fields.
        Returns None if no error found.
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

    def compile_file(
        self,
        file_path: Path,
        workspace: Optional[Path] = None,
        keep_vo: bool = True
    ) -> Dict[str, Any]:
        # Resolve file_path and workspace to absolute paths
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
        return result

    def verify(
        self,
        file_path: Path,
        theorem_name: str,
        workspace: Optional[Path] = None
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
            result["error"] = error
        return result

    def start_session(
        self,
        file_path: Path,
        theorem_name: str,
        workspace: Optional[Path] = None
    ) -> Tuple[str, List[str]]:
        file_path = file_path.resolve()
        if workspace is not None:
            workspace = workspace.resolve()
        params = {"file": str(file_path), "theorem": theorem_name}
        if workspace is not None:
            params["workspace"] = str(workspace)
        logger.info(f"rocq_start request params: {params}")

        resp = self._call_tool("rocq_start", params)
        logger.info(f"rocq_start raw response: {resp}")

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

        error = self._extract_error_from_response(resp)
        if error:
            logger.error(f"rocq_start returned error: {error}")
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

    def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke an MCP tool via `tools/call`."""
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
