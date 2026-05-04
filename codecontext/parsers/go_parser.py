"""Tree-sitter based parser for Go."""

from __future__ import annotations

import hashlib
from pathlib import Path

import tree_sitter_go as tsgo
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


_GO_LANG = TSLanguage(tsgo.language())


def _txt(node: Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _find(node: Node, type_name: str) -> Node | None:
    for c in node.children:
        if c.type == type_name:
            return c
    return None


class GoParser(BaseParser):
    def __init__(self):
        self._parser = Parser(_GO_LANG)

    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix == ".go"

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
            language=Language.GO,
            nodes=nodes,
            imports=imports,
            lines_of_code=source.count(b"\n") + 1,
            sha256=sha,
        )

    def _walk(self, node: Node, source: bytes, rel_path: str, nodes: list[CodeNode], imports: list[str]):
        if node.type == "import_declaration":
            imports.append(_txt(node, source).strip())
            return

        elif node.type == "function_declaration":
            nodes.append(self._parse_func(node, source, rel_path))
            return

        elif node.type == "method_declaration":
            nodes.append(self._parse_method(node, source, rel_path))
            return

        elif node.type == "type_declaration":
            for child in node.children:
                if child.type == "type_spec":
                    type_name_node = _find(child, "type_identifier")
                    if type_name_node:
                        name = _txt(type_name_node, source)
                        type_node = _find(child, "struct_type") or _find(child, "interface_type")
                        if type_node:
                            is_struct = type_node.type == "struct_type"
                            struct_fields: list[str] = []
                            methods: list[str] = []

                            if is_struct:
                                field_list = _find(type_node, "field_declaration_list")
                                if field_list:
                                    for f in field_list.children:
                                        if f.type == "field_declaration":
                                            for fc in f.children:
                                                if fc.type == "field_identifier":
                                                    struct_fields.append(_txt(fc, source))
                                                    break

                            nodes.append(CodeNode(
                                name=name,
                                node_type=NodeType.CLASS if is_struct else NodeType.INTERFACE,
                                file_path=rel_path,
                                line_start=node.start_point[0] + 1,
                                line_end=node.end_point[0] + 1,
                                visibility=Visibility.PUBLIC if name[0].isupper() else Visibility.PRIVATE,
                                attributes=struct_fields,
                                meta={"is_struct": is_struct, "fields": struct_fields},
                            ))
            return

        for child in node.children:
            self._walk(child, source, rel_path, nodes, imports)

    def _parse_func(self, node: Node, source: bytes, rel_path: str) -> CodeNode:
        name = ""
        params: list[Parameter] = []
        return_type = None
        calls: set[str] = set()

        for child in node.children:
            if child.type == "identifier":
                name = _txt(child, source)
            elif child.type == "parameter_list":
                params = self._parse_params(child, source)
            elif child.type == "type_identifier" or child.type == "array_type" or child.type == "pointer_type" or child.type == "slice_type" or child.type == "channel_type" or child.type == "function_type" or child.type == "map_type" or child.type == "interface_type" or child.type == "struct_type":
                if not return_type:
                    return_type = _txt(child, source)
            elif child.type in ("block",):
                calls = self._extract_calls(child, source)

        return CodeNode(
            name=name,
            node_type=NodeType.FUNCTION,
            file_path=rel_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            visibility=Visibility.PUBLIC if name and name[0].isupper() else Visibility.PRIVATE,
            parameters=params,
            return_type=return_type,
            calls=list(calls),
        )

    def _parse_method(self, node: Node, source: bytes, rel_path: str) -> CodeNode:
        name = ""
        receiver_type = ""
        params: list[Parameter] = []
        return_type = None
        calls: set[str] = set()

        for child in node.children:
            if child.type == "field_identifier":
                name = _txt(child, source)
            elif child.type == "parameter_list":
                params = self._parse_params(child, source)
            elif child.type == "receiver":
                for rc in child.children:
                    if rc.type == "type_identifier" or rc.type == "pointer_type":
                        receiver_type = _txt(rc, source).lstrip("*")
            elif child.type == "block":
                calls = self._extract_calls(child, source)

        return CodeNode(
            name=name,
            node_type=NodeType.METHOD,
            file_path=rel_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            visibility=Visibility.PUBLIC if name and name[0].isupper() else Visibility.PRIVATE,
            parameters=params,
            return_type=return_type,
            calls=list(calls),
            meta={"receiver": receiver_type},
        )

    def _parse_params(self, node: Node, source: bytes) -> list[Parameter]:
        params = []
        for child in node.children:
            if child.type == "parameter_declaration":
                param_name = ""
                param_type = None
                for pc in child.children:
                    if pc.type == "identifier":
                        param_name = _txt(pc, source)
                    elif pc.type in ("type_identifier", "pointer_type", "slice_type", "array_type", "map_type", "channel_type", "function_type", "ellipsis_parameter", "variadic_parameter"):
                        param_type = _txt(pc, source)
                if param_name:
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
                    elif func.type == "selector_expression":
                        field = _find(func, "field_identifier")
                        if field:
                            calls.add(_txt(field, source))
            for child in current.children:
                stack.append(child)
        return calls
