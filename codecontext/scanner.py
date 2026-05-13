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
from codecontext.analyzers.traceability import build_traces, build_role_map
from codecontext.analyzers.blade_views import extract_blade_views
from codecontext.analyzers.observers import extract_observers, extract_events
from codecontext.analyzers.csharp_extractors import (
    extract_ef_schema, extract_ef_relations, extract_di_registrations,
    extract_mvvm_views, extract_cs_routes,
)
from codecontext.analyzers.go_extractors import (
    extract_go_routes, extract_go_middleware, extract_go_schema,
)
from codecontext.analyzers.python_extractors import (
    extract_python_routes, extract_python_models,
)
from codecontext.rules.engine import load_rules, evaluate_custom_rules
from codecontext.generators import generate_json_index, generate_compact_json_string
from codecontext.generators.markdown import generate_markdown
from codecontext.generators.summary import generate_summary
from codecontext.generators.issues import generate_issues_json
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


def _iter_files_safe(root: Path):
    """Iterate all files under root, skipping inaccessible directories."""
    visited = set()
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            real = current.resolve()
        except (PermissionError, OSError):
            continue
        if real in visited:
            continue
        visited.add(real)
        try:
            entries = list(current.iterdir())
        except (PermissionError, OSError):
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry)
                elif entry.is_file():
                    yield entry
            except (PermissionError, OSError):
                continue


def scan_project(
    root_path: str | Path,
    max_workers: int = 4,
    incremental_cache: Optional[Path] = None,
    rules_path: Optional[str] = None,
) -> ProjectIndex:
    root = Path(root_path).resolve()

    if not root.exists():
        raise FileNotFoundError(f"Path does not exist: {root}")

    parsers = get_parsers()
    skipped_errors: list[str] = []

    files_to_parse: list[tuple[Path, object]] = []
    for path in _iter_files_safe(root):
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if _should_ignore(rel):
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
        except (PermissionError, OSError) as e:
            msg = f"Warning: cannot access {path}: {e}"
            print(msg)
            skipped_errors.append(msg)
        except Exception as e:
            msg = f"Warning: failed to parse {path}: {e}"
            print(msg)
            skipped_errors.append(msg)

    summaries.sort(key=lambda s: s.file_path)

    index = ProjectIndex(
        root_path=str(root),
        files=summaries,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    try:
        index.dependencies = resolve_dependencies(index)
    except Exception as e:
        print(f"Warning: dependency resolution failed: {e}")

    try:
        index.architecture = detect_architecture(index, index.dependencies)
    except Exception as e:
        print(f"Warning: architecture detection failed: {e}")

    index.entry_points = index.architecture.get("entry_points", [])

    try:
        _extract_framework_specifics(index, root, rules_path)
    except Exception as e:
        print(f"Warning: framework extraction failed: {e}")

    return index


def _extract_framework_specifics(index: ProjectIndex, root: Path, rules_path: Optional[str] = None):
    lang_dist: dict[str, int] = {}
    for f in index.files:
        lang_dist[f.language.value] = lang_dist.get(f.language.value, 0) + 1
    primary = max(lang_dist, key=lang_dist.get) if lang_dist else "unknown"

    if primary == "php":
        _extract_laravel_specifics(index, root, rules_path)
    elif primary == "csharp":
        _extract_csharp_specifics(index, root, rules_path)
    elif primary == "go":
        _extract_go_specifics(index, root, rules_path)
    elif primary == "python":
        _extract_python_specifics(index, root, rules_path)
    else:
        _apply_risks_and_rules(index, root, rules_path)


def _apply_risks_and_rules(index: ProjectIndex, root: Path, rules_path: Optional[str] = None):
    from codecontext.analyzers.risks import detect_risks
    from codecontext.analyzers.gaps import detect_gaps

    try:
        index.risks = detect_risks(index)
        index.risks.extend(detect_gaps(index))
    except Exception as e:
        print(f"Warning: risk detection failed: {e}")

    try:
        custom_rules = load_rules(rules_path)
        if custom_rules:
            index.risks.extend(evaluate_custom_rules(index, custom_rules))
    except Exception as e:
        print(f"Warning: custom rules evaluation failed: {e}")


def _safe_extract(fn, *args, default=None, label=""):
    try:
        return fn(*args)
    except Exception as e:
        print(f"Warning: {label or fn.__name__} failed: {e}")
        return default


def _extract_csharp_specifics(index: ProjectIndex, root: Path, rules_path: Optional[str] = None):
    index.migrations = _safe_extract(extract_ef_schema, index, default=[], label="ef_schema")
    index.model_relations = _safe_extract(extract_ef_relations, index, default=[], label="ef_relations")
    index.di_registrations = _safe_extract(extract_di_registrations, index, default=[], label="di_registrations")
    index.view_mappings = _safe_extract(extract_mvvm_views, root, default=[], label="mvvm_views")
    index.routes = _safe_extract(extract_cs_routes, index, default=[], label="cs_routes")

    _apply_risks_and_rules(index, root, rules_path)


def _extract_go_specifics(index: ProjectIndex, root: Path, rules_path: Optional[str] = None):
    index.routes = _safe_extract(extract_go_routes, index, root, default=[], label="go_routes")
    index.migrations = _safe_extract(extract_go_schema, index, root, default=[], label="go_schema")
    mw = _safe_extract(extract_go_middleware, index, root, default=[], label="go_middleware")
    if mw:
        index.architecture["middleware"] = mw

    _apply_risks_and_rules(index, root, rules_path)


def _extract_python_specifics(index: ProjectIndex, root: Path, rules_path: Optional[str] = None):
    index.routes = _safe_extract(extract_python_routes, index, root, default=[], label="python_routes")
    index.migrations = _safe_extract(extract_python_models, index, root, default=[], label="python_models")

    _apply_risks_and_rules(index, root, rules_path)


def _extract_laravel_specifics(index: ProjectIndex, root: Path, rules_path: Optional[str] = None):
    routes_dirs = [
        root / "routes",
        root / "app" / "routes",
    ]
    for rd in routes_dirs:
        if rd.is_dir():
            index.routes = _safe_extract(extract_routes, rd, root, default=[], label="routes")
            break

    model_files = [
        f for f in index.files
        if any(n.node_type == NodeType.MODEL for n in f.nodes)
    ]
    if model_files:
        index.model_relations = _safe_extract(extract_model_relations, model_files, root, default=[], label="model_relations")

    migration_dirs = [
        root / "database" / "migrations",
        root / "app" / "database" / "migrations",
    ]
    for md in migration_dirs:
        if md.is_dir():
            index.migrations = _safe_extract(extract_migrations, md, root, default=[], label="migrations")
            break

    _apply_risks_and_rules(index, root, rules_path)

    if index.routes:
        index.traces = _safe_extract(build_traces, index, root, default=[], label="traces")
        index.role_map = _safe_extract(build_role_map, index, default={}, label="role_map")

    index.blade_views = _safe_extract(extract_blade_views, root, default=[], label="blade_views")
    index.observers = _safe_extract(extract_observers, root, index.files, default=[], label="observers")
    index.events = _safe_extract(extract_events, root, default=[], label="events")


def write_outputs(index: ProjectIndex, output_dir: Path, fail_on: str = "high") -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "SUMMARY.md"
    json_path = output_dir / "context.json"
    md_path = output_dir / "CONTEXT.md"
    graph_path = output_dir / "deps.json"
    issues_path = output_dir / "issues.json"

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

    ci_result = generate_issues_json(index, issues_path, fail_on=fail_on)

    summary_tokens = len(summary_content) // 4

    return {
        "summary": str(summary_path),
        "json": str(json_path),
        "markdown": str(md_path),
        "deps": str(graph_path),
        "issues": str(issues_path),
        "summary_tokens": summary_tokens,
        "total_files": len(index.files),
        "total_loc": sum(f.lines_of_code for f in index.files),
        "total_symbols": sum(len(f.nodes) for f in index.files),
        "total_routes": len(index.routes),
        "total_relations": len(index.model_relations),
        "total_tables": len(index.migrations),
        "total_risks": len(index.risks),
        "total_traces": len(index.traces),
        "total_blade_views": len(index.blade_views),
        "total_observers": len(index.observers),
        "total_events": len(index.events),
        "total_di": len(index.di_registrations),
        "total_view_mappings": len(index.view_mappings),
        "ci_blocking": ci_result["blocking_issues"],
        "ci_should_fail": ci_result["should_fail"],
        "circular_deps": len(deps_data.get("circular", [])),
    }
