#!/usr/bin/env python3
"""Runner-agnostic MCP client for the common gateway at 11620.

Any runner can use this to reach all 13+ upstream MCP servers through a
single multiplexed connection.  No runner-specific tokens required.

Usage::

    from common_mcp_client import CommonMCPClient

    gw = CommonMCPClient()
    gw.initialize()

    # Direct upstream tool call
    result = gw.call_upstream("antigravity_local", "memory_store", {
        "content": "...",
        "metadata": {"source_runner": "claude-code", ...}
    })

    # Convenience: memory operations (routed through antigravity_local)
    gw.memory_store(content="...", metadata={...})
    gw.memory_query(query="LMPP", top_k=5)

    # Convenience: other upstreams
    gw.jcodemunch("search_symbols", {"query": "Pipeline", "repo": "agl-ocr-pipeline"})
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests


class CommonMCPError(RuntimeError):
    """Raised when common gateway MCP calls fail."""


@dataclass(frozen=True)
class CommonMCPConfig:
    url: str
    timeout_s: int = 30


def _pick_memfab_api_url() -> str:
    explicit = os.getenv("ANTIGRAVITY_MEMORY_FABRIC_API_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    host = os.getenv("ANTIGRAVITY_MEMORY_FABRIC_API_HOST", "127.0.0.1").strip() or "127.0.0.1"
    primus_root = Path("/usr/production")
    legacy_root = Path("/mnt/f/Production")
    primus_root_is_dir = primus_root.is_dir()
    # Memory Fabric API defaults are separate from the 11888 inference router.
    if Path("/usr/production/start_memfab_tunnel.sh").exists() or Path("/linuxdata/Github").exists() or primus_root_is_dir:
        default_port = "18001"
    elif not primus_root.exists() and legacy_root.is_dir():
        # Legacy Datacube-only fallback when the Primus production tree is absent.
        default_port = "8001"
    else:
        default_port = "18001"
    port = os.getenv("ANTIGRAVITY_MEMORY_FABRIC_API_PORT", default_port).strip() or default_port
    return f"http://{host}:{port}"


def _pick_url() -> str:
    explicit = os.getenv("ANTIGRAVITY_COMMON_MCP_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    host = os.getenv("ANTIGRAVITY_COMMON_MCP_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = os.getenv("ANTIGRAVITY_COMMON_MCP_PORT", "11620").strip() or "11620"
    mount = os.getenv("ANTIGRAVITY_COMMON_MCP_MOUNT_PATH", "/mcp").strip() or "/mcp"
    if not mount.startswith("/"):
        mount = f"/{mount}"
    return f"http://{host}:{port}{mount}"


def config_from_env() -> CommonMCPConfig:
    timeout_s = 30
    try:
        timeout_s = max(5, min(300, int(os.getenv("ANTIGRAVITY_COMMON_MCP_TIMEOUT_S", "30"))))
    except Exception:
        timeout_s = 30
    return CommonMCPConfig(url=_pick_url(), timeout_s=timeout_s)


def _parse_jsonrpc_response(text: str) -> dict[str, Any]:
    """Parse JSON-RPC response from either JSON or SSE transport."""
    raw = str(text or "").strip()
    if not raw:
        raise CommonMCPError("Empty MCP response body")
    if raw.startswith("{"):
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise CommonMCPError("MCP response is not a JSON object")
        return payload
    # SSE format: data: {...}
    data_lines: list[str] = []
    for line in raw.splitlines():
        if line.startswith("data:"):
            data_lines.append(line[5:].strip())
    if not data_lines:
        raise CommonMCPError(f"Unsupported MCP response body: {raw[:200]}")
    payload = json.loads("\n".join(data_lines))
    if not isinstance(payload, dict):
        raise CommonMCPError("MCP SSE response is not a JSON object")
    return payload


class CommonMCPClient:
    """Runner-agnostic MCP client for the common gateway.

    Connects to the shared gateway at 11620 (default) and multiplexes
    calls to any registered upstream server.  No runner-specific tokens
    or sessions required — just the gateway session.
    """

    def __init__(self, config: CommonMCPConfig | None = None, *, source_runner: str = ""):
        self._config = config or config_from_env()
        self._session_id: str | None = None
        self._http = requests.Session()
        self._source_runner = source_runner or os.getenv("ANTIGRAVITY_RUNNER_ID", "unknown")
        self._memfab_api_url = _pick_memfab_api_url()

    # -- transport --------------------------------------------------------

    def _headers(self, include_session: bool) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if include_session and self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def _post(self, payload: dict[str, Any], include_session: bool) -> dict[str, Any]:
        try:
            response = self._http.post(
                self._config.url,
                json=payload,
                headers=self._headers(include_session),
                timeout=self._config.timeout_s,
            )
        except requests.RequestException as exc:
            raise CommonMCPError(f"MCP request failed: {exc}") from exc
        if response.status_code >= 400:
            raise CommonMCPError(f"MCP HTTP {response.status_code}: {response.text}")
        data = _parse_jsonrpc_response(response.text)
        if not include_session:
            new_sid = response.headers.get("Mcp-Session-Id")
            if new_sid:
                self._session_id = new_sid
        if "error" in data:
            raise CommonMCPError(f"MCP error: {data['error']}")
        return data

    def initialize(self) -> dict[str, Any]:
        """Initialize the MCP session with the gateway."""
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "common-mcp-client", "version": "1.0"},
            },
        }
        return self._post(payload, include_session=False)

    def _ensure_session(self) -> None:
        if not self._session_id:
            self.initialize()

    def call_gateway_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a gateway-level tool (gateway_status, gateway_list_tools, etc.)."""
        self._ensure_session()
        call_arguments = arguments
        if call_arguments and "params" not in call_arguments:
            call_arguments = {"params": call_arguments}
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {"name": name, "arguments": call_arguments},
        }
        return self._post(payload, include_session=True)

    # -- upstream routing -------------------------------------------------

    def call_upstream(
        self,
        upstream: str,
        tool: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call a tool on a specific upstream server through the gateway.

        Upstream tools declared as ``tool(params: Model)`` need their
        arguments wrapped in a ``params`` key.  This method handles that
        automatically — callers pass flat dicts.
        """
        args = arguments or {}
        # Upstream tools (antigravity_local, etc.) expect {params: {...}}
        if args and "params" not in args:
            args = {"params": args}
        return self.call_gateway_tool("gateway_call_tool", {
            "upstream": upstream,
            "tool": tool,
            "arguments": args,
        })

    @staticmethod
    def extract_payload(response: dict[str, Any]) -> Any:
        """Extract the useful payload from a gateway_call_tool response.

        Malformed JSON in the wrapped text payload is a hard failure so callers
        do not mistake partial gateway output for a successful result.
        """
        result = response.get("result", {})
        content = result.get("content", [])
        for item in content:
            if item.get("type") != "text":
                continue
            text = item.get("text", "")
            try:
                outer = json.loads(text)
            except json.JSONDecodeError:
                raise CommonMCPError(f"MCP payload is not valid JSON: {text[:200]}")
            # gateway_call_tool wraps in {status, upstream, tool, result}
            if isinstance(outer, dict) and "result" in outer:
                return outer["result"]
            return outer
        if result.get("isError"):
            raise CommonMCPError(str(result))
        return result

    # -- memory convenience (antigravity_local) ---------------------------
    #
    # memory_store is the live canonical write surface. Keep the historical
    # memory_write method as a compatibility wrapper, but never route callers
    # to a tool that is absent from the advertised upstream schema.

    def memory_write(
        self,
        content: str = "",
        *,
        text: str = "",
        file_path: str = "",
        title: str = "",
        abstract: str = "",
        user_id: str = "global",
        summary: str = "",
        event_type: str = "",
        what: str = "",
        why: str = "",
        impact: str = "",
        category: str = "",
        source_runner: str = "",
        source_tool: str = "common_mcp_client",
        source: str = "antigravity_local_mcp",
        workspace: str = "Memory Fabric",
        repo_or_system: str = "",
        component: str = "",
        tags: list[str] | None = None,
        observed_at_utc: str = "",
        scope: str = "global",
        durability: str = "long-term",
        storage_scope: str = "long_term",
        artifact_kind: str = "",
        source_receipts: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        preserve_artifact: bool = False,
        supersedes: list[str] | None = None,
        update_existing: bool = True,
        idempotency_key: str = "",
        sync: bool = False,
    ) -> dict[str, Any]:
        """Canonical Memory Fabric write entry point.

        The antigravity_local upstream decides whether the write is a memory
        note, source document, or preserved long artifact.
        """
        args: dict[str, Any] = {}
        if content:
            args["content"] = content
        elif text:
            args["text"] = text
        if user_id:
            args["user_id"] = user_id
        if category:
            args["category"] = category
        if source:
            args["source"] = source
        if component:
            args["component"] = component
        if tags:
            args["tags"] = tags
        if observed_at_utc:
            args["timestamp_utc"] = observed_at_utc
        if sync:
            args["sync"] = True

        # Preserve the richer historical API fields as metadata. The live
        # memory_store schema intentionally accepts only its stable write
        # contract at top level; passing the legacy fields directly caused
        # callers to hit the removed memory_write tool or drift by gateway.
        compatibility_metadata = dict(metadata or {})
        legacy_metadata = {
            "file_path": file_path,
            "title": title,
            "abstract": abstract,
            "summary": summary,
            "event_type": event_type,
            "what": what,
            "why": why,
            "impact": impact,
            "source_runner": source_runner or self._source_runner,
            "source_tool": source_tool,
            "workspace": workspace,
            "repo_or_system": repo_or_system,
            "scope": scope,
            "durability": durability,
            "storage_scope": storage_scope,
            "artifact_kind": artifact_kind,
            "source_receipts": source_receipts,
            "preserve_artifact": preserve_artifact,
            "supersedes": supersedes,
            "update_existing": update_existing,
            # The live Datacube service currently enforces an older
            # extra-forbid schema without a top-level idempotency_key. Keep
            # the identity in supported metadata; content fingerprinting then
            # provides deterministic replay suppression without schema drift.
            "idempotency_key": idempotency_key,
        }
        for key, value in legacy_metadata.items():
            if value not in ("", None, [], False) or key in {"update_existing", "idempotency_key"}:
                compatibility_metadata.setdefault(key, value)
        if compatibility_metadata:
            args["metadata"] = compatibility_metadata
        return self.call_upstream("antigravity_local", "memory_store", args)

    def memory_store(
        self,
        content: str,
        *,
        user_id: str = "global",
        summary: str = "",
        event_type: str = "",
        what: str = "",
        why: str = "",
        impact: str = "",
        category: str = "",
        source_runner: str = "",
        source_tool: str = "common_mcp_client",
        repo_or_system: str = "",
        component: str = "",
        tags: list[str] | None = None,
        observed_at_utc: str = "",
        scope: str = "global",
        durability: str = "long-term",
        storage_scope: str = "long_term",
        supersedes: list[str] | None = None,
        update_existing: bool = True,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str = "",
        sync: bool = False,
    ) -> dict[str, Any]:
        """Compatibility wrapper for structured memory notes."""
        return self.memory_write(
            content=content,
            user_id=user_id,
            summary=summary,
            event_type=event_type,
            what=what,
            why=why,
            impact=impact,
            category=category,
            source_runner=source_runner,
            source_tool=source_tool,
            repo_or_system=repo_or_system,
            component=component,
            tags=tags,
            observed_at_utc=observed_at_utc,
            scope=scope,
            durability=durability,
            storage_scope=storage_scope,
            supersedes=supersedes,
            update_existing=update_existing,
            metadata=metadata,
            idempotency_key=idempotency_key,
            sync=sync,
        )

    def memory_query(
        self, question: str, top_k: int = 8, *, force_exact: bool = False
    ) -> dict[str, Any]:
        """Query memory via antigravity_local (RAG-style, returns answer)."""
        return self.call_upstream("antigravity_local", "memory_query", {
            "question": question,
            "top_k": top_k,
            "force_exact": force_exact,
        })

    def memory_retrieve(
        self, query: str, top_k: int = 10, *, force_exact: bool = False
    ) -> dict[str, Any]:
        """Retrieve raw memories by semantic similarity via antigravity_local."""
        return self.call_upstream("antigravity_local", "memory_retrieve", {
            "query": query,
            "top_k": top_k,
            "force_exact": force_exact,
        })

    def memory_search(
        self, query: str, limit: int = 10, *, force_exact: bool = False
    ) -> dict[str, Any]:
        """Search memories via antigravity_local."""
        return self.call_upstream("antigravity_local", "memory_search", {
            "query": query,
            "limit": limit,
            "force_exact": force_exact,
        })

    def wiki_lookup(
        self,
        key: str = "",
        *,
        slug: str = "",
        canonical_for: str = "",
        skill_name: str = "",
        user_id: str = "global",
        limit: int = 10,
    ) -> dict[str, Any]:
        """Resolve current MemWiki artifacts by deterministic keys."""
        lookup_canonical_for = canonical_for or key
        if not any((slug.strip(), lookup_canonical_for.strip(), skill_name.strip())):
            raise ValueError("wiki_lookup requires key, slug, canonical_for, or skill_name")
        params = {
            "slug": slug,
            "canonical_for": lookup_canonical_for,
            "skill_name": skill_name,
            "user_id": user_id,
            "limit": max(1, min(int(limit), 20)),
            "include_sections": False,
        }
        try:
            response = self._http.get(
                f"{self._memfab_api_url}/wiki/lookup",
                params=params,
                timeout=self._config.timeout_s,
            )
        except requests.RequestException as exc:
            raise CommonMCPError(f"MemWiki lookup failed: {exc}") from exc
        if response.status_code >= 400:
            raise CommonMCPError(f"MemWiki HTTP {response.status_code}: {response.text}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise CommonMCPError("MemWiki response is not a JSON object")
        return payload

    def wiki_then_memory_search(
        self,
        key: str,
        *,
        query: str = "",
        limit: int = 10,
        user_id: str = "global",
    ) -> dict[str, Any]:
        """Exact MemWiki lookup first, broad memory search only when empty.

        Malformed payloads from the memory-search path propagate as hard
        failures instead of being treated as a successful lookup.
        """
        wiki = self.wiki_lookup(key, user_id=user_id, limit=limit)
        if wiki.get("results"):
            return {"route": "wiki_lookup", **wiki}
        search = self.memory_search(query or key, limit=limit)
        # The gateway text payload must decode cleanly; otherwise fail closed.
        payload = self.extract_payload(search)
        return {"route": "memory_search", "wiki": wiki, "memory": payload}

    def memory_store_long_artifact(
        self,
        title: str,
        body_markdown: str,
        *,
        abstract: str = "",
        user_id: str = "global",
        source: str = "runner_long_artifact",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Compatibility wrapper for preserved long-form artifacts."""
        return self.memory_write(
            content=body_markdown,
            title=title,
            abstract=abstract,
            source=source,
            user_id=user_id,
            source_tool="common_mcp_client_long_artifact",
            artifact_kind="generated_document",
            metadata=metadata,
            preserve_artifact=True,
            storage_scope="long_term",
        )

    def task_context_bootstrap(self) -> dict[str, Any]:
        """Run task_context_bootstrap via antigravity_local."""
        return self.call_upstream("antigravity_local", "task_context_bootstrap", {})

    # -- other upstream convenience methods -------------------------------

    def jcodemunch(self, tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call a jCodeMunch tool."""
        return self.call_upstream("jcodemunch", tool, arguments)

    def jdocmunch(self, tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call a jDocMunch tool."""
        return self.call_upstream("jdocmunch_mcp", tool, arguments)

    def orchestrator(self, tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call an orchestrator tool."""
        return self.call_upstream("orchestrator", tool, arguments)

    def agent_mail(self, tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call an agent mail tool."""
        return self.call_gateway_tool("gateway_call_tool", {
            "upstream": "mcp_agent_mail",
            "tool": tool,
            "arguments": arguments or {},
        })

    def list_upstreams(self) -> dict[str, Any]:
        """List all upstream servers and their connection status."""
        return self.call_gateway_tool("gateway_list_upstreams", {})

    def list_tools(
        self,
        upstream: str | None = None,
        query: str | None = None,
        include_schema: bool = False,
    ) -> dict[str, Any]:
        """List tools, optionally filtered by upstream or keyword."""
        params: dict[str, Any] = {"include_schema": include_schema}
        if upstream:
            params["upstream"] = upstream
        if query:
            params["query"] = query
        return self.call_gateway_tool("gateway_list_tools", params)

    def close(self) -> None:
        self._http.close()


# -- singleton for shared use -------------------------------------------------

_shared_lock = threading.Lock()
_shared_client: CommonMCPClient | None = None


def get_shared_client(source_runner: str = "") -> CommonMCPClient:
    """Get or create the process-wide shared CommonMCPClient."""
    global _shared_client
    with _shared_lock:
        if _shared_client is None:
            _shared_client = CommonMCPClient(source_runner=source_runner)
        return _shared_client


def close_shared_client() -> None:
    global _shared_client
    with _shared_lock:
        if _shared_client is not None:
            _shared_client.close()
            _shared_client = None
