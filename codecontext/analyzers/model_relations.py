"""Laravel Eloquent model relationship and property extractor."""

from __future__ import annotations

import re
from pathlib import Path

from codecontext.models import ModelRelation


ELOQUENT_RELATIONS = {
    "hasOne", "hasMany", "belongsTo", "belongsToMany",
    "morphOne", "morphMany", "morphTo", "morphToMany",
    "morphedByMany", "hasManyThrough", "hasOneThrough",
}


def extract_model_relations(models: list, root: Path) -> list[ModelRelation]:
    relations: list[ModelRelation] = []

    for f in models:
        source = f.file_path
        path = root / source
        if not path.exists():
            continue

        content = path.read_text(encoding="utf-8", errors="replace")
        use_map = _extract_use_map(content)

        class_name = ""
        class_match = re.search(r"class\s+(\w+)\s+extends", content)
        if class_match:
            class_name = class_match.group(1)

        for line_num, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()

            for rel_type in ELOQUENT_RELATIONS:
                pattern = rf"->\s*{rel_type}\s*\(\s*([\w\\]+)::class"
                match = re.search(pattern, stripped)
                if match:
                    related = match.group(1)
                    related_resolved = use_map.get(related, related)
                    if "\\" in related_resolved:
                        related_resolved = related_resolved.split("\\")[-1]

                    func_match = re.search(r"public\s+function\s+(\w+)\s*\(", stripped)
                    if not func_match:
                        for prev in range(max(0, line_num - 5), line_num):
                            fm = re.search(r"public\s+function\s+(\w+)\s*\(", content.split("\n")[prev])
                            if fm:
                                func_match = fm
                                break

                    rel_name = func_match.group(1) if func_match else rel_type

                    relations.append(ModelRelation(
                        model_file=source,
                        model_class=class_name,
                        relation_type=rel_type,
                        relation_name=rel_name,
                        related_class=related_resolved,
                        line=line_num,
                    ))
                    break

    return relations


def extract_model_properties(models: list, root: Path) -> dict:
    props: dict = {}

    for f in models:
        source = f.file_path
        path = root / source
        if not path.exists():
            continue

        content = path.read_text(encoding="utf-8", errors="replace")

        class_name = ""
        class_match = re.search(r"class\s+(\w+)\s+extends", content)
        if class_match:
            class_name = class_match.group(1)

        model_info: dict = {}

        fillable = _extract_array_property(content, "fillable")
        if fillable:
            model_info["fillable"] = fillable

        casts = _extract_casts(content)
        if casts:
            model_info["casts"] = casts

        table = _extract_string_property(content, "table")
        if table:
            model_info["table"] = table

        hidden = _extract_array_property(content, "hidden")
        if hidden:
            model_info["hidden"] = hidden

        traits = re.findall(r"use\s+(\w+)(?:\s*,|\s*;)", content.split("class")[0] if "class" in content else content)
        model_traits = [t for t in re.findall(r"use\s+(\w+)", content.split("{")[1] if "{" in content else "") if t in (
            "HasFactory", "SoftDeletes", "LogsActivity", "HasRoles",
            "HasPermissions", "Notifiable", "HasApiTokens",
        )]
        if model_traits:
            model_info["traits"] = model_traits

        if model_info:
            props[f"{class_name} ({source})"] = model_info

    return props


def _extract_use_map(source: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for match in re.finditer(r"use\s+([\w\\]+)", source):
        fqn = match.group(1)
        short = fqn.split("\\")[-1]
        mapping[short] = fqn
    return mapping


def _extract_array_property(content: str, prop_name: str) -> list[str]:
    pattern = rf"\${prop_name}\s*=\s*\[([^\]]*)\]"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return []
    raw = match.group(1)
    items = re.findall(r"['\"](\w+)['\"]", raw)
    return items


def _extract_casts(content: str) -> dict[str, str]:
    pattern = r"casts\s*\(\s*\)\s*:\s*array\s*\{([^}]+)\}"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        raw = match.group(1)
        casts = {}
        for cm in re.findall(r"['\"](\w+)['\"]\s*=>\s*['\"]?(\w+)['\"]?", raw):
            casts[cm[0]] = cm[1]
        return casts

    pattern = r"\$casts\s*=\s*\[([^\]]*)\]"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        raw = match.group(1)
        casts = {}
        for cm in re.findall(r"['\"](\w+)['\"]\s*=>\s*['\"]?(\w+)['\"]?", raw):
            casts[cm[0]] = cm[1]
        return casts

    return {}


def _extract_string_property(content: str, prop_name: str) -> str | None:
    pattern = rf"\${prop_name}\s*=\s*['\"](\w+)['\"]"
    match = re.search(pattern, content)
    return match.group(1) if match else None
