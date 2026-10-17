"""Thin MCP client used by the agents: spawns kap.mcp_server over stdio with the agent's identity
and data permissions in the environment, and exposes call(tool, **args).

The MCP session lives on one background thread with its own event loop (anyio task groups must be
entered and exited by the same task), and synchronous callers submit coroutines to it."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from kap.config import REPO_ROOT


class MCPToolClient:
    def __init__(self, agent: str, allowed_tools: list[str], caller: str = "agent-runtime", task_id: str | None = None) -> None:
        self.agent, self.allowed_tools, self.caller, self.task_id = agent, list(allowed_tools), caller, task_id
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._session: ClientSession | None = None
        self._stack: AsyncExitStack | None = None
        self._shutdown: asyncio.Event | None = None
        self._main_fut = None

    # -- lifecycle --------------------------------------------------------------------------
    def __enter__(self) -> "MCPToolClient":
        self._thread.start()
        opened = threading.Event()
        self._main_fut = asyncio.run_coroutine_threadsafe(self._main(opened), self._loop)
        if not opened.wait(timeout=60):
            raise RuntimeError("MCP server did not start")
        if self._main_fut.done() and self._main_fut.exception():
            raise self._main_fut.exception()  # type: ignore[misc]
        return self

    def __exit__(self, *exc) -> None:
        try:
            self._loop.call_soon_threadsafe(self._shutdown.set)  # type: ignore[union-attr]
            self._main_fut.result(timeout=30)  # type: ignore[union-attr]
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=10)

    async def _main(self, opened: threading.Event) -> None:
        """Open and close the session in ONE task; anyio cancel scopes require it."""
        env = {**os.environ, "KAP_CALLER": self.caller, "KAP_AGENT": self.agent,
               "KAP_ALLOWED_TOOLS": ",".join(self.allowed_tools), "PYTHONPATH": str(REPO_ROOT / "src")}
        if self.task_id:
            env["KAP_TASK_ID"] = self.task_id
        params = StdioServerParameters(command=sys.executable, args=["-m", "kap.mcp_server"], env=env, cwd=str(REPO_ROOT))
        self._shutdown = asyncio.Event()
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._session = session
                    opened.set()
                    await self._shutdown.wait()
        finally:
            opened.set()

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=300)

    # -- API --------------------------------------------------------------------------------
    def list_tools(self) -> list[str]:
        assert self._session
        return [t.name for t in self._run(self._session.list_tools()).tools]

    def call(self, tool: str, **args: Any) -> dict[str, Any]:
        """Client-side permission check first (the server enforces the same list), then the call."""
        if tool not in self.allowed_tools:
            raise PermissionError(f"agent '{self.agent}' may not call '{tool}'")
        self.calls.append((tool, args))
        assert self._session
        res = self._run(self._session.call_tool(tool, args))
        if res.is_error:
            text = res.content[0].text if res.content else "tool error"
            raise RuntimeError(text)
        if res.structured_content is not None:
            sc = res.structured_content
            return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
        return json.loads(res.content[0].text)
