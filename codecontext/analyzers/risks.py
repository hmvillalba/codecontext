"""Risk detector - static analysis rules for common issues."""

from __future__ import annotations

from codecontext.models import CodeNode, FileSummary, NodeType, ProjectIndex, Risk, MigrationTable


GOD_CLASS_METHOD_THRESHOLD = 15
GOD_CLASS_LOC_THRESHOLD = 400


def detect_risks(index: ProjectIndex) -> list[Risk]:
    risks: list[Risk] = []

    risks.extend(_detect_god_classes(index))
    risks.extend(_detect_controllers_without_validation(index))
    risks.extend(_detect_routes_without_auth(index))
    risks.extend(_detect_fk_without_index(index))
    risks.extend(_detect_duplicate_methods(index))
    risks.extend(_detect_large_files(index))

    risks.sort(key=lambda r: {"critical": 0, "warning": 1, "info": 2}[r.severity])
    return risks


def _detect_god_classes(index: ProjectIndex) -> list[Risk]:
    risks = []
    for f in index.files:
        for node in f.nodes:
            if node.node_type in (NodeType.CLASS, NodeType.CONTROLLER, NodeType.SERVICE, NodeType.MODEL):
                method_count = node.meta.get("methods_count", 0)
                if method_count >= GOD_CLASS_METHOD_THRESHOLD:
                    risks.append(Risk(
                        severity="warning",
                        category="god-class",
                        message=f"{node.name} has {method_count} methods",
                        location=f"{f.file_path}:{node.line_start}",
                        detail=f"Consider splitting into smaller classes. Methods: {', '.join(node.meta.get('methods', [])[:10])}",
                    ))
    return risks


def _detect_controllers_without_validation(index: ProjectIndex) -> list[Risk]:
    risks = []
    request_classes = set()
    controller_files: list[tuple[FileSummary, CodeNode]] = []

    for f in index.files:
        for node in f.nodes:
            if node.node_type == NodeType.REQUEST:
                request_classes.add(node.name)
            elif node.node_type == NodeType.CONTROLLER:
                controller_files.append((f, node))

    for f, node in controller_files:
        methods = node.meta.get("methods", [])
        has_validation = False
        for rq in request_classes:
            if rq.lower().replace("request", "") in node.name.lower():
                has_validation = True
                break

        store_update = [m for m in methods if m in ("store", "update", "create", "edit")]
        if store_update and not has_validation:
            methods_str = ", ".join(store_update)
            risks.append(Risk(
                severity="info",
                category="missing-validation",
                message=f"{node.name} has write methods without dedicated Request class",
                location=f"{f.file_path}:{node.line_start}",
                detail=f"Methods needing validation: {methods_str}",
            ))

    return risks[:20]


def _detect_routes_without_auth(index: ProjectIndex) -> list[Risk]:
    risks = []
    auth_keywords = {"auth", "verified", "role:", "permission:", "role_or_permission:"}

    for route in index.routes:
        if route.uri in ("/", "/login", "/logout", "/forgot-password", "/reset-password/{token}"):
            continue
        if route.method in ("__invoke", "_render", "anonymous"):
            continue

        has_auth = False
        for mw in route.middleware:
            for kw in auth_keywords:
                if kw in mw.lower():
                    has_auth = True
                    break
            if has_auth:
                break

        if not has_auth:
            risks.append(Risk(
                severity="warning",
                category="unauthed-route",
                message=f"{route.http_method} {route.uri} has no auth middleware",
                location=f"{route.controller}@{route.method}",
                detail=f"Middleware present: {route.middleware or 'none'}",
            ))

    return risks[:30]


def _detect_fk_without_index(index: ProjectIndex) -> list[Risk]:
    risks = []
    for table in index.migrations:
        if table.action != "create":
            continue
        fk_cols = [c for c in table.columns if c.is_foreign_key]
        indexed_cols = set()
        for idx in table.indexes:
            for col_name in idx.replace("idx_", "").split("+"):
                indexed_cols.add(col_name)

        for fk in fk_cols:
            if fk.name not in indexed_cols:
                ref = f"→ {fk.references_table}" if fk.references_table else ""
                risks.append(Risk(
                    severity="info",
                    category="missing-index",
                    message=f"{table.name}.{fk.name} is FK without explicit index",
                    location=table.file_path,
                    detail=f"Foreign key to {ref}. Consider adding ->index()",
                ))

    return risks[:20]


def _detect_duplicate_methods(index: ProjectIndex) -> list[Risk]:
    risks = []
    method_locations: dict[str, list[str]] = {}

    for f in index.files:
        for node in f.nodes:
            if node.node_type == NodeType.METHOD and node.visibility.value == "public":
                key = node.name.lower()
                method_locations.setdefault(key, []).append(f"{f.file_path}:{node.line_start}")

    for name, locs in method_locations.items():
        if len(locs) >= 3 and name not in ("__construct", "__invoke", "handle", "up", "down", "boot"):
            risks.append(Risk(
                severity="info",
                category="duplicate-method",
                message=f"`{name}` defined in {len(locs)} places",
                location=locs[0],
                detail=f"Locations: {'; '.join(locs[:5])}",
            ))

    return risks[:15]


def _detect_large_files(index: ProjectIndex) -> list[Risk]:
    risks = []
    for f in index.files:
        if f.lines_of_code > 500:
            risks.append(Risk(
                severity="info",
                category="large-file",
                message=f"{f.file_path} is {f.lines_of_code} LOC",
                location=f.file_path,
            ))
    return sorted(risks, key=lambda r: int(r.message.split(" ")[-2] or "0"), reverse=True)[:10]
