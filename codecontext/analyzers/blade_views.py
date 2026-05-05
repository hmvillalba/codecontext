"""Extract Blade view structure: includes, extends, components, livewire, route refs."""

from __future__ import annotations

import re
from pathlib import Path

from codecontext.models import BladeView

_RE_EXTENDS = re.compile(r"@extends\s*\(\s*['\"]([^'\"]+)['\"]")
_RE_INCLUDE = re.compile(r"@include\s*\(\s*['\"]([^'\"]+)['\"]")
_RE_LIVEWIRE_TAG = re.compile(r"<\s*livewire\s*:\s*([\w.-]+)")
_RE_LIVEWIRE_DIR = re.compile(r"@livewire\s*\(\s*['\"]([^'\"]+)['\"]")
_RE_X_COMPONENT = re.compile(r"<\s*x-([\w.-]+)")
_RE_ROUTE = re.compile(r"\{\{\s*route\s*\(\s*['\"]([^'\"]+)['\"]")


def _view_name_from_path(blade_path: Path, views_root: Path) -> str:
    try:
        rel = blade_path.relative_to(views_root)
    except ValueError:
        return blade_path.stem
    parts = list(rel.parts)
    if parts:
        parts[-1] = Path(parts[-1]).stem
        if parts[-1] == "index":
            parts = parts[:-1]
    return ".".join(parts)


def extract_blade_views(root: Path) -> list[BladeView]:
    views_dirs = [
        root / "resources" / "views",
        root / "app" / "resources" / "views",
    ]
    views_root = None
    for vd in views_dirs:
        if vd.is_dir():
            views_root = vd
            break

    if not views_root:
        return []

    views: list[BladeView] = []

    for blade_file in views_root.rglob("*.blade.php"):
        name = _view_name_from_path(blade_file, views_root)
        rel = str(blade_file.relative_to(root)).replace("\\", "/")

        try:
            content = blade_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        extends = ""
        m = _RE_EXTENDS.search(content)
        if m:
            extends = m.group(1)

        includes = [m.group(1) for m in _RE_INCLUDE.finditer(content)]

        livewire = [m.group(1) for m in _RE_LIVEWIRE_TAG.finditer(content)]
        livewire += [m.group(1) for m in _RE_LIVEWIRE_DIR.finditer(content)]

        components = [m.group(1) for m in _RE_X_COMPONENT.finditer(content)]

        route_refs = [m.group(1) for m in _RE_ROUTE.finditer(content)]

        views.append(BladeView(
            name=name,
            file_path=rel,
            extends=extends,
            includes=includes,
            components=components,
            livewire_components=livewire,
            route_refs=route_refs,
        ))

    return views
