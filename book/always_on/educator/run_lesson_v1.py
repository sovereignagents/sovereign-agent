"""Execute a shipped classroom notebook without installing a notebook server."""

import argparse
import contextlib
import io
import json
from pathlib import Path

EDUCATOR = Path(__file__).resolve().parent


def run_lesson(chapter, *, follow_on=False):
    if chapter == 1:
        name = (
            "ch01-prompts-and-harness-class-v1.ipynb"
            if follow_on
            else "ch01-first-model-call-class-v1.ipynb"
        )
    else:
        if follow_on:
            raise ValueError("the follow-on is a Chapter 1 lesson")
        rows = json.loads((EDUCATOR / "curriculum-v1.json").read_text())["chapters"]
        name = next(row["notebook"] for row in rows if row["number"] == chapter)
    notebook = json.loads((EDUCATOR / name).read_text())
    scope, outputs = {}, []
    for index, cell in enumerate(notebook["cells"], 1):
        if cell["cell_type"] != "code":
            continue
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            exec(compile("".join(cell["source"]), f"{name}:cell{index}", "exec"), scope)
        outputs.append({"cell": index, "stdout": captured.getvalue()})
    return {
        "notebook": name,
        "scope": "Executed supplied cells; no automatic learner mastery claim.",
        "student_submission": scope.get("submission_results", "teacher assessment required"),
        "student_transfer": scope.get("transfer_results", "teacher assessment required"),
        "outputs": outputs,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chapter", type=int, choices=range(1, 17), required=True)
    parser.add_argument("--follow-on", action="store_true")
    parser.add_argument(
        "--output", type=Path, help="new JSON evidence file; existing files refused"
    )
    args = parser.parse_args()
    if args.follow_on and args.chapter != 1:
        parser.error("--follow-on requires --chapter 1")
    # Refuse an existing evidence path before any notebook side effects.
    if args.output and args.output.exists():
        raise FileExistsError(args.output)
    report = run_lesson(args.chapter, follow_on=args.follow_on)
    encoded = json.dumps(report, indent=2) + "\n"
    if args.output:
        with args.output.open("x") as stream:
            stream.write(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
