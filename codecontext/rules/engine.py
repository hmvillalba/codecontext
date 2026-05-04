"""YAML rule engine for custom static analysis rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from codecontext.models import Risk, ProjectIndex


@dataclass
class Rule:
    id: str
    title: str
    severity: str = "info"
    scope: str = "static"
    check: str = ""
    query: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)
    message_template: str = ""

    def to_risk(self, location: str, detail: str = "") -> Risk:
        return Risk(
            severity=self.severity,
            category=self.id,
            message=self.title,
            location=location,
            detail=detail,
        )


def load_rules(rules_path: Optional[str] = None) -> list[Rule]:
    rules: list[Rule] = []

    if rules_path:
        p = Path(rules_path)
        if p.exists():
            rules.extend(_load_yaml(p))
        else:
            print(f"Warning: rules file not found: {rules_path}")

    default = Path(__file__).parent / "default.yaml"
    if default.exists():
        rules.extend(_load_yaml(default))

    return rules


def _load_yaml(path: Path) -> list[Rule]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Warning: failed to load rules from {path}: {e}")
        return []

    if not data or "rules" not in data:
        return []

    rules = []
    for item in data["rules"]:
        rules.append(Rule(
            id=item.get("id", "UNKNOWN"),
            title=item.get("title", ""),
            severity=item.get("severity", "info"),
            scope=item.get("scope", "static"),
            check=item.get("check", ""),
            query=item.get("query", {}),
            evidence=item.get("evidence", {}),
            message_template=item.get("message_template", ""),
        ))
    return rules


def evaluate_custom_rules(index: ProjectIndex, rules: list[Rule]) -> list[Risk]:
    risks: list[Risk] = []

    check_map = {
        "migration_has_unique": _check_migration_unique,
        "migration_has_unique_or_code_guard": _check_migration_unique_or_code_guard,
        "migration_has_column": _check_migration_column,
        "model_has_relation": _check_model_relation,
        "route_has_middleware": _check_route_middleware,
        "route_has_policy": _check_route_policy,
        "route_has_test": _check_route_test,
        "class_max_methods": _check_class_max_methods,
        "file_max_loc": _check_file_max_loc,
        "table_has_index_on_fk": _check_fk_index,
        "no_bare_try_catch": _check_no_bare_try,
    }

    for rule in rules:
        handler = check_map.get(rule.check)
        if handler:
            results = handler(index, rule)
            risks.extend(results)

    return risks


def _get_unique_cols(rule: Rule) -> list[str]:
    return rule.query.get("expected_unique_on", []) or rule.query.get("unique_on", [])


def _find_table_migrations(index: ProjectIndex, table_name: str):
    for table in index.migrations:
        if table.action != "create":
            continue
        if table.name == table_name or table_name in table.name:
            yield table


def _migration_has_unique(table, unique_cols: list[str]) -> bool:
    for uq in table.unique_constraints:
        uq_cols = set(uq.replace("unique_", "").split("+"))
        if set(unique_cols).issubset(uq_cols) or uq_cols == set(unique_cols):
            return True
    return False


def _check_migration_unique(index: ProjectIndex, rule: Rule) -> list[Risk]:
    risks = []
    table_name = rule.query.get("table", "")
    unique_cols = _get_unique_cols(rule)

    if not table_name or not unique_cols:
        return []

    for table in _find_table_migrations(index, table_name):
        if not _migration_has_unique(table, unique_cols):
            risks.append(rule.to_risk(
                location=table.file_path,
                detail=f"Missing unique constraint on [{', '.join(unique_cols)}] in table '{table.name}'. "
                       f"Existing: {', '.join(table.unique_constraints) or 'none'}",
            ))

    return risks


_CODE_GUARD_PATTERNS = (
    "firstOrCreate",
    "firstOrNew",
    "updateOrCreate",
    "validateUnique",
    "->unique(",
    "'unique':",
    '"unique":',
    "'unique'",
    "UniqueRule",
    "unique:",
)


def _find_code_guards(index: ProjectIndex, table_name: str, unique_cols: list[str]) -> list[str]:
    guards: list[str] = []
    col_set = set(c.lower() for c in unique_cols)
    model_name = "".join(word.capitalize() for word in table_name.split("_"))
    table_terms = {table_name.lower(), model_name.lower()}

    for f in index.files:
        for n in f.nodes:
            body_refs = (
                " ".join(n.calls)
                + " " + " ".join(n.attributes)
                + " " + " ".join(str(d) for d in n.decorators)
                + " " + (n.docstring or "")
                + " " + " ".join(n.imports)
                + " " + f.file_path.lower()
            ).lower()

            if not any(p.lower() in body_refs for p in _CODE_GUARD_PATTERNS):
                continue

            has_table_ctx = any(t in body_refs for t in table_terms)
            relevant_cols = sum(1 for c in unique_cols if c.lower() in body_refs)

            if has_table_ctx and relevant_cols >= 1:
                guards.append(f"{n.node_type.value}:{n.name} in {f.file_path}:{n.line_start}")

    return guards


def _check_migration_unique_or_code_guard(index: ProjectIndex, rule: Rule) -> list[Risk]:
    table_name = rule.query.get("table", "")
    unique_cols = _get_unique_cols(rule)

    if not table_name or not unique_cols:
        return []

    for table in _find_table_migrations(index, table_name):
        if _migration_has_unique(table, unique_cols):
            return []

        guards = _find_code_guards(index, table_name, unique_cols)
        if guards:
            return []

        return [rule.to_risk(
            location=table.file_path,
            detail=f"No unique constraint NOR code guard found for [{', '.join(unique_cols)}] "
                   f"in table '{table.name}'. Add a migration unique() or a validation/app-level guard.",
        )]

    return []


def _check_migration_column(index: ProjectIndex, rule: Rule) -> list[Risk]:
    risks = []
    table_name = rule.query.get("table", "")
    required_columns = rule.query.get("columns", [])

    if not table_name or not required_columns:
        return []

    for table in index.migrations:
        if table.action != "create":
            continue
        if table.name != table_name and table_name not in table.name:
            continue

        existing = {c.name for c in table.columns}
        for col in required_columns:
            if col not in existing:
                risks.append(rule.to_risk(
                    location=table.file_path,
                    detail=f"Column '{col}' missing from table '{table.name}'",
                ))

    return risks


def _check_model_relation(index: ProjectIndex, rule: Rule) -> list[Risk]:
    risks = []
    model_name = rule.query.get("model", "")
    relation_type = rule.query.get("relation_type", "")
    relation_name = rule.query.get("relation_name", "")
    related = rule.query.get("related", "")

    if not model_name:
        return []

    for rel in index.model_relations:
        if rel.model_class == model_name:
            if relation_type and rel.relation_type != relation_type:
                continue
            if relation_name and rel.relation_name != relation_name:
                continue
            if related and rel.related_class != related:
                continue
            return []

    risks.append(rule.to_risk(
        location="",
        detail=f"Model '{model_name}' missing relation: {relation_type}({related}). "
               f"Found: {', '.join(f'{r.relation_name}({r.relation_type}→{r.related_class})' for r in index.model_relations if r.model_class == model_name) or 'none'}",
    ))
    return risks


def _check_route_middleware(index: ProjectIndex, rule: Rule) -> list[Risk]:
    risks = []
    required_mw = rule.query.get("middleware", "")
    uri_pattern = rule.query.get("uri_pattern", "")

    if not required_mw:
        return []

    for route in index.routes:
        if uri_pattern and uri_pattern.lower() not in route.uri.lower():
            continue
        if not any(required_mw.lower() in mw.lower() for mw in route.middleware):
            risks.append(rule.to_risk(
                location=f"{route.controller}@{route.method}",
                detail=f"Route {route.http_method} {route.uri} missing middleware '{required_mw}'. "
                       f"Has: {', '.join(route.middleware) or 'none'}",
            ))

    return risks


def _check_route_policy(index: ProjectIndex, rule: Rule) -> list[Risk]:
    risks = []
    model_name = rule.query.get("model", "")

    if not model_name:
        return []

    policy_classes = set()
    for f in index.files:
        for n in f.nodes:
            if n.node_type.value == "policy":
                policy_classes.add(n.name)

    expected_policy = f"{model_name}Policy"
    if expected_policy not in policy_classes:
        risks.append(rule.to_risk(
            location="",
            detail=f"No policy found for model '{model_name}'. Expected: {expected_policy}. "
                   f"Existing policies: {', '.join(sorted(policy_classes)) or 'none'}",
        ))

    return risks


def _check_route_test(index: ProjectIndex, rule: Rule) -> list[Risk]:
    risks = []
    controller_name = rule.query.get("controller", "")

    if not controller_name:
        return []

    test_classes = set()
    for f in index.files:
        for n in f.nodes:
            if n.node_type.value == "test":
                test_classes.add(n.name)

    test_patterns = [f"{controller_name}Test", f"{controller_name}FeatureTest", f"{controller_name}UnitTest"]
    found = any(p in test_classes for p in test_patterns)

    if not found:
        risks.append(rule.to_risk(
            location="",
            detail=f"No test found for '{controller_name}'. Expected one of: {', '.join(test_patterns)}. "
                   f"Existing tests: {', '.join(sorted(test_classes)[:10]) or 'none'}",
        ))

    return risks


def _check_class_max_methods(index: ProjectIndex, rule: Rule) -> list[Risk]:
    risks = []
    max_methods = int(rule.query.get("max", 15))
    class_pattern = rule.query.get("class_pattern", "")
    node_types = rule.query.get("node_types", ["class", "controller", "service"])

    for f in index.files:
        for n in f.nodes:
            if n.node_type.value not in node_types:
                continue
            if class_pattern and class_pattern.lower() not in n.name.lower():
                continue

            method_count = n.meta.get("methods_count", 0)
            if method_count > max_methods:
                risks.append(rule.to_risk(
                    location=f"{f.file_path}:{n.line_start}",
                    detail=f"{n.name} has {method_count} methods (max allowed: {max_methods})",
                ))

    return risks


def _check_file_max_loc(index: ProjectIndex, rule: ProjectIndex, rule_obj: Rule = None) -> list[Risk]:
    if rule_obj is None:
        return []
    risks = []
    max_loc = int(rule_obj.query.get("max", 500))

    for f in index.files:
        if f.lines_of_code > max_loc:
            risks.append(rule_obj.to_risk(
                location=f.file_path,
                detail=f"{f.lines_of_code} LOC (max allowed: {max_loc})",
            ))

    return risks


def _check_fk_index(index: ProjectIndex, rule: Rule) -> list[Risk]:
    risks = []
    table_name = rule.query.get("table", "")

    for table in index.migrations:
        if table.action != "create":
            continue
        if table_name and table.name != table_name and table_name not in table.name:
            continue

        indexed_cols = set()
        for idx in table.indexes:
            for col in idx.replace("idx_", "").split("+"):
                indexed_cols.add(col)

        for col in table.columns:
            if col.is_foreign_key and col.name not in indexed_cols:
                ref = f"→ {col.references_table}" if col.references_table else ""
                risks.append(rule.to_risk(
                    location=table.file_path,
                    detail=f"Table '{table.name}': FK '{col.name}' {ref} has no explicit index",
                ))

    return risks


def _check_no_bare_try(index: ProjectIndex, rule: Rule) -> list[Risk]:
    return []
