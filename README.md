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
- **Livewire detection** — Automatic identification of Livewire components
- **Fillable/casts/traits** — Model properties extracted from code

### Risk detection (static rules, no AI)
- **God classes** — Classes with 15+ methods flagged
- **Missing validation** — Controllers with write methods but no FormRequest
- **Unprotected routes** — Routes without auth middleware
- **Missing indexes** — Foreign keys without explicit index
- **Duplicate methods** — Same method name across 3+ files
- **Large files** — Files over 500 LOC highlighted

### Traceability chains
```
GET /panel/asistencias → AttendanceManagement (Livewire)
  → AttendanceService → GeofenceService → Observer → AbsenceAlertService
  Middleware: auth, force_password_change
  Permission: attendances.register
```

### Role & permission map
Automatically extracts roles from `middleware('role:Admin|Director')` and maps which routes each role can access.

### 3-layer output

| File | Purpose | Size |
|------|---------|------|
| `SUMMARY.md` | Inject into AI agent prompt | **~1,000 tokens** |
| `context.json` | Structured data for querying | Full |
| `CONTEXT.md` | Human-readable report | Full |

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

## Roles & Permissions
- AdministradorGeneral: 432 routes
- Director: 378 routes
- Docente: 45 routes

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
          ├── Risk detector ────────→ rule-based warnings
          └── Trace builder ────────→ route→controller→service→model
                  │
                  ▼
    SUMMARY.md (1K tokens) + context.json + CONTEXT.md
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
├── cli.py                 # CLI (typer)
├── models.py              # Data models (CodeNode, RouteEntry, Risk, etc.)
├── scanner.py             # Core orchestration engine
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
│   ├── risks.py           # Static risk detection
│   └── traceability.py    # Route→Controller→Service→Model chains
└── generators/
    ├── __init__.py        # JSON index generator
    ├── markdown.py        # Full CONTEXT.md generator
    └── summary.py         # Compact SUMMARY.md generator
```

---

## Roadmap

- [ ] MCP server for live agent queries
- [ ] Incremental updates (`--update` flag, hash-based)
- [ ] Blade view extraction
- [ ] Observer/Event/Listener mapping
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
- **Detección de Livewire** — Identificación automática de componentes Livewire
- **Fillable/casts/traits** — Propiedades de modelos extraídas del código

### Detección de riesgos (reglas estáticas, sin IA)
- **God classes** — Clases con 15+ métodos marcadas
- **Validación faltante** — Controllers con métodos de escritura sin FormRequest
- **Rutas desprotegidas** — Rutas sin middleware de autenticación
- **Índices faltantes** — Foreign keys sin índice explícito
- **Métodos duplicados** — Mismo nombre de método en 3+ archivos
- **Archivos grandes** — Archivos de más de 500 LOC destacados

### Cadenas de trazabilidad
```
GET /panel/asistencias → AttendanceManagement (Livewire)
  → AttendanceService → GeofenceService → Observer → AbsenceAlertService
  Middleware: auth, force_password_change
  Permission: attendances.register
```

### Mapa de roles y permisos
Extrae automáticamente los roles desde `middleware('role:Admin|Director')` y mapea qué rutas puede acceder cada rol.

### Output en 3 capas

| Archivo | Propósito | Tamaño |
|---------|-----------|--------|
| `SUMMARY.md` | Inyectar en el prompt del agente de IA | **~1,000 tokens** |
| `context.json` | Datos estructurados para consultas | Completo |
| `CONTEXT.md` | Reporte legible para humanos | Completo |

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
          ├── Detector de riesgos ────→ advertencias por reglas
          └── Constructor de trazas ───→ ruta→controller→service→model
                  │
                  ▼
    SUMMARY.md (1K tokens) + context.json + CONTEXT.md
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
├── cli.py                 # CLI (typer)
├── models.py              # Modelos de datos (CodeNode, RouteEntry, Risk, etc.)
├── scanner.py             # Motor de orquestación principal
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
│   ├── risks.py           # Detección estática de riesgos
│   └── traceability.py    # Cadenas Ruta→Controller→Service→Model
└── generators/
    ├── __init__.py        # Generador de índice JSON
    ├── markdown.py        # Generador de CONTEXT.md completo
    └── summary.py         # Generador de SUMMARY.md compacto
```

---

## Roadmap

- [ ] Servidor MCP para consultas en vivo por agentes
- [ ] Actualizaciones incrementales (`--update`, basado en hashes)
- [ ] Extracción de vistas Blade
- [ ] Mapeo de Observers/Events/Listeners
- [ ] Soporte para Spring Boot / Java
- [ ] Visualización HTML
- [ ] Export a Neo4j

---

## Licencia

MIT
