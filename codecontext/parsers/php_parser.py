"""Tree-sitter based parser for PHP with Laravel awareness."""

from __future__ import annotations

import hashlib
from pathlib import Path

import tree_sitter_php as tsphp
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

_PHP_LANG = TSLanguage(tsphp.language_php())


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _find_first_child(node: Node, type_name: str) -> Node | None:
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _find_all_children(node: Node, type_name: str) -> list[Node]:
    return [c for c in node.children if c.type == type_name]


class PhpParser(BaseParser):
    def __init__(self):
        self._parser = Parser(_PHP_LANG)

    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix in (".php",)

    def parse(self, file_path: Path, root: Path) -> FileSummary:
        source = file_path.read_bytes()
        rel_path = self._relative_path(file_path, root)
        sha = hashlib.sha256(source).hexdigest()[:16]

        tree = self._parser.parse(source)
        nodes: list[CodeNode] = []
        imports: list[str] = []

        self._walk(tree.root_node, source, rel_path, nodes, imports)

        laravel_type = self._detect_laravel_type(file_path, nodes)
        if laravel_type:
            for n in nodes:
                if n.node_type == NodeType.CLASS:
                    n.node_type = laravel_type

        return FileSummary(
            file_path=rel_path,
            language=Language.PHP,
            nodes=nodes,
            imports=imports,
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
    ):
        if node.type == "namespace_definition":
            name_node = _find_first_child(node, "namespace_name")
            if name_node:
                imports.append(f"namespace {_node_text(name_node, source)}")

        elif node.type == "namespace_use_declaration":
            imports.append(_node_text(node, source).strip())

        elif node.type == "class_declaration":
            nodes.append(self._parse_class(node, source, rel_path))
            return

        elif node.type == "interface_declaration":
            cls = self._parse_class(node, source, rel_path)
            cls.node_type = NodeType.INTERFACE
            nodes.append(cls)
            return

        elif node.type == "enum_declaration":
            cls = self._parse_class(node, source, rel_path)
            cls.node_type = NodeType.ENUM
            nodes.append(cls)
            return

        elif node.type == "trait_declaration":
            cls = self._parse_class(node, source, rel_path)
            cls.node_type = NodeType.TRAIT
            nodes.append(cls)
            return

        elif node.type == "function_definition":
            nodes.append(self._parse_function(node, source, rel_path))
            return

        for child in node.children:
            self._walk(child, source, rel_path, nodes, imports)

    def _parse_class(self, node: Node, source: bytes, rel_path: str) -> CodeNode:
        name = ""
        for child in node.children:
            if child.type == "name":
                name = _node_text(child, source)
                break

        extends = []
        implements = []
        for child in node.children:
            if child.type == "base_clause":
                extends.append(_node_text(child, source).replace("extends ", "").strip())
            elif child.type == "interface_clause":
                impl = _node_text(child, source).replace("implements ", "").strip()
                implements = [i.strip() for i in impl.split(",")]

        methods: list[CodeNode] = []
        attributes: list[str] = []
        all_calls: set[str] = set()

        class_body = _find_first_child(node, "declaration_list")
        if class_body:
            for child in class_body.children:
                if child.type == "class_constant_declaration":
                    for const in _find_all_children(child, "const_element"):
                        const_name = _find_first_child(const, "name")
                        if const_name:
                            attributes.append(_node_text(const_name, source))
                elif child.type == "property_element" or child.type == "property_declaration":
                    prop_name = None
                    for pc in child.children:
                        if pc.type == "variable_name" or pc.type == "property_declaration":
                            prop_name = _node_text(pc, source).lstrip("$")
                            break
                    if prop_name:
                        attributes.append(prop_name)
                elif child.type == "method_declaration":
                    method = self._parse_method(child, source, rel_path)
                    methods.append(method)
                    all_calls.update(method.calls)

        visibility = Visibility.PUBLIC
        for child in node.children:
            if child.type == "modifier":
                text = _node_text(child, source)
                if "abstract" in text:
                    visibility = Visibility.PUBLIC
                    break

        return CodeNode(
            name=name,
            node_type=NodeType.CLASS,
            file_path=rel_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            visibility=visibility,
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
            if child.type == "modifier":
                text = _node_text(child, source)
                if "private" in text:
                    visibility = Visibility.PRIVATE
                elif "protected" in text:
                    visibility = Visibility.PROTECTED
                elif "public" in text:
                    visibility = Visibility.PUBLIC
                elif "static" in text:
                    decorators.append("static")
            elif child.type == "name":
                name = _node_text(child, source)
            elif child.type == "formal_parameters":
                params = self._parse_params(child, source)
            elif child.type == "type_declaration" or child.type == "union_type" or child.type == "intersection_type":
                return_type = _node_text(child, source).strip()
            elif child.type == "attribute":
                attr_text = _node_text(child, source)
                decorators.append(attr_text.strip("#[] \n"))
            elif child.type == "compound_statement" or child.type == "block":
                calls = self._extract_calls_from_block(child, source)

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
            if child.type == "name":
                name = _node_text(child, source)
            elif child.type == "formal_parameters":
                params = self._parse_params(child, source)
            elif child.type == "type_declaration":
                return_type = _node_text(child, source).strip()
            elif child.type == "compound_statement":
                calls = self._extract_calls_from_block(child, source)

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
            if child.type == "simple_parameter" or child.type == "variadic_parameter":
                param_name = ""
                param_type = None
                for pc in child.children:
                    if pc.type == "variable_name":
                        param_name = _node_text(pc, source).lstrip("$")
                    elif pc.type in ("type_declaration", "union_type", "intersection_type", "named_type", "primitive_type", "nullable_type"):
                        param_type = _node_text(pc, source).strip()
                if param_name:
                    params.append(Parameter(name=param_name, type_hint=param_type))
        return params

    def _extract_calls_from_block(self, node: Node, source: bytes) -> set[str]:
        calls = set()
        stack = [node]
        while stack:
            current = stack.pop()
            if current.type == "function_call_expression":
                func = current.child_by_field_name("function")
                if func:
                    if func.type == "name":
                        calls.add(_node_text(func, source))
                    elif func.type == "member_access_expression" or func.type == "scoped_access_expression":
                        method = _find_first_child(func, "name")
                        if method:
                            calls.add(_node_text(method, source))
            elif current.type == "member_access_expression":
                method = _find_first_child(current, "name")
                if method:
                    calls.add(_node_text(method, source))
            elif current.type == "scoped_call_expression":
                method = current.child_by_field_name("name")
                if method:
                    calls.add(_node_text(method, source))
            for child in current.children:
                stack.append(child)
        return calls

    def _detect_laravel_type(self, file_path: Path, nodes: list[CodeNode]) -> NodeType | None:
        path_str = str(file_path).replace("\\", "/")
        name = file_path.stem

        laravel_patterns = {
            "/Controllers/": NodeType.CONTROLLER,
            "/Models/": NodeType.MODEL,
            "/Middleware/": NodeType.MIDDLEWARE,
            "/Services/": NodeType.SERVICE,
            "/Repositories/": NodeType.REPOSITORY,
            "/Migrations/": NodeType.MIGRATION,
            "/Routes/": NodeType.ROUTE,
            "/Commands/": NodeType.COMMAND,
            "/Events/": NodeType.EVENT,
            "/Listeners/": NodeType.LISTENER,
            "/Jobs/": NodeType.JOB,
            "/Policies/": NodeType.POLICY,
            "/Requests/": NodeType.REQUEST,
            "/Resources/": NodeType.RESOURCE,
            "/Providers/": NodeType.PROVIDER,
            "/Tests/": NodeType.TEST,
        }

        for pattern, ntype in laravel_patterns.items():
            if pattern.lower() in path_str.lower():
                return ntype

        for n in nodes:
            if n.node_type == NodeType.CLASS:
                inherits = " ".join(n.inherits_from)
                if "Controller" in inherits or n.name.endswith("Controller"):
                    return NodeType.CONTROLLER
                if "Model" in inherits or "Eloquent" in inherits:
                    return NodeType.MODEL
                if "Middleware" in inherits:
                    return NodeType.MIDDLEWARE
                if "Migration" in inherits:
                    return NodeType.MIGRATION
                if "Command" in inherits:
                    return NodeType.COMMAND
                if "Request" in inherits and "FormRequest" in inherits:
                    return NodeType.REQUEST
                if "Resource" in inherits and ("JsonResource" in inherits or "ResourceCollection" in inherits):
                    return NodeType.RESOURCE
                if "Policy" in inherits:
                    return NodeType.POLICY
                if "Event" in inherits and "dispatch" in n.meta.get("methods", []):
                    return NodeType.EVENT
                if "Job" in inherits or "ShouldQueue" in " ".join(n.implements):
                    return NodeType.JOB
                if "Provider" in inherits or n.name.endswith("ServiceProvider"):
                    return NodeType.PROVIDER
                if n.name.startswith("Test") or "TestCase" in inherits:
                    return NodeType.TEST

        return None
