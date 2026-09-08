"""Run current classroom cells and retain failed assessments without claiming mastery."""

import argparse
import contextlib
import io
import json
from pathlib import Path

EDUCATOR = Path(__file__).resolve().parent


def run_lesson(chapter, *, follow_on=False, notebook_path=None):
    if chapter == 1:
        name = (
            "ch01-prompts-and-harness-class-v2.ipynb"
            if follow_on
            else "ch01-first-model-call-class-v2.ipynb"
        )
    else:
        if follow_on:
            raise ValueError("the follow-on is a Chapter 1 lesson")
        rows = json.loads((EDUCATOR / "curriculum-v2.json").read_text())["chapters"]
        name = next(row["notebook"] for row in rows if row["number"] == chapter)
    path = notebook_path or EDUCATOR / name
    notebook = json.loads(Path(path).read_text())
    scope, outputs = {}, []
    execution = "COMPLETED"
    try:
        for index, cell in enumerate(notebook["cells"], 1):
            if cell["cell_type"] != "code":
                continue
            error_type = None
            with (
                contextlib.redirect_stdout(io.StringIO()) as stdout,
                contextlib.redirect_stderr(io.StringIO()) as stderr,
            ):
                try:
                    exec(compile("".join(cell["source"]), f"{name}:cell{index}", "exec"), scope)
                except Exception as error:
                    error_type = type(error).__name__
            outputs.append(
                {
                    "cell": index,
                    "stdout": stdout.getvalue(),
                    "stderr": stderr.getvalue(),
                    "error_type": error_type,
                }
            )
            if error_type:
                execution = "CELL_FAILED"
                break  # Retain evidence; do not execute dependent cells after an arbitrary failure.
    finally:
        if "lab" in scope:
            scope["lab"].close()
    return {
        "notebook": str(path),
        "execution": execution,
        "scope": "Supplied scaffold execution is not learner mastery.",
        "student_submission": scope.get("submission_results", "teacher assessment required"),
        "submission_summary": scope.get("submission_summary"),
        "student_transfer": scope.get("transfer_results", "teacher assessment required"),
        "transfer_summary": scope.get("transfer_summary"),
        "student_integration": scope.get("integration_results"),
        "runtime": scope.get("runtime_results"),
        "outputs": outputs,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chapter", type=int, choices=range(1, 17), required=True)
    parser.add_argument("--follow-on", action="store_true")
    parser.add_argument("--notebook", type=Path, help="Your trusted edited local notebook")
    parser.add_argument("--output", type=Path, help="New evidence path; existing files refused")
    args = parser.parse_args()
    if args.follow_on and args.chapter != 1:
        parser.error("--follow-on requires --chapter 1")
    if args.output and args.output.exists():
        raise FileExistsError(args.output)
    report = run_lesson(args.chapter, follow_on=args.follow_on, notebook_path=args.notebook)
    encoded = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.output:
        with args.output.open("x") as stream:
            stream.write(encoded)
    print(encoded, end="")
    return 0 if report["execution"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
