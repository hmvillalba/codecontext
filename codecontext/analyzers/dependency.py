"""Dependency analyzer - builds import/dependency graph between files."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from codecontext.models import DependencyEdge, FileSummary, ProjectIndex


def resolve_dependencies(index: ProjectIndex) -> list[DependencyEdge]:
    file_map: dict[str, FileSummary] = {f.file_path: f for f in index.files}
    dir_files: dict[str, set[str]] = defaultdict(set)
    for f in index.files:
        parent = str(Path(f.file_path).parent)
        dir_files[parent].add(Path(f.file_path).stem)
        dir_files[parent].add(Path(f.file_path).name)

    edges: list[DependencyEdge] = []
    for f in index.files:
        for imp in f.imports:
            targets = _resolve_import(imp, f.file_path, file_map, dir_files)
            for target in targets:
                if target != f.file_path:
                    edges.append(DependencyEdge(
                        source_file=f.file_path,
                        target_file=target,
                        import_type="import",
                        symbols=[],
                    ))

    return edges


def _resolve_import(
    imp: str,
    source_file: str,
    file_map: dict[str, FileSummary],
    dir_files: dict[str, set[str]],
) -> list[str]:
    targets: list[str] = []
    clean = imp.strip()

    if source_file.endswith(".py"):
        targets.extend(_resolve_python_import(clean, source_file, file_map))
    elif source_file.endswith((".ts", ".tsx", ".js", ".jsx")):
        targets.extend(_resolve_ts_import(clean, source_file, file_map))
    elif source_file.endswith(".go"):
        targets.extend(_resolve_go_import(clean, source_file, file_map))
    elif source_file.endswith(".rs"):
        targets.extend(_resolve_rust_import(clean, source_file, file_map))
    elif source_file.endswith(".php"):
        targets.extend(_resolve_php_import(clean, source_file, file_map))

    return targets


def _resolve_python_import(imp: str, source: str, file_map: dict) -> list[str]:
    parts = imp.split(",")
    results = []
    for part in parts:
        module = part.strip().split(" as ")[0].strip()
        if module.startswith("."):
            continue
        candidates = [
            module.replace(".", "/") + ".py",
            module.replace(".", "/") + "/__init__.py",
            module.replace(".", "/") + "/index.py",
        ]
        for c in candidates:
            if c in file_map:
                results.append(c)
                break
    return results


def _resolve_ts_import(imp: str, source: str, file_map: dict) -> list[str]:
    match = re.search(r"""from\s+['"](.+?)['"]|import\s+['"](.+?)['"]|require\s*\(\s*['"](.+?)['"]\s*\)""", imp)
    if not match:
        return []
    module = match.group(1) or match.group(2) or match.group(3)
    if module.startswith("."):
        source_dir = str(Path(source).parent)
        rel = Path(source_dir) / module
        candidates = [
            str(rel) + ".ts",
            str(rel) + ".tsx",
            str(rel) + ".js",
            str(rel) + "/index.ts",
            str(rel) + "/index.tsx",
            str(rel) + "/index.js",
        ]
        for c in candidates:
            c_clean = c.replace("\\", "/")
            if c_clean in file_map:
                return [c_clean]
    return []


def _resolve_go_import(imp: str, source: str, file_map: dict) -> list[str]:
    match = re.search(r'"(.+?)"', imp)
    if not match:
        return []
    pkg = match.group(1)
    results = []
    for fp in file_map:
        if fp.endswith(".go") and fp.replace("\\", "/").endswith(pkg.split("/")[-1] + "/"):
            continue
        fp_dir = str(Path(fp).parent).replace("\\", "/")
        if fp_dir.endswith(pkg.split("/")[-1]):
            results.append(fp)
    return results[:5]


def _resolve_rust_import(imp: str, source: str, file_map: dict) -> list[str]:
    return []


def _resolve_php_import(imp: str, source: str, file_map: dict) -> list[str]:
    if "use " not in imp and "namespace " not in imp:
        return []
    clean = imp.replace("use ", "").replace("namespace ", "").strip().rstrip(";")
    parts = clean.replace("\\", "/").split("/")
    if len(parts) < 2:
        return []
    class_name = parts[-1]
    results = []
    for fp in file_map:
        stem = Path(fp).stem
        if stem == class_name:
            results.append(fp)
    return results


def find_circular_dependencies(edges: list[DependencyEdge]) -> list[list[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        graph[e.source_file].add(e.target_file)

    cycles: list[list[str]] = []
    visited: set[str] = set()
    rec_stack: set[str] = set()
    path: list[str] = []

    def dfs(node: str):
        visited.add(node)
        rec_stack.add(node)
        path.append(node)
        for neighbor in graph[node]:
            if neighbor not in visited:
                dfs(neighbor)
            elif neighbor in rec_stack:
                idx = path.index(neighbor)
                cycle = path[idx:] + [neighbor]
                cycles.append(cycle)
        path.pop()
        rec_stack.discard(node)

    for node in list(graph.keys()):
        if node not in visited:
            dfs(node)

    return cycles
