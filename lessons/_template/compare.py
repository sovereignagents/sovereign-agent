"""Comparison script (template).

Run:

    python lessons/YYYY-MM-<slug>/compare.py

Runs the baseline and the variant across the standard scenarios and
writes metrics to results/.

The shape below is prescribed so lessons are comparable. Don't invent
your own runner unless you have a specific reason.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path


SCENARIOS: list[str] = [
    # Pick from: "research_assistant", "code_reviewer", "pub_booking"
    # or add new ones to examples/ and register here.
]


RUNS_PER_CONDITION = 3


async def run_baseline(scenario: str) -> dict:
    """Run the named scenario with the BASELINE extension. Return metrics."""
    raise NotImplementedError("fill in with the baseline trajectory")


async def run_variant(scenario: str) -> dict:
    """Run the named scenario with the NEW extension. Return metrics."""
    raise NotImplementedError("fill in with the variant trajectory")


def aggregate(runs: list[dict]) -> dict:
    """Mean + stddev across N runs of the same condition."""
    if not runs:
        return {}
    keys = set().union(*[set(r.keys()) for r in runs])
    out: dict[str, dict] = {}
    for k in keys:
        vals = [r[k] for r in runs if isinstance(r.get(k), (int, float))]
        if not vals:
            continue
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        out[k] = {"mean": mean, "stddev": var**0.5, "n": len(vals)}
    return out


async def main() -> None:
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)

    all_results: dict = {"baseline": {}, "variant": {}}
    for scenario in SCENARIOS:
        baseline_runs = [await run_baseline(scenario) for _ in range(RUNS_PER_CONDITION)]
        variant_runs = [await run_variant(scenario) for _ in range(RUNS_PER_CONDITION)]
        all_results["baseline"][scenario] = aggregate(baseline_runs)
        all_results["variant"][scenario] = aggregate(variant_runs)

    (results_dir / "metrics.json").write_text(json.dumps(all_results, indent=2))

    # Render a markdown summary.
    lines = ["# Comparison results", ""]
    for scenario in SCENARIOS:
        lines.append(f"## {scenario}")
        lines.append("")
        lines.append("| Metric | Baseline (mean ± sd) | Variant (mean ± sd) |")
        lines.append("|---|---|---|")
        b = all_results["baseline"][scenario]
        v = all_results["variant"][scenario]
        metrics = sorted(set(b.keys()) | set(v.keys()))
        for m in metrics:
            bm = b.get(m, {"mean": None, "stddev": None})
            vm = v.get(m, {"mean": None, "stddev": None})
            lines.append(
                f"| `{m}` | "
                f"{bm.get('mean', '-'):.3f} ± {bm.get('stddev', 0):.3f} | "
                f"{vm.get('mean', '-'):.3f} ± {vm.get('stddev', 0):.3f} |"
                if bm.get("mean") is not None and vm.get("mean") is not None
                else f"| `{m}` | n/a | n/a |"
            )
        lines.append("")
    (results_dir / "summary.md").write_text("\n".join(lines) + "\n")
    print(f"Wrote {results_dir / 'metrics.json'} and {results_dir / 'summary.md'}.")


if __name__ == "__main__":
    asyncio.run(main())
