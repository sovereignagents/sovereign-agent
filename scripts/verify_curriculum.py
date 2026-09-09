#!/usr/bin/env python3
"""Check that the book is a real, runnable learning path.

Catches the ways a curriculum rots:

- a chapter that lost a required section
- a `solution.py` that no longer imports
- a solution that copies implementation instead of importing the package
- a chapter promising behaviour the code does not have (e.g. Pulse before
  Chapter 7 genuinely produces it)
- a referenced script or chapter that does not exist
- a chapter missing its co-located INSTRUCTOR.md, or one missing a required
  section
- a chapter's forward/backward links not forming one coherent sequence
- injected site frontmatter in source Markdown, while allowing declared Jupytext exercise metadata

Exits 0 when the curriculum is sound, 1 otherwise.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BOOK = REPO_ROOT / "book"
sys.path.insert(0, str(REPO_ROOT / "src"))

REQUIRED_CHAPTERS = (
    "ch00_first_shift",
    "ch01_organization_remembers",
    "ch02_work_needs_governance",
    "ch03_actor_is_not_a_model",
    "ch04_work_stays_inside_its_boundary",
    "ch05_authority_needs_a_fence",
    "ch06_the_organization_recovers",
    "ch07_the_organization_wakes_itself",
    # Added Unit 11, following the exact pattern Unit 10 already established
    # growing this tuple from 4 to 8: nothing in this module's structure
    # assumed exactly 8 entries.
    "ch08_the_store_becomes_a_catalog",
    "ch09_each_product_has_its_own_threshold",
    "ch10_one_signal_wakes_one_need",
    "ch11_replenishment_scales_without_losing_governance",
    "ch12_the_pilot_begins_with_a_receipt",
)

# The last chapter number that may NOT claim Pulse fired. Chapter 7 (index 7)
# is the one chapter allowed to, and only when its own exercise produces the
# durable evidence -- see PULSE_EVIDENCE_CHAPTER and check_pulse_claims below.
LAST_UNCONDITIONALLY_PULSE_FREE_CHAPTER_INDEX = 6
PULSE_EVIDENCE_CHAPTER = "ch07_the_organization_wakes_itself"

# Chapter solutions that take a root path and run the exercise end to end.
# EVERY required chapter's exercise must EXECUTE, not merely import. ch03 was
# required but absent here, so the gate reported "3 exercises executed" across
# four required chapters -- a gate overstating its own coverage, which is the
# defect this project exists to remove. It runs offline on the scripted
# provider; no credential is needed, so nothing justified the exclusion.
RUNNABLE = {
    "ch00_first_shift": "run_simulated",
    "ch01_organization_remembers": "observe_memory",
    "ch02_work_needs_governance": "explore_governance",
    "ch03_actor_is_not_a_model": "run_exercise",
    "ch04_work_stays_inside_its_boundary": "explore_workspace_lifecycle",
    "ch05_authority_needs_a_fence": "explore_fencing",
    "ch06_the_organization_recovers": "recover_from_a_real_hard_kill",
    "ch07_the_organization_wakes_itself": "the_organization_wakes_itself",
    "ch08_the_store_becomes_a_catalog": "the_store_becomes_a_catalog",
    "ch09_each_product_has_its_own_threshold": "each_product_has_its_own_threshold",
    "ch10_one_signal_wakes_one_need": "one_signal_wakes_one_need",
    "ch11_replenishment_scales_without_losing_governance": (
        "replenishment_scales_without_losing_governance"
    ),
    "ch12_the_pilot_begins_with_a_receipt": "the_pilot_begins_with_a_receipt",
}

# Exercises whose entry point needs an argument beyond the root path.
RUNNABLE_ARGS: dict[str, tuple[object, ...]] = {
    # Offline by default: the chapter teaches provider REBINDING, and the
    # scripted provider proves identity survives it without any credential.
    "ch03_actor_is_not_a_model": ("scripted",),
}

REQUIRED_SECTIONS = (
    ("learning objective", ("## Learning objective",)),
    ("runnable exercise", ("## The exercise", "## Exercise 1", "## Exercise")),
    ("expected observations", ("Expected", "## Expected observations")),
    ("learner verification command", ("## Learner verification command",)),
    ("explain it back", ("## Explain it back",)),
)

# Every chapter's own co-located INSTRUCTOR.md must carry all seven of these,
# matching the contract in book/INSTRUCTOR.md and book/CONTENT-SOURCE.md. A
# structural check, the same shape as REQUIRED_SECTIONS above, applied to a
# different file.
REQUIRED_INSTRUCTOR_SECTIONS = (
    ("teaching intent", ("## Teaching intent",)),
    ("prerequisite knowledge", ("## Prerequisite knowledge",)),
    ("likely misconceptions", ("## Likely misconceptions",)),
    ("observation checkpoints", ("## Observation checkpoints",)),
    ("discussion prompts", ("## Discussion prompts",)),
    ("facilitation timing", ("## Facilitation timing",)),
    ("exercise debrief and assessment", ("## Exercise debrief and assessment",)),
)

# Pulse arrives in Unit 9 as production code, but a chapter must not claim
# the organization wakes itself unless it is Chapter 7 AND its own exercise
# genuinely produced the durable evidence for that claim (see
# check_pulse_claims). Unchanged from the pre-Unit-10 guard in shape; what
# changed is that the guard is no longer applied identically to every
# chapter regardless of number.
FORBIDDEN_CLAIMS = (
    re.compile(r"\bpulse\b\s+(?:event\s+)?(?:fires|fired|wakes|woke)", re.IGNORECASE),
    re.compile(r"organization wakes itself (?:up )?(?:now|today)", re.IGNORECASE),
)

# A leading YAML block can be either forbidden site collection metadata or the
# required Jupytext representation/kernel declaration for a canonical exercise.
FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)

# Added Unit 11: Chapter 12 exercises the pilot-start mechanism and MUST
# NEVER be able to reach the real named pilot organization, by construction,
# not merely by convention -- the governing SOW's own words. Every pilot_id
# this chapter's own exercise writes to `pilots` must carry this reserved
# prefix; nothing in this project's real-pilot tooling (there is none yet)
# ever uses it. This is checked mechanically below (see
# check_pilot_disposable_identity), the same "run it, then inspect the
# resulting database" discipline check_pulse_claims already established for
# Chapter 7's own Pulse-evidence guard.
PILOT_DISPOSABLE_ID_CHAPTER = "ch12_the_pilot_begins_with_a_receipt"
PILOT_DISPOSABLE_ID_PREFIX = "book-ch12-exercise-"


def check_chapter(name: str) -> list[str]:
    problems: list[str] = []
    directory = BOOK / name
    if not directory.is_dir():
        return [f"{name}: chapter directory is missing"]

    readme = directory / "README.md"
    if not readme.is_file():
        problems.append(f"{name}: README.md is missing")
        return problems
    text = readme.read_text(encoding="utf-8")

    for label, markers in REQUIRED_SECTIONS:
        if not any(marker in text for marker in markers):
            problems.append(f"{name}: no {label} section")

    solution = directory / "solution.py"
    if not solution.is_file():
        problems.append(f"{name}: solution.py is missing")
        return problems

    source = solution.read_text(encoding="utf-8")
    if not re.search(r"^from (sovereign_agent|reference_organizations)", source, re.MULTILINE):
        problems.append(f"{name}: solution.py does not import the production package")
    if "class Database" in source or "CREATE TABLE" in source:
        problems.append(f"{name}: solution.py appears to copy implementation code")

    spec = importlib.util.spec_from_file_location(f"book_{name}_solution", solution)
    if spec is None or spec.loader is None:
        problems.append(f"{name}: solution.py could not be loaded")
    else:
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as error:  # noqa: BLE001 - any import failure is a curriculum failure
            problems.append(
                f"{name}: solution.py failed to import: {type(error).__name__}: {error}"
            )
            return problems

        # Importing proves the file parses. RUNNING it proves the chapter still
        # works: an exercise rots when the API moves underneath it, and an
        # import-only check never notices. Each runs against a fresh root.
        entry_point = RUNNABLE.get(name)
        if entry_point is not None:
            function = getattr(module, entry_point, None)
            if function is None:
                problems.append(f"{name}: solution.py has no {entry_point}()")
            else:
                with tempfile.TemporaryDirectory() as scratch:
                    root = Path(scratch) / "root"
                    try:
                        function(root, *RUNNABLE_ARGS.get(name, ()))
                    except Exception as error:  # noqa: BLE001 - broken exercise, broken chapter
                        problems.append(
                            f"{name}: {entry_point}() failed to run: "
                            f"{type(error).__name__}: {error}"
                        )
                    else:
                        problems.extend(check_pulse_claims(name, text, root))
                        problems.extend(check_pilot_disposable_identity(name, root))

    # Every local link and referenced script must exist.
    for target in re.findall(r"\]\(([^)]+)\)", text):
        if target.startswith(("http://", "https://", "#")):
            continue
        if not (directory / target).resolve().exists():
            problems.append(f"{name}: broken link to {target}")
    for script in re.findall(r"(scripts/[\w_]+\.py)", text):
        if not (REPO_ROOT / script).is_file():
            problems.append(f"{name}: references missing script {script}")
    return problems


def check_pulse_claims(name: str, readme_text: str, exercise_root: Path) -> list[str]:
    """The chapter-scoped Pulse guard (Unit 10, SOW section 3).

    Chapters 0-6 keep the exact prior, unconditional prohibition: any
    Pulse-fired-shaped claim in their prose is a failure, regardless of
    whether the underlying code can now back it up elsewhere in the repo --
    a chapter's own claim must be backed by ITS OWN exercise, not by the
    existence of Pulse somewhere else in the codebase.

    Chapter 7 MAY make that claim, but only when its own already-executed
    exercise (this function runs strictly after `check_chapter` has already
    called the chapter's RUNNABLE entry point against `exercise_root`) left
    durable, structured evidence in that exact database: a real `pulse.*`
    event in the append-only `events` table, AND a `pulse_origins` row whose
    `wake_decision_id` resolves to a `pulse_wake_decisions` row -- the full
    signal -> decision -> event -> SOW -> assignment chain this project's own
    governing ruling requires to be a column read, never an inference. A
    chapter that claims Pulse but whose own exercise run left no such
    evidence fails here -- whether because the claim survived a since-removed
    call to `run_pulse_once`, or because nothing in the exercise ever called
    it, or because the "evidence" was fabricated by a direct `append_event`
    call standing in for the real mechanism (fabricated evidence has no
    traceable wake-decision chain behind it, so the join below returns no
    rows -- the same failure mode as never having called Pulse at all).
    """
    problems: list[str] = []
    makes_pulse_claim = any(pattern.search(readme_text) for pattern in FORBIDDEN_CLAIMS)

    if name != PULSE_EVIDENCE_CHAPTER:
        if makes_pulse_claim:
            problems.append(f"{name}: claims Pulse behaviour that does not exist until Chapter 7")
        return problems

    if not makes_pulse_claim:
        # Chapter 7 is not REQUIRED to phrase a claim in the forbidden shape
        # -- it is merely the one chapter permitted to. No claim, no check.
        return problems

    db_path = exercise_root / ".sovereign" / "organization.db"
    if not db_path.is_file():
        problems.append(
            f"{name}: claims Pulse behaviour, but its own exercise left no organization "
            "database to check evidence against"
        )
        return problems

    import sqlite3

    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        pulse_events = connection.execute(
            "SELECT COUNT(*) AS c FROM events WHERE kind LIKE 'pulse.%'"
        ).fetchone()["c"]
        if pulse_events == 0:
            problems.append(
                f"{name}: claims Pulse behaviour, but its own exercise's database has no "
                "durable pulse.* event -- the claim is not backed by the real mechanism"
            )
            return problems

        # The full chain, required to be traceable end to end: a
        # pulse_origins row whose wake_decision_id resolves to a REAL
        # pulse_wake_decisions row naming a real source_signal_id. A
        # fabricated event inserted directly (bypassing run_pulse_once, and
        # therefore never inserting the matching pulse_wake_decisions /
        # pulse_origins rows create_pulse_work's own single transaction
        # always writes together) produces pulse.* events with no such
        # chain -- this join returns zero rows for that case, which is
        # exactly the failure this check exists to catch.
        traceable = connection.execute(
            "SELECT COUNT(*) AS c FROM pulse_origins po "
            "JOIN pulse_wake_decisions wd ON wd.id = po.wake_decision_id "
            "WHERE po.origin_kind = 'pulse' AND wd.source_signal_id IS NOT NULL"
        ).fetchone()["c"]
        if traceable == 0:
            problems.append(
                f"{name}: claims Pulse behaviour, and a pulse.* event exists, but no "
                "traceable pulse_origins -> pulse_wake_decisions chain backs it -- this is "
                "the exact shape a fabricated event (inserted directly rather than produced "
                "by run_pulse_once) would leave behind"
            )
    finally:
        connection.close()
    return problems


def check_pilot_disposable_identity(name: str, exercise_root: Path) -> list[str]:
    """Chapter 12's own pilot-start exercise must be mechanically incapable
    of reaching a real pilot identity (Unit 11, governing SOW section 3):
    "never the same database, never the same pilot identity value, never
    reachable by accident through a shared default."

    Runs strictly after `check_chapter` has already executed this chapter's
    own RUNNABLE entry point against `exercise_root` -- the same "run it,
    then inspect the resulting database" shape `check_pulse_claims` already
    established for Chapter 7. Every row this chapter's own exercise wrote
    to `pilots` must carry the reserved `PILOT_DISPOSABLE_ID_PREFIX`. A
    chapter that accidentally used a bare, unprefixed, or otherwise
    non-reserved pilot_id -- the exact mistake a shared default value could
    silently cause -- fails here even though nothing else in this module
    would notice.
    """
    if name != PILOT_DISPOSABLE_ID_CHAPTER:
        return []
    db_path = exercise_root / ".sovereign" / "organization.db"
    if not db_path.is_file():
        return [
            f"{name}: exercise left no organization database to check the pilot identity against"
        ]

    import sqlite3

    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'pilots'"
            ).fetchall()
        }
        if "pilots" not in tables:
            return [f"{name}: exercise ran but wrote no `pilots` table row at all"]
        pilot_ids = [
            str(row["pilot_id"]) for row in connection.execute("SELECT pilot_id FROM pilots")
        ]
        if not pilot_ids:
            return [f"{name}: the pilot-start mechanism ran but created no pilot row"]
        non_disposable = [
            pilot_id
            for pilot_id in pilot_ids
            if not pilot_id.startswith(PILOT_DISPOSABLE_ID_PREFIX)
        ]
        if non_disposable:
            return [
                f"{name}: exercise created a pilot row whose identity "
                f"{non_disposable!r} does not carry the reserved disposable prefix "
                f"{PILOT_DISPOSABLE_ID_PREFIX!r} -- this chapter must never be able to "
                "reach a real pilot identity"
            ]
    finally:
        connection.close()
    return []


def check_instructor_notes() -> list[str]:
    """Every chapter's own INSTRUCTOR.md exists and carries all seven
    required sections -- structural, matching REQUIRED_SECTIONS' own shape,
    applied to a different file. Content quality (is the misconception list
    actually correct, is the timing realistic) is explicitly NOT something
    this check can grade -- see book/INSTRUCTOR.md's own closing paragraph.
    """
    problems: list[str] = []
    book_index = BOOK / "INSTRUCTOR.md"
    if not book_index.is_file():
        problems.append("book/INSTRUCTOR.md is missing")

    for name in REQUIRED_CHAPTERS:
        note = BOOK / name / "INSTRUCTOR.md"
        if not note.is_file():
            problems.append(f"{name}: INSTRUCTOR.md is missing")
            continue
        text = note.read_text(encoding="utf-8")
        for label, markers in REQUIRED_INSTRUCTOR_SECTIONS:
            if not any(marker in text for marker in markers):
                problems.append(f"{name}: INSTRUCTOR.md has no {label} section")
    return problems


def check_chapter_sequence() -> list[str]:
    """Previous/next chapter links and the book index form ONE coherent
    sequence -- not merely that each individual link resolves (check_chapter
    already verifies that), but that chapter N's forward link points at
    chapter N+1, every chapter but the last carries one, the last carries
    none, and book/README.md's own index lists every required chapter in
    order.
    """
    problems: list[str] = []
    index_text = (BOOK / "README.md").read_text(encoding="utf-8")
    index_positions = [index_text.find(name) for name in REQUIRED_CHAPTERS]
    for name, position in zip(REQUIRED_CHAPTERS, index_positions, strict=True):
        if position == -1:
            problems.append(f"book/README.md does not link {name}")
    present_positions = [p for p in index_positions if p != -1]
    if present_positions != sorted(present_positions):
        problems.append("book/README.md does not list the required chapters in order")

    for i, name in enumerate(REQUIRED_CHAPTERS):
        readme = BOOK / name / "README.md"
        if not readme.is_file():
            continue
        text = readme.read_text(encoding="utf-8")
        forward_links = re.findall(r"Next:\s*\[[^\]]*\]\(([^)]+)\)", text)
        is_last = i == len(REQUIRED_CHAPTERS) - 1
        if is_last:
            if forward_links:
                problems.append(
                    f"{name}: is the last chapter but still carries a 'Next:' forward link"
                )
            continue
        if not forward_links:
            problems.append(f"{name}: has no 'Next:' forward link to the following chapter")
            continue
        expected_next = REQUIRED_CHAPTERS[i + 1]
        if not any(expected_next in link for link in forward_links):
            problems.append(
                f"{name}: forward link does not point at the next chapter "
                f"({expected_next}); found {forward_links}"
            )
    return problems


def check_no_frontmatter() -> list[str]:
    """No source Markdown under book/ begins with site collection metadata.

    Canonical exercise Markdown is also a Jupytext source file, so its leading
    block declares Jupytext and kernelspec metadata. That narrow block is not a
    site's collection schema and is allowed only under always_on/exercises.
    """
    problems: list[str] = []
    for markdown_file in sorted(BOOK.rglob("*.md")):
        text = markdown_file.read_text(encoding="utf-8")
        frontmatter = FRONTMATTER_PATTERN.match(text)
        relative = markdown_file.relative_to(BOOK)
        is_exercise = relative.parts[:2] == ("always_on", "exercises")
        is_jupytext = bool(
            frontmatter
            and frontmatter.group().startswith("---\njupyter:\n")
            and "\n  jupytext:\n" in frontmatter.group()
            and "\n  kernelspec:\n" in frontmatter.group()
        )
        if frontmatter and not (is_exercise and is_jupytext):
            problems.append(
                f"{markdown_file.relative_to(REPO_ROOT)}: begins with a site frontmatter "
                "block, which book/ source files must never carry"
            )
    return problems


def check_rulings_index() -> list[str]:
    """The rulings index and the rulings directory must agree, both ways.

    The index was written for a site navigation that no longer exists, was
    referenced by nothing, and was already stale at 9 of 10 the moment a new
    ruling landed. An unreferenced listing that drifts is the ghost citation
    this project keeps deleting -- so it is either checked or removed. It is
    checked.

    The first version compared raw text with `in`, which can only ever detect
    an OMISSION. A ghost row pointing at a ruling that does not exist passed
    silently, and this seat reported the check as proven after testing one
    direction. Comparing two SETS makes both failures the same failure.
    """
    directory = REPO_ROOT / "docs" / "rulings"
    index = directory / "index.md"
    if not index.is_file():
        return ["docs/rulings/index.md is missing"]

    on_disk = {r.name for r in directory.glob("*.md") if r.name != "index.md"}
    linked = set(re.findall(r"\]\(([^)#]+\.md)\)", index.read_text(encoding="utf-8")))

    problems = [f"docs/rulings/index.md does not list {n}" for n in sorted(on_disk - linked)]
    problems += [
        f"docs/rulings/index.md links {n}, which does not exist" for n in sorted(linked - on_disk)
    ]
    return problems


def main() -> int:
    problems: list[str] = []
    problems.extend(check_rulings_index())
    problems.extend(check_instructor_notes())
    problems.extend(check_chapter_sequence())
    problems.extend(check_no_frontmatter())

    index = BOOK / "README.md"
    if not index.is_file():
        problems.append("book/README.md is missing")
    else:
        index_text = index.read_text(encoding="utf-8")
        for name in REQUIRED_CHAPTERS:
            if name not in index_text:
                problems.append(f"book/README.md does not link {name}")

    for name in REQUIRED_CHAPTERS:
        problems.extend(check_chapter(name))

    for problem in problems:
        print(f"CURRICULUM: {problem}")
    if problems:
        print(f"\n{len(problems)} curriculum problem(s).")
        return 1
    print(
        f"curriculum sound: {len(REQUIRED_CHAPTERS)} chapters, "
        f"{len(RUNNABLE)} exercises executed, all links resolve"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
