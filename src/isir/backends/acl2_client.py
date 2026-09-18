# src/isir/backends/acl2_client.py
#
# MCP-based client for ACL2 using the acl2-mcp server.
# Maintains a background event loop to keep the MCP session active.
# All public methods exposed by this client are synchronous.

import asyncio
import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from isir.utils.logger import get_logger
from isir.utils.config_loader import get_config

logger = get_logger(__name__)


class ACL2ClientError(Exception):
    """Raised when ACL2 communication fails."""
    pass


class ACL2Client:
    def __init__(
        self,
        mcp_path: str = "acl2-mcp",
        timeout: int = 30,
        init_commands: Optional[List[str]] = None,
    ):
        self.mcp_path = mcp_path
        self.timeout = timeout
        self.init_commands = init_commands or []
        self.session: Optional[ClientSession] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._started = False

        # Signalled by _session_main after the contexts are entered.
        self._ready_event: Optional[threading.Event] = None
        # Set from stop() to ask _session_main to exit its contexts.
        self._stop_event_async: Optional[asyncio.Event] = None
        # Future for the long-lived task, resolved when it finishes.
        self._session_future = None
        # If _session_main failed during startup, the exception is stored here.
        self._init_error: Optional[BaseException] = None

    def start(self) -> None:
        """Start the ACL2 MCP server in a background thread."""
        if self._started:
            return
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        self._ready_event = threading.Event()
        self._init_error = None
        self._session_future = asyncio.run_coroutine_threadsafe(
            self._session_main(), self._loop
        )

        if not self._ready_event.wait(timeout=30):
            # The session task never signalled readiness.
            self._cleanup_thread()
            raise ACL2ClientError("Timed out starting ACL2 MCP client")
        if self._init_error is not None:
            self._cleanup_thread()
            raise ACL2ClientError(
                f"Failed to start ACL2 MCP client: {self._init_error}"
            )
        self._started = True
        logger.info("ACL2 MCP client started successfully.")

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _session_main(self) -> None:
        """Long-lived task that owns the stdio_client and ClientSession.

        Anyio task groups require __aenter__ and __aexit__ to run in the
        same task.  Keeping both inside this one coroutine satisfies that
        requirement.
        """
        server_params = StdioServerParameters(command=self.mcp_path, args=[])
        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    self.session = session
                    await session.initialize()
                    logger.info("ACL2 MCP session initialized.")
                    for cmd in self.init_commands:
                        await session.call_tool("evaluate", arguments={"form": cmd})

                    # Create the stop event *before* signalling readiness, so
                    # callers that call stop() immediately after start() will
                    # find it.
                    self._stop_event_async = asyncio.Event()
                    self._ready_event.set()

                    # Wait until stop() is called.
                    await self._stop_event_async.wait()
                    self.session = None
        except BaseException as e:  # noqa: BLE001
            self._init_error = e
            if self._ready_event is not None:
                self._ready_event.set()
        finally:
            self.session = None

    def stop(self) -> None:
        """Signal the session task to exit, then shut down the loop."""
        if not self._started:
            return
        try:
            if self._stop_event_async is not None and self._loop is not None:
                self._loop.call_soon_threadsafe(self._stop_event_async.set)
            if self._session_future is not None:
                try:
                    self._session_future.result(timeout=5)
                except Exception as e:
                    logger.warning(
                        "Error during ACL2 client shutdown: %s", e
                    )
        finally:
            self._cleanup_thread()

    def _cleanup_thread(self) -> None:
        """Stop the loop and join the thread (idempotent)."""
        if self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except RuntimeError:
                # Loop already stopped.
                pass
            if self._thread is not None and self._thread.is_alive():
                self._thread.join(timeout=2)
        self._started = False
        self.session = None
        self._loop = None
        self._thread = None
        self._session_future = None
        self._stop_event_async = None

    def _run_async(self, coro):
        """Schedule a coroutine on the background loop and wait for it."""
        if not self._loop or not self._loop.is_running():
            raise ACL2ClientError("Background event loop is not running")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=self.timeout)

    def send(self, command: str, wait: bool = True) -> Optional[str]:
        if not self._started:
            raise ACL2ClientError("ACL2 client not started")
        if not wait:
            logger.warning("wait=False is not supported in MCP mode; ignoring.")
        logger.debug("ACL2 evaluate: %s", command)
        result = self._run_async(self._send_async(command))
        logger.debug(
            "ACL2 response (%d chars): %s",
            len(result) if result else 0,
            (result or "")[:500],
        )
        return result

    async def _send_async(self, command: str) -> str:
        """Asynchronous send using the evaluate tool."""
        try:
            result = await self.session.call_tool(
                "evaluate", arguments={"form": command}
            )
            if result.content and len(result.content) > 0:
                return result.content[0].text
            return ""
        except Exception as e:
            logger.error("ACL2 evaluate failed: %s", e)
            raise ACL2ClientError(f"ACL2 evaluate failed: {e}")

    async def _call_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Call an MCP tool and log the raw response.

        Returns a dict with keys: success, output, error.
        """
        logger.debug("Calling tool '%s' with args: %s", tool_name, arguments)
        try:
            result = await self.session.call_tool(tool_name, arguments=arguments)
            logger.debug(
                "Tool '%s' raw result: %s",
                tool_name,
                str(result.content)[:500],
            )
            if result.content and len(result.content) > 0:
                text = result.content[0].text
                try:
                    data = json.loads(text)
                    success = data.get("success", False)
                    output = data.get("output", text)
                    error = data.get("error")
                    return {"success": success, "output": output, "error": error}
                except json.JSONDecodeError:
                    success = not self._contains_error(text)
                    return {
                        "success": success,
                        "output": text,
                        "error": None if success else text,
                    }
            return {
                "success": False,
                "output": "",
                "error": "Empty response from MCP tool",
            }
        except Exception as e:
            logger.warning("Tool '%s' failed: %s", tool_name, e)
            return {"success": False, "output": "", "error": str(e)}

    def load_file(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Load a Lisp file containing ACL2 definitions into the session.

        Sends ``(ld "path")`` to ACL2.  Accepts either ``str`` or
        ``pathlib.Path``.

        Returns:
            A dict with keys ``success``, ``output``, and optionally ``error``.
        """
        if not self._started:
            raise ACL2ClientError("ACL2 client not started")

        path_str = str(file_path)
        logger.info("Loading ACL2 file: %s", path_str)
        try:
            result = self.send(f'(ld "{path_str}")')
            success = not self._contains_error(result)
            if success:
                logger.info("ACL2 file loaded successfully: %s", path_str)
            else:
                logger.error(
                    "Failed to load ACL2 file %s: %s",
                    path_str,
                    (result or "")[:500],
                )
            return {"success": success, "output": result}
        except Exception as e:
            logger.error("Failed to load ACL2 file %s: %s", path_str, e)
            return {"success": False, "output": "", "error": str(e)}

    def defun(
        self,
        func_name: str,
        args: List[str],
        body: str,
        guard: Optional[str] = None,
        mode: str = ":logic",
        verify_guards: bool = True,
    ) -> Dict[str, Any]:
        args_str = " ".join(args)
        xargs_parts = []
        if guard:
            guard_str = f":guard {guard}"
            if not verify_guards:
                guard_str += " :verify-guards nil"
            xargs_parts.append(guard_str)
        if mode and mode != ":logic":
            xargs_parts.append(f":mode {mode}")

        if xargs_parts:
            declare_str = f"(declare (xargs {' '.join(xargs_parts)}))"
            form = f"(defun {func_name} ({args_str})\n  {declare_str}\n  {body})"
        else:
            form = f"(defun {func_name} ({args_str})\n  {body})"

        output = self.send(form)
        success = not self._contains_error(output)
        return {"success": success, "output": output}

    def defthm(
        self,
        theorem_name: str,
        statement: str,
        hints: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if not self._started:
            raise ACL2ClientError("ACL2 client not started")
        return self._run_async(
            self._defthm_async(theorem_name, statement, hints)
        )

    async def _defthm_async(
        self,
        theorem_name: str,
        statement: str,
        hints: Optional[List[str]],
    ) -> Dict[str, Any]:
        hints_str = " ".join(hints) if hints else ""
        if hints_str:
            form = (
                f"(defthm {theorem_name}\n  {statement}\n"
                f"  :hints ({hints_str}))"
            )
        else:
            form = f"(defthm {theorem_name}\n  {statement})"

        logger.info("Attempting to prove '%s' via MCP 'prove' tool.", theorem_name)
        result = await self._call_tool(
            "prove",
            {
                "theorem": statement,
                "name": theorem_name,
                **({"hints": hints} if hints else {}),
            },
        )
        if result["success"]:
            return result

        logger.warning(
            "'prove' tool failed (error: %s). Falling back to evaluate.",
            result.get("error"),
        )
        logger.debug("Falling back to evaluate with form: %s", form)
        eval_result = await self._call_tool("evaluate", {"form": form})
        return {
            "success": eval_result["success"],
            "output": eval_result["output"],
            "error": eval_result.get("error"),
        }

    def undo(self) -> Dict[str, Any]:
        result = self.send(":u")
        success = not self._contains_error(result)
        return {"success": success, "output": result}

    def undo_back_to(self, name: str) -> Dict[str, Any]:
        result = self.send(f"(ubt! '{name})")
        success = not self._contains_error(result)
        return {"success": success, "output": result}

    def save_checkpoint(self, name: str) -> Dict[str, Any]:
        if not self._started:
            raise ACL2ClientError("ACL2 client not started")
        return self._run_async(self._save_checkpoint_async(name))

    async def _save_checkpoint_async(self, name: str) -> Dict[str, Any]:
        return await self._call_tool("save_checkpoint", {"name": name})

    def restore_checkpoint(self, name: str) -> Dict[str, Any]:
        if not self._started:
            raise ACL2ClientError("ACL2 client not started")
        return self._run_async(self._restore_checkpoint_async(name))

    async def _restore_checkpoint_async(self, name: str) -> Dict[str, Any]:
        return await self._call_tool("restore_checkpoint", {"name": name})

    def include_book(self, book_path: str) -> Dict[str, Any]:
        result = self.send(f'(include-book "{book_path}")')
        success = not self._contains_error(result)
        return {"success": success, "output": result}

    def certify_book(self, book_path: str) -> Dict[str, Any]:
        result = self.send(f'(certify-book "{book_path}")')
        success = not self._contains_error(result)
        return {"success": success, "output": result}

    @staticmethod
    def _contains_error(output: str) -> bool:
        if not output:
            return False
        error_indicators = ["Error:", "ACL2 Error", "***"]
        return any(ind in output for ind in error_indicators)


def get_acl2_client_from_config(
    config: Optional[Dict[str, Any]] = None,
) -> ACL2Client:
    if config is None:
        config = get_config()

    acl2_cfg = config.get("provers", {}).get("acl2", {})
    return ACL2Client(
        mcp_path=acl2_cfg.get("mcp_path", "acl2-mcp"),
        timeout=acl2_cfg.get("mcp_timeout", 30),
        init_commands=acl2_cfg.get("init_commands", []),
    )
