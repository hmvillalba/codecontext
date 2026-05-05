"""CLI interface for CodeContext."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from codecontext.scanner import scan_project, write_outputs

app = typer.Typer(
    name="codecontext",
    help="Generate compact code context for AI agents from any codebase.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def scan(
    path: str = typer.Argument(".", help="Root path of the project to scan"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output directory (default: <project>/.codecontext)"),
    workers: int = typer.Option(4, "--workers", "-w", help="Number of parallel workers"),
    compact: bool = typer.Option(False, "--compact", "-c", help="Print compact JSON to stdout for agent consumption"),
    rules: Optional[str] = typer.Option(None, "--rules", "-r", help="Path to custom rules YAML file"),
):
    """Scan a project and generate context files."""
    root = Path(path).resolve()

    if not root.exists():
        console.print(f"[red]Error:[/red] Path does not exist: {root}")
        raise typer.Exit(1)

    console.print(Panel(f"Scanning [bold]{root}[/bold]", title="CodeContext"))

    with console.status("[bold green]Parsing files..."):
        index = scan_project(root, max_workers=workers, rules_path=rules)

    if not index.files:
        console.print("[yellow]No supported files found.[/yellow]")
        raise typer.Exit(0)

    output_dir = Path(output) if output else root / ".codecontext"

    with console.status("[bold green]Generating outputs..."):
        results = write_outputs(index, output_dir)

    _print_results(index, results)

    if compact:
        from codecontext.generators import generate_compact_json_string
        console.print("\n--- COMPACT JSON (for agents) ---")
        console.print(generate_compact_json_string(index))


@app.command()
def ci(
    path: str = typer.Argument(".", help="Root path of the project"),
    rules: Optional[str] = typer.Option(None, "--rules", "-r", help="Path to custom rules YAML file"),
    fail_on: str = typer.Option("high", "--fail-on", help="Fail CI on this severity or higher (critical, high, warning, info)"),
):
    """Run analysis for CI/CD. Fails if blocking issues found."""
    root = Path(path).resolve()

    if not root.exists():
        console.print(f"[red]Error:[/red] Path does not exist: {root}")
        raise typer.Exit(1)

    with console.status("[bold green]Scanning for CI..."):
        index = scan_project(root, rules_path=rules)

    output_dir = root / ".codecontext"
    results = write_outputs(index, output_dir, fail_on=fail_on)

    table = Table(title="CI Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Total issues", str(results["total_risks"]))
    table.add_row("Blocking issues", str(results["ci_blocking"]))
    table.add_row("Fail threshold", fail_on)
    table.add_row("Issues file", results["issues"])
    console.print(table)

    if results["ci_should_fail"]:
        console.print(f"\n[red bold]FAIL:[/red bold] {results['ci_blocking']} blocking issue(s) found.")
        raise typer.Exit(1)
    else:
        console.print(f"\n[green bold]PASS:[/green bold] No blocking issues.")


@app.command()
def query(
    path: str = typer.Argument(".", help="Project root path"),
    symbol: Optional[str] = typer.Option(None, "--symbol", "-s", help="Search for a specific symbol"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Show context for a specific file"),
    type_filter: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by node type (class, function, method, controller, model, etc.)"),
):
    """Query the generated context."""
    root = Path(path).resolve()
    ctx_file = root / ".codecontext" / "context.json"

    if not ctx_file.exists():
        console.print("[yellow]No context found. Run [bold]codecontext scan[/bold] first.[/yellow]")
        raise typer.Exit(1)

    import json
    data = json.loads(ctx_file.read_text(encoding="utf-8"))

    if symbol:
        _query_symbol(data, symbol)
    elif file:
        _query_file(data, file)
    elif type_filter:
        _query_type(data, type_filter)
    else:
        _show_overview(data)


def _print_results(index, results: dict):
    table = Table(title="Scan Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Files scanned", str(results["total_files"]))
    table.add_row("Lines of code", f"{results['total_loc']:,}")
    table.add_row("Symbols extracted", str(results["total_symbols"]))
    table.add_row("Routes", str(results.get("total_routes", 0)))
    table.add_row("Model relations", str(results.get("total_relations", 0)))
    table.add_row("DB tables", str(results.get("total_tables", 0)))
    table.add_row("Risks found", str(results.get("total_risks", 0)))
    table.add_row("CI blocking", str(results.get("ci_blocking", 0)))
    table.add_row("Trace chains", str(results.get("total_traces", 0)))
    table.add_row("Blade views", str(results.get("total_blade_views", 0)))
    table.add_row("Observers", str(results.get("total_observers", 0)))
    table.add_row("Circular deps", str(results["circular_deps"]))
    table.add_row("SUMMARY tokens", f"~{results.get('summary_tokens', 0):,}")

    arch = index.architecture.get("pattern", "unknown")
    table.add_row("Architecture", arch)

    console.print(table)

    console.print(f"\n[bold green]SUMMARY:[/bold green] {results.get('summary', '')}")
    console.print(f"[green]JSON:[/green]     {results['json']}")
    console.print(f"[green]Report:[/green]   {results['markdown']}")
    console.print(f"[green]Deps:[/green]      {results['deps']}")
    console.print(f"[green]Issues:[/green]    {results.get('issues', '')}")


def _query_symbol(data: dict, symbol: str):
    structure = data.get("structure", {})
    results = []

    def search(node, path=""):
        if isinstance(node, dict):
            files = node.get("_files", [])
            for f in files:
                if isinstance(f, dict):
                    for fname, info in f.items():
                        for n in info.get("nodes", []):
                            if symbol.lower() in n.get("name", "").lower():
                                results.append({"file": f"{path}/{fname}" if path else fname, **n})
            for key, val in node.items():
                if key != "_files":
                    search(val, f"{path}/{key}" if path else key)

    search(structure)

    if results:
        table = Table(title=f"Symbols matching '{symbol}'")
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("File", style="yellow")
        table.add_column("Line", style="magenta")

        for r in results[:20]:
            table.add_row(r.get("name", ""), r.get("type", ""), r.get("file", ""), str(r.get("line", "")))

        console.print(table)
    else:
        console.print(f"[yellow]No symbols found matching '{symbol}'[/yellow]")


def _query_file(data: dict, file_pattern: str):
    structure = data.get("structure", {})
    results = []

    def search(node, path=""):
        if isinstance(node, dict):
            files = node.get("_files", [])
            for f in files:
                if isinstance(f, dict):
                    for fname, info in f.items():
                        full = f"{path}/{fname}" if path else fname
                        if file_pattern.lower() in full.lower():
                            results.append({"file": full, **info})
            for key, val in node.items():
                if key != "_files":
                    search(val, f"{path}/{key}" if path else key)

    search(structure)

    if results:
        for r in results[:10]:
            console.print(Panel(str(r), title=r.get("file", "File")))
    else:
        console.print(f"[yellow]No files matching '{file_pattern}'[/yellow]")


def _query_type(data: dict, type_filter: str):
    structure = data.get("structure", {})
    results = []

    def search(node, path=""):
        if isinstance(node, dict):
            files = node.get("_files", [])
            for f in files:
                if isinstance(f, dict):
                    for fname, info in f.items():
                        for n in info.get("nodes", []):
                            if n.get("type", "").lower() == type_filter.lower():
                                results.append({"file": f"{path}/{fname}" if path else fname, **n})
            for key, val in node.items():
                if key != "_files":
                    search(val, f"{path}/{key}" if path else key)

    search(structure)

    if results:
        table = Table(title=f"All {type_filter} symbols")
        table.add_column("Name", style="cyan")
        table.add_column("File", style="yellow")

        for r in results[:30]:
            table.add_row(r.get("name", ""), r.get("file", ""))

        console.print(table)
        if len(results) > 30:
            console.print(f"[dim]... and {len(results) - 30} more[/dim]")
    else:
        console.print(f"[yellow]No symbols of type '{type_filter}'[/yellow]")


def _show_overview(data: dict):
    meta = data.get("meta", {})
    console.print(Panel(
        f"Architecture: {meta.get('architecture', '?')}\n"
        f"Files: {meta.get('total_files', 0)}\n"
        f"LOC: {meta.get('total_loc', 0):,}\n"
        f"Symbols: {meta.get('total_nodes', 0):,}",
        title="Project Overview",
    ))

    layers = data.get("layers", {})
    if layers:
        console.print("\n[bold]Layers:[/bold]")
        for name, info in layers.items():
            if isinstance(info, dict) and "count" in info:
                console.print(f"  {name}: {info['count']}")


if __name__ == "__main__":
    app()
