"""Compact JSON index generator for AI agent consumption."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from codecontext.models import ProjectIndex


def generate_json_index(index: ProjectIndex, max_output_tokens: int = 8000) -> dict:
    compact = {
        "meta": {
            "root": index.root_path,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_files": len(index.files),
            "total_loc": sum(f.lines_of_code for f in index.files),
            "total_nodes": sum(len(f.nodes) for f in index.files),
            "architecture": index.architecture.get("pattern", "unknown"),
        },
        "structure": _build_structure(index),
        "entry_points": index.entry_points,
        "dependencies": _build_dep_summary(index),
        "modules": index.architecture.get("modules", {}),
    }

    if index.architecture.get("layers"):
        compact["layers"] = index.architecture["layers"]

    if index.routes:
        compact["routes"] = _build_routes(index)

    if index.model_relations:
        compact["model_relations"] = _build_model_relations(index)

    if index.migrations:
        compact["database_schema"] = _build_schema(index)

    if index.blade_views:
        compact["blade_views"] = _build_blade_views(index)

    if index.observers:
        compact["observers"] = _build_observers(index)

    if index.events:
        compact["events"] = _build_events(index)

    return compact


def generate_compact_json_string(index: ProjectIndex, indent: int = 2) -> str:
    data = generate_json_index(index)
    return json.dumps(data, indent=indent, ensure_ascii=False, default=str)


def _build_structure(index: ProjectIndex) -> dict:
    structure: dict = {}

    for f in index.files:
        rel = f.file_path
        parts = rel.replace("\\", "/").split("/")
        current = structure

        for part in parts[:-1]:
            if part not in current:
                current[part] = {"_files": []}
            elif "_files" not in current[part]:
                current[part]["_files"] = []
            current = current[part]

        file_info = {
            "lang": f.language.value,
            "loc": f.lines_of_code,
        }

        nodes_summary = _summarize_nodes(f)
        if nodes_summary:
            file_info["nodes"] = nodes_summary

        if f.exports:
            file_info["exports"] = f.exports[:10]

        parent = structure
        for part in parts[:-1]:
            parent = parent[part]
        if "_files" not in parent:
            parent["_files"] = []
        parent["_files"].append({parts[-1]: file_info})

    return structure


def _summarize_nodes(f) -> list[dict]:
    summaries = []
    for node in f.nodes:
        s: dict = {
            "name": node.name,
            "type": node.node_type.value,
        }
        if node.visibility.value != "public":
            s["vis"] = node.visibility.value[:3]
        if node.parameters:
            params = []
            for p in node.parameters:
                ps = p.name
                if p.type_hint:
                    ps += f": {p.type_hint}"
                params.append(ps)
            s["params"] = params
        if node.return_type:
            s["returns"] = node.return_type
        if node.inherits_from:
            s["extends"] = node.inherits_from
        if node.implements:
            s["implements"] = node.implements
        if node.decorators:
            s["decorators"] = node.decorators[:5]
        if node.meta.get("methods"):
            s["methods"] = node.meta["methods"][:20]
        s["line"] = node.line_start
        summaries.append(s)
    return summaries


def _build_dep_summary(index: ProjectIndex) -> dict:
    dep_count: dict[str, int] = {}
    for dep in index.dependencies:
        dep_count[dep.source_file] = dep_count.get(dep.source_file, 0) + 1

    if not dep_count:
        return {}

    sorted_deps = sorted(dep_count.items(), key=lambda x: x[1], reverse=True)
    return {
        "most_connected": sorted_deps[:10],
        "total_edges": len(index.dependencies),
    }


def _build_routes(index: ProjectIndex) -> list[dict]:
    return [
        {
            "method": r.http_method,
            "uri": r.uri,
            "controller": r.controller,
            "action": r.method,
            "name": r.name,
            "middleware": r.middleware[:5] if r.middleware else [],
        }
        for r in index.routes
    ]


def _build_model_relations(index: ProjectIndex) -> list[dict]:
    return [
        {
            "model": r.model_class,
            "relation": f"{r.relation_name} ({r.relation_type})",
            "related": r.related_class,
        }
        for r in index.model_relations
    ]


def _build_schema(index: ProjectIndex) -> list[dict]:
    tables = []
    for t in index.migrations:
        cols = []
        for c in t.columns:
            col_info: dict = {"name": c.name, "type": c.type}
            if c.nullable:
                col_info["nullable"] = True
            if c.is_foreign_key and c.references_table:
                col_info["fk"] = f"→ {c.references_table}.{c.references_column}"
            if c.default:
                col_info["default"] = c.default
            cols.append(col_info)
        tables.append({
            "table": t.name,
            "action": t.action,
            "columns": cols,
            "indexes": t.indexes[:10],
            "unique": t.unique_constraints[:10],
        })
    return tables


def _build_blade_views(index: ProjectIndex) -> list[dict]:
    views = []
    for v in index.blade_views:
        entry: dict = {"name": v.name, "file": v.file_path}
        if v.extends:
            entry["extends"] = v.extends
        if v.includes:
            entry["includes"] = v.includes
        if v.components:
            entry["components"] = v.components
        if v.livewire_components:
            entry["livewire"] = v.livewire_components
        if v.route_refs:
            entry["routes"] = v.route_refs
        views.append(entry)
    return views


def _build_observers(index: ProjectIndex) -> list[dict]:
    return [
        {
            "model": o.model,
            "observer": o.observer,
            "file": o.file_path,
            "events": o.events,
        }
        for o in index.observers
    ]


def _build_events(index: ProjectIndex) -> list[dict]:
    return [
        {
            "event": e.event,
            "listeners": e.listeners,
            "file": e.file_path,
        }
        for e in index.events
    ]
