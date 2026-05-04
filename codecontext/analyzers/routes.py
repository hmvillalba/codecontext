"""Laravel route extractor - maps URLs to controllers and Livewire components."""

from __future__ import annotations

import re
from pathlib import Path

from codecontext.models import RouteEntry


RELATION_TYPES = {
    "hasOne", "hasMany", "belongsTo", "belongsToMany",
    "morphOne", "morphMany", "morphTo", "morphToMany", "morphedByMany",
    "hasManyThrough", "hasOneThrough",
}


def extract_routes(routes_dir: Path, root: Path) -> list[RouteEntry]:
    routes: list[RouteEntry] = []
    route_files = list(routes_dir.glob("*.php"))

    for rf in route_files:
        source = rf.read_text(encoding="utf-8", errors="replace")
        rel_path = str(rf.relative_to(root)).replace("\\", "/")
        file_routes = _parse_route_file(source, rel_path)
        routes.extend(file_routes)

    return routes


def _parse_route_file(source: str, file_path: str) -> list[RouteEntry]:
    routes: list[RouteEntry] = []
    use_map = _extract_use_map(source)

    middleware_stack: list[str] = []
    prefix_stack: list[str] = []

    lines = source.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if not line or line.startswith("//") or line.startswith("/*") or line.startswith("*"):
            i += 1
            continue

        if "Route::middleware(" in line:
            mw = _extract_middleware_from_line(line)
            middleware_stack.append(mw)

        if "Route::prefix(" in line:
            pf = _extract_string_arg(line, "prefix")
            if pf:
                prefix_stack.append(pf)

        route = _try_parse_route(line, file_path, use_map, middleware_stack, prefix_stack)
        if route:
            routes.append(route)

        i += 1

    return routes


def _extract_use_map(source: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for match in re.finditer(r"use\s+([\w\\]+)\s+as\s+(\w+)", source):
        mapping[match.group(2)] = match.group(1)
    for match in re.finditer(r"use\s+([\w\\]+)", source):
        fqn = match.group(1)
        short = fqn.split("\\")[-1]
        mapping[short] = fqn
    return mapping


def _extract_middleware_from_line(line: str) -> str:
    match = re.search(r"middleware\s*\(\s*\[([^\]]*)\]", line)
    if match:
        return match.group(1).strip().strip("'\"")
    match = re.search(r"middleware\s*\(\s*['\"](\w+)['\"]", line)
    if match:
        return match.group(1)
    return ""


def _extract_string_arg(line: str, func_name: str) -> str | None:
    match = re.search(rf"{func_name}\s*\(\s*['\"]([^'\"]+)['\"]", line)
    return match.group(1) if match else None


def _try_parse_route(
    line: str,
    file_path: str,
    use_map: dict[str, str],
    middleware_stack: list[str],
    prefix_stack: list[str],
) -> RouteEntry | None:
    method_match = re.search(
        r"Route::(get|post|put|patch|delete|options|any)\s*\(\s*['\"](/[^'\"]*)['\"]",
        line,
    )
    if not method_match:
        return None

    http_method = method_match.group(1).upper()
    uri = method_match.group(2)

    prefix = "/".join(p for p in prefix_stack if p)
    if prefix:
        uri = f"/{prefix}{uri}"
    uri = re.sub(r"/+", "/", uri)

    controller = ""
    method = ""
    name = None

    name_match = re.search(r"->name\s*\(\s*['\"]([^'\"]+)['\"]", line)
    if name_match:
        name = name_match.group(1)

    array_match = re.search(
        r"\[\s*(\w+)::class\s*,\s*['\"](\w+)['\"]\s*\]", line
    )
    if array_match:
        ctrl_short = array_match.group(1)
        method = array_match.group(2)
        controller = use_map.get(ctrl_short, ctrl_short)
    else:
        livewire_match = re.search(r"(\w+)::class\s*\)", line)
        if livewire_match:
            lw_short = livewire_match.group(1)
            controller = use_map.get(lw_short, lw_short)
            method = "__invoke"
        else:
            view_match = re.search(r"Route::view\s*\(", line)
            if view_match:
                controller = "view"
                method = "_render"

    if not controller and "function ()" in line:
        controller = "Closure"
        method = "anonymous"

    mw = []
    for m in middleware_stack:
        if m:
            mw.extend(x.strip().strip("'\"") for x in m.split(",") if x.strip())

    inline_mw = re.findall(r"middleware\s*\(\s*['\"]([^'\"]+)['\"]", line)
    mw.extend(inline_mw)

    return RouteEntry(
        http_method=http_method,
        uri=uri,
        controller=controller,
        method=method,
        name=name,
        middleware=mw,
        file_path=file_path,
    )
