"""Compact SUMMARY generator for agent context injection (~2K tokens)."""

from __future__ import annotations

from codecontext.models import ProjectIndex


def generate_summary(index: ProjectIndex) -> str:
    sections = [
        _header(index),
        _domain(index),
        _key_flows(index),
        _module_map(index),
        _data_model(index),
        _permissions(index),
        _views_and_observers(index),
        _risks(index),
    ]
    return "\n".join(s for s in sections if s)


def _header(index: ProjectIndex) -> str:
    arch = index.architecture.get("pattern", "unknown")
    total_loc = sum(f.lines_of_code for f in index.files)
    total_nodes = sum(len(f.nodes) for f in index.files)
    lang_dist: dict[str, int] = {}
    for f in index.files:
        lang_dist[f.language.value] = lang_dist.get(f.language.value, 0) + 1
    langs = "/".join(sorted(lang_dist.keys()))
    return f"# {index.root_path.split('/')[-1].split('\\\\')[-1]}\n{arch} | {langs} | {len(index.files)} files | {total_loc:,} LOC | {total_nodes} symbols"


def _domain(index: ProjectIndex) -> str:
    lines = ["\n## Domain"]

    model_names = set()
    for f in index.files:
        for n in f.nodes:
            if n.node_type.value == "model":
                model_names.add(n.name)

    if model_names:
        models_str = ", ".join(sorted(model_names))
        lines.append(f"Entities: {models_str}")

    route_count = len(index.routes)
    if route_count:
        methods: dict[str, int] = {}
        for r in index.routes:
            methods[r.http_method] = methods.get(r.http_method, 0) + 1
        route_summary = ", ".join(f"{m} {c}" for m, c in sorted(methods.items()))
        lines.append(f"Routes: {route_count} ({route_summary})")

    if index.migrations:
        create_tables = [t for t in index.migrations if t.action == "create"]
        lines.append(f"DB tables: {len(create_tables)}")

    return "\n".join(lines)


def _key_flows(index: ProjectIndex) -> str:
    if not index.traces:
        return ""

    lines = ["\n## Key Flows"]

    seen_uris: set[str] = set()
    shown = 0
    for t in index.traces:
        if shown >= 12:
            break
        if t.route_uri in seen_uris:
            continue
        seen_uris.add(t.route_uri)

        chain_str = " → ".join(t.chain[:6])
        line = f"- {chain_str}"

        extras = []
        if t.roles:
            extras.append(f"roles: {', '.join(t.roles[:3])}")
        if t.permissions:
            extras.append(f"perm: {', '.join(t.permissions[:3])}")
        if extras:
            line += f" ({'; '.join(extras)})"

        lines.append(line)
        shown += 1

    return "\n".join(lines)


def _module_map(index: ProjectIndex) -> str:
    layers = index.architecture.get("layers", {})
    if not layers:
        return ""

    lines = ["\n## Architecture"]

    type_counts: dict[str, int] = {}
    for f in index.files:
        for n in f.nodes:
            type_counts[n.node_type.value] = type_counts.get(n.node_type.value, 0) + 1

    parts = []
    for t, c in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:8]:
        parts.append(f"{t}({c})")

    if parts:
        lines.append(" → ".join(parts))

    entry_points = index.entry_points[:3]
    if entry_points:
        lines.append(f"Entry: {', '.join(entry_points)}")

    return "\n".join(lines)


def _data_model(index: ProjectIndex) -> str:
    if not index.model_relations:
        return ""

    lines = ["\n## Data Model"]

    by_model: dict[str, list] = {}
    for r in index.model_relations:
        by_model.setdefault(r.model_class, []).append(r)

    for model_name in sorted(by_model.keys())[:15]:
        rels = by_model[model_name]
        parts = []
        for r in rels[:5]:
            arrow = {"hasMany": "→*", "hasOne": "→1", "belongsTo": "←", "belongsToMany": "↔"}.get(r.relation_type, "→")
            parts.append(f"{r.relation_name}{arrow}{r.related_class}")
        lines.append(f"- {model_name}: {', '.join(parts)}")

    return "\n".join(lines)


def _permissions(index: ProjectIndex) -> str:
    role_map = index.role_map
    if not role_map:
        return ""

    lines = ["\n## Roles & Permissions"]

    for role in sorted(role_map.keys())[:10]:
        routes = role_map[role]
        uris = [r["uri"] for r in routes[:8]]
        lines.append(f"- {role}: {', '.join(uris)}")
        if len(routes) > 8:
            lines.append(f"  ... +{len(routes) - 8} more routes")

    return "\n".join(lines)


def _views_and_observers(index: ProjectIndex) -> str:
    parts = []

    if index.blade_views:
        total = len(index.blade_views)
        with_livewire = sum(1 for v in index.blade_views if v.livewire_components)
        with_routes = sum(1 for v in index.blade_views if v.route_refs)
        parts.append(f"Blade: {total} views ({with_livewire} livewire, {with_routes} route refs)")

    if index.observers:
        obs_str = ", ".join(f"{o.model}→{o.observer}" for o in index.observers if o.model)
        if obs_str:
            parts.append(f"Observers: {obs_str}")

    if index.events:
        evt_str = ", ".join(f"{e.event}({len(e.listeners)}L)" for e in index.events)
        if evt_str:
            parts.append(f"Events: {evt_str}")

    if not parts:
        return ""

    return "\n## Views & Observers\n" + "\n".join(f"- {p}" for p in parts)


def _risks(index: ProjectIndex) -> str:
    if not index.risks:
        return ""

    lines = ["\n## Risks"]

    by_sev: dict[str, list] = {}
    for r in index.risks:
        by_sev.setdefault(r.severity, []).append(r)

    icons = {"critical": "!!!", "warning": "!!", "info": "!"}

    for sev in ("critical", "warning", "info"):
        rs = by_sev.get(sev, [])[:5]
        for r in rs:
            lines.append(f"- [{icons.get(sev, '!')}] {r.category}: {r.message}")
            if r.location:
                lines[-1] += f" ({r.location})"

    return "\n".join(lines)
