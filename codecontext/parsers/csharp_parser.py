"""Tree-sitter based parser for C# / .NET."""

from __future__ import annotations

import hashlib
from pathlib import Path

import tree_sitter_c_sharp as tscs
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


CS_LANG = TSLanguage(tscs.language())


def _txt(node: Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _find(node: Node, type_name: str) -> Node | None:
    for c in node.children:
        if c.type == type_name:
            return c
    return None


def _find_all(node: Node, type_name: str) -> list[Node]:
    return [c for c in node.children if c.type == type_name]


class CSharpParser(BaseParser):
    def __init__(self):
        self._parser = Parser(CS_LANG)

    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix in (".cs", ".csx")

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
            language=Language.CSHARP,
            nodes=nodes,
            imports=imports,
            lines_of_code=source.count(b"\n") + 1,
            sha256=sha,
        )

    def _walk(self, node: Node, source: bytes, rel_path: str, nodes: list[CodeNode], imports: list[str]):
        if node.type == "using_directive":
            imports.append(_txt(node, source).strip())
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

        elif node.type == "struct_declaration":
            st = self._parse_class(node, source, rel_path)
            st.node_type = NodeType.CLASS
            nodes.append(st)
            return

        elif node.type == "record_declaration" or node.type == "record_struct_declaration":
            rec = self._parse_class(node, source, rel_path)
            rec.node_type = NodeType.CLASS
            nodes.append(rec)
            return

        elif node.type == "method_declaration":
            nodes.append(self._parse_method(node, source, rel_path))
            return

        elif node.type == "constructor_declaration":
            m = self._parse_method(node, source, rel_path)
            m.name = f"__init__"
            nodes.append(m)
            return

        elif node.type == "delegate_declaration":
            nodes.append(self._parse_delegate(node, source, rel_path))
            return

        elif node.type == "global_attribute_list" or node.type == "attribute_list":
            return

        elif node.type == "namespace_declaration":
            for child in node.children:
                self._walk(child, source, rel_path, nodes, imports)
            return

        for child in node.children:
            self._walk(child, source, rel_path, nodes, imports)

    def _parse_class(self, node: Node, source: bytes, rel_path: str) -> CodeNode:
        name = ""
        visibility = Visibility.PUBLIC
        decorators: list[str] = []
        inherits: list[str] = []
        implements: list[str] = []

        for child in node.children:
            if child.type == "identifier":
                name = _txt(child, source)
            elif child.type == "modifier":
                text = _txt(child, source)
                if "private" in text:
                    visibility = Visibility.PRIVATE
                elif "protected" in text:
                    visibility = Visibility.PROTECTED
                elif "internal" in text:
                    visibility = Visibility.INTERNAL
                elif "public" in text:
                    visibility = Visibility.PUBLIC
            elif child.type == "attribute_list":
                for attr in child.children:
                    if attr.type == "attribute":
                        decorators.append(_txt(attr, source))
            elif child.type == "base_list":
                for bc in child.children:
                    if bc.type in ("identifier", "qualified_name", "generic_name"):
                        base_name = _txt(bc, source)
                        inherits.append(base_name)
            elif child.type == "type_parameter_list":
                pass

        methods: list[CodeNode] = []
        attributes: list[str] = []
        all_calls: set[str] = set()

        body = _find(node, "declaration_list") or _find(node, "class_body")
        if body:
            for child in body.children:
                if child.type == "method_declaration":
                    m = self._parse_method(child, source, rel_path)
                    methods.append(m)
                    all_calls.update(m.calls)
                elif child.type == "constructor_declaration":
                    m = self._parse_method(child, source, rel_path)
                    m.name = "__init__"
                    methods.append(m)
                    all_calls.update(m.calls)
                elif child.type == "property_declaration":
                    prop_name = child.child_by_field_name("name")
                    if prop_name:
                        attributes.append(_txt(prop_name, source))
                elif child.type == "field_declaration":
                    for vc in child.children:
                        if vc.type == "variable_declaration":
                            for vc2 in vc.children:
                                if vc2.type == "variable_declarator":
                                    vn = _find(vc2, "identifier")
                                    if vn:
                                        attributes.append(_txt(vn, source))

        is_interface = node.type == "interface_declaration"
        if is_interface:
            implements = list(inherits)
            inherits = []
        else:
            split_inherits = []
            for base_name in inherits:
                simple = base_name.split(".")[-1].split("<")[0]
                if simple.startswith("I") and len(simple) > 1 and simple[1].isupper():
                    implements.append(base_name)
                else:
                    split_inherits.append(base_name)
            inherits = split_inherits

        return CodeNode(
            name=name,
            node_type=NodeType.CLASS,
            file_path=rel_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            visibility=visibility,
            decorators=decorators,
            inherits_from=inherits,
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
            if child.type == "identifier":
                if not name:
                    name = _txt(child, source)
            elif child.type == "modifier":
                text = _txt(child, source)
                if "private" in text:
                    visibility = Visibility.PRIVATE
                elif "protected" in text:
                    visibility = Visibility.PROTECTED
                elif "internal" in text:
                    visibility = Visibility.INTERNAL
                elif "public" in text:
                    visibility = Visibility.PUBLIC
                elif "static" in text:
                    decorators.append("static")
                elif "async" in text:
                    decorators.append("async")
                elif "override" in text:
                    decorators.append("override")
                elif "virtual" in text:
                    decorators.append("virtual")
                elif "abstract" in text:
                    decorators.append("abstract")
            elif child.type == "parameter_list":
                params = self._parse_params(child, source)
            elif child.type in ("type", "predefined_type", "identifier", "qualified_name", "generic_name", "array_type", "nullable_type", "void_keyword"):
                if not return_type:
                    return_type = _txt(child, source)
            elif child.type == "attribute_list":
                for attr in child.children:
                    if attr.type == "attribute":
                        decorators.append(_txt(attr, source))
            elif child.type == "block" or child.type == "arrow_expression_clause" or child.type == "block_body":
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

    def _parse_delegate(self, node: Node, source: bytes, rel_path: str) -> CodeNode:
        name = ""
        params: list[Parameter] = []
        return_type = None

        for child in node.children:
            if child.type == "identifier":
                name = _txt(child, source)
            elif child.type == "parameter_list":
                params = self._parse_params(child, source)
            elif child.type in ("type", "predefined_type", "void_keyword", "identifier", "qualified_name"):
                if not return_type:
                    return_type = _txt(child, source)

        return CodeNode(
            name=name,
            node_type=NodeType.FUNCTION,
            file_path=rel_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            parameters=params,
            return_type=return_type,
        )

    def _parse_params(self, node: Node, source: bytes) -> list[Parameter]:
        params = []
        for child in node.children:
            if child.type == "parameter":
                param_name = ""
                param_type = None
                for pc in child.children:
                    if pc.type == "identifier":
                        param_name = _txt(pc, source)
                    elif pc.type in ("type", "predefined_type", "qualified_name", "generic_name", "array_type", "nullable_type"):
                        if not param_type:
                            param_type = _txt(pc, source)
                if param_name:
                    params.append(Parameter(name=param_name, type_hint=param_type))
        return params

    def _extract_calls(self, node: Node, source: bytes) -> set[str]:
        calls = set()
        stack = [node]
        while stack:
            current = stack.pop()
            if current.type == "invocation_expression":
                func = current.child_by_field_name("function")
                if func:
                    if func.type == "identifier":
                        calls.add(_txt(func, source))
                    elif func.type == "member_access_expression":
                        prop = _find(func, "identifier")
                        if prop:
                            calls.add(_txt(prop, source))
            for child in current.children:
                stack.append(child)
        return calls
