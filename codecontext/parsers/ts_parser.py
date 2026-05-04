"""Tree-sitter based parser for TypeScript and JavaScript."""

from __future__ import annotations

import hashlib
from pathlib import Path

import tree_sitter_typescript as tstypescript
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


_TS_LANG = TSLanguage(tstypescript.language_typescript())


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _find_first(node: Node, type_name: str) -> Node | None:
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _find_all(node: Node, type_name: str) -> list[Node]:
    return [c for c in node.children if c.type == type_name]


class TypeScriptParser(BaseParser):
    def __init__(self):
        self._ts_parser = Parser(_TS_LANG)
        self._js_parser = Parser(_TS_LANG)

    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")

    def parse(self, file_path: Path, root: Path) -> FileSummary:
        source = file_path.read_bytes()
        rel_path = self._relative_path(file_path, root)
        sha = hashlib.sha256(source).hexdigest()[:16]

        is_ts = file_path.suffix in (".ts", ".tsx")
        parser = self._ts_parser if is_ts else self._js_parser
        lang = Language.TYPESCRIPT if is_ts else Language.JAVASCRIPT

        tree = parser.parse(source)
        nodes: list[CodeNode] = []
        imports: list[str] = []
        exports: list[str] = []

        self._walk(tree.root_node, source, rel_path, nodes, imports, exports)

        return FileSummary(
            file_path=rel_path,
            language=lang,
            nodes=nodes,
            imports=imports,
            exports=exports,
            lines_of_code=source.count(b"\n") + 1,
            sha256=sha,
        )

    def _walk(
        self,
        node: Node,
        source: bytes,
        rel_path: str,
        nodes: list[CodeNode],
        imports: list[str],
        exports: list[str],
    ):
        if node.type == "import_statement" or node.type == "import_declaration":
            imports.append(_node_text(node, source).strip())
            return

        elif node.type == "export_statement":
            text = _node_text(node, source).strip()
            exports.append(text)
            for child in node.children:
                if child.type in (
                    "function_declaration",
                    "class_declaration",
                    "interface_declaration",
                    "enum_declaration",
                    "lexical_declaration",
                    "variable_declaration",
                ):
                    self._walk(child, source, rel_path, nodes, imports, exports)
            return

        elif node.type == "class_declaration":
            nodes.append(self._parse_class(node, source, rel_path))
            return

        elif node.type == "interface_declaration":
            iface = self._parse_class(node, source, rel_path)
            iface.node_type = NodeType.INTERFACE
            nodes.append(iface)
            return

        elif node.type == "enum_declaration":
            en = self._parse_class(node, source, rel_path)
            en.node_type = NodeType.ENUM
            nodes.append(en)
            return

        elif node.type == "function_declaration":
            nodes.append(self._parse_function(node, source, rel_path))
            return

        elif node.type == "arrow_function" or node.type == "function_expression":
            parent = node.parent
            if parent and parent.type == "variable_declarator":
                var_name = _find_first(parent, "identifier")
                if var_name:
                    fn = self._parse_function(node, source, rel_path)
                    fn.name = _node_text(var_name, source)
                    nodes.append(fn)
            return

        elif node.type == "lexical_declaration" or node.type == "variable_declaration":
            for child in node.children:
                if child.type == "variable_declarator":
                    name_node = _find_first(child, "identifier")
                    value_node = _find_first(child, "arrow_function") or _find_first(child, "function_expression")
                    if value_node and name_node:
                        fn = self._parse_function(value_node, source, rel_path)
                        fn.name = _node_text(name_node, source)
                        nodes.append(fn)

        for child in node.children:
            self._walk(child, source, rel_path, nodes, imports, exports)

    def _parse_class(self, node: Node, source: bytes, rel_path: str) -> CodeNode:
        name = ""
        for child in node.children:
            if child.type == "type_identifier" or child.type == "identifier":
                name = _node_text(child, source)
                break

        extends = []
        implements = []
        heritage = _find_first(node, "class_heritage")
        if heritage:
            for child in heritage.children:
                if child.type == "extends_clause":
                    extends.append(_node_text(child, source).replace("extends ", "").strip())
                elif child.type == "implements_clause":
                    impl = _node_text(child, source).replace("implements ", "").strip()
                    implements = [i.strip() for i in impl.split(",")]

        methods: list[CodeNode] = []
        attributes: list[str] = []
        all_calls: set[str] = set()

        body = _find_first(node, "class_body") or _find_first(node, "object_type")
        if body:
            for child in body.children:
                if child.type == "method_definition" or child.type == "public_field_definition":
                    if child.type == "public_field_definition":
                        prop_name = child.child_by_field_name("name")
                        if prop_name:
                            attributes.append(_node_text(prop_name, source))
                    else:
                        method = self._parse_method(child, source, rel_path)
                        methods.append(method)
                        all_calls.update(method.calls)
                elif child.type == "property_declaration" or child.type == "field_definition":
                    prop_name = child.child_by_field_name("name")
                    if prop_name:
                        attributes.append(_node_text(prop_name, source))

        return CodeNode(
            name=name,
            node_type=NodeType.CLASS,
            file_path=rel_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            inherits_from=extends,
            implements=implements,
            calls=list(all_calls),
            attributes=attributes,
            meta={"methods": [m.name for m in methods], "methods_count": len(methods)},
        )

    def _parse_method(self, node: Node, source: bytes, rel_path: str) -> CodeNode:
        name = ""
        visibility = Visibility.PUBLIC
        params: list[Parameter] = []
        return_type = None
        decorators: list[str] = []
        calls: set[str] = set()

        for child in node.children:
            if child.type == "property_identifier" or child.type == "identifier":
                name = _node_text(child, source)
            elif child.type == "accessibility_modifier":
                text = _node_text(child, source)
                if "private" in text:
                    visibility = Visibility.PRIVATE
                elif "protected" in text:
                    visibility = Visibility.PROTECTED
            elif child.type == "formal_parameters" or child.type == "parameters":
                params = self._parse_params(child, source)
            elif child.type == "type_annotation":
                return_type = _node_text(child, source).strip().lstrip(":").strip()
            elif child.type == "decorator":
                decorators.append(_node_text(child, source).strip())
            elif child.type in ("statement_block", "function_body"):
                calls = self._extract_calls(child, source)

        return CodeNode(
            name=name,
            node_type=NodeType.METHOD,
            file_path=rel_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            visibility=visibility,
            parameters=params,
            return_type=return_type,
            decorators=decorators,
            calls=list(calls),
        )

    def _parse_function(self, node: Node, source: bytes, rel_path: str) -> CodeNode:
        name = ""
        params: list[Parameter] = []
        return_type = None
        calls: set[str] = set()

        for child in node.children:
            if child.type == "identifier" or child.type == "property_identifier":
                name = _node_text(child, source)
            elif child.type == "formal_parameters" or child.type == "parameters":
                params = self._parse_params(child, source)
            elif child.type == "type_annotation":
                return_type = _node_text(child, source).strip().lstrip(":").strip()
            elif child.type in ("statement_block", "function_body"):
                calls = self._extract_calls(child, source)

        return CodeNode(
            name=name,
            node_type=NodeType.FUNCTION,
            file_path=rel_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parameters=params,
            return_type=return_type,
            calls=list(calls),
        )

    def _parse_params(self, node: Node, source: bytes) -> list[Parameter]:
        params = []
        for child in node.children:
            if child.type == "required_parameter" or child.type == "optional_parameter" or child.type == "rest_parameter":
                param_name = ""
                param_type = None
                for pc in child.children:
                    if pc.type == "identifier" or pc.type == "property_identifier":
                        param_name = _node_text(pc, source)
                    elif pc.type == "type_annotation":
                        param_type = _node_text(pc, source).strip().lstrip(":").strip()
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
                        calls.add(_node_text(func, source))
                    elif func.type == "member_expression":
                        prop = _find_first(func, "property_identifier")
                        if prop:
                            calls.add(_node_text(prop, source))
            for child in current.children:
                stack.append(child)
        return calls
