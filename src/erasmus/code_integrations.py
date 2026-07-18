"""Optional local code-intelligence connectors; unavailable services fail closed."""
from __future__ import annotations
from dataclasses import dataclass
import shutil

@dataclass(frozen=True)
class IntegrationStatus:
    name: str
    available: bool
    reason: str

def lsp_status(command: str = "pyright-langserver") -> IntegrationStatus:
    path = shutil.which(command)
    return IntegrationStatus("lsp", bool(path), "connected executable" if path else "LSP server not configured")

def context7_status() -> IntegrationStatus:
    return IntegrationStatus("context7", False, "Context7 MCP not exposed to this runtime")
