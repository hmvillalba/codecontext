"""Core scanner - orchestrates parsing, analysis, and generation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from codecontext.analyzers.architecture import detect_architecture
from codecontext.analyzers.dependency import resolve_dependencies, find_circular_dependencies
from codecontext.analyzers.routes import extract_routes
from codecontext.analyzers.model_relations import extract_model_relations, extract_model_properties
from codecontext.analyzers.migrations import extract_migrations
from codecontext.analyzers.risks import detect_risks
from codecontext.analyzers.traceability import build_traces, build_role_map
from codecontext.generators import generate_json_index, generate_compact_json_string
from codecontext.generators.markdown import generate_markdown
from codecontext.generators.summary import generate_summary
from codecontext.models import FileSummary, Language, NodeType, ProjectIndex
from codecontext.parsers.go_parser import GoParser
from codecontext.parsers.php_parser import PhpParser
from codecontext.parsers.python_parser import PythonParser
from codecontext.parsers.rust_parser import RustParser
from codecontext.parsers.ts_parser import TypeScriptParser
from codecontext.parsers.csharp_parser import CSharpParser

IGNORE_DIRS = {
    "node_modules", "vendor", ".git", "__pycache__", ".venv", "venv",
    "env", ".env", "dist", "build", ".next", ".nuxt", "target",
    "vendor", ".idea", ".vscode", "coverage", ".coverage",
    "htmlcov", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "storage", "bootstrap/cache", "public/build", "public/hot",
}

IGNORE_EXTENSIONS = {
    ".lock", ".map", ".min.js", ".min.css", ".bundle.js",
    ".woff", ".woff2", ".ttf", ".eot", ".ico", ".png", ".jpg",
    ".jpeg", ".gif", ".svg", ".mp4", ".mp3", ".wav", ".zip",
    ".tar", ".gz", ".rar", ".7z", ".pdf", ".exe", ".dll",
    ".so", ".dylib", ".o", ".a", ".class", ".jar", ".war",
    ".pyc", ".pyo", ".obj", ".bin", ".dat", ".db", ".sqlite",
}


def get_parsers():
    return [
        PythonParser(),
        PhpParser(),
        TypeScriptParser(),
        GoParser(),
        RustParser(),
        CSharpParser(),
    ]


def _should_ignore(path: Path) -> bool:
    parts = path.parts
    for part in parts:
        if part.lower() in IGNORE_DIRS:
            return True
        if part.startswith(".") and part not in (".env.example",):
            return True

    if path.suffix.lower() in IGNORE_EXTENSIONS:
        return True

    name = path.name.lower()
    if name.startswith(".") and name not in (".env.example",):
        return True

    return False


def _get_parser_for_file(path: Path, parsers) -> Optional[object]:
    for p in parsers:
        if p.can_parse(path):
            return p
    return None


def scan_project(
    root_path: str | Path,
    max_workers: int = 4,
    incremental_cache: Optional[Path] = None,
) -> ProjectIndex:
    root = Path(root_path).resolve()

    if not root.exists():
        raise FileNotFoundError(f"Path does not exist: {root}")

    parsers = get_parsers()
    files_to_parse: list[tuple[Path, object]] = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if _should_ignore(path.relative_to(root)):
            continue
        parser = _get_parser_for_file(path, parsers)
        if parser:
            files_to_parse.append((path, parser))

    if not files_to_parse:
        return ProjectIndex(
            root_path=str(root),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    summaries: list[FileSummary] = []

    for path, parser in files_to_parse:
        try:
            result = parser.parse(path, root)
            summaries.append(result)
        except Exception as e:
            print(f"Warning: failed to parse {path}: {e}")

    summaries.sort(key=lambda s: s.file_path)

    index = ProjectIndex(
        root_path=str(root),
        files=summaries,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    index.dependencies = resolve_dependencies(index)
    index.architecture = detect_architecture(index, index.dependencies)
    index.entry_points = index.architecture.get("entry_points", [])

    _extract_laravel_specifics(index, root)

    return index


def _extract_laravel_specifics(index: ProjectIndex, root: Path):
    routes_dirs = [
        root / "routes",
        root / "app" / "routes",
    ]
    for rd in routes_dirs:
        if rd.is_dir():
            index.routes = extract_routes(rd, root)
            break

    model_files = [
        f for f in index.files
        if any(n.node_type == NodeType.MODEL for n in f.nodes)
    ]
    if model_files:
        index.model_relations = extract_model_relations(model_files, root)

    migration_dirs = [
        root / "database" / "migrations",
        root / "app" / "database" / "migrations",
    ]
    for md in migration_dirs:
        if md.is_dir():
            index.migrations = extract_migrations(md, root)
            break

    index.risks = detect_risks(index)

    if index.routes:
        index.traces = build_traces(index, root)
        index.role_map = build_role_map(index)


def write_outputs(index: ProjectIndex, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "SUMMARY.md"
    json_path = output_dir / "context.json"
    md_path = output_dir / "CONTEXT.md"
    graph_path = output_dir / "deps.json"

    summary_content = generate_summary(index)
    summary_path.write_text(summary_content, encoding="utf-8")

    json_data = generate_json_index(index)
    json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    md_content = generate_markdown(index)
    md_path.write_text(md_content, encoding="utf-8")

    deps_data = {
        "edges": [
            {"from": d.source_file, "to": d.target_file, "type": d.import_type}
            for d in index.dependencies
        ],
        "circular": find_circular_dependencies(index.dependencies),
    }
    graph_path.write_text(json.dumps(deps_data, indent=2, ensure_ascii=False), encoding="utf-8")

    summary_tokens = len(summary_content) // 4

    return {
        "summary": str(summary_path),
        "json": str(json_path),
        "markdown": str(md_path),
        "deps": str(graph_path),
        "summary_tokens": summary_tokens,
        "total_files": len(index.files),
        "total_loc": sum(f.lines_of_code for f in index.files),
        "total_symbols": sum(len(f.nodes) for f in index.files),
        "total_routes": len(index.routes),
        "total_relations": len(index.model_relations),
        "total_tables": len(index.migrations),
        "total_risks": len(index.risks),
        "total_traces": len(index.traces),
        "circular_deps": len(deps_data.get("circular", [])),
    }
