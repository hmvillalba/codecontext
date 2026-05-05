"""Go framework extractors: net/http routes, middleware chain, embedded SQL schema."""

from __future__ import annotations

import re
from pathlib import Path

from codecontext.models import MigrationTable, ModelField, RouteEntry

_RE_HANDLE_FUNC = re.compile(r'(\w+)\.HandleFunc\s*\(\s*"([^"]+)"\s*,\s*(\w+)')
_RE_HANDLE = re.compile(r'(\w+)\.Handle\s*\(\s*"([^"]+)"\s*,\s*(\w+)')
_RE_METHOD_PREFIX = re.compile(r'HandleFunc\s*\(\s*"([^"]+)"\s*,\s*(\w+)(?:\s*\.(\w+))?')

_RE_CREATE_TABLE = re.compile(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["\`]?(\w+)["\`]?\s*\((.*?)\)(?:\s*;|\s*$)', re.IGNORECASE | re.DOTALL)
_RE_CREATE_INDEX = re.compile(r'CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?["\`]?(\w+)["\`]?\s+ON\s+["\`]?(\w+)["\`]?\s*\(([^)]+)\)', re.IGNORECASE)
_RE_COL_DEF = re.compile(r'["\`]?(\w+)["\`]?\s+([\w]+(?:\([^)]*\))?)')
_RE_PK = re.compile(r'PRIMARY\s+KEY', re.IGNORECASE)
_RE_FK = re.compile(r'REFERENCES\s+["\`]?(\w+)["\`]?\s*\(["\`]?(\w+)["\`]?\)', re.IGNORECASE)

_RE_MW_TYPE = re.compile(r'type\s+Middleware\s*=\s*func\s*\(\s*http\.Handler\s*\)\s*http\.Handler')
_RE_MW_FUNC = re.compile(r'func\s+(\w+)\s*\([^)]*\)\s*(?:Middleware|func\s*\(http\.Handler\)\s*http\.Handler)')
_RE_CHAIN = re.compile(r'NewChain\s*\(\s*([^)]+)\)')
_RE_THEN = re.compile(r'\.Then\s*\(')


def extract_go_routes(index, root: Path) -> list[RouteEntry]:
    routes: list[RouteEntry] = []
    seen: set[tuple[str, str]] = set()

    for f in index.files:
        try:
            content = Path(root, f.file_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for m in _RE_HANDLE_FUNC.finditer(content):
            path = m.group(2)
            handler = m.group(3)
            key = (path, handler)
            if key not in seen:
                seen.add(key)
                routes.append(RouteEntry(
                    http_method="GET",
                    uri=path,
                    controller=handler,
                    method="",
                    file_path=f.file_path,
                ))

        for m in _RE_HANDLE.finditer(content):
            path = m.group(2)
            handler = m.group(3)
            key = (path, handler)
            if key not in seen:
                seen.add(key)
                routes.append(RouteEntry(
                    http_method="GET",
                    uri=path,
                    controller=handler,
                    method="",
                    file_path=f.file_path,
                ))

    for f in index.files:
        for n in f.nodes:
            if n.node_type.value != "function":
                continue
            for call in n.calls:
                if call in ("HandleFunc", "Handle"):
                    try:
                        content = Path(root, f.file_path).read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        continue
                    for m in _RE_HANDLE_FUNC.finditer(content):
                        path = m.group(2)
                        handler = m.group(3)
                        key = (path, handler)
                        if key not in seen:
                            seen.add(key)
                            routes.append(RouteEntry(
                                http_method="GET",
                                uri=path,
                                controller=handler,
                                method="",
                                file_path=f.file_path,
                            ))
                    break

    return routes


def extract_go_middleware(index, root: Path) -> list[dict]:
    middleware: list[dict] = []

    for f in index.files:
        try:
            content = Path(root, f.file_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        rel = f.file_path

        for m in _RE_MW_FUNC.finditer(content):
            name = m.group(1)
            middleware.append({
                "name": name,
                "file": rel,
                "type": "function",
            })

        for m in _RE_CHAIN.finditer(content):
            chain_content = m.group(1)
            names = [n.strip() for n in chain_content.split(",") if n.strip()]
            for name in names:
                middleware.append({
                    "name": name,
                    "file": rel,
                    "type": "chain",
                })

    seen: set[str] = set()
    unique: list[dict] = []
    for mw in middleware:
        if mw["name"] not in seen:
            seen.add(mw["name"])
            unique.append(mw)

    return unique


def extract_go_schema(index, root: Path) -> list[MigrationTable]:
    tables: dict[str, MigrationTable] = {}

    for f in index.files:
        try:
            content = Path(root, f.file_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for m in _RE_CREATE_TABLE.finditer(content):
            table_name = m.group(1)
            cols_block = m.group(2)

            if table_name not in tables:
                tables[table_name] = MigrationTable(
                    name=table_name,
                    file_path=f.file_path,
                    action="create",
                )

            for line in cols_block.split(","):
                line = line.strip()
                cm = _RE_COL_DEF.match(line)
                if not cm:
                    continue
                col_name = cm.group(1)
                col_type = cm.group(2)

                if col_name.upper() in ("PRIMARY", "UNIQUE", "FOREIGN", "CONSTRAINT", "CHECK", "INDEX", "KEY"):
                    continue

                is_fk = bool(_RE_FK.search(line))
                ref_table = ""
                ref_col = ""
                fk_match = _RE_FK.search(line)
                if fk_match:
                    ref_table = fk_match.group(1)
                    ref_col = fk_match.group(2)

                is_pk = bool(_RE_PK.search(line))

                tables[table_name].columns.append(ModelField(
                    name=col_name,
                    type=col_type,
                    is_foreign_key=is_fk,
                    references_table=ref_table or None,
                    references_column=ref_col or None,
                ))

        for m in _RE_CREATE_INDEX.finditer(content):
            idx_name = m.group(1)
            table_name = m.group(2)
            idx_cols = m.group(3)

            if table_name not in tables:
                tables[table_name] = MigrationTable(
                    name=table_name,
                    file_path=f.file_path,
                    action="create",
                )
            tables[table_name].indexes.append(idx_name)

    return list(tables.values())
