# src/specir/backends/acl2_client.py
#
# MCP-based client for ACL2 using the acl2-mcp server.
# Maintains a background event loop to keep the MCP session active.
# All public methods exposed by this client are synchronous.

import asyncio
import json
import threading
from typing import Any, Dict, List, Optional, Union

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from specir.utils.logger import get_logger
from specir.utils.config_loader import get_config

logger = get_logger(__name__)


class ACL2ClientError(Exception):
    """Raised when ACL2 communication fails."""
    pass


class ACL2Client:
    """
    Client for ACL2 via acl2-mcp MCP server.

    This client uses a background event loop to keep the MCP session alive.
    All public methods are synchronous.
    """
    def __init__(
        self,
        mcp_path: str = "acl2-mcp",
        timeout: int = 30,
        init_commands: Optional[List[str]] = None
    ):
        self.mcp_path = mcp_path
        self.timeout = timeout
        self.init_commands = init_commands or []
        self.session: Optional[ClientSession] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._started = False

    def start(self) -> None:
        """Start the ACL2 MCP server in a background thread."""
        if self._started:
            return
        try:
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            future = asyncio.run_coroutine_threadsafe(self._init_session(), self._loop)
            future.result(timeout=30)
            self._started = True
            logger.info("ACL2 MCP client started successfully.")
        except Exception as e:
            self._loop = None
            raise ACL2ClientError(f"Failed to start ACL2 MCP client: {e}")

    def _run_loop(self) -> None:
        """Set the event loop for the background thread and run forever."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _init_session(self) -> None:
        """Initialise the MCP session."""
        server_params = StdioServerParameters(command=self.mcp_path, args=[])
        self._stdio_ctx = stdio_client(server_params)
        read, write = await self._stdio_ctx.__aenter__()
        self._session_ctx = ClientSession(read, write)
        self.session = await self._session_ctx.__aenter__()
        await self.session.initialize()
        logger.info("ACL2 MCP session initialized.")
        for cmd in self.init_commands:
            await self._send_async(cmd)

    def stop(self) -> None:
        """Stop the background event loop and clean up."""
        if not self._started:
            return
        try:
            future = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
            future.result(timeout=5)
        except Exception as e:
            logger.warning(f"Error during ACL2 client shutdown: {e}")
        finally:
            if self._loop:
                self._loop.call_soon_threadsafe(self._loop.stop)
                if self._thread and self._thread.is_alive():
                    self._thread.join(timeout=2)
            self._started = False
            self.session = None
            self._loop = None
            self._thread = None

    async def _shutdown(self) -> None:
        if self.session:
            await self.session.__aexit__(None, None, None)
            self.session = None
        if hasattr(self, '_session_ctx'):
            await self._session_ctx.__aexit__(None, None, None)
        if hasattr(self, '_stdio_ctx'):
            await self._stdio_ctx.__aexit__(None, None, None)

    def _run_async(self, coro):
        """Run a coroutine in the background event loop and return result."""
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
        logger.debug("ACL2 response (%d chars): %s", len(result), result[:500])
        return result

    async def _send_async(self, command: str) -> str:
        """Asynchronous send using evaluate tool."""
        try:
            result = await self.session.call_tool("evaluate", arguments={"form": command})
            if result.content and len(result.content) > 0:
                return result.content[0].text
            return ""
        except Exception as e:
            logger.error("ACL2 evaluate failed: %s", e)
            raise ACL2ClientError(f"ACL2 evaluate failed: {e}")

    async def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call an MCP tool and log the raw response.

        Returns a dict with keys: success, output, error.
        If the tool call itself throws (e.g. method not found), the error
        is captured and returned as a failure.
        """
        logger.debug("Calling tool '%s' with args: %s", tool_name, arguments)
        try:
            result = await self.session.call_tool(tool_name, arguments=arguments)
            logger.debug("Tool '%s' raw result: %s", tool_name, str(result.content)[:500])
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
                    return {"success": success, "output": text, "error": None if success else text}
            return {"success": False, "output": "", "error": "Empty response from MCP tool"}
        except Exception as e:
            logger.warning("Tool '%s' failed: %s", tool_name, e)
            return {"success": False, "output": "", "error": str(e)}

    def defun(
        self,
        func_name: str,
        args: List[str],
        body: str,
        guard: Optional[str] = None,
        mode: str = ":logic",
        verify_guards: bool = True
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
        hints: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        if not self._started:
            raise ACL2ClientError("ACL2 client not started")
        return self._run_async(self._defthm_async(theorem_name, statement, hints))

    async def _defthm_async(self, theorem_name: str, statement: str, hints: Optional[List[str]]) -> Dict[str, Any]:
        hints_str = " ".join(hints) if hints else ""
        if hints_str:
            form = f"(defthm {theorem_name}\n  {statement}\n  :hints ({hints_str}))"
        else:
            form = f"(defthm {theorem_name}\n  {statement})"

        logger.info("Attempting to prove '%s' via MCP 'prove' tool.", theorem_name)
        result = await self._call_tool("prove", {
            "theorem": statement,
            "name": theorem_name,
            **({"hints": hints} if hints else {})
        })
        if result["success"]:
            return result

        logger.warning("'prove' tool failed (error: %s). Falling back to evaluate.", result.get("error"))
        logger.debug("Falling back to evaluate with form: %s", form)
        eval_result = await self._call_tool("evaluate", {"form": form})

        return {
            "success": eval_result["success"],
            "output": eval_result["output"],
            "error": eval_result.get("error")
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


def get_acl2_client_from_config(config: Optional[Dict[str, Any]] = None) -> ACL2Client:
    if config is None:
        config = get_config()

    acl2_cfg = config.get("provers", {}).get("acl2", {})
    return ACL2Client(
        mcp_path=acl2_cfg.get("mcp_path", "acl2-mcp"),
        timeout=acl2_cfg.get("mcp_timeout", 30),
        init_commands=acl2_cfg.get("init_commands", [])
    )
