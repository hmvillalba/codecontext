"""Traceability builder - route to model chains and permission maps."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from codecontext.models import (
    CodeNode,
    FileSummary,
    NodeType,
    ProjectIndex,
    RouteEntry,
    TraceChain,
)


def build_traces(index: ProjectIndex, root: Path) -> list[TraceChain]:
    traces: list[TraceChain] = []

    file_map: dict[str, FileSummary] = {f.file_path: f for f in index.files}
    class_map: dict[str, tuple[FileSummary, CodeNode]] = {}
    for f in index.files:
        for node in f.nodes:
            key = f"{f.file_path}::{node.name}"
            class_map[node.name.lower()] = (f, node)
            class_map[key.lower()] = (f, node)

    for route in index.routes:
        if route.method in ("anonymous", "_render") or route.controller in ("Closure", "view"):
            continue

        ctrl_short = route.controller.split("\\")[-1] if "\\" in route.controller else route.controller
        ctrl_short = ctrl_short.replace("::class", "")

        chain = [f"{route.http_method} {route.uri}"]

        if route.method == "__invoke":
            chain.append(f"Livewire:{ctrl_short}")
            entry = _find_class_node(ctrl_short, class_map)
            if entry:
                chain.extend(_trace_calls(entry[1], class_map, depth=3))
        else:
            chain.append(f"Controller:{ctrl_short}@{route.method}")
            entry = _find_class_node(ctrl_short, class_map)
            if entry:
                method_calls = _find_method_calls(entry[1], route.method, class_map)
                chain.extend(method_calls)

        roles, permissions = _extract_role_permissions(route)

        traces.append(TraceChain(
            route_uri=route.uri,
            route_method=route.http_method,
            chain=chain[:8],
            middleware=route.middleware[:5],
            roles=roles,
            permissions=permissions,
        ))

    return traces


def build_role_map(index: ProjectIndex) -> dict:
    role_map: dict[str, list[dict]] = defaultdict(list)

    for route in index.routes:
        roles, permissions = _extract_role_permissions(route)
        if roles or permissions:
            ctrl = route.controller.split("\\")[-1] if "\\" in route.controller else route.controller
            for role in roles:
                role_map[role].append({
                    "uri": route.uri,
                    "method": route.http_method,
                    "controller": f"{ctrl}@{route.method}" if route.method != "__invoke" else ctrl,
                })

    return dict(role_map)


def _find_class_node(name: str, class_map: dict) -> tuple | None:
    for key in (name.lower(), f"::{name.lower()}"):
        if key in class_map:
            return class_map[key]
    for key, val in class_map.items():
        if key.endswith(f"::{name.lower()}"):
            return val
    return None


def _trace_calls(node: CodeNode, class_map: dict, depth: int = 3) -> list[str]:
    if depth <= 0:
        return []

    chain: list[str] = []
    seen: set[str] = set()

    for call in node.calls[:10]:
        if call in seen:
            continue
        seen.add(call)

        entry = _find_class_node(call, class_map)
        if entry:
            f, n = entry
            layer = _classify_node(n)
            if layer:
                chain.append(f"{layer}:{call}")
                if depth > 1:
                    chain.extend(_trace_calls(n, class_map, depth - 1)[:3])

    return chain[:5]


def _find_method_calls(class_node: CodeNode, method_name: str, class_map: dict) -> list[str]:
    chain: list[str] = []
    calls = class_node.calls or []

    seen = set()
    for call in calls[:15]:
        if call in seen:
            continue
        seen.add(call)

        entry = _find_class_node(call, class_map)
        if entry:
            f, n = entry
            layer = _classify_node(n)
            if layer:
                chain.append(f"{layer}:{call}")

    if not chain:
        for call in calls[:10]:
            if call[0].isupper() and call not in seen:
                chain.append(f"Service:{call}")

    return chain[:5]


def _classify_node(node: CodeNode) -> str | None:
    type_map = {
        NodeType.CONTROLLER: "Controller",
        NodeType.SERVICE: "Service",
        NodeType.MODEL: "Model",
        NodeType.REPOSITORY: "Repository",
        NodeType.MIDDLEWARE: "Middleware",
        NodeType.POLICY: "Policy",
        NodeType.EVENT: "Event",
        NodeType.LISTENER: "Listener",
        NodeType.JOB: "Job",
    }
    return type_map.get(node.node_type)


def _extract_role_permissions(route: RouteEntry) -> tuple[list[str], list[str]]:
    roles: list[str] = []
    permissions: list[str] = []

    for mw in route.middleware:
        role_match = re.search(r"role:(.+?)(?:\||$)", mw)
        if not role_match:
            role_match = re.search(r"role_or_permission:(.+?)(?:\||$)", mw)
        if role_match:
            raw = mw.split(":", 1)[1] if ":" in mw else ""
            for part in raw.split("|"):
                part = part.strip()
                if part and part[0].isupper():
                    roles.append(part)

        perm_match = re.search(r"permission:([\w.]+)", mw)
        if perm_match:
            permissions.append(perm_match.group(1))

    return roles, permissions
