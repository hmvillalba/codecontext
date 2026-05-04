"""Python parser using the built-in ast module."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from codecontext.models import (
    CodeNode,
    DependencyEdge,
    FileSummary,
    Language,
    NodeType,
    Parameter,
    Visibility,
)
from codecontext.parsers import BaseParser


class PythonParser(BaseParser):
    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix == ".py"

    def parse(self, file_path: Path, root: Path) -> FileSummary:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        rel_path = self._relative_path(file_path, root)
        sha = hashlib.sha256(source.encode()).hexdigest()[:16]

        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError:
            return FileSummary(
                file_path=rel_path,
                language=Language.PYTHON,
                sha256=sha,
                lines_of_code=source.count("\n") + 1,
            )

        nodes: list[CodeNode] = []
        imports: list[str] = []
        top_level_classes = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imp = self._extract_import(node)
                if imp:
                    imports.append(imp)
            elif isinstance(node, ast.ClassDef):
                nodes.append(self._parse_class(node, rel_path, source))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                n = self._parse_function(node, rel_path, source)
                if any(d.id == "pytest" or "test" in d.id.lower() for d in ast.walk(node) if isinstance(d, ast.Name)):
                    n.node_type = NodeType.TEST
                    n.meta["framework"] = "pytest"
                nodes.append(n)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        nodes.append(CodeNode(
                            name=target.id,
                            node_type=NodeType.CONSTANT,
                            file_path=rel_path,
                            line_start=node.lineno,
                            line_end=node.end_lineno or node.lineno,
                            visibility=Visibility.PUBLIC,
                        ))

        for cls_node in nodes:
            if cls_node.node_type == NodeType.CLASS:
                for child in ast.walk(ast.parse(source)):
                    pass

        return FileSummary(
            file_path=rel_path,
            language=Language.PYTHON,
            nodes=nodes,
            imports=imports,
            lines_of_code=source.count("\n") + 1,
            sha256=sha,
        )

    def _extract_import(self, node: ast.Import | ast.ImportFrom) -> str | None:
        if isinstance(node, ast.ImportFrom):
            return node.module or ""
        elif isinstance(node, ast.Import):
            parts = []
            for alias in node.names:
                parts.append(alias.name)
            return ", ".join(parts)
        return None

    def _parse_class(self, node: ast.ClassDef, rel_path: str, source: str) -> CodeNode:
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(ast.dump(base))

        decorators = []
        for d in node.decorator_list:
            if isinstance(d, ast.Name):
                decorators.append(d.id)
            elif isinstance(d, ast.Attribute):
                decorators.append(ast.dump(d))
            elif isinstance(d, ast.Call):
                if isinstance(d.func, ast.Name):
                    decorators.append(d.func.id)
                elif isinstance(d.func, ast.Attribute):
                    decorators.append(ast.dump(d.func))

        docstring = ast.get_docstring(node)
        methods: list[CodeNode] = []
        attributes: list[str] = []
        calls_in_class: list[str] = []

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(self._parse_method(item, rel_path))
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        attributes.append(target.id)

        all_calls = set()
        for method in methods:
            all_calls.update(method.calls)
            method.inherits_from = bases

        return CodeNode(
            name=node.name,
            node_type=NodeType.CLASS,
            file_path=rel_path,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            visibility=Visibility.PUBLIC,
            parameters=[],
            decorators=decorators,
            inherits_from=bases,
            docstring=docstring[:200] if docstring else None,
            calls=list(all_calls),
            attributes=attributes,
            meta={"methods": [m.name for m in methods], "methods_count": len(methods)},
        )

    def _parse_method(self, node: ast.FunctionDef | ast.AsyncFunctionDef, rel_path: str) -> CodeNode:
        params = self._extract_params(node)
        decorators = []
        for d in node.decorator_list:
            if isinstance(d, ast.Name):
                decorators.append(d.id)
            elif isinstance(d, ast.Attribute):
                decorators.append(ast.dump(d))
            elif isinstance(d, ast.Call):
                if isinstance(d.func, ast.Name):
                    decorators.append(d.func.id)
                elif isinstance(d.func, ast.Attribute):
                    decorators.append(ast.dump(d.func))

        return_type = None
        if node.returns:
            return_type = ast.unparse(node.returns) if hasattr(ast, "unparse") else None

        calls = self._extract_calls(node)
        visibility = Visibility.PUBLIC
        if node.name.startswith("__") and node.name.endswith("__"):
            visibility = Visibility.PUBLIC
        elif node.name.startswith("_"):
            visibility = Visibility.PROTECTED
            if node.name.startswith("__"):
                visibility = Visibility.PRIVATE

        is_static = any(d in decorators for d in ["staticmethod", "classmethod"])
        is_property = "property" in decorators

        return CodeNode(
            name=node.name,
            node_type=NodeType.METHOD,
            file_path=rel_path,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            visibility=visibility,
            parameters=params,
            return_type=return_type,
            decorators=decorators,
            calls=calls,
            meta={"is_static": is_static, "is_property": is_property},
        )

    def _parse_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, rel_path: str, source: str = "") -> CodeNode:
        params = self._extract_params(node)
        return_type = None
        if node.returns:
            return_type = ast.unparse(node.returns) if hasattr(ast, "unparse") else None

        decorators = []
        for d in node.decorator_list:
            if isinstance(d, ast.Name):
                decorators.append(d.id)
            elif isinstance(d, ast.Call):
                if isinstance(d.func, ast.Name):
                    decorators.append(d.func.id)

        calls = self._extract_calls(node)

        return CodeNode(
            name=node.name,
            node_type=NodeType.FUNCTION,
            file_path=rel_path,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            visibility=Visibility.PUBLIC if not node.name.startswith("_") else Visibility.PRIVATE,
            parameters=params,
            return_type=return_type,
            decorators=decorators,
            calls=calls,
        )

    def _extract_params(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[Parameter]:
        params = []
        for arg in node.args.args:
            if arg.arg == "self" or arg.arg == "cls":
                continue
            type_hint = ast.unparse(arg.annotation) if arg.annotation and hasattr(ast, "unparse") else None
            params.append(Parameter(name=arg.arg, type_hint=type_hint))
        return params

    def _extract_calls(self, node: ast.AST) -> list[str]:
        calls = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.add(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.add(child.func.attr)
        return list(calls)
