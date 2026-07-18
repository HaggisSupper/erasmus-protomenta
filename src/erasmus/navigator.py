"""Read-only local code navigator for bounded work-package routing."""
from __future__ import annotations
import ast
from dataclasses import asdict, dataclass
from pathlib import Path

@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str
    file: str
    line: int

class Navigator:
    def __init__(self, root: str | Path): self.root = Path(root).resolve()
    def index(self) -> dict:
        symbols: list[Symbol] = []; imports: dict[str, list[str]] = {}
        for path in self.root.rglob("*.py"):
            if any(part in {".git", ".venv", "__pycache__"} for part in path.parts): continue
            try: tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError): continue
            rel = str(path.relative_to(self.root))
            imports[rel] = [node.names[0].name if isinstance(node, ast.Import) else node.module or "" for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    symbols.append(Symbol(node.name, "class" if isinstance(node, ast.ClassDef) else "function", rel, node.lineno))
        return {"root": str(self.root), "symbols": [asdict(s) for s in symbols], "imports": imports, "backend": "python-ast", "readonly": True}
    def route(self, query: str) -> dict:
        index = self.index(); needle = query.lower(); matches = [s for s in index["symbols"] if needle in s["name"].lower() or needle in s["file"].lower()]
        files = sorted({s["file"] for s in matches})
        return {"query": query, "candidate_files": files[:50], "symbols": matches[:100], "dependencies": sorted({d for f in files for d in index["imports"].get(f, [])}), "required_tests": [f for f in index["imports"] if Path(f).name.startswith("test_")], "readonly": True}
