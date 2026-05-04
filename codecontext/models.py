"""Core data models for CodeContext."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Language(str, Enum):
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    PHP = "php"
    GO = "go"
    RUST = "rust"
    CSHARP = "csharp"
    UNKNOWN = "unknown"


class NodeType(str, Enum):
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    INTERFACE = "interface"
    TRAIT = "trait"
    ENUM = "enum"
    CONSTANT = "constant"
    VARIABLE = "variable"
    NAMESPACE = "namespace"
    MODULE = "module"
    CONTROLLER = "controller"
    MODEL = "model"
    MIDDLEWARE = "middleware"
    SERVICE = "service"
    REPOSITORY = "repository"
    MIGRATION = "migration"
    ROUTE = "route"
    COMMAND = "command"
    EVENT = "event"
    LISTENER = "listener"
    JOB = "job"
    POLICY = "policy"
    REQUEST = "request"
    RESOURCE = "resource"
    PROVIDER = "provider"
    TEST = "test"


class Visibility(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    PROTECTED = "protected"
    INTERNAL = "internal"


@dataclass
class Parameter:
    name: str
    type_hint: Optional[str] = None
    default_value: Optional[str] = None


@dataclass
class CodeNode:
    name: str
    node_type: NodeType
    file_path: str
    line_start: int
    line_end: int
    visibility: Visibility = Visibility.PUBLIC
    parameters: list[Parameter] = field(default_factory=list)
    return_type: Optional[str] = None
    decorators: list[str] = field(default_factory=list)
    inherits_from: list[str] = field(default_factory=list)
    implements: list[str] = field(default_factory=list)
    docstring: Optional[str] = None
    calls: list[str] = field(default_factory=list)
    attributes: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


@dataclass
class DependencyEdge:
    source_file: str
    target_file: str
    import_type: str = "import"
    symbols: list[str] = field(default_factory=list)


@dataclass
class FileSummary:
    file_path: str
    language: Language
    nodes: list[CodeNode] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    lines_of_code: int = 0
    sha256: str = ""


@dataclass
class RouteEntry:
    http_method: str
    uri: str
    controller: str
    method: str
    name: Optional[str] = None
    middleware: list[str] = field(default_factory=list)
    file_path: str = ""


@dataclass
class ModelRelation:
    model_file: str
    model_class: str
    relation_type: str
    relation_name: str
    related_class: str
    line: int = 0


@dataclass
class ModelField:
    name: str
    type: str = ""
    nullable: bool = False
    default: Optional[str] = None
    is_foreign_key: bool = False
    references_table: Optional[str] = None
    references_column: Optional[str] = None


@dataclass
class MigrationTable:
    name: str
    file_path: str
    action: str = "create"
    columns: list[ModelField] = field(default_factory=list)
    indexes: list[str] = field(default_factory=list)
    unique_constraints: list[str] = field(default_factory=list)


@dataclass
class Risk:
    severity: str
    category: str
    message: str
    location: str
    detail: str = ""


@dataclass
class TraceChain:
    route_uri: str
    route_method: str
    chain: list[str] = field(default_factory=list)
    middleware: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)


@dataclass
class ProjectIndex:
    root_path: str
    files: list[FileSummary] = field(default_factory=list)
    dependencies: list[DependencyEdge] = field(default_factory=list)
    architecture: dict = field(default_factory=dict)
    entry_points: list[str] = field(default_factory=list)
    routes: list[RouteEntry] = field(default_factory=list)
    model_relations: list[ModelRelation] = field(default_factory=list)
    migrations: list[MigrationTable] = field(default_factory=list)
    risks: list[Risk] = field(default_factory=list)
    traces: list[TraceChain] = field(default_factory=list)
    role_map: dict = field(default_factory=dict)
    generated_at: str = ""
