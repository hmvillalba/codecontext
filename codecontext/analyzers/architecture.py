"""Architecture pattern detector."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from codecontext.models import (
    DependencyEdge,
    FileSummary,
    Language,
    NodeType,
    ProjectIndex,
)


def detect_architecture(index: ProjectIndex, edges: list[DependencyEdge]) -> dict:
    arch: dict = {
        "pattern": "unknown",
        "layers": {},
        "entry_points": [],
        "modules": {},
        "stats": {},
    }

    if not index.files:
        return arch

    lang_dist: dict[str, int] = defaultdict(int)
    type_dist: dict[str, int] = defaultdict(int)
    for f in index.files:
        lang_dist[f.language.value] += 1
        for n in f.nodes:
            type_dist[n.node_type.value] += 1

    arch["stats"]["total_files"] = len(index.files)
    arch["stats"]["total_nodes"] = sum(len(f.nodes) for f in index.files)
    arch["stats"]["total_loc"] = sum(f.lines_of_code for f in index.files)
    arch["stats"]["languages"] = dict(lang_dist)
    arch["stats"]["node_types"] = dict(type_dist)

    primary_lang = max(lang_dist, key=lang_dist.get) if lang_dist else "unknown"

    if primary_lang == "php":
        arch.update(_detect_laravel(index, edges))
    elif primary_lang in ("typescript", "javascript"):
        arch.update(_detect_nextjs_react(index, edges))
    elif primary_lang == "python":
        arch.update(_detect_python_framework(index, edges))
    elif primary_lang == "go":
        arch.update(_detect_go_layout(index, edges))
    elif primary_lang == "rust":
        arch.update(_detect_rust_layout(index, edges))
    elif primary_lang == "csharp":
        arch.update(_detect_dotnet(index, edges))

    dirs = _group_by_directory(index.files)
    arch["modules"] = {d: {"files": len(fs), "loc": sum(f.lines_of_code for f in fs)} for d, fs in dirs.items()}

    return arch


def _group_by_directory(files: list[FileSummary]) -> dict[str, list[FileSummary]]:
    groups: dict[str, list[FileSummary]] = defaultdict(list)
    for f in files:
        parent = str(Path(f.file_path).parent)
        groups[parent].append(f)
    return groups


def _detect_laravel(index: ProjectIndex, edges: list[DependencyEdge]) -> dict:
    result = {"pattern": "laravel", "layers": {}, "entry_points": []}

    laravel_layers = {
        "Controllers": ["controller"],
        "Models": ["model"],
        "Views": ["view"],
        "Routes": ["route"],
        "Middleware": ["middleware"],
        "Services": ["service"],
        "Repositories": ["repository"],
        "Migrations": ["migration"],
        "Requests": ["request"],
        "Resources": ["resource"],
        "Policies": ["policy"],
        "Events": ["event"],
        "Listeners": ["listener"],
        "Jobs": ["job"],
        "Commands": ["command"],
        "Providers": ["provider"],
        "Config": ["config"],
        "Tests": ["test"],
    }

    type_counts: dict[str, int] = defaultdict(int)
    for f in index.files:
        for n in f.nodes:
            type_counts[n.node_type.value] += 1

    for layer_name, types in laravel_layers.items():
        count = sum(type_counts.get(t, 0) for t in types)
        if count > 0:
            result["layers"][layer_name] = {
                "count": count,
                "types": types,
            }

    route_files = [f.file_path for f in index.files if "/routes/" in f.file_path.replace("\\", "/").lower()]
    result["entry_points"] = route_files

    return result


def _detect_nextjs_react(index: ProjectIndex, edges: list[DependencyEdge]) -> dict:
    result = {"pattern": "unknown", "layers": {}, "entry_points": []}

    has_app_dir = any("/app/" in f.file_path.replace("\\", "/") for f in index.files)
    has_pages_dir = any("/pages/" in f.file_path.replace("\\", "/") for f in index.files)
    has_components = any("/components/" in f.file_path.replace("\\", "/") for f in index.files)
    has_api = any("/api/" in f.file_path.replace("\\", "/") for f in index.files)

    if has_app_dir or has_pages_dir:
        result["pattern"] = "next.js"
        if has_app_dir:
            result["layers"]["app_router"] = {"description": "Next.js App Router"}
        if has_pages_dir:
            result["layers"]["pages_router"] = {"description": "Next.js Pages Router"}
    elif has_components:
        result["pattern"] = "react"
    else:
        result["pattern"] = "javascript/typescript"

    if has_components:
        result["layers"]["components"] = {
            "count": sum(1 for f in index.files if "/components/" in f.file_path.replace("\\", "/"))
        }

    if has_api:
        result["layers"]["api_routes"] = {
            "count": sum(1 for f in index.files if "/api/" in f.file_path.replace("\\", "/"))
        }

    result["entry_points"] = [
        f.file_path for f in index.files
        if f.file_path.replace("\\", "/").endswith(("page.tsx", "page.ts", "layout.tsx", "layout.ts", "index.ts", "index.tsx"))
        or "main.ts" in f.file_path or "main.tsx" in f.file_path or "App.tsx" in f.file_path
    ]

    return result


def _detect_python_framework(index: ProjectIndex, edges: list[DependencyEdge]) -> dict:
    result = {"pattern": "python", "layers": {}, "entry_points": []}

    has_django = any("django" in imp.lower() or "from django" in imp.lower() for f in index.files for imp in f.imports)
    has_fastapi = any("fastapi" in imp.lower() for f in index.files for imp in f.imports)
    has_flask = any("flask" in imp.lower() for f in index.files for imp in f.imports)

    if has_django:
        result["pattern"] = "django"
    elif has_fastapi:
        result["pattern"] = "fastapi"
    elif has_flask:
        result["pattern"] = "flask"

    for f in index.files:
        if "manage.py" in f.file_path or "wsgi.py" in f.file_path or "asgi.py" in f.file_path or "main.py" in f.file_path or "app.py" in f.file_path:
            result["entry_points"].append(f.file_path)

    dirs = _group_by_directory(index.files)
    for d, fs in dirs.items():
        result["layers"][d] = {"files": len(fs), "loc": sum(f.lines_of_code for f in fs)}

    return result


def _detect_go_layout(index: ProjectIndex, edges: list[DependencyEdge]) -> dict:
    result = {"pattern": "go", "layers": {}, "entry_points": []}

    has_cmd = any("/cmd/" in f.file_path.replace("\\", "/") for f in index.files)
    has_internal = any("/internal/" in f.file_path.replace("\\", "/") for f in index.files)
    has_pkg = any("/pkg/" in f.file_path.replace("\\", "/") for f in index.files)

    if has_cmd and has_internal:
        result["pattern"] = "go-standard-layout"

    result["entry_points"] = [
        f.file_path for f in index.files
        if f.file_path.replace("\\", "/").endswith("main.go") or "cmd/" in f.file_path.replace("\\", "/")
    ]

    return result


def _detect_rust_layout(index: ProjectIndex, edges: list[DependencyEdge]) -> dict:
    result = {"pattern": "rust", "layers": {}, "entry_points": []}

    has_bin = any("/bin/" in f.file_path.replace("\\", "/") for f in index.files)
    has_lib = any("/lib/" in f.file_path.replace("\\", "/") or f.file_path.replace("\\", "/").endswith("lib.rs") for f in index.files)

    if has_lib:
        result["layers"]["lib"] = {"description": "Library crate"}
    if has_bin:
        result["layers"]["bin"] = {"description": "Binary targets"}

    result["entry_points"] = [
        f.file_path for f in index.files
        if f.file_path.replace("\\", "/").endswith("main.rs") or f.file_path.replace("\\", "/").endswith("lib.rs")
    ]

    return result


def _detect_dotnet(index: ProjectIndex, edges: list[DependencyEdge]) -> dict:
    result = {"pattern": ".net", "layers": {}, "entry_points": []}

    has_avalonia = any("Avalonia" in imp for f in index.files for imp in f.imports)
    has_ef = any("EntityFramework" in imp or "Microsoft.EntityFrameworkCore" in imp for f in index.files for imp in f.imports)

    if has_avalonia:
        result["pattern"] = "avalonia-ui"
    if has_ef:
        result["pattern"] += "+ef-core"

    project_dirs: dict[str, list] = defaultdict(list)
    for f in index.files:
        parts = f.file_path.replace("\\", "/").split("/")
        if len(parts) > 1:
            project_dirs[parts[0]].append(f)

    for proj_name, files in project_dirs.items():
        if any(f.file_path.endswith(".csproj") for f in files):
            loc = sum(f.lines_of_code for f in files)
            node_count = sum(len(f.nodes) for f in files)
            result["layers"][proj_name] = {"files": len(files), "loc": loc, "symbols": node_count}

    result["entry_points"] = [
        f.file_path for f in index.files
        if f.file_path.replace("\\", "/").endswith("Program.cs")
    ]

    return result
