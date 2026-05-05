"""C#/.NET framework extractors: EF Core schema, DI registrations, MVVM views."""

from __future__ import annotations

import re
from pathlib import Path

from codecontext.models import (
    DIRegistration,
    MigrationTable,
    ModelField,
    ModelRelation,
    RouteEntry,
    ViewMapping,
    NodeType,
)

_RE_DBSET = re.compile(r"DbSet\s*<\s*(\w+)\s*>\s+(\w+)")
_RE_HAS_ONE = re.compile(r"\.HasOne\s*\(\s*(\w*)\s*\)")
_RE_HAS_MANY = re.compile(r"\.HasMany\s*\(\s*(\w*)\s*\)")
_RE_HAS_FK = re.compile(r"\.HasForeignKey\s*\(\s*\w+\s*=>\s*\w+\.(\w+)\s*\)")
_RE_HAS_INDEX = re.compile(r"\.HasIndex\s*\(\s*\w+\s*=>\s*(?:new\s*\{)?([^})]+)")
_RE_IS_UNIQUE = re.compile(r"\.IsUnique\s*\(")
_RE_ENTITY = re.compile(r"modelBuilder\.Entity\s*<\s*(\w+)\s*>\s*\(\)")

_RE_ADD_SERVICE = re.compile(r"(AddTransient|AddScoped|AddSingleton)\s*<\s*(\w+)\s*,\s*(\w+)\s*>")
_RE_ADD_DBCTX = re.compile(r"AddDbContext\s*<\s*(\w+)\s*>")

_RE_X_DATATYPE = re.compile(r"x:DataType\s*=\s*\"([^\"]+)\"")
_RE_X_CLASS = re.compile(r"x:Class\s*=\s*\"([^\"]+)\"")


def extract_ef_schema(index) -> list[MigrationTable]:
    tables: dict[str, MigrationTable] = {}

    for f in index.files:
        try:
            content = Path(index.root_path, f.file_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for n in f.nodes:
            if "DbContext" not in " ".join(n.inherits_from):
                continue

            for m in _RE_DBSET.finditer(content):
                entity_name = m.group(1)
                prop_name = m.group(2)
                if entity_name not in tables:
                    tables[entity_name] = MigrationTable(
                        name=_camel_to_snake(entity_name),
                        file_path=f.file_path,
                        action="create",
                    )

            for em in _RE_ENTITY.finditer(content):
                entity = em.group(1)
                if entity not in tables:
                    tables[entity] = MigrationTable(
                        name=_camel_to_snake(entity),
                        file_path=f.file_path,
                        action="create",
                    )

                chunk = content[em.end():em.end() + 2000]

                idx_matches = _RE_HAS_INDEX.findall(chunk)
                for idx_str in idx_matches:
                    cols = [c.strip().split(".")[-1].strip() for c in idx_str.split(",")]
                    tables[entity].indexes.append(f"idx_{'_'.join(cols)}")

                if _RE_IS_UNIQUE.search(chunk):
                    for idx_str in idx_matches:
                        cols = [c.strip().split(".")[-1].strip() for c in idx_str.split(",")]
                        tables[entity].unique_constraints.append(f"unique_{'_'.join(cols)}")

    for f in index.files:
        for n in f.nodes:
            if n.node_type.value not in ("class",):
                continue
            entity_name = n.name
            if entity_name in tables:
                for attr in n.attributes:
                    if attr.endswith("Id") or attr.endswith("ID"):
                        fk_entity = attr[:-2] if attr.endswith("Id") else attr[:-2]
                        tables[entity_name].columns.append(ModelField(
                            name=attr,
                            type="int",
                            is_foreign_key=True,
                            references_table=_camel_to_snake(fk_entity),
                            references_column="Id",
                        ))
                    elif attr not in ("Id", "id"):
                        tables[entity_name].columns.append(ModelField(
                            name=attr,
                            type="?",
                        ))

    return [t for t in tables.values() if t.columns or t.indexes or t.unique_constraints]


def extract_ef_relations(index) -> list[ModelRelation]:
    relations: list[ModelRelation] = []

    for f in index.files:
        try:
            content = Path(index.root_path, f.file_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for n in f.nodes:
            if "DbContext" not in " ".join(n.inherits_from):
                continue

            entity_blocks = list(_RE_ENTITY.finditer(content))
            for em in entity_blocks:
                entity = em.group(1)
                chunk = content[em.end():em.end() + 2000]

                for mm in _RE_HAS_MANY.finditer(chunk):
                    nav_prop = mm.group(1) or "Items"
                    relations.append(ModelRelation(
                        model_file=f.file_path,
                        model_class=entity,
                        relation_type="hasMany",
                        relation_name=nav_prop,
                        related_class="?",
                        line=content[:mm.start()].count("\n") + 1,
                    ))

                for om in _RE_HAS_ONE.finditer(chunk):
                    nav_prop = om.group(1) or "Parent"
                    relations.append(ModelRelation(
                        model_file=f.file_path,
                        model_class=entity,
                        relation_type="hasOne",
                        relation_name=nav_prop,
                        related_class="?",
                        line=content[:om.start()].count("\n") + 1,
                    ))

    return relations


def extract_di_registrations(index) -> list[DIRegistration]:
    regs: list[DIRegistration] = []
    seen: set[tuple[str, str]] = set()

    for f in index.files:
        try:
            content = Path(index.root_path, f.file_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for m in _RE_ADD_SERVICE.finditer(content):
            key = (m.group(2), m.group(3))
            if key not in seen:
                seen.add(key)
                regs.append(DIRegistration(
                    interface=m.group(2),
                    implementation=m.group(3),
                    lifetime=m.group(1).replace("Add", "").lower(),
                    file_path=f.file_path,
                ))
        for m in _RE_ADD_DBCTX.finditer(content):
            key = ("DbContext", m.group(1))
            if key not in seen:
                seen.add(key)
                regs.append(DIRegistration(
                    interface="DbContext",
                    implementation=m.group(1),
                    lifetime="scoped",
                    file_path=f.file_path,
                ))

    return regs


def extract_mvvm_views(root: Path) -> list[ViewMapping]:
    views: list[ViewMapping] = []

    for axaml in root.rglob("*.axaml"):
        try:
            content = axaml.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        rel = str(axaml.relative_to(root)).replace("\\", "/")
        view_name = axaml.stem

        x_class = _RE_X_CLASS.search(content)
        x_dtype = _RE_X_DATATYPE.search(content)

        vm = ""
        if x_dtype:
            dtype = x_dtype.group(1)
            vm = dtype.split(":")[-1] if ":" in dtype else dtype
        elif x_class:
            cls = x_class.group(1)
            cls_short = cls.split(".")[-1]
            if cls_short.endswith("View"):
                vm = cls_short.replace("View", "ViewModel")

        if vm or x_class:
            views.append(ViewMapping(
                view_name=view_name,
                view_model=vm,
                file_path=rel,
                framework="avalonia",
            ))

    for razor in root.rglob("*.cshtml"):
        try:
            content = razor.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        rel = str(razor.relative_to(root)).replace("\\", "/")
        views.append(ViewMapping(
            view_name=razor.stem,
            view_model="",
            file_path=rel,
            framework="razor",
        ))

    return views


def extract_cs_routes(index) -> list[RouteEntry]:
    routes: list[RouteEntry] = []

    for f in index.files:
        for n in f.nodes:
            has_http_attr = any(
                a in n.decorators or any(a in d for d in n.decorators)
                for a in ("HttpGet", "HttpPost", "HttpPut", "HttpDelete", "HttpPatch")
            )
            if not has_http_attr:
                continue

            base_route = ""
            for d in n.decorators:
                rm = re.search(r'\[Route\s*\(\s*"([^"]+)"', d)
                if rm:
                    base_route = rm.group(1)

            for d in n.decorators:
                for method_attr, http_method in [
                    ("HttpGet", "GET"), ("HttpPost", "POST"),
                    ("HttpPut", "PUT"), ("HttpDelete", "DELETE"),
                    ("HttpPatch", "PATCH"),
                ]:
                    if method_attr not in d:
                        continue
                    rm = re.search(r'"([^"]*)"', d)
                    sub_route = rm.group(1) if rm else ""
                    uri = (base_route + "/" + sub_route).replace("//", "/")
                    if not uri.startswith("/"):
                        uri = "/" + uri

                    ctrl = n.name
                    for m_node in n.meta.get("methods", []):
                        if m_node.startswith("__"):
                            continue

                    routes.append(RouteEntry(
                        http_method=http_method,
                        uri=uri,
                        controller=ctrl,
                        method="",
                        file_path=f.file_path,
                    ))

    return routes


def _camel_to_snake(name: str) -> str:
    result = []
    for i, c in enumerate(name):
        if c.isupper() and i > 0:
            result.append("_")
        result.append(c.lower())
    return "".join(result)
