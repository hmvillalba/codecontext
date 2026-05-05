"""MCP server for CodeContext — live queries from AI agents."""

from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP

from codecontext.models import ProjectIndex
from codecontext.scanner import scan_project as _scan_project
from codecontext.generators.summary import generate_summary
from codecontext.rules.engine import load_rules, evaluate_custom_rules

mcp = FastMCP("codecontext")

_cache: dict[str, ProjectIndex] = {}


def _get_index(path: str, rules_path: str = "") -> ProjectIndex:
    key = path
    if rules_path:
        key = f"{path}::{rules_path}"
    if key not in _cache:
        _cache[key] = _scan_project(path, rules_path=rules_path or None)
        rp = rules_path or None
        custom = load_rules(rp)
        if custom:
            _cache[key].risks.extend(evaluate_custom_rules(_cache[key], custom))
    return _cache[key]


def _sym_dict(n) -> dict:
    d: dict = {"name": n.name, "type": n.node_type.value, "file": n.file_path, "line": n.line_start}
    if n.inherits_from:
        d["extends"] = n.inherits_from
    if n.implements:
        d["implements"] = n.implements
    if n.parameters:
        d["params"] = [f"{p.name}:{p.type_hint}" if p.type_hint else p.name for p in n.parameters]
    if n.return_type:
        d["returns"] = n.return_type
    if n.meta.get("methods"):
        d["methods"] = n.meta["methods"]
    return d


def _route_dict(r) -> dict:
    d: dict = {"method": r.http_method, "uri": r.uri, "controller": r.controller, "action": r.method}
    if r.name:
        d["name"] = r.name
    if r.middleware:
        d["middleware"] = r.middleware
    return d


def _risk_dict(r) -> dict:
    return {"severity": r.severity, "category": r.category, "message": r.message, "location": r.location, "detail": r.detail}


def _table_dict(t) -> dict:
    cols = []
    for c in t.columns:
        cd: dict = {"name": c.name, "type": c.type}
        if c.nullable:
            cd["nullable"] = True
        if c.is_foreign_key and c.references_table:
            cd["fk"] = f"{c.references_table}.{c.references_column}"
        cols.append(cd)
    return {"table": t.name, "action": t.action, "columns": cols, "indexes": t.indexes, "unique": t.unique_constraints}


def _view_dict(v) -> dict:
    d: dict = {"name": v.name, "file": v.file_path}
    if v.extends:
        d["extends"] = v.extends
    if v.includes:
        d["includes"] = v.includes
    if v.livewire_components:
        d["livewire"] = v.livewire_components
    if v.route_refs:
        d["routes"] = v.route_refs
    return d


@mcp.tool()
def scan_project(path: str, rules_path: str = "") -> dict:
    """Scan a project and cache the index. Returns summary stats."""
    index = _get_index(path, rules_path)
    summary = generate_summary(index)
    return {
        "files": len(index.files),
        "loc": sum(f.lines_of_code for f in index.files),
        "symbols": sum(len(f.nodes) for f in index.files),
        "routes": len(index.routes),
        "relations": len(index.model_relations),
        "tables": len(index.migrations),
        "risks": len(index.risks),
        "traces": len(index.traces),
        "blade_views": len(index.blade_views),
        "observers": len(index.observers),
        "events": len(index.events),
        "summary_tokens": len(summary) // 4,
        "architecture": index.architecture.get("pattern", "unknown"),
    }


@mcp.tool()
def get_summary(path: str) -> str:
    """Get compact SUMMARY.md content (~1K tokens) for AI agent injection."""
    index = _get_index(path)
    return generate_summary(index)


@mcp.tool()
def query_symbols(path: str, name: str = "", type_filter: str = "") -> list[dict]:
    """Search symbols by name and/or type across all files."""
    index = _get_index(path)
    results = []
    name_l = name.lower()
    type_l = type_filter.lower()
    for f in index.files:
        for n in f.nodes:
            if name_l and name_l not in n.name.lower():
                continue
            if type_l and n.node_type.value != type_l:
                continue
            results.append(_sym_dict(n))
            if len(results) >= 50:
                return results
    return results


@mcp.tool()
def query_routes(path: str, uri_filter: str = "", method: str = "") -> list[dict]:
    """Query routes with optional URI and HTTP method filtering."""
    index = _get_index(path)
    results = []
    uri_l = uri_filter.lower()
    method_u = method.upper()
    for r in index.routes:
        if uri_l and uri_l not in r.uri.lower():
            continue
        if method_u and r.http_method != method_u:
            continue
        results.append(_route_dict(r))
        if len(results) >= 100:
            return results
    return results


@mcp.tool()
def query_data_model(path: str, model: str = "") -> dict:
    """Get model relationships and database schema. Optionally filter by model name."""
    index = _get_index(path)
    model_l = model.lower()

    rels = []
    for r in index.model_relations:
        if model_l and model_l not in r.model_class.lower() and model_l not in r.related_class.lower():
            continue
        rels.append({
            "model": r.model_class,
            "relation": r.relation_name,
            "type": r.relation_type,
            "related": r.related_class,
        })

    tables = []
    for t in index.migrations:
        if t.action != "create":
            continue
        if model_l and model_l not in t.name.lower():
            continue
        tables.append(_table_dict(t))

    return {"relations": rels, "tables": tables}


@mcp.tool()
def query_schema(path: str, table: str = "") -> list[dict]:
    """Query database schema from migrations. Optionally filter by table name."""
    index = _get_index(path)
    table_l = table.lower()
    results = []
    for t in index.migrations:
        if table_l and table_l not in t.name.lower():
            continue
        results.append(_table_dict(t))
    return results


@mcp.tool()
def query_risks(path: str, severity: str = "", category: str = "") -> list[dict]:
    """Get detected risks filtered by severity and/or category."""
    index = _get_index(path)
    sev_l = severity.lower()
    cat_l = category.lower()
    results = []
    for r in index.risks:
        if sev_l and r.severity.lower() != sev_l:
            continue
        if cat_l and cat_l not in r.category.lower():
            continue
        results.append(_risk_dict(r))
        if len(results) >= 100:
            return results
    return results


@mcp.tool()
def query_trace(path: str, uri: str) -> dict:
    """Get full traceability chain for a route URI."""
    index = _get_index(path)
    uri_l = uri.lower()
    for t in index.traces:
        if uri_l in t.route_uri.lower():
            return {
                "uri": t.route_uri,
                "method": t.route_method,
                "chain": t.chain,
                "middleware": t.middleware,
                "roles": t.roles,
                "permissions": t.permissions,
            }
    return {"error": f"No trace found for URI matching '{uri}'"}


@mcp.tool()
def query_blade(path: str, view_name: str = "") -> list[dict]:
    """Query Blade views with component, livewire, and route references."""
    index = _get_index(path)
    name_l = view_name.lower()
    results = []
    for v in index.blade_views:
        if name_l and name_l not in v.name.lower():
            continue
        results.append(_view_dict(v))
        if len(results) >= 100:
            return results
    return results


def main():
    mcp.run()


if __name__ == "__main__":
    main()
