# Example: parallel research

## What it shows

Module 1 (`parallel_safe=True`) in action. Five arXiv lookups complete in
roughly the time of a single call, not five.

## Run

```bash
# Default: the executor batches parallel_safe calls
python -m examples.parallel_research.run
# -> Executor finished in ~0.33s

# Force sequential for comparison
python -m examples.parallel_research.run --sequential
# -> Executor finished in ~1.54s

# Against a real LLM (needs NEBIUS_KEY)
python -m examples.parallel_research.run --real
```

## The one line that matters

In `run.py`:

```python
_RegisteredTool(
    name="fetch_arxiv_paper",
    ...
    parallel_safe=True,   # <-- without this, sequential
)
```

Remove that flag and the default behaviour is sequential dispatch —
that's v0.1.0. With it, the executor groups contiguous parallel-safe
calls and `asyncio.gather`s them. Writes and handoffs are still
serialised automatically because they're marked `parallel_safe=False`
at registration.

## What the numbers mean

| Mode | Wall clock | Note |
|---|---|---|
| Parallel (default) | ~0.33s | Five 0.3s calls overlap |
| Sequential (`--sequential`) | ~1.54s | Five 0.3s calls one after another |

The overhead beyond 0.3s in parallel mode is executor bookkeeping and
trace writes. The gap closes if you cache the tool registry across
runs, but we keep it explicit here for teaching.
