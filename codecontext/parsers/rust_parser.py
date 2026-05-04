"""Tree-sitter based parser for Rust."""

from __future__ import annotations

import hashlib
from pathlib import Path

import tree_sitter_rust as tsrust
from tree_sitter import Language as TSLanguage, Parser, Node

from codecontext.models import (
    CodeNode,
    FileSummary,
    Language,
    NodeType,
    Parameter,
    Visibility,
)
from codecontext.parsers import BaseParser


_RUST_LANG = TSLanguage(tsrust.language())


def _txt(node: Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _find(node: Node, type_name: str) -> Node | None:
    for c in node.children:
        if c.type == type_name:
            return c
    return None


class RustParser(BaseParser):
    def __init__(self):
        self._parser = Parser(_RUST_LANG)

    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix == ".rs"

    def parse(self, file_path: Path, root: Path) -> FileSummary:
        source = file_path.read_bytes()
        rel_path = self._relative_path(file_path, root)
        sha = hashlib.sha256(source).hexdigest()[:16]

        tree = self._parser.parse(source)
        nodes: list[CodeNode] = []
        imports: list[str] = []

        self._walk(tree.root_node, source, rel_path, nodes, imports)

        return FileSummary(
            file_path=rel_path,
            language=Language.RUST,
            nodes=nodes,
            imports=imports,
            lines_of_code=source.count(b"\n") + 1,
            sha256=sha,
        )

    def _walk(self, node: Node, source: bytes, rel_path: str, nodes: list[CodeNode], imports: list[str]):
        if node.type == "use_declaration":
            imports.append(_txt(node, source).strip())
            return

        elif node.type == "function_item":
            nodes.append(self._parse_function(node, source, rel_path))
            return

        elif node.type == "struct_item":
            nodes.append(self._parse_struct(node, source, rel_path))
            return

        elif node.type == "enum_item":
            en = self._parse_struct(node, source, rel_path)
            en.node_type = NodeType.ENUM
            nodes.append(en)
            return

        elif node.type == "trait_item":
            tr = self._parse_struct(node, source, rel_path)
            tr.node_type = NodeType.TRAIT
            nodes.append(tr)
            return

        elif node.type == "impl_item":
            self._parse_impl(node, source, rel_path, nodes)
            return

        for child in node.children:
            self._walk(child, source, rel_path, nodes, imports)

    def _parse_function(self, node: Node, source: bytes, rel_path: str) -> CodeNode:
        name = ""
        visibility = Visibility.PUBLIC
        params: list[Parameter] = []
        return_type = None
        calls: set[str] = set()
        decorators: list[str] = []

        for child in node.children:
            if child.type == "visibility_modifier":
                text = _txt(child, source)
                if "pub" in text:
                    visibility = Visibility.PUBLIC
                else:
                    visibility = Visibility.PRIVATE
            elif child.type == "identifier":
                name = _txt(child, source)
            elif child.type == "parameters":
                params = self._parse_params(child, source)
            elif child.type == "type_identifier" or child.type == "generic_type" or child.type == "reference_type" or child.type == "pointer_type" or child.type == "tuple_type" or child.type == "array_type" or child.type == "slice_type":
                if not return_type:
                    return_type = _txt(child, source)
            elif child.type == "block":
                calls = self._extract_calls(child, source)
            elif child.type == "attribute_item":
                decorators.append(_txt(child, source).strip())

        return CodeNode(
            name=name,
            node_type=NodeType.FUNCTION,
            file_path=rel_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            visibility=visibility,
            parameters=params,
            return_type=return_type,
            decorators=decorators,
            calls=list(calls),
        )

    def _parse_struct(self, node: Node, source: bytes, rel_path: str) -> CodeNode:
        name = ""
        visibility = Visibility.PUBLIC
        attributes: list[str] = []
        decorators: list[str] = []

        for child in node.children:
            if child.type == "visibility_modifier":
                text = _txt(child, source)
                visibility = Visibility.PUBLIC if "pub" in text else Visibility.PRIVATE
            elif child.type == "type_identifier" or child.type == "identifier":
                name = _txt(child, source)
            elif child.type == "attribute_item":
                decorators.append(_txt(child, source).strip())
            elif child.type == "field_declaration_list":
                for fc in child.children:
                    if fc.type == "field_declaration":
                        for fcc in fc.children:
                            if fcc.type == "field_identifier":
                                attributes.append(_txt(fcc, source))
                                break

        return CodeNode(
            name=name,
            node_type=NodeType.CLASS,
            file_path=rel_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            visibility=visibility,
            attributes=attributes,
            decorators=decorators,
            meta={"fields": attributes},
        )

    def _parse_impl(self, node: Node, source: bytes, rel_path: str, nodes: list[CodeNode]):
        target_type = ""
        trait_name = ""

        for child in node.children:
            if child.type == "type_identifier":
                target_type = _txt(child, source)
            elif child.type == "trait_bound" or child.type == "for_binding":
                trait_name = _txt(child, source)

        impl_body = _find(node, "declaration_list") or _find(node, "field_declaration_list")
        if impl_body:
            for child in impl_body.children:
                if child.type == "function_item":
                    method = self._parse_function(child, source, rel_path)
                    method.node_type = NodeType.METHOD
                    method.meta["impl_for"] = target_type
                    if trait_name:
                        method.meta["implements_trait"] = trait_name
                    nodes.append(method)

    def _parse_params(self, node: Node, source: bytes) -> list[Parameter]:
        params = []
        for child in node.children:
            if child.type == "parameter":
                param_name = ""
                param_type = None
                for pc in child.children:
                    if pc.type == "identifier" or pc.type == "_":
                        param_name = _txt(pc, source)
                    elif pc.type in ("type_identifier", "generic_type", "reference_type", "pointer_type", "tuple_type", "array_type", "slice_type", "scoped_identifier"):
                        param_type = _txt(pc, source)
                if param_name and param_name != "self" and param_name != "&self" and param_name != "mut self":
                    params.append(Parameter(name=param_name, type_hint=param_type))
        return params

    def _extract_calls(self, node: Node, source: bytes) -> set[str]:
        calls = set()
        stack = [node]
        while stack:
            current = stack.pop()
            if current.type == "call_expression":
                func = current.child_by_field_name("function")
                if func:
                    if func.type == "identifier":
                        calls.add(_txt(func, source))
                    elif func.type == "field_expression":
                        field = _find(func, "field_identifier")
                        if field:
                            calls.add(_txt(field, source))
                    elif func.type == "scoped_identifier":
                        calls.add(_txt(func, source))
            for child in current.children:
                stack.append(child)
        return calls
