"""
Accuracy evaluation runner for the LLM classifier.

Usage:
    uv run python scripts/eval_classifier.py

Runs every utterance in tests/fixtures/utterances.json through the live
classifier and prints a per-intent accuracy report plus confidence distribution.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from classifier.llm_classifier import classify_intent  # noqa: E402
from classifier.providers.factory import get_provider  # noqa: E402
from models.intent import SessionState  # noqa: E402

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures" / "utterances.json"

console = Console()


def main() -> None:
    """Run accuracy evaluation over all utterance fixtures and print a results table."""
    provider = get_provider()
    utterances = json.loads(FIXTURES.read_text())

    per_intent: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "correct": 0, "conf_sum": 0.0,
        "latency_sum": 0.0, "latency_min": float("inf"), "latency_max": 0.0,
    })
    conf_buckets = {"high": 0, "medium": 0, "low": 0}
    total_latency_ms = 0.0

    console.print(f"\n[bold]Provider:[/bold] {provider.provider_name()} ({provider.model_name()})")
    console.print(f"[dim]Running {len(utterances)} utterances...[/dim]\n")

    for i, item in enumerate(utterances):
        session = SessionState(session_id=f"eval_{i}", user_id="eval_user", turn_count=1)

        t0 = perf_counter()
        result = classify_intent(item["text"], session, provider)
        latency_ms = (perf_counter() - t0) * 1000

        expected = item["intent"]
        correct = result.intent == expected
        mark = "[green]✓[/green]" if correct else "[red]✗[/red]"
        console.print(
            f"  {mark} [{i+1:02d}] {item['text']!r:55s} "
            f"→ {result.intent} (conf={result.confidence:.2f}, {latency_ms:.0f}ms)"
            + (f"  [red]expected={expected}[/red]" if not correct else "")
        )

        stats = per_intent[expected]
        stats["total"] += 1
        stats["correct"] += (1 if correct else 0)
        stats["conf_sum"] += result.confidence
        stats["latency_sum"] += latency_ms
        stats["latency_min"] = min(stats["latency_min"], latency_ms)
        stats["latency_max"] = max(stats["latency_max"], latency_ms)
        total_latency_ms += latency_ms

        if result.confidence >= 0.80:
            conf_buckets["high"] += 1
        elif result.confidence >= 0.40:
            conf_buckets["medium"] += 1
        else:
            conf_buckets["low"] += 1

    # Print results table
    console.print()
    table = Table(title="Intent Classification Accuracy", show_lines=True)
    table.add_column("Intent", style="cyan")
    table.add_column("Total", justify="right")
    table.add_column("Correct", justify="right")
    table.add_column("Accuracy", justify="right")
    table.add_column("Avg Conf", justify="right")
    table.add_column("Avg ms", justify="right")
    table.add_column("Max ms", justify="right")

    total_all = correct_all = 0
    for intent, stats in sorted(per_intent.items()):
        t = stats["total"]
        c = stats["correct"]
        acc = c / t if t else 0
        avg_conf = stats["conf_sum"] / t if t else 0
        avg_ms = stats["latency_sum"] / t if t else 0
        max_ms = stats["latency_max"]
        color = "green" if acc >= 0.85 else "yellow" if acc >= 0.60 else "red"
        table.add_row(
            intent, str(t), str(c),
            f"[{color}]{acc:.0%}[/{color}]",
            f"{avg_conf:.2f}",
            f"{avg_ms:.0f}",
            f"{max_ms:.0f}",
        )
        total_all += t
        correct_all += c

    overall_acc = correct_all / total_all if total_all else 0
    avg_total_ms = total_latency_ms / total_all if total_all else 0
    table.add_row(
        "[bold]Overall[/bold]", str(total_all), str(correct_all),
        f"[bold]{overall_acc:.0%}[/bold]", "",
        f"[bold]{avg_total_ms:.0f}[/bold]", "",
        style="bold",
    )
    console.print(table)

    # Latency summary
    console.print("\n[bold]Latency Summary[/bold]")
    console.print(f"  Total wall-clock:  {total_latency_ms:.0f}ms across {total_all} requests")
    console.print(f"  Average per call:  {avg_total_ms:.0f}ms")

    # Confidence distribution
    console.print("\n[bold]Confidence Distribution[/bold]")
    console.print(f"  >= 0.80 (proceed):    {conf_buckets['high']:3d} / {total_all}")
    console.print(f"  0.40-0.79 (clarify):  {conf_buckets['medium']:3d} / {total_all}")
    console.print(f"  < 0.40 (redirect):    {conf_buckets['low']:3d} / {total_all}")

    if overall_acc < 0.85:
        console.print("\n[red]Warning: Overall accuracy below 85% target.[/red]")
    else:
        console.print("\n[green]Accuracy target met (>= 85%).[/green]")


if __name__ == "__main__":
    main()
