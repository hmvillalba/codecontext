"""Laravel migration schema extractor - columns, foreign keys, indexes."""

from __future__ import annotations

import re
from pathlib import Path

from codecontext.models import MigrationTable, ModelField


def extract_migrations(migration_dir: Path, root: Path) -> list[MigrationTable]:
    tables: list[MigrationTable] = []

    for mf in migration_dir.glob("*.php"):
        content = mf.read_text(encoding="utf-8", errors="replace")
        rel_path = str(mf.relative_to(root)).replace("\\", "/")

        table = _parse_migration(content, rel_path)
        if table:
            tables.append(table)

    tables.sort(key=lambda t: t.name)
    return tables


def _parse_migration(content: str, file_path: str) -> MigrationTable | None:
    create_match = re.search(
        r"Schema::create\s*\(\s*['\"](\w+)['\"]", content
    )
    if create_match:
        table_name = create_match.group(1)
        schema_block = _extract_schema_block(content, "create")
        if schema_block:
            columns = _extract_columns(schema_block)
            indexes = _extract_indexes(schema_block)
            unique = _extract_unique(schema_block)
            return MigrationTable(
                name=table_name,
                file_path=file_path,
                action="create",
                columns=columns,
                indexes=indexes,
                unique_constraints=unique,
            )

    table_match = re.search(
        r"Schema::table\s*\(\s*['\"](\w+)['\"]", content
    )
    if table_match:
        table_name = table_match.group(1)
        schema_block = _extract_schema_block(content, "table")
        if schema_block:
            columns = _extract_columns(schema_block)
            if columns:
                return MigrationTable(
                    name=table_name,
                    file_path=file_path,
                    action="alter",
                    columns=columns,
                )

    return None


def _extract_schema_block(content: str, schema_type: str) -> str | None:
    pattern = rf"Schema::{schema_type}\s*\(\s*['\"]\w+['\"]\s*,\s*function\s*\([^)]*\)\s*\{{"
    match = re.search(pattern, content)
    if not match:
        return None

    start = match.end() - 1
    depth = 0
    for i in range(start, len(content)):
        if content[i] == "{":
            depth += 1
        elif content[i] == "}":
            depth -= 1
            if depth == 0:
                return content[start:i + 1]

    return content[start:]


def _extract_columns(block: str) -> list[ModelField]:
    fields: list[ModelField] = []
    seen: set[str] = set()

    col_patterns = [
        (r"\$table->id\s*\(\s*\)", "id", "bigint", False),
        (r"\$table->id\s*\(\s*['\"](\w+)['\"]\s*\)", None, "bigint", False),
        (r"\$table->foreignId\s*\(\s*['\"](\w+)['\"]\s*\)", None, "foreign_bigint", False),
        (r"\$table->foreignIdFor\s*\(\s*([\w\\]+)::class\s*(?:,\s*['\"](\w+)['\"])?\s*\)", None, "foreign_bigint", False),
        (r"\$table->foreignUlid\s*\(\s*['\"](\w+)['\"]\s*\)", None, "foreign_ulid", False),
        (r"\$table->string\s*\(\s*['\"](\w+)['\"]\s*(?:,\s*(\d+))?\s*\)", None, "string", False),
        (r"\$table->text\s*\(\s*['\"](\w+)['\"]\s*\)", None, "text", False),
        (r"\$table->longText\s*\(\s*['\"](\w+)['\"]\s*\)", None, "longtext", False),
        (r"\$table->mediumText\s*\(\s*['\"](\w+)['\"]\s*\)", None, "mediumtext", False),
        (r"\$table->integer\s*\(\s*['\"](\w+)['\"]\s*\)", None, "integer", False),
        (r"\$table->unsignedInteger\s*\(\s*['\"](\w+)['\"]\s*\)", None, "unsigned_integer", False),
        (r"\$table->bigInteger\s*\(\s*['\"](\w+)['\"]\s*\)", None, "bigint", False),
        (r"\$table->unsignedBigInteger\s*\(\s*['\"](\w+)['\"]\s*\)", None, "unsigned_bigint", False),
        (r"\$table->tinyInteger\s*\(\s*['\"](\w+)['\"]\s*\)", None, "tinyint", False),
        (r"\$table->boolean\s*\(\s*['\"](\w+)['\"]\s*\)", None, "boolean", False),
        (r"\$table->decimal\s*\(\s*['\"](\w+)['\"]\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", None, "decimal", False),
        (r"\$table->float\s*\(\s*['\"](\w+)['\"]\s*\)", None, "float", False),
        (r"\$table->double\s*\(\s*['\"](\w+)['\"]\s*\)", None, "double", False),
        (r"\$table->date\s*\(\s*['\"](\w+)['\"]\s*\)", None, "date", False),
        (r"\$table->datetime\s*\(\s*['\"](\w+)['\"]\s*\)", None, "datetime", False),
        (r"\$table->timestamp\s*\(\s*['\"](\w+)['\"]\s*\)", None, "timestamp", False),
        (r"\$table->timestamps\s*\(\s*\)", "timestamps", "timestamps", False),
        (r"\$table->softDeletes\s*\(\s*\)", "soft_deletes", "timestamp", True),
        (r"\$table->enum\s*\(\s*['\"](\w+)['\"]\s*,\s*\[([^\]]*)\]", None, "enum", False),
        (r"\$table->json\s*\(\s*['\"](\w+)['\"]\s*\)", None, "json", False),
        (r"\$table->jsonb\s*\(\s*['\"](\w+)['\"]\s*\)", None, "jsonb", False),
        (r"\$table->uuid\s*\(\s*['\"](\w+)['\"]\s*\)", None, "uuid", False),
        (r"\$table->ulid\s*\(\s*['\"](\w+)['\"]\s*\)", None, "ulid", False),
        (r"\$table->macAddress\s*\(\s*['\"](\w+)['\"]\s*\)", None, "string", False),
        (r"\$table->ipAddress\s*\(\s*['\"](\w+)['\"]\s*\)", None, "string", False),
        (r"\$table->rememberToken\s*\(\s*\)", "remember_token", "string", False),
    ]

    lines = block.split("\n")
    for line in lines:
        for pattern, fixed_name, col_type, is_nullable_default in col_patterns:
            match = re.search(pattern, line)
            if not match:
                continue

            name = fixed_name or match.group(1)
            if name in seen:
                continue
            seen.add(name)

            is_fk = col_type.startswith("foreign_") or "foreignId" in line.split(name)[0] if name in line else False
            ref_table = None
            ref_col = None
            default = None

            constrained = re.search(r"constrained\s*\(\s*['\"](\w+)['\"]\s*(?:,\s*['\"](\w+)['\"])?\s*\)", line)
            if constrained:
                ref_table = constrained.group(1)
                ref_col = constrained.group(2) or "id"
                is_fk = True
            elif re.search(r"constrained\s*\(\s*\)", line):
                base = re.sub(r"_id$", "", name)
                ref_table = base
                ref_col = "id"
                is_fk = True

            if "->nullable" in line:
                is_nullable_default = True

            if col_type == "enum":
                enum_values = re.findall(r"['\"](\w+)['\"]", match.group(2) if match.lastindex and match.lastindex >= 2 else "")
                default = f"values: [{', '.join(enum_values[:10])}]"

            if "->default(" in line:
                def_match = re.search(r"->default\s*\(\s*([^)]+)\)", line)
                if def_match:
                    default = def_match.group(1).strip().strip("'\"")

            fields.append(ModelField(
                name=name,
                type=col_type,
                nullable=is_nullable_default,
                default=default,
                is_foreign_key=is_fk,
                references_table=ref_table,
                references_column=ref_col,
            ))
            break

    return fields


def _extract_indexes(block: str) -> list[str]:
    indexes = []
    for match in re.finditer(r"\$table->index\s*\(\s*\[([^\]]*)\]", block):
        cols = re.findall(r"['\"](\w+)['\"]", match.group(1))
        indexes.append(f"idx_{'+'.join(cols)}")
    for match in re.finditer(r"\$table->index\s*\(\s*['\"](\w+)['\"]", block):
        indexes.append(f"idx_{match.group(1)}")
    return indexes


def _extract_unique(block: str) -> list[str]:
    uniques = []
    for match in re.finditer(r"\$table->unique\s*\(\s*\[([^\]]*)\]", block):
        cols = re.findall(r"['\"](\w+)['\"]", match.group(1))
        uniques.append(f"unique_{'+'.join(cols)}")
    for match in re.finditer(r"\$table->unique\s*\(\s*['\"](\w+)['\"]", block):
        uniques.append(f"unique_{match.group(1)}")
    return uniques
