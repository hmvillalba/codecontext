"""Markdown report generator."""

from __future__ import annotations

from codecontext.models import ProjectIndex


def generate_markdown(index: ProjectIndex) -> str:
    sections = [
        _header(index),
        _overview(index),
        _architecture(index),
        _file_tree(index),
        _entry_points(index),
        _routes_section(index),
        _model_relations_section(index),
        _database_schema_section(index),
        _blade_views_section(index),
        _observers_events_section(index),
        _detailed_nodes(index),
        _dependency_map(index),
    ]
    return "\n\n".join(s for s in sections if s)


def _header(index: ProjectIndex) -> str:
    arch = index.architecture.get("pattern", "unknown")
    total_loc = sum(f.lines_of_code for f in index.files)
    total_nodes = sum(len(f.nodes) for f in index.files)
    return f"""# CodeContext Report

**Root:** `{index.root_path}`
**Architecture:** {arch}
**Files:** {len(index.files)} | **LOC:** {total_loc:,} | **Symbols:** {total_nodes:,}"""


def _overview(index: ProjectIndex) -> str:
    stats = index.architecture.get("stats", {})
    langs = stats.get("languages", {})
    types = stats.get("node_types", {})

    lines = ["## Overview", ""]

    if langs:
        lines.append("**Languages:**")
        for lang, count in sorted(langs.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"- {lang}: {count} files")
        lines.append("")

    if types:
        lines.append("**Symbol Types:**")
        for t, count in sorted(types.items(), key=lambda x: x[1], reverse=True)[:15]:
            lines.append(f"- {t}: {count}")
        lines.append("")

    return "\n".join(lines)


def _architecture(index: ProjectIndex) -> str:
    layers = index.architecture.get("layers", {})
    if not layers:
        return ""

    lines = ["## Architecture Layers", ""]
    for name, info in layers.items():
        if isinstance(info, dict):
            count = info.get("count", "")
            desc = info.get("description", "")
            if count:
                lines.append(f"- **{name}**: {count} ({desc})" if desc else f"- **{name}**: {count}")
            elif desc:
                lines.append(f"- **{name}**: {desc}")
            else:
                files = info.get("files", "")
                loc = info.get("loc", "")
                if files:
                    lines.append(f"- **{name}**: {files} files, {loc} LOC")
        else:
            lines.append(f"- **{name}**: {info}")

    return "\n".join(lines)


def _file_tree(index: ProjectIndex) -> str:
    lines = ["## File Tree", "", "```"]

    files_sorted = sorted(index.files, key=lambda f: f.file_path)
    for f in files_sorted:
        node_count = len(f.nodes)
        badge = f"[{f.language.value}:{f.lines_of_code}loc"
        if node_count:
            badge += f":{node_count}symbols"
        badge += "]"
        lines.append(f"  {f.file_path} {badge}")

    lines.append("```")
    return "\n".join(lines)


def _entry_points(index: ProjectIndex) -> str:
    if not index.entry_points:
        return ""

    lines = ["## Entry Points", ""]
    for ep in index.entry_points:
        lines.append(f"- `{ep}`")
    return "\n".join(lines)


def _blade_views_section(index: ProjectIndex) -> str:
    if not index.blade_views:
        return ""

    lines = ["## Blade Views", ""]

    by_dir: dict[str, list] = {}
    for v in index.blade_views:
        parts = v.file_path.split("/")
        dir_key = "/".join(parts[:-1]) if len(parts) > 1 else "(root)"
        by_dir.setdefault(dir_key, []).append(v)

    for dir_name in sorted(by_dir.keys()):
        views = by_dir[dir_name]
        lines.append(f"### {dir_name}/ ({len(views)} views)")
        lines.append("")
        for v in views:
            parts = [f"`{v.name}`"]
            if v.extends:
                parts.append(f"extends:`{v.extends}`")
            if v.includes:
                parts.append(f"includes:{len(v.includes)}")
            if v.livewire_components:
                parts.append(f"livewire:{','.join(v.livewire_components[:3])}")
            if v.route_refs:
                parts.append(f"routes:{len(v.route_refs)}")
            lines.append(f"- {' | '.join(parts)}")
        lines.append("")

    return "\n".join(lines)


def _observers_events_section(index: ProjectIndex) -> str:
    if not index.observers and not index.events:
        return ""

    lines = ["## Observers & Events", ""]

    if index.observers:
        lines.append("### Observers")
        lines.append("")
        for o in index.observers:
            events_str = ", ".join(o.events) if o.events else "?"
            model_part = f"`{o.model}`" if o.model else "(auto-detected)"
            lines.append(f"- {model_part} → `{o.observer}` [{events_str}]")
        lines.append("")

    if index.events:
        lines.append("### Events & Listeners")
        lines.append("")
        for e in index.events:
            listeners_str = ", ".join(f"`{l}`" for l in e.listeners) if e.listeners else "(none)"
            lines.append(f"- `{e.event}` → {listeners_str}")
        lines.append("")

    return "\n".join(lines)


def _detailed_nodes(index: ProjectIndex) -> str:
    files_with_nodes = [f for f in index.files if f.nodes]
    if not files_with_nodes:
        return ""

    lines = ["## Symbols", ""]

    for f in files_sorted_by_path(files_with_nodes):
        lines.append(f"### `{f.file_path}` [{f.language.value}]")
        lines.append("")

        for node in f.nodes:
            vis = "" if node.visibility.value == "public" else f"[{node.visibility.value[:3]}] "
            type_tag = node.node_type.value

            sig = f"- **{vis}{node.name}** `{type_tag}`"

            if node.inherits_from:
                sig += f" extends `{', '.join(node.inherits_from)}`"
            if node.implements:
                sig += f" implements `{', '.join(node.implements)}`"

            if node.parameters:
                params = []
                for p in node.parameters:
                    ps = p.name
                    if p.type_hint:
                        ps += f": `{p.type_hint}`"
                    params.append(ps)
                sig += f"({', '.join(params)})"

            if node.return_type:
                sig += f" -> `{node.return_type}`"

            sig += f" :{node.line_start}"
            lines.append(sig)

            if node.meta.get("methods"):
                methods = node.meta["methods"]
                lines.append(f"  - methods: {', '.join(f'`{m}`' for m in methods[:15])}")
                if len(methods) > 15:
                    lines.append(f"  - ... and {len(methods) - 15} more")

            if node.attributes:
                attrs = node.attributes[:10]
                lines.append(f"  - attrs: {', '.join(f'`{a}`' for a in attrs)}")

            if node.decorators:
                lines.append(f"  - decorators: {', '.join(f'`{d}`' for d in node.decorators[:5])}")

        lines.append("")

    return "\n".join(lines)


def _dependency_map(index: ProjectIndex) -> str:
    if not index.dependencies:
        return ""

    dep_by_source: dict[str, list[str]] = {}
    for d in index.dependencies:
        dep_by_source.setdefault(d.source_file, []).append(d.target_file)

    lines = ["## Dependencies", ""]

    for source in sorted(dep_by_source.keys())[:30]:
        targets = dep_by_source[source]
        lines.append(f"- `{source}` -> {len(targets)} deps")
        for t in sorted(set(targets))[:5]:
            lines.append(f"  - `{t}`")
        if len(set(targets)) > 5:
            lines.append(f"  - ... and {len(set(targets)) - 5} more")

    total = len(index.dependencies)
    shown = sum(min(len(set(v)), 5) for v in list(dep_by_source.values())[:30])
    if total > shown:
        lines.append(f"\n*Total: {total} dependency edges*")

    return "\n".join(lines)


def files_sorted_by_path(files):
    return sorted(files, key=lambda f: f.file_path)


def _routes_section(index: ProjectIndex) -> str:
    if not index.routes:
        return ""

    lines = ["## Routes", ""]

    by_method: dict[str, list] = {}
    for r in index.routes:
        key = r.http_method
        by_method.setdefault(key, []).append(r)

    for method in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
        routes = by_method.get(method, [])
        if not routes:
            continue
        lines.append(f"### {method} ({len(routes)} routes)")
        lines.append("")
        for r in routes:
            ctrl = r.controller.split("\\")[-1] if r.controller else "?"
            action = f"{ctrl}@{r.method}" if r.method != "__invoke" else ctrl
            entry = f"- `{r.uri}` → **{action}**"
            if r.name:
                entry += f" `[{r.name}]`"
            mw = r.middleware[:3]
            if mw:
                entry += f" _middleware: {', '.join(mw)}_"
            lines.append(entry)
        lines.append("")

    return "\n".join(lines)


def _model_relations_section(index: ProjectIndex) -> str:
    if not index.model_relations:
        return ""

    lines = ["## Model Relationships", ""]

    by_model: dict[str, list] = {}
    for r in index.model_relations:
        by_model.setdefault(r.model_class, []).append(r)

    for model_name in sorted(by_model.keys()):
        rels = by_model[model_name]
        lines.append(f"### {model_name}")
        lines.append("")
        for r in rels:
            arrow = "→" if r.relation_type in ("hasMany", "hasOne", "hasManyThrough", "hasOneThrough", "morphMany", "morphOne", "morphToMany") else "←"
            if r.relation_type in ("belongsToMany", "morphedByMany"):
                arrow = "↔"
            lines.append(f"- `{r.relation_name}` **{r.relation_type}** {arrow} `{r.related_class}`")
        lines.append("")

    return "\n".join(lines)


def _database_schema_section(index: ProjectIndex) -> str:
    if not index.migrations:
        return ""

    lines = ["## Database Schema", ""]

    for t in index.migrations:
        action = " (ALTER)" if t.action == "alter" else ""
        lines.append(f"### `{t.name}`{action}")
        lines.append("")
        lines.append("| Column | Type | Nullable | FK |")
        lines.append("|--------|------|----------|-----|")
        for c in t.columns:
            fk = f"→ {c.references_table}.{c.references_column}" if c.is_foreign_key and c.references_table else ""
            nullable = "✓" if c.nullable else ""
            lines.append(f"| {c.name} | {c.type} | {nullable} | {fk} |")

        if t.indexes:
            lines.append(f"\nIndexes: {', '.join(f'`{i}`' for i in t.indexes)}")
        if t.unique_constraints:
            lines.append(f"Unique: {', '.join(f'`{u}`' for u in t.unique_constraints)}")
        lines.append("")

    return "\n".join(lines)
