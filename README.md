<p align="center">
  <h1 align="center">CodeContext</h1>
  <p align="center">
    <strong>Generate compact code context for AI agents from any codebase</strong>
  </p>
  <p align="center">
    No LLM. No tokens. Pure static analysis.
  </p>
</p>

---

## What it does

CodeContext scans your codebase using AST and tree-sitter parsers, then generates a **compact context file (~1,000 tokens)** that gives AI agents a complete understanding of your project structure, architecture, data model, routes, permissions, and risks — without reading a single source file.

**78,000 LOC Laravel project → 1,487 tokens. 120,000 LOC → 906 tokens.**

---

## Features

### Multi-language parsing
| Language | Parser | Extracts |
|----------|--------|----------|
| **Python** | Built-in `ast` | Classes, functions, methods, decorators, type hints, imports |
| **PHP / Laravel** | tree-sitter | Controllers, Models, Services, Middleware, Policies, Jobs, Commands, Requests |
| **TypeScript / JavaScript** | tree-sitter | Classes, interfaces, functions, exports, type annotations |
| **Go** | tree-sitter | Structs, interfaces, functions, methods, receivers |
| **Rust** | tree-sitter | Structs, enums, traits, impls, functions |
| **C# / .NET** | tree-sitter | Classes, interfaces, structs, records, methods, properties |

### Laravel-specific deep analysis
- **Route extraction** — URL → Controller@method mapping with middleware and names
- **Model relationships** — `hasMany`, `belongsTo`, `belongsToMany`, etc.
- **Database schema** — Migration columns, foreign keys, indexes, unique constraints
- **Blade views** — 124 views with `@extends`, `@include`, `<livewire:>`, `<x-*>` components, `{{ route() }}` refs
- **Observers** — `Model::observe()` registration extraction (created/updated/deleted events)
- **Events & Listeners** — `EventServiceProvider` `$listen` arrays, `event()` dispatch mapping
- **Livewire detection** — Automatic identification of Livewire components
- **Fillable/casts/traits** — Model properties extracted from code

### Risk detection (static rules, no AI)
- **God classes** — Classes with 15+ methods flagged
- **Missing validation** — Controllers with write methods but no FormRequest
- **Unprotected routes** — Routes without auth middleware
- **Missing indexes** — Foreign keys without explicit index
- **Duplicate methods** — Same method name across 3+ files
- **Large files** — Files over 500 LOC highlighted
- **Gap detection** — Missing policies, missing tests per controller, routes without permissions

### YAML Rules Engine
Define custom static analysis rules in YAML. 11 built-in check types:

| Check | What it verifies |
|-------|-----------------|
| `migration_has_unique` | Unique constraint exists in migration |
| `migration_has_unique_or_code_guard` | Unique constraint OR code-level guard (firstOrCreate, unique validation, etc.) |
| `migration_has_column` | Required columns exist in table |
| `model_has_relation` | Eloquent relationship exists on model |
| `route_has_middleware` | Routes have required middleware |
| `route_has_policy` | Policy class exists for a model |
| `route_has_test` | Test class exists for a controller |
| `class_max_methods` | Flag classes with too many methods |
| `file_max_loc` | Flag files over size limit |
| `table_has_index_on_fk` | Foreign keys without explicit index |
| `no_bare_try_catch` | Flag bare try/catch blocks |

```yaml
rules:
  - id: DB-001
    title: "Active enrollment unique per student per year"
    severity: high
    check: migration_has_unique_or_code_guard
    query:
      table: enrollments
      invariant: "max 1 active enrollment per user per academic year"
      expected_unique_on: ["user_id", "academic_year_id", "status"]
```

### CI/CD Integration
```bash
# Fails with exit code 1 if blocking issues found
codecontext ci /path/to/project --fail-on high
codecontext ci /path/to/project --rules ./rules.yaml
```
Outputs `issues.json` with all detected risks for pipeline integration.

### Traceability chains
```
GET /panel/asistencias → AttendanceManagement (Livewire)
  → AttendanceService → GeofenceService → Observer → AbsenceAlertService
  Middleware: auth, force_password_change
  Permission: attendances.register
```

### Role & permission map
Automatically extracts roles from `middleware('role:Admin|Director')` and maps which routes each role can access.

### MCP Server for AI Agents
Live query interface for AI agents via Model Context Protocol (stdio transport):

```json
{
  "mcpServers": {
    "codecontext": {
      "command": "codecontext-mcp"
    }
  }
}
```

9 tools: `scan_project`, `get_summary`, `query_symbols`, `query_routes`, `query_data_model`, `query_schema`, `query_risks`, `query_trace`, `query_blade`

### 5-layer output

| File | Purpose | Size |
|------|---------|------|
| `SUMMARY.md` | Inject into AI agent prompt | **~1,000 tokens** |
| `context.json` | Structured data for querying | Full |
| `CONTEXT.md` | Human-readable report | Full |
| `deps.json` | Dependency graph + circular deps | Full |
| `issues.json` | CI issues with severity | Full |

### Architecture detection
Automatically detects: **Laravel**, **Next.js**, **React**, **Django**, **FastAPI**, **Flask**, **Go standard layout**, **Rust**, **Avalonia UI + EF Core**

---

## Installation

```bash
pip install git+https://github.com/hmvillalba/codecontext.git
```

For local development:
```bash
git clone https://github.com/hmvillalba/codecontext.git
cd codecontext
pip install -e .
```

Requires Python 3.10+.

---

## Usage

### Scan a project

```bash
# Scan current directory
codecontext scan .

# Scan a specific project
codecontext scan /path/to/project

# Scan and print compact JSON to stdout
codecontext scan /path/to/project --compact

# Custom output directory
codecontext scan /path/to/project --output ./my-context

# Scan with custom rules
codecontext scan /path/to/project --rules ./rules.yaml
```

### CI/CD

```bash
# Fail pipeline if high/critical issues found
codecontext ci /path/to/project --fail-on high

# With custom rules
codecontext ci /path/to/project --rules ./rules.yaml
```

### Query the context

```bash
# Search for a symbol
codecontext query /path/to/project --symbol User

# Filter by type
codecontext query /path/to/project --type controller

# Show specific file
codecontext query /path/to/project --file "AuthController"
```

---

## Output files

### SUMMARY.md (~1,000 tokens)

```markdown
# school-attendance
laravel | php | 546 files | 78,707 LOC | 316 symbols

## Domain
Entities: Attendance, Enrollment, Course, Division, User, Shift...
Routes: 166 (GET 101, POST 52, DELETE 9)
DB tables: 45

## Key Flows
- GET /staff-dashboard → Livewire:Dashboard
- GET /escaner/preceptor → Livewire:PreceptorScanner (roles: Preceptor, Docente)
- POST /panel/asistencias → Controller:AttendanceManagement@store

## Data Model
- Attendance: enrollment←Enrollment, justifications→*AttendanceJustification
- Enrollment: user←User, course←Course, attendances→*Attendance

## Views & Observers
- Blade: 124 views (58 livewire, 136 route refs)
- Observers: Attendance→AttendanceObserver, StaffAttendance→StaffAttendanceObserver

## Risks
- [!!] god-class: AttendanceManagement has 34 methods
- [!] missing-validation: AcademicStageController has no Request class
```

### context.json

Full structured data including:
- File tree with symbol tables
- Route map with middleware
- Model relationships
- Database schema (columns, FKs, indexes)
- Blade views with component/livewire/route references
- Observer and Event mappings
- Dependency graph
- Risk list with severity and location

### CONTEXT.md

Complete human-readable report with:
- Overview (languages, symbol types)
- Architecture layers
- File tree with LOC counts
- Routes by HTTP method
- Model relationship diagram
- Database schema tables
- Blade views by directory
- Observer & Event mappings
- Symbol reference (all classes, methods, functions with signatures)
- Dependency map

---

## How it works

```
Source files
    │
    ├── Python ──── ast module
    ├── PHP ─────── tree-sitter-php
    ├── TS/JS ───── tree-sitter-typescript
    ├── Go ──────── tree-sitter-go
    ├── Rust ────── tree-sitter-rust
    └── C# ──────── tree-sitter-c-sharp
          │
          ▼
    Parsed nodes (classes, methods, functions, imports)
          │
          ├── Dependency resolver ──→ import graph, circular deps
          ├── Architecture detector → pattern detection
          ├── Route extractor ──────→ URL → controller map
          ├── Model extractor ──────→ Eloquent relationships
          ├── Schema extractor ─────→ migration columns, FKs
          ├── Blade extractor ──────→ views, includes, components
          ├── Observer extractor ───→ Model → Observer mapping
          ├── Risk detector ────────→ rule-based warnings
          ├── Gap detector ─────────→ missing policies/tests/validators
          ├── Rules engine ─────────→ YAML custom rules
          └── Trace builder ────────→ route→controller→service→model
                  │
                  ▼
    SUMMARY.md (1K tokens) + context.json + CONTEXT.md + issues.json
```

---

## Benchmarks

| Project | Language | Files | LOC | Symbols | SUMMARY tokens | Compression |
|---------|----------|-------|-----|---------|----------------|-------------|
| school-attendance | PHP/Laravel | 546 | 78,707 | 316 | 1,487 | 53:1 |
| gestionescolar | PHP/Laravel | 824 | 120,626 | 869 | 906 | 133:1 |
| facturador | C#/.NET | 262 | 44,423 | 314 | ~800 | 55:1 |
| fact-elec-service | Go | 88 | 11,158 | 477 | ~400 | 28:1 |

---

## Project structure

```
codecontext/
├── cli.py                 # CLI (typer) — scan, ci, query commands
├── models.py              # Data models (CodeNode, RouteEntry, Risk, BladeView, etc.)
├── scanner.py             # Core orchestration engine
├── mcp/
│   └── server.py          # MCP server for live AI agent queries (9 tools)
├── parsers/
│   ├── python_parser.py   # AST-based Python parser
│   ├── php_parser.py      # tree-sitter PHP + Laravel detection
│   ├── ts_parser.py       # tree-sitter TypeScript/JavaScript
│   ├── go_parser.py       # tree-sitter Go
│   ├── rust_parser.py     # tree-sitter Rust
│   └── csharp_parser.py   # tree-sitter C# / .NET
├── analyzers/
│   ├── architecture.py    # Framework pattern detection
│   ├── dependency.py      # Import graph + circular deps
│   ├── routes.py          # Laravel route extraction
│   ├── model_relations.py # Eloquent relationship extraction
│   ├── migrations.py      # Schema extraction from migrations
│   ├── blade_views.py     # Blade view extraction (includes, livewire, routes)
│   ├── observers.py       # Observer + Event/Listener mapping
│   ├── risks.py           # Static risk detection (built-in rules)
│   ├── gaps.py            # Gap detection (missing policies/tests/validators)
│   └── traceability.py    # Route→Controller→Service→Model chains
├── rules/
│   ├── engine.py          # YAML rule loader + evaluator (11 check types)
│   └── default.yaml       # Default rules shipped with CodeContext
└── generators/
    ├── __init__.py        # JSON index generator
    ├── markdown.py        # Full CONTEXT.md generator
    ├── summary.py         # Compact SUMMARY.md generator
    └── issues.py          # CI issues.json generator
```

---

## Roadmap

- [x] Blade view extraction (extends, includes, livewire, components, route refs)
- [x] Observer/Event/Listener mapping
- [x] YAML rules engine (11 check types)
- [x] CI/CD integration (exit codes, issues.json)
- [x] MCP server for live agent queries (9 tools)
- [ ] Multi-language extractors (C#/.NET EF Core, Python Django/Flask, Go)
- [ ] Incremental updates (`--update` flag, hash-based)
- [ ] Spring Boot / Java support
- [ ] HTML visualization
- [ ] Neo4j export

---

## License

MIT

---
---

<p align="center">
  <h2 align="center">CodeContext</h2>
  <p align="center">
    <strong>Genera contexto compacto de código para agentes de IA desde cualquier codebase</strong>
  </p>
  <p align="center">
    Sin LLM. Sin tokens. Análisis estático puro.
  </p>
</p>

---

## Qué hace

CodeContext escanea tu código usando parsers AST y tree-sitter, y genera un **archivo de contexto compacto (~1,000 tokens)** que le da a los agentes de IA una comprensión completa de tu proyecto — estructura, arquitectura, modelo de datos, rutas, permisos y riesgos — sin leer un solo archivo fuente.

**78,000 LOC en Laravel → 1,487 tokens. 120,000 LOC → 906 tokens.**

---

## Características

### Parseo multi-lenguaje
| Lenguaje | Parser | Extrae |
|----------|--------|--------|
| **Python** | `ast` nativo | Clases, funciones, métodos, decoradores, type hints, imports |
| **PHP / Laravel** | tree-sitter | Controllers, Models, Services, Middleware, Policies, Jobs, Commands, Requests |
| **TypeScript / JavaScript** | tree-sitter | Clases, interfaces, funciones, exports, anotaciones de tipo |
| **Go** | tree-sitter | Structs, interfaces, funciones, métodos, receivers |
| **Rust** | tree-sitter | Structs, enums, traits, impls, funciones |
| **C# / .NET** | tree-sitter | Clases, interfaces, structs, records, métodos, propiedades |

### Análisis profundo para Laravel
- **Extracción de rutas** — Mapeo URL → Controller@method con middleware y nombres
- **Relaciones de modelos** — `hasMany`, `belongsTo`, `belongsToMany`, etc.
- **Schema de base de datos** — Columnas de migraciones, foreign keys, índices, unique constraints
- **Vistas Blade** — 124 vistas con `@extends`, `@include`, `<livewire:>`, `<x-*>`, `{{ route() }}`
- **Observers** — Extracción de registros `Model::observe()` (eventos created/updated/deleted)
- **Events & Listeners** — Arrays `$listen` de EventServiceProvider, mapeo de `event()`
- **Detección de Livewire** — Identificación automática de componentes Livewire
- **Fillable/casts/traits** — Propiedades de modelos extraídas del código

### Detección de riesgos (reglas estáticas, sin IA)
- **God classes** — Clases con 15+ métodos marcadas
- **Validación faltante** — Controllers con métodos de escritura sin FormRequest
- **Rutas desprotegidas** — Rutas sin middleware de autenticación
- **Índices faltantes** — Foreign keys sin índice explícito
- **Métodos duplicados** — Mismo nombre de método en 3+ archivos
- **Archivos grandes** — Archivos de más de 500 LOC destacados
- **Detección de gaps** — Policies faltantes, tests faltantes por controller, rutas sin permisos

### Motor de reglas YAML
Define reglas custom de análisis estático en YAML. 11 tipos de check incorporados:

| Check | Qué verifica |
|-------|-------------|
| `migration_has_unique` | Existe unique constraint en la migración |
| `migration_has_unique_or_code_guard` | Unique constraint O guard a nivel código (firstOrCreate, unique validation, etc.) |
| `migration_has_column` | Columnas requeridas existen en la tabla |
| `model_has_relation` | Relación Eloquent existe en el modelo |
| `route_has_middleware` | Rutas tienen el middleware requerido |
| `route_has_policy` | Existe clase Policy para el modelo |
| `route_has_test` | Existe clase Test para el controller |
| `class_max_methods` | Marca clases con demasiados métodos |
| `file_max_loc` | Marca archivos que superan el límite |
| `table_has_index_on_fk` | Foreign keys sin índice explícito |
| `no_bare_try_catch` | Marca bloques try/catch sin tipo |

```yaml
rules:
  - id: DB-001
    title: "Enrollment activo único por alumno y año académico"
    severity: high
    check: migration_has_unique_or_code_guard
    query:
      table: enrollments
      invariant: "max 1 active enrollment per user per academic year"
      expected_unique_on: ["user_id", "academic_year_id", "status"]
```

### Integración CI/CD
```bash
# Falla con exit code 1 si encuentra issues blocking
codecontext ci /ruta/al/proyecto --fail-on high
codecontext ci /ruta/al/proyecto --rules ./rules.yaml
```
Genera `issues.json` con todos los riesgos detectados para integración en pipelines.

### Cadenas de trazabilidad
```
GET /panel/asistencias → AttendanceManagement (Livewire)
  → AttendanceService → GeofenceService → Observer → AbsenceAlertService
  Middleware: auth, force_password_change
  Permission: attendances.register
```

### Mapa de roles y permisos
Extrae automáticamente los roles desde `middleware('role:Admin|Director')` y mapea qué rutas puede acceder cada rol.

### Servidor MCP para agentes de IA
Interfaz de consultas en vivo para agentes de IA vía Model Context Protocol (stdio):

```json
{
  "mcpServers": {
    "codecontext": {
      "command": "codecontext-mcp"
    }
  }
}
```

9 tools: `scan_project`, `get_summary`, `query_symbols`, `query_routes`, `query_data_model`, `query_schema`, `query_risks`, `query_trace`, `query_blade`

### Output en 5 capas

| Archivo | Propósito | Tamaño |
|---------|-----------|--------|
| `SUMMARY.md` | Inyectar en el prompt del agente de IA | **~1,000 tokens** |
| `context.json` | Datos estructurados para consultas | Completo |
| `CONTEXT.md` | Reporte legible para humanos | Completo |
| `deps.json` | Grafo de dependencias + deps circulares | Completo |
| `issues.json` | Issues de CI con severidad | Completo |

### Detección de arquitectura
Detecta automáticamente: **Laravel**, **Next.js**, **React**, **Django**, **FastAPI**, **Flask**, **Go standard layout**, **Rust**, **Avalonia UI + EF Core**

---

## Instalación

```bash
pip install git+https://github.com/hmvillalba/codecontext.git
```

Para desarrollo local:
```bash
git clone https://github.com/hmvillalba/codecontext.git
cd codecontext
pip install -e .
```

Requiere Python 3.10+.

---

## Uso

### Escanear un proyecto

```bash
# Escanear el directorio actual
codecontext scan .

# Escanear un proyecto específico
codecontext scan /ruta/al/proyecto

# Escanear e imprimir JSON compacto en consola
codecontext scan /ruta/al/proyecto --compact

# Directorio de salida personalizado
codecontext scan /ruta/al/proyecto --output ./mi-contexto

# Escanear con reglas custom
codecontext scan /ruta/al/proyecto --rules ./rules.yaml
```

### CI/CD

```bash
# Fallar el pipeline si hay issues high/critical
codecontext ci /ruta/al/proyecto --fail-on high

# Con reglas custom
codecontext ci /ruta/al/proyecto --rules ./rules.yaml
```

### Consultar el contexto

```bash
# Buscar un símbolo
codecontext query /ruta/al/proyecto --symbol User

# Filtrar por tipo
codecontext query /ruta/al/proyecto --type controller

# Mostrar archivo específico
codecontext query /ruta/al/proyecto --file "AuthController"
```

---

## Archivos de salida

### SUMMARY.md (~1,000 tokens)

```markdown
# school-attendance
laravel | php | 546 files | 78,707 LOC | 316 symbols

## Domain
Entities: Attendance, Enrollment, Course, Division, User, Shift...
Routes: 166 (GET 101, POST 52, DELETE 9)
DB tables: 45

## Key Flows
- GET /staff-dashboard → Livewire:Dashboard
- GET /escaner/preceptor → Livewire:PreceptorScanner (roles: Preceptor, Docente)

## Data Model
- Attendance: enrollment←Enrollment, justifications→*AttendanceJustification
- Enrollment: user←User, course←Course, attendances→*Attendance

## Views & Observers
- Blade: 124 views (58 livewire, 136 route refs)
- Observers: Attendance→AttendanceObserver, StaffAttendance→StaffAttendanceObserver

## Risks
- [!!] god-class: AttendanceManagement has 34 methods
- [!] missing-validation: AcademicStageController has no Request class
```

### context.json

Datos estructurados completos incluyendo:
- Árbol de archivos con tabla de símbolos
- Mapa de rutas con middleware
- Relaciones de modelos
- Schema de base de datos (columnas, FKs, índices)
- Vistas Blade con refs a componentes/livewire/rutas
- Mapeo de Observers y Events
- Grafo de dependencias
- Lista de riesgos con severidad y ubicación

### CONTEXT.md

Reporte completo legible con:
- Resumen general (lenguajes, tipos de símbolos)
- Capas de arquitectura
- Árbol de archivos con conteo LOC
- Rutas por método HTTP
- Diagrama de relaciones de modelos
- Tablas del schema de base de datos
- Vistas Blade por directorio
- Mapeo de Observers y Events
- Referencia de símbolos (clases, métodos, funciones con firmas)
- Mapa de dependencias

---

## Cómo funciona

```
Archivos fuente
    │
    ├── Python ──── módulo ast
    ├── PHP ─────── tree-sitter-php
    ├── TS/JS ───── tree-sitter-typescript
    ├── Go ──────── tree-sitter-go
    ├── Rust ────── tree-sitter-rust
    └── C# ──────── tree-sitter-c-sharp
          │
          ▼
    Nodos parseados (clases, métodos, funciones, imports)
          │
          ├── Resolver de dependencias → grafo de imports, deps circulares
          ├── Detector de arquitectura → detección de patrones
          ├── Extractor de rutas ──────→ mapa URL → controller
          ├── Extractor de modelos ────→ relaciones Eloquent
          ├── Extractor de schema ─────→ columnas de migraciones, FKs
          ├── Extractor de Blade ─────→ vistas, includes, componentes
          ├── Extractor de Observers ─→ mapeo Model → Observer
          ├── Detector de riesgos ────→ advertencias por reglas
          ├── Detector de gaps ───────→ policies/tests/validators faltantes
          ├── Motor de reglas YAML ──→ reglas custom de análisis
          └── Constructor de trazas ───→ ruta→controller→service→model
                  │
                  ▼
    SUMMARY.md (1K tokens) + context.json + CONTEXT.md + issues.json
```

---

## Benchmarks

| Proyecto | Lenguaje | Archivos | LOC | Símbolos | Tokens SUMMARY | Compresión |
|----------|----------|----------|-----|----------|----------------|------------|
| school-attendance | PHP/Laravel | 546 | 78,707 | 316 | 1,487 | 53:1 |
| gestionescolar | PHP/Laravel | 824 | 120,626 | 869 | 906 | 133:1 |
| facturador | C#/.NET | 262 | 44,423 | 314 | ~800 | 55:1 |
| fact-elec-service | Go | 88 | 11,158 | 477 | ~400 | 28:1 |

---

## Estructura del proyecto

```
codecontext/
├── cli.py                 # CLI (typer) — comandos scan, ci, query
├── models.py              # Modelos de datos (CodeNode, RouteEntry, Risk, BladeView, etc.)
├── scanner.py             # Motor de orquestación principal
├── mcp/
│   └── server.py          # Servidor MCP para consultas en vivo (9 tools)
├── parsers/
│   ├── python_parser.py   # Parser Python basado en AST
│   ├── php_parser.py      # tree-sitter PHP + detección Laravel
│   ├── ts_parser.py       # tree-sitter TypeScript/JavaScript
│   ├── go_parser.py       # tree-sitter Go
│   ├── rust_parser.py     # tree-sitter Rust
│   └── csharp_parser.py   # tree-sitter C# / .NET
├── analyzers/
│   ├── architecture.py    # Detección de patrones de framework
│   ├── dependency.py      # Grafo de imports + deps circulares
│   ├── routes.py          # Extracción de rutas Laravel
│   ├── model_relations.py # Extracción de relaciones Eloquent
│   ├── migrations.py      # Extracción de schema desde migraciones
│   ├── blade_views.py     # Extracción de vistas Blade (includes, livewire, rutas)
│   ├── observers.py       # Mapeo de Observers + Events/Listeners
│   ├── risks.py           # Detección estática de riesgos (reglas built-in)
│   ├── gaps.py            # Detección de gaps (policies/tests/validators faltantes)
│   └── traceability.py    # Cadenas Ruta→Controller→Service→Model
├── rules/
│   ├── engine.py          # Cargador + evaluador de reglas YAML (11 check types)
│   └── default.yaml       # Reglas default incluidas con CodeContext
└── generators/
    ├── __init__.py        # Generador de índice JSON
    ├── markdown.py        # Generador de CONTEXT.md completo
    ├── summary.py         # Generador de SUMMARY.md compacto
    └── issues.py          # Generador de issues.json para CI
```

---

## Roadmap

- [x] Extracción de vistas Blade (extends, includes, livewire, componentes, route refs)
- [x] Mapeo de Observers/Events/Listeners
- [x] Motor de reglas YAML (11 check types)
- [x] Integración CI/CD (exit codes, issues.json)
- [x] Servidor MCP para consultas en vivo (9 tools)
- [ ] Extractores multi-lenguaje (C#/.NET EF Core, Python Django/Flask, Go)
- [ ] Actualizaciones incrementales (`--update`, basado en hashes)
- [ ] Soporte para Spring Boot / Java
- [ ] Visualización HTML
- [ ] Export a Neo4j

---

## Licencia

MIT
