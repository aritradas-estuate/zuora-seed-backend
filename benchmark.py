"""
Performance benchmarking script for Zuora Seed Agent.
Tests cold vs warm cache performance and generates timing reports.
"""
import time
import sys
from agents.zuora_client import get_zuora_client
from agents.cache import get_cache
from rich.console import Console
from rich.table import Table
from rich import print as rprint

console = Console()


def benchmark_operation(name: str, operation_func, iterations: int = 3):
    """Run a benchmark for a given operation."""
    times = []

    console.print(f"\n[bold cyan]Benchmarking: {name}[/bold cyan]")

    for i in range(iterations):
        console.print(f"  Iteration {i + 1}/{iterations}...", end="")
        start = time.time()

        try:
            result = operation_func()
            duration_ms = (time.time() - start) * 1000
            times.append(duration_ms)

            # Check if result indicates success
            success = (
                result.get("success") if isinstance(result, dict) else
                result.get("connected") if isinstance(result, dict) else
                True
            )

            status = "[green]✓[/green]" if success else "[red]✗[/red]"
            console.print(f" {status} {duration_ms:.0f}ms")

        except Exception as e:
            console.print(f" [red]✗ Error: {str(e)}[/red]")
            times.append(None)

    # Calculate statistics
    valid_times = [t for t in times if t is not None]

    if valid_times:
        avg = sum(valid_times) / len(valid_times)
        min_time = min(valid_times)
        max_time = max(valid_times)

        console.print(f"  [yellow]Avg: {avg:.0f}ms, Min: {min_time:.0f}ms, Max: {max_time:.0f}ms[/yellow]")

        return {
            "name": name,
            "avg": avg,
            "min": min_time,
            "max": max_time,
            "iterations": len(valid_times),
            "times": valid_times
        }
    else:
        console.print(f"  [red]All iterations failed[/red]")
        return {
            "name": name,
            "avg": 0,
            "min": 0,
            "max": 0,
            "iterations": 0,
            "times": []
        }


def run_benchmarks():
    """Run comprehensive performance benchmarks."""
    console.print("\n[bold magenta]═══ Zuora Seed Agent Performance Benchmark ═══[/bold magenta]\n")

    client = get_zuora_client()
    cache = get_cache()

    # Test 1: Connection & OAuth (cold cache)
    console.print("[bold]Phase 1: Cold Cache Performance[/bold]")
    cache.clear()

    benchmark_1 = benchmark_operation(
        "OAuth Connection (Cold)",
        lambda: client.check_connection(),
        iterations=3
    )

    # Test 2: Connection & OAuth (warm cache)
    console.print("\n[bold]Phase 2: Warm Cache Performance[/bold]")

    benchmark_2 = benchmark_operation(
        "OAuth Connection (Warm)",
        lambda: client.check_connection(),
        iterations=3
    )

    # Test 3: List products (cold cache)
    cache.clear()
    client._access_token = None  # Force re-auth

    benchmark_3 = benchmark_operation(
        "List Products (Cold)",
        lambda: client.list_all_products(page_size=10),
        iterations=2
    )

    # Test 4: List products (warm cache)
    benchmark_4 = benchmark_operation(
        "List Products (Warm)",
        lambda: client.list_all_products(page_size=10),
        iterations=3
    )

    # Generate summary table
    console.print("\n[bold magenta]═══ Performance Summary ═══[/bold magenta]\n")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Operation", style="dim", width=30)
    table.add_column("Avg (ms)", justify="right")
    table.add_column("Min (ms)", justify="right")
    table.add_column("Max (ms)", justify="right")
    table.add_column("Iterations", justify="right")

    for benchmark in [benchmark_1, benchmark_2, benchmark_3, benchmark_4]:
        table.add_row(
            benchmark["name"],
            f"{benchmark['avg']:.0f}",
            f"{benchmark['min']:.0f}",
            f"{benchmark['max']:.0f}",
            str(benchmark["iterations"])
        )

    console.print(table)

    # Cache performance comparison
    if benchmark_1["avg"] > 0 and benchmark_2["avg"] > 0:
        oauth_improvement = ((benchmark_1["avg"] - benchmark_2["avg"]) / benchmark_1["avg"]) * 100
        console.print(f"\n[bold green]OAuth Cache Improvement: {oauth_improvement:.1f}%[/bold green]")

    if benchmark_3["avg"] > 0 and benchmark_4["avg"] > 0:
        api_improvement = ((benchmark_3["avg"] - benchmark_4["avg"]) / benchmark_3["avg"]) * 100
        console.print(f"[bold green]API Cache Improvement: {api_improvement:.1f}%[/bold green]")

    # Cache statistics
    cache_stats = cache.stats()

    console.print(f"\n[bold magenta]═══ Cache Statistics ═══[/bold magenta]\n")
    stats_table = Table(show_header=False)
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", style="yellow", justify="right")

    stats_table.add_row("Total Requests", str(cache_stats["total_requests"]))
    stats_table.add_row("Cache Hits", str(cache_stats["hits"]))
    stats_table.add_row("Cache Misses", str(cache_stats["misses"]))
    stats_table.add_row("Hit Rate", f"{cache_stats['hit_rate']:.1f}%")
    stats_table.add_row("Cache Size", str(cache_stats["size"]))
    stats_table.add_row("Expirations", str(cache_stats["expirations"]))

    console.print(stats_table)

    console.print(f"\n[bold green]✓ Benchmark complete![/bold green]\n")


if __name__ == "__main__":
    try:
        run_benchmarks()
    except KeyboardInterrupt:
        console.print("\n[yellow]Benchmark interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]Error running benchmark: {str(e)}[/red]")
        sys.exit(1)
