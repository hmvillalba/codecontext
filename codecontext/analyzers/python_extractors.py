"""Python framework extractors: Flask routes, Django models/URLconf, FastAPI routes."""

from __future__ import annotations

import re
from pathlib import Path

from codecontext.models import MigrationTable, ModelField, RouteEntry

_RE_FLASK_ROUTE = re.compile(r'@(\w+(?:\.\w+)*)\.route\s*\(\s*["\']([^"\']+)["\']\s*(?:,\s*methods\s*=\s*\[([^\]]+)\])?')
_RE_BLUEPRINT = re.compile(r'(\w+)\s*=\s*Blueprint\s*\(\s*["\']')
_RE_APP_FLASK = re.compile(r'(\w+)\s*=\s*Flask\s*\(\s*__name__')

_RE_DJANGO_URL = re.compile(r'(?:path|re_path)\s*\(\s*["\']([^"\']+)["\']\s*,\s*(\w+(?:\.\w+)*)')
_RE_DJANGO_INCLUDE = re.compile(r'(?:path|re_path)\s*\(\s*["\']([^"\']+)["\']\s*,\s*include\s*\(\s*["\']([^"\']+)["\']')
_RE_DJANGO_MODEL = re.compile(r'class\s+(\w+)\s*\(\s*(?:models\.)?Model\s*\)')

_RE_FASTAPI_ROUTE = re.compile(r'@(\w+(?:\.\w+)*)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']')
_RE_APIROUTER = re.compile(r'(\w+)\s*=\s*APIRouter\s*\(')
_RE_FASTAPI_APP = re.compile(r'(\w+)\s*=\s*FastAPI\s*\(')


def extract_flask_routes(index, root: Path) -> list[RouteEntry]:
    routes: list[RouteEntry] = []
    seen: set[tuple[str, str]] = set()

    for f in index.files:
        try:
            content = Path(root, f.file_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for m in _RE_FLASK_ROUTE.finditer(content):
            app_var = m.group(1)
            uri = m.group(2)
            methods_str = m.group(3)

            http_methods = ["GET"]
            if methods_str:
                http_methods = [x.strip().strip("'\"") for x in methods_str.split(",")]

            lines_before = content[:m.start()].count("\n")
            func_match = re.search(r'def\s+(\w+)\s*\(', content[m.start():m.start() + 200])
            func_name = func_match.group(1) if func_match else "?"

            for method in http_methods:
                key = (method, uri)
                if key not in seen:
                    seen.add(key)
                    routes.append(RouteEntry(
                        http_method=method,
                        uri=uri,
                        controller=app_var,
                        method=func_name,
                        file_path=f.file_path,
                    ))

    return routes


def extract_django_urls(index, root: Path) -> list[RouteEntry]:
    routes: list[RouteEntry] = []
    seen: set[str] = set()

    for f in index.files:
        if "urls" not in f.file_path.lower():
            continue
        try:
            content = Path(root, f.file_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for m in _RE_DJANGO_URL.finditer(content):
            uri = m.group(1)
            view = m.group(2)
            if uri not in seen:
                seen.add(uri)
                routes.append(RouteEntry(
                    http_method="GET",
                    uri=uri,
                    controller=view,
                    method="",
                    file_path=f.file_path,
                ))

    return routes


def extract_django_models(index, root: Path) -> list[MigrationTable]:
    tables: list[MigrationTable] = []

    for f in index.files:
        try:
            content = Path(root, f.file_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for m in _RE_DJANGO_MODEL.finditer(content):
            model_name = m.group(1)
            table_name = _camel_to_snake(model_name)

            table = MigrationTable(
                name=table_name,
                file_path=f.file_path,
                action="create",
            )

            class_start = m.end()
            class_end = content.find("\nclass ", class_start)
            if class_end == -1:
                class_end = content.find("\ndef ", class_start)
            if class_end == -1:
                class_end = min(class_start + 3000, len(content))

            class_body = content[class_start:class_end]

            for field_match in re.finditer(r'(\w+)\s*=\s*models\.(\w+)\(', class_body):
                field_name = field_match.group(1)
                field_type = field_match.group(2)

                if field_name.startswith("_"):
                    continue

                is_fk = field_type in ("ForeignKey", "OneToOneField")
                ref_table = ""
                ref_col = ""

                if is_fk:
                    fk_ref = re.search(r'models\.' + field_type + r'\s*\(\s*(\w+)', class_body[field_match.start():field_match.start() + 100])
                    if fk_ref:
                        ref_model = fk_ref.group(1)
                        ref_table = _camel_to_snake(ref_model)

                table.columns.append(ModelField(
                    name=field_name if not is_fk else field_name + "_id",
                    type=field_type,
                    is_foreign_key=is_fk,
                    references_table=ref_table or None,
                    references_column="id" if ref_table else None,
                ))

            if table.columns:
                tables.append(table)

    return tables


def extract_fastapi_routes(index, root: Path) -> list[RouteEntry]:
    routes: list[RouteEntry] = []
    seen: set[tuple[str, str]] = set()

    for f in index.files:
        try:
            content = Path(root, f.file_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for m in _RE_FASTAPI_ROUTE.finditer(content):
            app_var = m.group(1)
            http_method = m.group(2).upper()
            uri = m.group(3)

            func_match = re.search(r'(?:async\s+)?def\s+(\w+)\s*\(', content[m.end():m.end() + 200])
            func_name = func_match.group(1) if func_match else "?"

            key = (http_method, uri)
            if key not in seen:
                seen.add(key)
                routes.append(RouteEntry(
                    http_method=http_method,
                    uri=uri,
                    controller=app_var,
                    method=func_name,
                    file_path=f.file_path,
                ))

    return routes


def extract_python_routes(index, root: Path) -> list[RouteEntry]:
    routes: list[RouteEntry] = []

    flask_routes = extract_flask_routes(index, root)
    routes.extend(flask_routes)

    fastapi_routes = extract_fastapi_routes(index, root)
    routes.extend(fastapi_routes)

    django_routes = extract_django_urls(index, root)
    routes.extend(django_routes)

    return routes


def extract_python_models(index, root: Path) -> list[MigrationTable]:
    return extract_django_models(index, root)


def _camel_to_snake(name: str) -> str:
    result = []
    for i, c in enumerate(name):
        if c.isupper() and i > 0:
            result.append("_")
        result.append(c.lower())
    return "".join(result)
