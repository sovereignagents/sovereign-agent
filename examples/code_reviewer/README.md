# Code reviewer example

A sovereign-agent scenario that reads a Python file, lists the issues it finds, and writes a review to `workspace/review.md`. Entirely offline — the "reviewer" is a custom tool with scripted findings, and the LLM trajectory is scripted by `FakeLLMClient`.

## Why this example

It demonstrates a common agent pattern: **read inputs → analyze with a domain-specific tool → write a structured output**. The architectural bit worth noticing is that the review is *not* an LLM call. The LLM decides which file to look at and formats the final output, but the actual code review is a deterministic tool — because that's a thing you can unit-test.

## Run

```bash
python -m examples.code_reviewer.run
```

Drops a `review.md` into the session's workspace and prints it.

## Replacing the mock reviewer

The `check_python_file` tool in `run.py` is a stand-in that flags a few obvious smells (print statements, wildcard imports, overly long functions). Swap it for:

- `ruff check` subprocessed into the tool
- `mypy --strict` with parsed output
- A real linter/formatter of your choice

The agent architecture doesn't change. You're just making the tool smarter.
